"""The page badge (web/badge.js): what adds to the count, what clears it; the number in the tab title on top of the name
the core sets, without a loop with the <title> observer."""
import json
import os
import shutil
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node")
RUN = """
import { Badge, Title } from %s;
const steps = JSON.parse(process.argv[1]);
const b = new Badge(), t = new Title();
let doc = steps.title || "";
const out = [];
for (const [op, arg] of steps.ops) {
  if (op === "add") out.push([b.add(arg), b.count]);
  if (op === "answered") out.push([b.answered(arg), b.count]);
  if (op === "clear") out.push([b.clear(), b.count]);
  if (op === "core") doc = arg;
  if (op === "title") {
    const sets = [];
    for (let i = 0; i < 5; i++) {   // like a MutationObserver: set, and it is called again until it says "already so"
      const next = t.next(doc, arg);
      if (next === null) break;
      doc = next;
      sets.push(next);
    }
    out.push([doc, sets.length]);
  }
}
console.log(JSON.stringify(out));
"""


def run(ops, title=""):
    src = RUN % json.dumps("file://" + os.path.join(ROOT, "web", "badge.js"))
    r = subprocess.run([NODE, "--input-type=module", "-e", src, json.dumps({"ops": ops, "title": title})],
                       capture_output=True, text=True, timeout=30)
    if r.returncode:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(NODE, "needs node")
class BadgeJs(unittest.TestCase):
    def test_each_new_alert_counts_once(self):
        got = run([["add", {"id": "a1", "kind": "ask", "qid": "q1"}], ["add", {"id": "a2", "kind": "task"}],
                   ["add", {"id": "a2", "kind": "task"}], ["add", {"id": "a3", "kind": "reminder", "qid": "q1"}]])
        self.assertEqual(got, [[True, 1], [True, 2], [False, 2], [True, 3]])

    def test_answered_and_empty_alerts_do_not_count(self):
        got = run([["add", {"id": "a1", "kind": "answered", "qid": "q1"}], ["add", {"kind": "task"}], ["add", None]])
        self.assertEqual(got, [[False, 0], [False, 0], [False, 0]])

    def test_an_answered_question_leaves_with_its_reminders(self):
        got = run([["add", {"id": "a1", "kind": "ask", "qid": "q1"}], ["add", {"id": "a2", "kind": "reply"}],
                   ["add", {"id": "a3", "kind": "reminder", "qid": "q1"}], ["answered", "q1"], ["answered", "q1"],
                   ["answered", "q9"]])
        self.assertEqual(got[3:], [[True, 1], [False, 1], [False, 1]])

    def test_back_on_the_tab_clears_everything(self):
        got = run([["clear", None], ["add", {"id": "a1", "kind": "notify"}], ["add", {"id": "a2", "kind": "task"}],
                   ["clear", None], ["add", {"id": "a1", "kind": "notify"}]])
        self.assertEqual(got, [[False, 0], [True, 1], [True, 2], [True, 0], [True, 1]])

    def test_the_title_carries_the_number_over_the_hub_name(self):
        got = run([["title", 0], ["title", 2], ["title", 2], ["title", 3], ["title", 0]], title="Hub · Work")
        self.assertEqual(got, [["Hub · Work", 0], ["(2) Hub · Work", 1], ["(2) Hub · Work", 0],
                               ["(3) Hub · Work", 1], ["Hub · Work", 1]])

    def test_the_core_resetting_the_name_gets_the_number_back_without_a_loop(self):
        got = run([["title", 1], ["core", "Hub"], ["title", 1], ["core", "Hub · Home"], ["title", 1], ["title", 0]],
                  title="Hub")
        self.assertEqual(got, [["(1) Hub", 1], ["(1) Hub", 1], ["(1) Hub · Home", 1], ["Hub · Home", 1]])

    def test_a_hub_name_that_looks_like_a_number_stays_the_name(self):
        got = run([["title", 1], ["title", 0]], title="(5) Hub")
        self.assertEqual(got, [["(1) (5) Hub", 1], ["(5) Hub", 1]])


if __name__ == "__main__":
    unittest.main()
