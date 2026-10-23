"""Бейдж страницы (web/badge.js): что прибавляет счёт, что его снимает; число в названии вкладки поверх имени, которое
ставит ядро, без цикла с наблюдателем за <title>."""
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
    for (let i = 0; i < 5; i++) {   // как MutationObserver: поставили, и он зовётся снова, пока не скажет «уже так»
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


@unittest.skipUnless(NODE, "нужен node")
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
        got = run([["title", 0], ["title", 2], ["title", 2], ["title", 3], ["title", 0]], title="Хаб · Работа")
        self.assertEqual(got, [["Хаб · Работа", 0], ["(2) Хаб · Работа", 1], ["(2) Хаб · Работа", 0],
                               ["(3) Хаб · Работа", 1], ["Хаб · Работа", 1]])

    def test_the_core_resetting_the_name_gets_the_number_back_without_a_loop(self):
        got = run([["title", 1], ["core", "Хаб"], ["title", 1], ["core", "Хаб · Дом"], ["title", 1], ["title", 0]],
                  title="Хаб")
        self.assertEqual(got, [["(1) Хаб", 1], ["(1) Хаб", 1], ["(1) Хаб · Дом", 1], ["Хаб · Дом", 1]])

    def test_a_hub_name_that_looks_like_a_number_stays_the_name(self):
        got = run([["title", 1], ["title", 0]], title="(5) Хаб")
        self.assertEqual(got, [["(1) (5) Хаб", 1], ["(5) Хаб", 1]])


if __name__ == "__main__":
    unittest.main()
