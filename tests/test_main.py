"""Процесс плагина: уведомления — постами в канал плагина от его имени; страница отмечается, что открыта (тогда
macOS молчит); говорит он только со страницей хаба; журнал читает с текущего места и после ротации."""
import json
import os
import shutil
import tempfile
import unittest

from core import journal

import main

PAGE = f"http://127.0.0.1:{main.WEB_PORT}"


class FakeMac:
    def __init__(self):
        self.got = []

    def handle(self, a, on, page_open):
        self.got.append((a["id"], on, page_open))

    def status(self, on):
        return {"available": True, "on": on, "problem": None}

    def post(self, a):
        return 0


class PluginTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="notify-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.now, self.posts, self.mac = 1000.0, [], FakeMac()
        self.p = main.Plugin(self.dir, mac=self.mac, put=self.posts.append, clock=lambda: self.now)
        self.p.test = lambda: None

    def test_alerts_go_to_the_plugin_channel_as_the_plugin(self):
        self.p.emit([{"id": "a5", "kind": "reply", "title": "hub отвечает", "text": "готово"}])
        (post,) = self.posts
        self.assertEqual((post["plugin"], post["channel"], post["sender"], post["owner"]),
                         (main.CHANNEL, "plugin", main.NAME, False))
        self.assertEqual(json.loads(post["text"])["id"], "a5")

    def test_macos_is_quiet_while_the_page_checks_in_and_speaks_after_it_goes(self):
        self.assertEqual(self.p.act("/mac/on", PAGE)[0], 200)
        self.assertEqual(self.p.act("/here", PAGE)[0], 200)
        self.p.emit([{"id": "a1", "kind": "reply"}])
        self.now += main.PAGE_ALIVE + 1
        self.p.emit([{"id": "a2", "kind": "reply"}])
        self.assertEqual(self.mac.got, [("a1", True, True), ("a2", True, False)])
        self.assertTrue(main.Settings(os.path.join(self.dir, "notify", "settings.json")).mac())

    def test_only_the_hub_page_may_talk_to_it(self):
        for origin in ("", "https://evil.example", "http://127.0.0.1:9999"):
            self.assertEqual(self.p.act("/mac/on", origin)[0], 403)
        self.assertFalse(self.p.settings.mac())
        self.assertEqual(self.p.act("/status", PAGE), (200, {"available": True, "on": False, "problem": None}))


class FollowerTest(unittest.TestCase):
    def test_new_events_only_and_after_rotation_the_new_journal(self):
        d = tempfile.mkdtemp(prefix="notify-j-")
        self.addCleanup(shutil.rmtree, d, True)
        j = journal.Journal(os.path.join(d, "journal.jsonl"))
        j.append("owner.notify", data={"text": "старое"}, ts=1)
        f = main.Follower(d)
        self.assertEqual(f.events(), ([], False))
        j.append("owner.notify", data={"text": "новое"}, ts=2)
        evs, restarted = f.events()
        self.assertEqual(([e["data"]["text"] for e in evs], restarted), (["новое"], False))
        os.replace(os.path.join(d, "journal.jsonl"), os.path.join(d, "old.jsonl"))
        journal.Journal(os.path.join(d, "journal.jsonl")).append("owner.notify", data={"text": "в новом"}, ts=3)
        self.assertEqual(f.events()[1], True)


if __name__ == "__main__":
    unittest.main()
