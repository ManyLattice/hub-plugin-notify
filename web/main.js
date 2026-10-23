// Уведомления браузера и macOS о том, что важно владельцу: вопрос ему, ответ хаба, ответ на его сообщение, итог его
// задачи, напоминание, сигнал монитора. Что важно, решает процесс плагина (main.py) и пишет в канал плагина; страница
// показывает новое, пока вкладка не перед глазами, и снимает уведомление о вопросе, на который уже ответили.
// Пока страница показывает уведомления браузера, она отмечается у процесса — уведомления macOS тогда молчат.
// Бейдж: пока вкладка не перед глазами, новое прибавляет число в названии вкладки, точку на её значке и число на значке
// приложения (где браузер его даёт); вернулись на вкладку, и всё снято. От разрешения на уведомления не зависит.
import { Badge, Title } from "./badge.js";

const CHANNEL = "notify";
const KEY = "hub.notify";
const BADGE_KEY = "hub.notify.badge";
const HERE_MS = 10000;

let hub = null;
const el = (...a) => hub.el(...a);
const supported = () => "Notification" in window && window.isSecureContext;
const on = () => supported() && Notification.permission === "granted" && localStorage.getItem(KEY) !== "off";
const local = () => ["127.0.0.1", "localhost"].includes(location.hostname);
const proc = (path, method = "GET") =>
  fetch(`http://${location.hostname}:${Number(location.port || 80) + 8}${path}`, { method }).then((r) => r.json());

let last = null, reading = false;
const shown = new Map();   // qid -> уведомление о вопросе: ответили — снять
const away = () => document.hidden || !document.hasFocus();
const badgeOn = () => localStorage.getItem(BADGE_KEY) !== "off";
const badge = new Badge(), title = new Title();
const count = () => (badgeOn() ? badge.count : 0);
let icon = null, dot = null, appBadge = 0;   // исходный значок вкладки, он же с точкой, число на значке приложения

function retitle() {
  const t = title.next(document.title, count());
  if (t !== null) document.title = t;
}

function dotIcon(href) {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => {
      try {
        const c = document.createElement("canvas");
        c.width = c.height = 64;
        const g = c.getContext("2d");
        g.drawImage(img, 0, 0, 64, 64);
        g.beginPath();
        g.arc(48, 16, 15, 0, 2 * Math.PI);
        g.fillStyle = "#ff3b30";
        g.fill();
        g.lineWidth = 4;
        g.strokeStyle = "#fff";
        g.stroke();
        resolve(c.toDataURL("image/png"));
      } catch { resolve(null); }
    };
    img.onerror = () => resolve(null);
    img.src = href;
  });
}

function setIcon(href, type) {
  const link = document.querySelector('link[rel~="icon"]');
  if (!link || link.href === href) return;
  link.type = type;
  link.href = href;
}

async function paintBadge() {
  const n = count();
  retitle();
  if (n !== appBadge && "setAppBadge" in navigator) {
    appBadge = n;
    (n ? navigator.setAppBadge(n) : navigator.clearAppBadge()).catch(() => {});
  }
  const link = document.querySelector('link[rel~="icon"]');
  if (link && !icon) icon = { href: link.href, type: link.type };
  if (!icon) return;
  if (!n) return setIcon(icon.href, icon.type);
  dot = dot || await dotIcon(icon.href);
  if (dot && count()) setIcon(dot, "image/png");   // пока рисовали, могли вернуться на вкладку
}

function back() {
  if (!away() && badge.clear()) paintBadge();
}

function show(a) {
  const ask = a.kind === "ask" || a.kind === "reminder";
  const n = new Notification((a.urgent ? "⛔ " : "") + a.title, {
    body: a.text, tag: a.id,   // одно и то же из нескольких вкладок — одно уведомление
    requireInteraction: ask || a.urgent,
  });
  n.onclick = () => { window.focus(); location.hash = a.href; n.close(); };
  if (a.qid) shown.set(a.qid, n);
}

async function tick(snap) {
  const top = (snap.feeds || {})[CHANNEL] || 0;
  if (last === null) { last = top; return; }   // открыли страницу — старое не показывать
  if (top <= last || reading) return;
  reading = true;
  try {
    for (const p of await hub.feed(last)) {
      last = Math.max(last, Number(String(p.id).slice(1)) || 0);
      if (!String(p.by).startsWith("плагин ")) continue;   // писать в канал могут и сессии — верим только процессу
      let a;
      try { a = JSON.parse(p.text); } catch { continue; }
      if (a.kind === "answered") {
        shown.get(a.qid)?.close();
        shown.delete(a.qid);
        if (badge.answered(a.qid)) paintBadge();
        continue;
      }
      if (!away()) continue;   // перед глазами — и так видно
      if (on()) show(a);
      if (badgeOn() && badge.add(a)) paintBadge();
    }
  } finally { reading = false; }
}

