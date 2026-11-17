"""What deserves a notification to the owner: a question to them, the hub's answer, a session's reply to their message,
the result of their task, a reminder about a question, a monitor's signal; and "the question was answered", to take its
notification away.

The hub state is kept by the same reduction as the core's (core.reducer), from the journal events: the plugin only reads.
Titles are in the owner's language: English by default, Russian for a Russian-speaking owner."""
from core import owner, reducer

TITLES = {
    "en": {"ask": "{who} asks", "task": "{who}: task result", "reply": "{who} replies",
           "reminder": "Reminder: {who} is waiting for an answer", "monitor": "Monitor"},
    "ru": {"ask": "{who} спрашивает", "task": "{who}: итог задачи", "reply": "{who} отвечает",
           "reminder": "Напоминание: {who} ждёт ответа", "monitor": "Монитор"},
}


def lang(st):
    """The owner's language from the hub state: the core's own pick (core.i18n); on an older core, owner.lang.
    "ru" for Russian, "en" for anything else."""
    try:
        from core import i18n
        code = i18n.state_lang(st)
    except (ImportError, AttributeError):
        code = ((st or {}).get("owner") or {}).get("lang")
    return "ru" if code in ("ru", "русский") else "en"


def one_line(text, n=300):
    line = " ".join(str(text or "").split())
    return line if len(line) <= n else line[:n] + "…"


def open_questions(st, now):
    return {q[0]: q for q in owner.questions(st, now)}


class Alerts:
    def __init__(self, state):
        self.st = state
        self.asked = {}   # session -> its turn began with an owner message (the result is an answer to them)

    def step(self, ev):
        """A journal event -> the notifications it gives (a list; empty — nothing)."""
        if ev["type"] == "core.snapshot" and (ev.get("data") or {}).get("state"):
            self.st = reducer.restore(ev)
            return []
        before = open_questions(self.st, ev["ts"])
        reminded = dict(self.st["owner"].get("reminders") or {})
        self.st, _, why = reducer.reduce(self.st, ev)
        if why is not None:
            return []
        st, kind, name, data = self.st, ev["type"], ev.get("entity"), ev.get("data") or {}
        after = open_questions(st, ev["ts"])
        say = TITLES[lang(st)]
        out = [{"kind": "ask", "session": who, "qid": qid, "title": say["ask"].format(who=who), "text": text}
               for qid, (_, who, _since, text) in after.items() if qid not in before]
        out += [{"kind": "answered", "session": before[qid][1], "qid": qid, "title": "", "text": ""}
                for qid in before if qid not in after]
        if kind == "turn.started" and name:
            msg = st["messages"].get(data.get("marker") or "") or {}
            self.asked[name] = bool(msg.get("from_owner"))
        if kind == "turn.result" and name in st["sessions"]:
            text = (data.get("text") or "").strip()
            asked = self.asked.pop(name, False)
            task = next((d for d in st["delegations"].values() if d.get("replied_seq") == ev["seq"] and d.get("for")
                         and (st["messages"].get(d["for"]) or {}).get("from_owner")), None)
            if text and text not in ("—", "-") and not data.get("is_error"):
                if task:
                    out.append({"kind": "task", "session": name, "title": say["task"].format(who=name), "text": text})
                elif st["sessions"][name].get("kind") == "hub" or asked:
                    out.append({"kind": "reply", "session": name, "title": say["reply"].format(who=name), "text": text})
        if kind == "timer.fired" and str(name or "").startswith("q:") \
                and st["owner"].get("reminders", {}).get(name) != reminded.get(name) and name in after:
            q = after[name]
            out.append({"kind": "reminder", "session": q[1], "qid": name, "title": say["reminder"].format(who=q[1]),
                        "text": q[3]})
        if kind == "owner.notify":
            out.append({"kind": "notify", "session": None, "title": data.get("title") or data.get("source") or say["monitor"],
                        "text": data.get("text") or "", "urgent": bool(data.get("urgent"))})
        for i, a in enumerate(out):
            a.update(id=f"a{ev['seq']}" + (f"-{i}" if i else ""), seq=ev["seq"], text=one_line(a["text"], 300),
                     href=f"#/s/{a['session']}" if a["session"] else "#/")
            a.setdefault("urgent", False)
        return out
