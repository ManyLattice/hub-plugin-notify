"""Процесс плагина «Уведомления»: читает журнал хаба, решает, что достойно уведомления (alerts.py), и пишет это в
канал плагина — страница показывает уведомлением браузера; когда ни одной страницы с ними нет — уведомление macOS
(mac.py). Ядро не правит: читает журнал, пишет только фактами в ящик (EXTENDING.md).

Страница и процесс говорят по 127.0.0.1:<порт страницы + 8>: отметка «я открыта и показываю уведомления» и
настройка уведомлений macOS. Принимаются только запросы со страницы хаба (Origin)."""
import http.server
import json
import os
import threading
import time

from core import journal, spool

from alerts import Alerts
from mac import Mac

STATE = os.environ.get("HUB_STATE_DIR", "")
NAME = os.environ.get("HUB_EXTENSION", "notify")
CHANNEL = NAME.split(":")[-1]   # канал плагина — имя без автора
WEB_PORT = int(os.environ.get("HUB_WEB_PORT", "8787"))
PORT = WEB_PORT + 8
PAGE_ALIVE = 25   # с: страница отмечается раз в 10 с; молчит дольше — закрыта


class Follower:
    """Новые события журнала по одному, с текущего места; после ротации — новый журнал с его состояния."""

    def __init__(self, state_dir):
        self.dir, self.path = state_dir, os.path.join(state_dir, "journal.jsonl")
        self.start()

    def start(self):
        self.ino = journal.identity(self.path)
        try:
            self.offset = os.path.getsize(self.path)
        except OSError:
            self.offset = 0
        self.state = journal.load_state(self.dir)
        self.seq = self.state.get("seq", 0)

    def events(self):
        """(новые события, начат ли журнал заново: тогда состояние — self.state)."""
        if journal.identity(self.path) != self.ino:
            self.start()
            return [], True
        try:
            with open(self.path, "rb") as f:
                f.seek(self.offset)
                chunk = f.read()
        except OSError:
            return [], False
        end = chunk.rfind(b"\n")
        if end < 0:
            return [], False
        self.offset += end + 1
        out = []
        for line in chunk[:end].split(b"\n"):
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if ev.get("seq", 0) > self.seq:
                self.seq = ev["seq"]
                out.append(ev)
        return out, False


class Settings:
    def __init__(self, path):
        self.path = path

    def mac(self):
        try:
            with open(self.path) as f:
                return bool(json.load(f).get("mac"))
        except (OSError, ValueError):
            return False

    def set_mac(self, on):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"mac": bool(on)}, f)
        os.replace(tmp, self.path)


class Plugin:
    def __init__(self, state_dir, mac=None, put=None, clock=time.time):
        self.dir = os.path.join(state_dir, "notify")
        self.settings = Settings(os.path.join(self.dir, "settings.json"))
        repo = os.environ.get("HUB_REPO") or ""
        self.mac = mac or Mac(self.dir, f"http://127.0.0.1:{WEB_PORT}/",
                              logo=os.path.join(repo, "deploy", "mac", "Agents Hub.app", "Contents", "Resources", "logo.icns"))
        self.put = put or (lambda data: spool.put(os.path.join(state_dir, "spool"), "ext.post", None, data,
                                                   src=f"ext:{NAME}"))
        self.clock, self.seen = clock, 0.0

    def page_open(self):
        return self.clock() - self.seen < PAGE_ALIVE

    def emit(self, alerts):
        on, page = self.settings.mac(), self.page_open()
        for a in alerts:
            self.put({"plugin": CHANNEL, "text": json.dumps(a, ensure_ascii=False), "channel": "plugin",
                      "owner": False, "sender": NAME})
            self.mac.handle(a, on, page)

    def act(self, path, origin):
        """Запрос страницы -> (код, ответ). Только со страницы хаба этой машины."""
        if origin not in (f"http://127.0.0.1:{WEB_PORT}", f"http://localhost:{WEB_PORT}"):
            return 403, {"error": "только со страницы хаба"}
        if path == "/here":
            self.seen = self.clock()
            return 200, {"ok": True}
        if path == "/status":
            return 200, self.mac.status(self.settings.mac())
        if path in ("/mac/on", "/mac/off"):
            self.settings.set_mac(path.endswith("/on"))
            if path.endswith("/on"):   # сборка помощника — до минуты; первое уведомление — и вопрос macOS о разрешении
                self.test()
                return 200, {"text": "Уведомления macOS включены. Первое придёт через несколько секунд"}
            return 200, {"text": "Уведомления macOS выключены"}
        if path == "/mac/test":
            self.test()
            return 200, {"text": "Пробное уведомление macOS придёт через несколько секунд"}
        return 404, {"error": "нет такого"}

    def test(self):
        threading.Thread(target=self.mac.post, daemon=True, args=({
            "id": "hub-test", "title": "Agents Hub", "text": "Так выглядят уведомления хаба. Клик открывает страницу.",
            "href": "#/settings"},)).start()


def serve(plugin):
    class Handler(http.server.BaseHTTPRequestHandler):
        def answer(self):
            origin = self.headers.get("Origin") or ""
            code, body = plugin.act(self.path.split("?")[0], origin)
            data = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            if code != 403:
                self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        do_GET = do_POST = answer

        def log_message(self, *a):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def main():
    plugin = Plugin(STATE)
    serve(plugin)
    follow = Follower(STATE)
    alerts = Alerts(follow.state)
    print(f"уведомления: канал {CHANNEL}, страница — 127.0.0.1:{PORT}", flush=True)
    while True:
        evs, restarted = follow.events()
        if restarted:
            alerts = Alerts(follow.state)
        for ev in evs:
            plugin.emit(alerts.step(ev))
        time.sleep(0.5)


if __name__ == "__main__":
    main()
