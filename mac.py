"""Уведомления macOS, когда ни одна страница хаба с уведомлениями браузера не открыта (иначе — два об одном).

Показывает маленький помощник (mac_notify.swift): плагин собирает его сам в папке состояния хаба (нужны Command
Line Tools: swiftc), подпись своя, без сертификата. osascript не годится: клик по его уведомлению открывает
«Редактор скриптов», а не хаб."""
import hashlib
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
import threading

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mac_notify.swift")
BUNDLE_ID = "com.hub-core.notify"
EXE = "hub-notify"
DENIED = 3   # код выхода помощника: macOS не разрешает ему уведомления


class Mac:
    def __init__(self, data_dir, base, logo=None, run=subprocess.run, platform=sys.platform, which=shutil.which):
        self.dir, self.base, self.logo = data_dir, base, logo
        self.run, self.platform, self.which = run, platform, which
        self.shown = {}       # qid -> id показанного уведомления о вопросе
        self.problem = None
        self.lock = threading.Lock()

    def app(self):
        return os.path.join(self.dir, "Agents Hub Notify.app")

    def status(self, on):
        if self.platform != "darwin":
            return {"available": False}
        if not self.which("swiftc"):
            return {"available": True, "on": on,
                    "problem": "Нужны Command Line Tools от Apple: выполните в терминале xcode-select --install"}
        return {"available": True, "on": on, "problem": self.problem}

    def handle(self, a, on, page_open):
        """Уведомление процесса: показать, снять показанное о вопросе (answered) или промолчать."""
        if self.platform != "darwin":
            return
        if a["kind"] == "answered":
            nid = self.shown.pop(a["qid"], None)
            if nid:
                self.helper("remove", nid)
            return
        if not on or page_open:
            return
        if self.post(a) == 0 and a.get("qid"):
            self.shown[a["qid"]] = a["id"]

    def post(self, a):
        return self.helper("post", a["id"], ("⛔ " if a.get("urgent") else "") + a["title"], a["text"],
                           self.base + a["href"])

    def ensure_built(self):
        """Собрать помощника, если его нет или исходник поменялся. Не из /tmp и с CFBundleVersion — иначе macOS
        молча запрещает ему уведомления."""
        with self.lock:
            with open(SRC, "rb") as f:
                digest = hashlib.sha256(f.read()).hexdigest()[:16]
            stamp = os.path.join(self.dir, "built")
            try:
                with open(stamp) as f:
                    if f.read().strip() == digest and os.path.exists(os.path.join(self.app(), "Contents", "MacOS", EXE)):
                        return
            except OSError:
                pass
            tmp = os.path.join(self.dir, "build")
            shutil.rmtree(tmp, ignore_errors=True)
            contents = os.path.join(tmp, "Agents Hub Notify.app", "Contents")
            os.makedirs(os.path.join(contents, "Resources"))
            os.makedirs(os.path.join(contents, "MacOS"))
            info = {"CFBundleIdentifier": BUNDLE_ID, "CFBundleName": "Agents Hub", "CFBundleDisplayName": "Agents Hub",
                    "CFBundleExecutable": EXE, "CFBundlePackageType": "APPL", "CFBundleVersion": digest,
                    "CFBundleShortVersionString": "1.0", "LSUIElement": True}
            if self.logo and os.path.exists(self.logo):
                shutil.copy(self.logo, os.path.join(contents, "Resources", "logo.icns"))
                info["CFBundleIconFile"] = "logo"
            with open(os.path.join(contents, "Info.plist"), "wb") as f:
                plistlib.dump(info, f)
            out = os.path.join(contents, "MacOS", EXE)
            r = self.run([self.which("swiftc"), "-O", "-swift-version", "5", SRC, "-o", out],
                         capture_output=True, text=True, timeout=300)
            if r.returncode != 0:
                raise RuntimeError("не собрался: " + (r.stderr or "").strip()[-300:])
            self.run([self.which("codesign") or "codesign", "--force", "--sign", "-", os.path.dirname(contents)],
                     capture_output=True, text=True, timeout=60)
            shutil.rmtree(self.app(), ignore_errors=True)
            os.replace(os.path.dirname(contents), self.app())
            shutil.rmtree(tmp, ignore_errors=True)
            with open(stamp, "w") as f:
                f.write(digest)

    def helper(self, *args):
        try:
            self.ensure_built()
        except (OSError, RuntimeError, subprocess.SubprocessError) as e:
            self.problem = f"Помощник уведомлений {e}"
            return None
        # через LaunchServices (open), не исполняемым файлом напрямую: так macOS уведомлять не пускает
        os.makedirs(self.dir, exist_ok=True)
        fd, err = tempfile.mkstemp(prefix="hub-notify-", dir=self.dir)
        os.close(fd)
        try:
            r = self.run(["open", "-n", "-g", "-W", "--stderr", err, self.app(), "--args", *args], capture_output=True,
                         text=True, timeout=30)
            with open(err) as f:
                said = f.read()
        finally:
            os.remove(err)
        code = r.returncode
        if code == 0 and said.strip():
            code = DENIED if "not allowed" in said else 1
            self.problem = None if code == DENIED else f"Помощник уведомлений: {said.strip()[-200:]}"
        if code == DENIED:
            self.problem = ("macOS запрещает уведомления хаба: разрешите их в «Системные настройки» → «Уведомления» → "
                            "«Agents Hub»")
        elif code == 0 and args[0] == "post":
            self.problem = None
        return code
