// Browser and macOS notifications about what matters to the owner: a question to them, the hub's answer, a reply to
// their message, the result of their task, a reminder, a monitor's signal. What matters is decided by the plugin process
// (main.py), which writes it to the plugin channel; the page shows what is new while the tab is out of sight, and takes
// away the notification about a question that has already been answered.
// While the page shows browser notifications, it checks in with the process — macOS notifications stay silent then.
// Badge: while the tab is out of sight, a new notification adds a number to the tab title, a dot to its icon and a
// number to the app icon (where the browser offers it); back on the tab, all is cleared. It does not need the
// notification permission.
import { Badge, Title } from "./badge.js";

const CHANNEL = "notify";
const KEY = "hub.notify";
const BADGE_KEY = "hub.notify.badge";
const HERE_MS = 10000;
// A plugin post's author as the core writes it (a protocol value, not a page text): only the process is trusted
const BY_PLUGIN = "плагин ";

// Page texts by hub.lang (Plugin API 1.25); English when the language is another one or unknown
const TEXT = {
  en: {
    title: "Notifications",
    check: "Test",
    hub: "Hub",
    sample: "This is how hub notifications look.",
    unsupported: "This address gives no notifications: the browser shows them only over https or on this same computer (127.0.0.1).",
    denied: "The browser has blocked notifications for this page. Allow them in the site settings (the icon left of the address) and reload the page.",
    browserOn: "On: when the hub tab is out of sight, the browser shows a question for you, the hub's answer, the result of your task, a reminder and a monitor's signal. A click opens the session.",
    off: "Off.",
    turnOff: "Turn off",
    turnOn: "Turn on",
    browser: "In the browser",
    browserHint: "They arrive while the hub page is open in at least one tab. How they are shown (banner, sound, Do Not Disturb) is set in the system notification settings for the browser.",
    badgeOn: "On: while the hub tab is out of sight, a new notification adds a number to the tab title and a red dot to its icon (Safari shows no dot: it takes the tab icon only when the page loads). Back on the tab, all is cleared.",
    badgeOff: "Off.",
    badge: "Tab icon",
    badgeHint: "Works without the notification permission too. A hub added to the Dock from Safari or installed from Chrome also shows the number on the app icon.",
    closed: "When the page is closed",
    macOn: "macOS notifications are on: the hub shows the same when no page with browser notifications is open. A click opens the session.",
    macOff: "macOS notifications are off.",
    noProcess: "The plugin process does not answer: \"Settings\" → \"Plugins\".",
    macHint: "The first macOS notification asks for permission. For them the plugin builds a small \"Agents Hub\" helper itself in the hub state folder.",
  },
  ru: {
    title: "Уведомления",
    check: "Проверить",
    hub: "Хаб",
    sample: "Так выглядят уведомления хаба.",
    unsupported: "Этот адрес уведомлений не даёт: браузер показывает их только на https или на этом же компьютере (127.0.0.1).",
    denied: "Браузер запретил уведомления этой странице. Разрешите их в настройках сайта (значок слева от адреса) и обновите страницу.",
    browserOn: "Включены: когда вкладка хаба не перед глазами, браузер покажет вопрос вам, ответ хаба, итог вашей задачи, напоминание и сигнал монитора. Клик открывает нужную сессию.",
    off: "Выключены.",
    turnOff: "Выключить",
    turnOn: "Включить",
    browser: "В браузере",
    browserHint: "Приходят, пока страница хаба открыта хотя бы в одной вкладке. Как показывать (баннер, звук, «Не беспокоить») — в системных настройках уведомлений для браузера.",
    badgeOn: "Включён: пока вкладка хаба не перед глазами, новое уведомление прибавляет число в названии вкладки и красную точку на её значке (Safari точку не показывает: значок вкладки он берёт только при загрузке страницы). Вернулись на вкладку, и всё снято.",
    badgeOff: "Выключен.",
    badge: "Значок на вкладке",
    badgeHint: "Работает и без разрешения на уведомления. Хаб, добавленный в Dock из Safari или установленный из Chrome, показывает число и на значке приложения.",
    closed: "Когда страница закрыта",
    macOn: "Уведомления macOS включены: хаб покажет то же самое, когда ни одна страница с уведомлениями браузера не открыта. Клик открывает сессию.",
    macOff: "Уведомления macOS выключены.",
    noProcess: "Процесс плагина не отвечает: «Настройки» → «Плагины».",
    macHint: "Первое уведомление macOS спросит разрешение. Плагин сам собирает для них маленький помощник «Agents Hub» в папке состояния хаба.",
  },
};

let hub = null;
const el = (...a) => hub.el(...a);
const T = (key) => (TEXT[hub && hub.lang] || TEXT.en)[key];
const supported = () => "Notification" in window && window.isSecureContext;
const on = () => supported() && Notification.permission === "granted" && localStorage.getItem(KEY) !== "off";
const local = () => ["127.0.0.1", "localhost"].includes(location.hostname);
const proc = (path, method = "GET") =>
  fetch(`http://${location.hostname}:${Number(location.port || 80) + 8}${path}`, { method }).then((r) => r.json());

