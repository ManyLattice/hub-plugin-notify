"""The "Notifications" plugin process: reads the hub journal, decides what deserves a notification (alerts.py) and
writes it to the plugin channel — the page shows it as a browser notification; when no page with them is open, a macOS
notification (mac.py). It does not change the core: it reads the journal and writes only facts to the spool
(EXTENDING.md).

The page and the process talk over 127.0.0.1:<page port + 8>: the check-in "I am open and show notifications" and the
macOS notification setting. Only requests from the hub page are accepted (Origin)."""
import http.server
import json
import os
import threading
import time

from core import journal, spool

from alerts import Alerts, lang
from mac import Mac

STATE = os.environ.get("HUB_STATE_DIR", "")
NAME = os.environ.get("HUB_EXTENSION", "notify")
CHANNEL = NAME.split(":")[-1]   # the plugin channel — the name without the author
WEB_PORT = int(os.environ.get("HUB_WEB_PORT", "8787"))
PORT = WEB_PORT + 8
PAGE_ALIVE = 25   # s: the page checks in every 10 s; silent longer — closed
TEXTS = {
    "en": {"on": "macOS notifications are on. The first one will arrive in a few seconds",
           "off": "macOS notifications are off",
           "test": "A test macOS notification will arrive in a few seconds",
           "sample": "This is how hub notifications look. A click opens the page."},
    "ru": {"on": "Уведомления macOS включены. Первое придёт через несколько секунд",
           "off": "Уведомления macOS выключены",
           "test": "Пробное уведомление macOS придёт через несколько секунд",
           "sample": "Так выглядят уведомления хаба. Клик открывает страницу."},
}


class Follower:
    """New journal events one by one, from the current place; after a rotation — the new journal from its state."""

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
        """(new events, whether the journal started anew: then the state is self.state)."""
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
    def __init__(self, state_dir, mac=None, put=None, clock=time.time, lang=lambda: "en"):
        self.dir = os.path.join(state_dir, "notify")
        self.settings = Settings(os.path.join(self.dir, "settings.json"))
        self.lang = lang   # () -> "en" | "ru": the language of the texts the page shows
        repo = os.environ.get("HUB_REPO") or ""
        self.mac = mac or Mac(self.dir, f"http://127.0.0.1:{WEB_PORT}/",
                              logo=os.path.join(repo, "deploy", "mac", "Agents Hub.app", "Contents", "Resources", "logo.icns"),
                              lang=lambda: self.lang())
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
        """A page request -> (code, answer). Only from the hub page of this machine."""
        if origin not in (f"http://127.0.0.1:{WEB_PORT}", f"http://localhost:{WEB_PORT}"):
            return 403, {"error": "only from the hub page"}
        say = TEXTS.get(self.lang(), TEXTS["en"])
        if path == "/here":
            self.seen = self.clock()
            return 200, {"ok": True}
        if path == "/status":
            return 200, self.mac.status(self.settings.mac())
        if path in ("/mac/on", "/mac/off"):
            self.settings.set_mac(path.endswith("/on"))
            if path.endswith("/on"):   # the helper builds in up to a minute; the first one also asks macOS for permission
                self.test()
                return 200, {"text": say["on"]}
            return 200, {"text": say["off"]}
        if path == "/mac/test":
            self.test()
            return 200, {"text": say["test"]}
        return 404, {"error": "no such path"}

    def test(self):
        threading.Thread(target=self.mac.post, daemon=True, args=({
            "id": "hub-test", "title": "Agents Hub", "text": TEXTS.get(self.lang(), TEXTS["en"])["sample"],
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
    follow = Follower(STATE)
    alerts = Alerts(follow.state)
    plugin = Plugin(STATE, lang=lambda: lang(alerts.st))
    serve(plugin)
    print(f"notify: channel {CHANNEL}, page — 127.0.0.1:{PORT}", flush=True)
    while True:
        evs, restarted = follow.events()
        if restarted:
            alerts = Alerts(follow.state)
        for ev in evs:
            plugin.emit(alerts.step(ev))
        time.sleep(0.5)


if __name__ == "__main__":
    main()