function browserSection() {
  const box = el("div", "settings-sec");
  const state = el("p", "jev-state");
  const btn = el("button", "btn");
  btn.type = "button";
  const test = el("button", "btn quiet", "Проверить");
  test.type = "button";
  test.addEventListener("click", () => show({ id: "test", kind: "reply", title: "Хаб", text: "Так выглядят уведомления хаба.", href: location.hash || "#/" }));
  const paint = () => {
    test.hidden = !on();
    btn.hidden = false;
    state.className = "jev-state";
    if (!supported()) {
      state.textContent = "Этот адрес уведомлений не даёт: браузер показывает их только на https или на этом же компьютере (127.0.0.1).";
      btn.hidden = true;
    } else if (Notification.permission === "denied") {
      state.textContent = "Браузер запретил уведомления этой странице. Разрешите их в настройках сайта (значок слева от адреса) и обновите страницу.";
      btn.hidden = true;
    } else if (on()) {
      state.className = "jev-state on";
      state.textContent = "Включены: когда вкладка хаба не перед глазами, браузер покажет вопрос вам, ответ хаба, итог вашей задачи, напоминание и сигнал монитора. Клик открывает нужную сессию.";
      btn.textContent = "Выключить";
    } else {
      state.textContent = "Выключены.";
      btn.textContent = "Включить";
    }
  };
  btn.addEventListener("click", async () => {
    if (on()) localStorage.setItem(KEY, "off");
    else {
      localStorage.removeItem(KEY);
      if (Notification.permission === "default") await Notification.requestPermission();
    }
    paint();
    here();
  });
  paint();
  const row = el("div", "upd-actions");
  row.append(btn, test);
  box.append(el("h3", "day", "В браузере"), state, row, el("p", "hint", "Приходят, пока страница хаба открыта хотя бы в одной вкладке. Как показывать (баннер, звук, «Не беспокоить») — в системных настройках уведомлений для браузера."));
  return box;
}

function badgeSection() {
  const box = el("div", "settings-sec");
  const state = el("p", "jev-state");
  const btn = el("button", "btn");
  btn.type = "button";
  const paint = () => {
    state.className = badgeOn() ? "jev-state on" : "jev-state";
    state.textContent = badgeOn()
      ? "Включён: пока вкладка хаба не перед глазами, новое уведомление прибавляет число в названии вкладки и красную точку на её значке (Safari точку не показывает: значок вкладки он берёт только при загрузке страницы). Вернулись на вкладку, и всё снято."
      : "Выключен.";
    btn.textContent = badgeOn() ? "Выключить" : "Включить";
  };
  btn.addEventListener("click", () => {
    if (badgeOn()) { localStorage.setItem(BADGE_KEY, "off"); badge.clear(); }
    else localStorage.removeItem(BADGE_KEY);
    paint();
    paintBadge();
  });
  paint();
  const row = el("div", "upd-actions");
  row.append(btn);
  box.append(el("h3", "day", "Значок на вкладке"), state, row, el("p", "hint", "Работает и без разрешения на уведомления. Хаб, добавленный в Dock из Safari или установленный из Chrome, показывает число и на значке приложения."));
  return box;
}

function macSection() {
  const box = el("div", "settings-sec");
  const note = el("p", "hint");
  note.hidden = true;
  const say = (text) => { note.textContent = text || ""; note.hidden = !note.textContent; };
  const paint = (m) => {
    if (!m.available) { box.hidden = true; return; }
    box.replaceChildren(el("h3", "day", "Когда страница закрыта"));
    box.append(el("p", m.on && !m.problem ? "jev-state on" : "jev-state", m.on
      ? "Уведомления macOS включены: хаб покажет то же самое, когда ни одна страница с уведомлениями браузера не открыта. Клик открывает сессию."
      : "Уведомления macOS выключены."));
    if (m.problem) box.append(el("p", "hint warn", m.problem));
    const act = async (path) => { try { say((await proc(path, "POST")).text); paint(await proc("/status")); } catch { say("Процесс плагина не отвечает: «Настройки» → «Плагины»."); } };
    const btn = el("button", "btn", m.on ? "Выключить" : "Включить");
    btn.type = "button";
    btn.addEventListener("click", () => act(m.on ? "/mac/off" : "/mac/on"));
    const row = el("div", "upd-actions");
    row.append(btn);
    if (m.on) {
      const test = el("button", "btn quiet", "Проверить");
      test.type = "button";
      test.addEventListener("click", () => act("/mac/test"));
      row.append(test);
    }
    box.append(row, note, el("p", "hint", "Первое уведомление macOS спросит разрешение. Плагин сам собирает для них маленький помощник «Agents Hub» в папке состояния хаба."));
  };
  box.hidden = true;
  if (local()) proc("/status").then((m) => { box.hidden = false; paint(m); }).catch(() => {});
  return box;
}

function here() {
  if (on() && local()) proc("/here").catch(() => {});
}

export default function register(api) {
  hub = api;
  hub.addSlot("sidebar.footer", { id: "notify", order: 1000, render(root, snap) { root.hidden = true; tick(snap); } });
  hub.addSettings({
    id: "notify", title: "Уведомления",
    render(root) {
      if (root.dataset.built) return;   // кнопки и ответы не терять на каждом снимке
      root.dataset.built = "1";
      root.replaceChildren(browserSection(), badgeSection(), macSection());
    },
  });
  const t = document.querySelector("title");
  if (t) new MutationObserver(retitle).observe(t, { childList: true, characterData: true, subtree: true });
  document.addEventListener("visibilitychange", back);
  window.addEventListener("focus", back);
  here();
  setInterval(here, HERE_MS);
}
