"""Что достойно уведомления владельцу: вопрос ему, ответ хаба, ответ сессии на его сообщение, итог его задачи,
напоминание о вопросе, сигнал монитора; и «на вопрос ответили», чтобы снять уведомление о нём.

Состояние хаба ведётся той же свёрткой, что у ядра (core.reducer), по событиям журнала: плагин только читает."""
from core import owner, reducer


def one_line(text, n=300):
    line = " ".join(str(text or "").split())
    return line if len(line) <= n else line[:n] + "…"


def open_questions(st, now):
    return {q[0]: q for q in owner.questions(st, now)}


class Alerts:
    def __init__(self, state):
        self.st = state
        self.asked = {}   # сессия -> её ход начат сообщением владельца (итог — ответ ему)

    def step(self, ev):
        """Событие журнала -> уведомления, которые оно даёт (список; пустой — ничего)."""
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
        out = [{"kind": "ask", "session": who, "qid": qid, "title": f"{who} спрашивает", "text": text}
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
                    out.append({"kind": "task", "session": name, "title": f"{name}: итог задачи", "text": text})
                elif st["sessions"][name].get("kind") == "hub" or asked:
                    out.append({"kind": "reply", "session": name, "title": f"{name} отвечает", "text": text})
        if kind == "timer.fired" and str(name or "").startswith("q:") \
                and st["owner"].get("reminders", {}).get(name) != reminded.get(name) and name in after:
            q = after[name]
            out.append({"kind": "reminder", "session": q[1], "qid": name, "title": f"Напоминание: {q[1]} ждёт ответа",
                        "text": q[3]})
        if kind == "owner.notify":
            out.append({"kind": "notify", "session": None, "title": data.get("title") or data.get("source") or "Монитор",
                        "text": data.get("text") or "", "urgent": bool(data.get("urgent"))})
        for i, a in enumerate(out):
            a.update(id=f"a{ev['seq']}" + (f"-{i}" if i else ""), seq=ev["seq"], text=one_line(a["text"], 300),
                     href=f"#/s/{a['session']}" if a["session"] else "#/")
            a.setdefault("urgent", False)
        return out
