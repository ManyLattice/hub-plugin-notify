// Счёт бейджа «есть новое уведомление» без DOM: что пришло, пока вкладка не перед глазами, и что из этого уже снято.
// Название вкладки «(N) <имя>»: ядро на каждой перерисовке ставит своё имя, плагин кладёт число поверх.

export class Badge {
  constructor() {
    this.items = new Map();   // id уведомления -> qid вопроса (ответили, и оно уходит из счёта)
  }

  get count() {
    return this.items.size;
  }

  add(a) {
    if (!a || !a.id || a.kind === "answered" || this.items.has(a.id)) return false;
    this.items.set(a.id, a.qid || null);
    return true;
  }

  answered(qid) {
    let gone = false;
    for (const [id, q] of this.items) if (q && q === qid) { this.items.delete(id); gone = true; }
    return gone;
  }

  clear() {
    const had = this.items.size > 0;
    this.items.clear();
    return had;
  }
}

// Название вкладки с числом поверх того, что ставит ядро. next(текущее, N) -> какое поставить или null (уже так):
// своё же название не принимается за новое имя, поэтому наблюдатель за <title> не уходит в цикл.
export class Title {
  constructor() {
    this.base = null;
    this.mine = null;
  }

  next(current, n) {
    if (current !== this.mine) this.base = current;
    this.mine = n > 0 ? `(${n}) ${this.base}` : this.base;
    return current === this.mine ? null : this.mine;
  }
}
