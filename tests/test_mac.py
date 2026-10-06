"""Уведомления macOS: показать новое, снять показанное о вопросе, на который ответили; молчать, пока открыта страница
с уведомлениями браузера или они выключены; помощник собирается один раз на исходник, в папке состояния."""
import os
import plistlib
import shutil
import tempfile
import unittest

import mac


def alert(seq, kind="reply", qid=None, session="hub"):
    a = {"id": f"a{seq}", "seq": seq, "kind": kind, "session": session, "title": f"{session} отвечает",
         "text": f"текст {seq}", "href": f"#/s/{session}", "urgent": False}
    if qid:
        a["qid"] = qid
    return a


class Runs:
    def __init__(self, code=0):
        self.calls, self.code = [], code

    def __call__(self, cmd, **kw):
        self.calls.append(cmd)
        if cmd[0].endswith("swiftc"):
            out = cmd[cmd.index("-o") + 1]
            os.makedirs(os.path.dirname(out), exist_ok=True)
            open(out, "w").close()
        return type("R", (), {"returncode": self.code, "stdout": "", "stderr": ""})()


class MacTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="notify-mac-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.run = Runs()
        self.mac = mac.Mac(self.dir, "http://127.0.0.1:8787/", run=self.run, platform="darwin",
                           which=lambda tool: "/usr/bin/" + tool)
        self.mac.ensure_built = lambda: None

    def posted(self):
        return [c[c.index("--args") + 1:] for c in self.run.calls if c[c.index("--args") + 1] == "post"]

    def test_shows_and_the_click_opens_the_session(self):
        self.mac.handle(alert(9, session="maps"), on=True, page_open=False)
        self.assertEqual(self.posted(), [["post", "a9", "maps отвечает", "текст 9", "http://127.0.0.1:8787/#/s/maps"]])
        self.assertEqual(self.run.calls[0][:2], ["open", "-n"])          # через LaunchServices: напрямую macOS не пускает

    def test_silent_while_a_page_shows_them_or_when_off(self):
        self.mac.handle(alert(3), on=True, page_open=True)
        self.mac.handle(alert(4), on=False, page_open=False)
        self.assertEqual(self.posted(), [])

    def test_an_answered_question_is_removed_even_if_a_page_opened_since(self):
        self.mac.handle(alert(7, "ask", qid="q:maps:r1", session="maps"), on=True, page_open=False)
        self.mac.handle({"kind": "answered", "qid": "q:maps:r1"}, on=True, page_open=True)
        self.assertEqual(self.run.calls[-1][-2:], ["remove", "a7"])

    def test_macos_refusal_is_in_the_status(self):
        self.run.code = mac.DENIED
        self.mac.handle(alert(2), on=True, page_open=False)
        self.assertIn("запрещ", self.mac.status(True)["problem"])

    def test_status_says_what_is_missing(self):
        self.assertFalse(mac.Mac(self.dir, "", platform="linux").status(True)["available"])
        bare = mac.Mac(self.dir, "", platform="darwin", which=lambda tool: None)
        self.assertIn("xcode-select --install", bare.status(True)["problem"])

    def test_builds_once_per_source_in_its_folder_with_a_full_info_plist(self):
        m = mac.Mac(self.dir, "", run=self.run, platform="darwin", which=lambda tool: "/usr/bin/" + tool)
        m.ensure_built()
        m.ensure_built()
        tools = [os.path.basename(c[0]) for c in self.run.calls]
        self.assertEqual(tools.count("swiftc"), 1)
        self.assertIn("codesign", tools)
        self.assertTrue(m.app().startswith(self.dir))                    # не в /tmp: оттуда macOS уведомлять не даёт
        with open(os.path.join(m.app(), "Contents", "Info.plist"), "rb") as f:
            info = plistlib.load(f)
        self.assertEqual((info["CFBundleIdentifier"], info["CFBundleName"]), (mac.BUNDLE_ID, "Agents Hub"))
        self.assertIn("CFBundleVersion", info)                           # без него macOS молча запрещает


if __name__ == "__main__":
    unittest.main()
