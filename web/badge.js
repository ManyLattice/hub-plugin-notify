// The "there is a new notification" badge count without the DOM: what came while the tab was out of sight, and what of
// it is already taken away. The tab title "(N) <name>": the core sets its name on every redraw, the plugin puts the
// number on top.

export class Badge {
  constructor() {
    this.items = new Map();   // notification id -> question qid (answered, and it leaves the count)
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

// The tab title with the number on top of what the core sets. next(current, N) -> the one to set, or null (already
// so): its own title is not taken for a new name, so the <title> observer does not loop.
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
