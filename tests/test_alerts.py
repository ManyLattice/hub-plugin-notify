"""What deserves a notification: a question to the owner, the hub's answer, a session's reply to their message, the
result of their task, a reminder, a monitor's signal; a closed question is "answered", to take its notification away."""
import unittest

from core import reducer

from alerts import Alerts

OWNER = {"channel": "web", "owner": True}
Q = {"questions": [{"question": "Which tiles to use?", "options": [{"label": "Raster"}, {"label": "Vector"}]}]}


class AlertsTest(unittest.TestCase):
    def setUp(self):
        self.a, self.seq, self.got = Alerts(reducer.empty()), 0, []
        self.ev("session.requested", "hub", cwd="/h", session_id="s-hub", kind="hub", **OWNER)
        self.ev("session.requested", "maps", cwd="/m", session_id="s-m", **OWNER)
        self.ev("session.started", "hub")
        self.ev("session.started", "maps")
        self.got = []

    def ev(self, type, entity=None, ts=None, **data):
        self.seq += 1
        self.got += self.a.step({"seq": self.seq, "ts": ts or 1000 + self.seq, "type": type, "entity": entity,
                                 "data": data})
        return self.seq

    def kinds(self):
        return [(x["kind"], x["session"]) for x in self.got]

    def turn(self, name, text, marker=None):
        self.ev("turn.started", name, marker=marker, prompt_head="x")
        return self.ev("turn.result", name, text=text)

    def ask(self, name="maps"):
        self.ev("turn.started", name, marker=None, prompt_head="x")
        self.ev("permission.requested", name, request_id="r1", tool="AskUserQuestion", interactive=True, input=Q)

    def test_a_question_is_an_alert_and_its_answer_closes_it(self):
        self.ask()
        (x,) = self.got
        self.assertEqual((x["kind"], x["session"], x["href"]), ("ask", "maps", "#/s/maps"))
        self.assertIn("Which tiles to use?", x["text"])
        self.ev("permission.answered", "maps", request_id="r1", behavior="allow",
                answers={"Which tiles to use?": "Raster"}, **OWNER)
        self.assertEqual([(y["kind"], y["qid"]) for y in self.got[1:]], [("answered", x["qid"])])

    def test_the_hub_answer_is_an_alert_a_silent_one_is_not(self):
        self.turn("hub", "—")
        self.assertEqual(self.got, [])
        self.turn("hub", "Done: the page is restarted.")
        self.assertEqual(self.kinds(), [("reply", "hub")])

    def test_a_worker_result_is_an_alert_only_when_the_owner_asked(self):
        self.turn("maps", "Did step 3 of 7.")
        self.assertEqual(self.got, [])
        self.ev("message.received", None, to="maps", text="how is it going?", **OWNER)
        self.turn("maps", "Almost done.", marker=f"m{self.seq}")
        self.assertEqual(self.kinds(), [("reply", "maps")])

    def test_the_result_of_the_owners_task_is_an_alert(self):
        hub = {"channel": "session", "owner": False, "sender": "hub"}
        self.ev("message.received", None, to="hub", text="make a map", **OWNER)
        self.ev("delegation.created", None, session="maps", **{"for": f"m{self.seq}"}, context="", **hub)
        d = self.a.st["delegations"][f"d{self.seq}"]
        self.turn("maps", "The map is ready: tiles/v2.", marker=d["message"])
        self.assertEqual(self.kinds(), [("task", "maps")])
        self.assertIn("The map is ready", self.got[0]["text"])

    def test_a_monitor_signal_is_an_alert(self):
        self.ev("owner.notify", None, source="ci", title="Build failed", text="main: 3 tests red", urgent=True)
        (x,) = self.got
        self.assertEqual((x["kind"], x["title"], x["urgent"], x["href"]), ("notify", "Build failed", True, "#/"))

    def test_titles_are_english_by_default_and_russian_for_a_russian_owner(self):
        self.ask()
        self.assertEqual(self.got[0]["title"], "maps asks")
        self.a.st["owner"]["lang"] = "ru"
        self.turn("hub", "Done.")
        self.assertEqual(self.got[-1]["title"], "hub отвечает")

    def test_a_reminder_about_an_open_question_is_an_alert(self):
        self.ask()
        qid = self.got[0]["qid"]
        self.ev("timer.fired", qid, ts=1000 + 31 * 60, n=1)
        self.assertEqual([(x["kind"], x.get("qid")) for x in self.got], [("ask", qid), ("reminder", qid)])

    def test_a_rejected_event_gives_nothing_and_ids_are_unique(self):
        self.ev("session.started", "nobody")
        self.assertEqual(self.got, [])
        for i in range(3):
            self.ev("owner.notify", None, source="ci", text=f"signal {i}")
        self.assertEqual(len({x["id"] for x in self.got}), 3)


if __name__ == "__main__":
    unittest.main()