let last = null, reading = false;
const shown = new Map();   // qid -> the notification about a question: answered — take it away
const away = () => document.hidden || !document.hasFocus();
const badgeOn = () => localStorage.getItem(BADGE_KEY) !== "off";
const badge = new Badge(), title = new Title();
const count = () => (badgeOn() ? badge.count : 0);
let icon = null, dot = null, appBadge = 0;   // the original tab icon, the same with a dot, the number on the app icon

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
  if (dot && count()) setIcon(dot, "image/png");   // while it was drawn, the owner may have come back to the tab
}

function back() {
  if (!away() && badge.clear()) paintBadge();
}

function show(a) {
  const ask = a.kind === "ask" || a.kind === "reminder";
  const n = new Notification((a.urgent ? "⛔ " : "") + a.title, {
    body: a.text, tag: a.id,   // the same one from several tabs — one notification
    requireInteraction: ask || a.urgent,
  });
  n.onclick = () => { window.focus(); location.hash = a.href; n.close(); };
  if (a.qid) shown.set(a.qid, n);
}

async function tick(snap) {
  const top = (snap.feeds || {})[CHANNEL] || 0;
  if (last === null) { last = top; return; }   // the page was opened — do not show the old ones
  if (top <= last || reading) return;
  reading = true;
  try {
    for (const p of await hub.feed(last)) {
      last = Math.max(last, Number(String(p.id).slice(1)) || 0);
      if (!String(p.by).startsWith(BY_PLUGIN)) continue;   // sessions may write to the channel too — trust only the process
      let a;
      try { a = JSON.parse(p.text); } catch { continue; }
      if (a.kind === "answered") {
        shown.get(a.qid)?.close();
        shown.delete(a.qid);
        if (badge.answered(a.qid)) paintBadge();
        continue;
      }
      if (!away()) continue;   // in sight — visible anyway
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
  const test = el("button", "btn quiet", T("check"));
  test.type = "button";
  test.addEventListener("click", () => show({ id: "test", kind: "reply", title: T("hub"), text: T("sample"), href: location.hash || "#/" }));
  const paint = () => {
    test.hidden = !on();
    btn.hidden = false;
    state.className = "jev-state";
    if (!supported()) {
      state.textContent = T("unsupported");
      btn.hidden = true;
    } else if (Notification.permission === "denied") {
      state.textContent = T("denied");
      btn.hidden = true;
    } else if (on()) {
      state.className = "jev-state on";
      state.textContent = T("browserOn");
      btn.textContent = T("turnOff");
    } else {
      state.textContent = T("off");
      btn.textContent = T("turnOn");
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
  box.append(el("h3", "day", T("browser")), state, row, el("p", "hint", T("browserHint")));
  return box;
}

function badgeSection() {
  const box = el("div", "settings-sec");
  const state = el("p", "jev-state");
  const btn = el("button", "btn");
  btn.type = "button";
  const paint = () => {
    state.className = badgeOn() ? "jev-state on" : "jev-state";
    state.textContent = badgeOn() ? T("badgeOn") : T("badgeOff");
    btn.textContent = badgeOn() ? T("turnOff") : T("turnOn");
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
  box.append(el("h3", "day", T("badge")), state, row, el("p", "hint", T("badgeHint")));
  return box;
}

function macSection() {
  const box = el("div", "settings-sec");
  const note = el("p", "hint");
  note.hidden = true;
  const say = (text) => { note.textContent = text || ""; note.hidden = !note.textContent; };
  const paint = (m) => {
    if (!m.available) { box.hidden = true; return; }
    box.replaceChildren(el("h3", "day", T("closed")));
    box.append(el("p", m.on && !m.problem ? "jev-state on" : "jev-state", m.on ? T("macOn") : T("macOff")));
    if (m.problem) box.append(el("p", "hint warn", m.problem));
    const act = async (path) => { try { say((await proc(path, "POST")).text); paint(await proc("/status")); } catch { say(T("noProcess")); } };
    const btn = el("button", "btn", m.on ? T("turnOff") : T("turnOn"));
    btn.type = "button";
    btn.addEventListener("click", () => act(m.on ? "/mac/off" : "/mac/on"));
    const row = el("div", "upd-actions");
    row.append(btn);
    if (m.on) {
      const test = el("button", "btn quiet", T("check"));
      test.type = "button";
      test.addEventListener("click", () => act("/mac/test"));
      row.append(test);
    }
    box.append(row, note, el("p", "hint", T("macHint")));
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
    id: "notify", title: T("title"),
    render(root) {
      if (root.dataset.built) return;   // do not lose the buttons and answers on every snapshot
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
