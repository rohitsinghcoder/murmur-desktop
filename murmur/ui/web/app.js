"use strict";

// ICONS comes from icons.js (Phosphor, regular weight).
const SIZES = { "try-icon": 19, search: 15, btn: 16, toast: 16, "row-lock": 22, "seg-icon": 15, "note-icon": 15, "pair-arrow": 14 };

function svg(name, size = 18) {
  return `<svg width="${size}" height="${size}" viewBox="0 0 256 256" fill="currentColor">${ICONS[name]}</svg>`;
}

// The logo: an M made of voice-waveform bars on a charcoal tile. The middle bar is the accent,
// like a recording light. Same drawing as logo_image() in ui/style.py.
const LOGO = (() => {
  const heights = [0.30, 0.54, 0.34, 0.54, 0.30];
  const w = 6.08, gap = 3.84, x0 = (64 - (5 * w + 4 * gap)) / 2;
  const bars = heights.map((h, i) => {
    const hh = h * 64;
    const fill = i === 2 ? "#e07a50" : "#ededee";
    return `<rect x="${x0 + i * (w + gap)}" y="${(64 - hh) / 2}" width="${w}" height="${hh}" rx="${w / 2}" fill="${fill}"/>`;
  }).join("");
  return `<svg viewBox="0 0 64 64"><rect width="64" height="64" rx="16" fill="#1d1d20"/>
    <rect x=".75" y=".75" width="62.5" height="62.5" rx="15.25" fill="none" stroke="#fff" stroke-opacity=".12" stroke-width="1.5"/>${bars}</svg>`;
})();

// Friendlier names for the apps text was typed into.
const APPS = {
  chrome: "Chrome", msedge: "Edge", firefox: "Firefox", brave: "Brave", opera: "Opera", arc: "Arc",
  code: "VS Code", cursor: "Cursor", windsurf: "Windsurf", devenv: "Visual Studio", idea64: "IntelliJ",
  whatsapp: "WhatsApp", discord: "Discord", slack: "Slack", telegram: "Telegram", "ms-teams": "Teams",
  teams: "Teams", zoom: "Zoom", notepad: "Notepad", winword: "Word", excel: "Excel", powerpnt: "PowerPoint",
  outlook: "Outlook", onenote: "OneNote", notion: "Notion", obsidian: "Obsidian", claude: "Claude",
  chatgpt: "ChatGPT", explorer: "File Explorer", windowsterminal: "Terminal", powershell: "PowerShell",
  cmd: "Command Prompt", spotify: "Spotify", murmur: "Murmur",
};

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
// A phrase as Murmur matches it: any case, spaces or hyphens between words (replace._key).
const phraseKey = (s) => s.trim().toLowerCase().replace(/[\s-]+/g, " ");
const tidy = (s) => s.trim().replace(/\s+/g, " ");
const byText = (a, b) => a.localeCompare(b, undefined, { sensitivity: "base" });
const sameList = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const short = (s, n = 28) => (s.length > n ? `${s.slice(0, n - 1).trimEnd()}…` : s);

let bridge = null;
let state = {};
let entries = [];

function paintIcons(root = document) {
  $$("[data-icon]", root).forEach((el) => {
    const cls = [...el.classList, el.parentElement?.classList.contains("btn") ? "btn" : ""].find((c) => SIZES[c]);
    el.innerHTML = svg(el.dataset.icon, SIZES[cls] || 18);
    el.style.display = "inline-flex";
  });
  $$("[data-logo]", root).forEach((el) => (el.innerHTML = LOGO));
}

function keycaps(labels) {
  return `<span class="keys">${labels.map((l) => `<kbd class="key">${esc(l)}</kbd>`).join('<span class="plus">+</span>')}</span>`;
}

// A short note at the bottom. With `action`, it has a button (like Undo) and stays a little longer.
// An "Undo" one can also be taken with Ctrl+Z.
function toast(text, { icon = "check", action = null, onAction = null, ms = action ? 4000 : 1600 } = {}) {
  const t = $("[data-toast]");
  $("[data-toast-icon]").innerHTML = svg(icon, SIZES.toast);
  $("[data-toast-text]").textContent = text;
  const button = $("[data-toast-action]");
  button.hidden = !action;
  button.textContent = action || "";
  button.onclick = () => { hideToast(); onAction(); };
  toast.onUndo = action === "Undo" ? onAction : null;
  t.classList.toggle("neutral", icon !== "check");
  t.classList.toggle("has-action", !!action);
  t.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(hideToast, ms);
}

function hideToast() {
  clearTimeout(toast.timer);
  toast.onUndo = null;
  $("[data-toast]").classList.remove("show", "has-action");
}

function greeting() {
  const h = new Date().getHours();
  return h < 5 ? "Working late?" : h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
}

// State from Murmur.

function applyState(s) {
  state = s;
  $$("[data-hotkey]").forEach((el) => (el.innerHTML = keycaps(s.hotkey)));
  // Paused (from the tray, or here) outranks the model's status.
  const status = $("[data-status]");
  status.className = `status ${s.paused ? "paused" : s.status}`;
  $("[data-status-text]").textContent = s.paused ? "Paused" : s.statusText;
  $("[data-resume]").hidden = !s.paused;
  $("[data-paused-hint]").hidden = !s.paused;
  $("[data-try]").placeholder = `Try it: click here, hold ${s.hotkeyText} and speak`;
  $("[data-version]").textContent = `Version ${s.version} · Private voice typing for Windows`;
  $("[data-version-title]").textContent = `Version ${s.version}`;
  $("[data-model]").textContent = s.model;
  $("[data-load]").textContent = s.loadSecs ? `${s.loadSecs.toFixed(1)} s` : "Loading…";
  $("[data-latency]").textContent = s.lastLatencyMs == null ? "None yet" : `Text ready ${s.lastLatencyMs} ms after you stopped`;
  $("[data-datadir]").textContent = s.dataDir;
  $("[data-reset]").hidden = s.isDefaultHotkey || recording;
  $("[data-speed]").disabled = s.status !== "ready" || speedRunning;
  applyTheme(s.theme, s.resolvedTheme);
  $$("[data-startup]").forEach((b) => { if (!b.disabled) setSwitch(b, s.startup); });
  $$("[data-option]").forEach((b) => setSwitch(b, s.options[b.dataset.option]));
  renderSetup();
  setRadios($('[data-radios="keep_history"]'), s.options.keep_history);
  showMic();
  renderWords();
  renderSnippets();
}

// Settings saved as they change. Values go to Murmur as JSON.
function setOption(key, value) {
  state.options[key] = value;
  bridge.setOption(key, JSON.stringify(value));
}

function setSwitch(el, on) { el.setAttribute("aria-checked", !!on); }
const isOn = (el) => el.getAttribute("aria-checked") === "true";

// `setting` is system, light or dark; `resolved` is what that means right now.
function applyTheme(setting, resolved) {
  if ((switchTheme.to || document.documentElement.dataset.theme) !== resolved) switchTheme(resolved);
  setRadios($('[data-radios="theme"]'), setting);
}

// The whole window crossfades from a picture of the old theme to the new one (a view
// transition), so every part changes together. Easing each element's colours instead left parts
// that applyState re-renders (keycaps), the scrollbar and placeholders snapping ahead, and
// repainted so much that it ran at a few frames a second. The title bar is part of the page
// (see ui/frame.py), so it fades with it; Murmur switches the frame's border halfway.
const THEME_MS = 300;  // ::view-transition-*(root) in style.css
function switchTheme(theme) {
  const root = document.documentElement;
  switchTheme.to = theme;  // state comes twice for one switch; the second mustn't restart it
  const set = () => {
    // Without the elements' own transitions (hover fades), or they'd ease in late.
    root.classList.add("instant");
    root.dataset.theme = theme;
    void root.offsetWidth;
    root.classList.remove("instant");
  };
  const shown = () => { if (switchTheme.to === theme) bridge.themeShown(); };
  if (!document.startViewTransition || document.hidden || matchMedia("(prefers-reduced-motion: reduce)").matches) {
    set();
    shown();
    return;
  }
  document.startViewTransition(set).ready.then(() => {
    // Painting the new theme takes a while (every pixel changes; ~150 ms here), and the fade's
    // clock would run meanwhile, so it'd appear half done. Hold it just after its start, which
    // makes the new theme paint (a fully transparent picture isn't), and let it go a few frames
    // later, once that paint is through.
    const fade = document.getAnimations().filter((a) => a.effect?.pseudoElement?.startsWith("::view-transition"));
    fade.forEach((a) => { a.pause(); a.currentTime = 1; });
    const hold = (frames) => requestAnimationFrame(() => {
      if (frames > 1) return hold(frames - 1);
      fade.forEach((a) => a.play());
      // "ease" is halfway at 30% of the time.
      Promise.all(fade.map((a) => a.ready)).then(() => setTimeout(shown, THEME_MS * 0.3));
    });
    hold(4);
  }, shown);
}

// Segmented controls are radio groups: one tab stop (the chosen option), and the arrow keys,
// Home and End move the choice, as in any Windows radio group.
function wireRadios(group, pick) {
  const radios = $$('[role="radio"]', group);
  radios.forEach((r) => r.addEventListener("click", () => { setRadios(group, r.dataset.value); pick(r.dataset.value); }));
  group.addEventListener("keydown", (e) => {
    const at = radios.indexOf(document.activeElement);
    const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key];
    const to = step ? (at + step + radios.length) % radios.length : e.key === "Home" ? 0 : e.key === "End" ? radios.length - 1 : -1;
    if (at < 0 || to < 0) return;
    e.preventDefault();
    radios[to].focus();
    radios[to].click();
  });
}

function setRadios(group, value) {
  $$('[role="radio"]', group).forEach((r) => {
    const on = r.dataset.value === value;
    r.classList.toggle("active", on);
    r.setAttribute("aria-checked", on);
    r.tabIndex = on ? 0 : -1;
  });
}

function loadState() { bridge.state((json) => applyState(JSON.parse(json))); }

// Home: stats and history.

function countUp(el, to) {
  const from = Number(el.dataset.value || 0);
  el.dataset.value = to;
  if (from === to) { el.textContent = to.toLocaleString(); return; }
  const start = performance.now();
  const step = (now) => {
    const t = Math.min(1, (now - start) / 600);
    const eased = 1 - Math.pow(1 - t, 3);
    el.textContent = Math.round(from + (to - from) * eased).toLocaleString();
    if (t < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

function applyStats(s) {
  // Nothing to count yet on a first run: four zeros would only be in the way of the checklist.
  $("[data-stats]").hidden = !s.dictations;
  countUp($('[data-stat="words"]'), s.words);
  countUp($('[data-stat="wpm"]'), s.wpm);
  countUp($('[data-stat="dictations"]'), s.dictations);
  countUp($('[data-stat="streak"]'), s.streak);
  $("[data-streak-label]").textContent = s.streak === 1 ? "Day in a row" : "Days in a row";
  // Compared with typing at 40 words per minute. Only worth saying once speaking was faster.
  $("[data-saved]").hidden = !(s.dictations && s.timesFaster > 1);
  const saved = s.minutesSaved >= 60 ? `${Math.floor(s.minutesSaved / 60)} h ${s.minutesSaved % 60} min` : `${s.minutesSaved} min`;
  $("[data-saved-text]").innerHTML = `<b>${s.timesFaster.toFixed(1)}×</b> faster than typing`
    + (s.minutesSaved >= 1 ? `<span class="sep">·</span><b>${saved}</b> saved` : "");
}

function loadHistory() {
  bridge.history((json) => {
    const data = JSON.parse(json);
    entries = data.entries;
    applyStats(data.stats);
    renderHistory();
  });
}

function dayLabel(d) {
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const day = new Date(d); day.setHours(0, 0, 0, 0);
  const diff = Math.round((today - day) / 86400000);
  if (diff === 0) return "Today";
  if (diff === 1) return "Yesterday";
  return d.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" });
}

function appName(exe) {
  if (!exe) return "";
  const base = exe.replace(/\.exe$/i, "");
  return APPS[base.toLowerCase()] || base.charAt(0).toUpperCase() + base.slice(1);
}

function duration(ms) {
  const s = Math.max(1, Math.round(ms / 1000));
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`;
}

// Showing one app's dictations. The picker only appears once there are two apps to choose from.
let appFilter = "";
let appCounts = new Map();

function renderAppFilter() {
  appCounts = new Map();
  entries.forEach((e) => {
    const name = appName(e.app);
    if (name) appCounts.set(name, (appCounts.get(name) || 0) + 1);
  });
  if (appFilter && !appCounts.has(appFilter)) appFilter = "";
  const button = $("[data-app-filter]");
  button.hidden = appCounts.size < 2 && !appFilter;
  button.classList.toggle("on", !!appFilter);
  $("[data-app-name]").textContent = appFilter || "All apps";
}

function pickApp() {
  const choose = (name) => () => { appFilter = name; limit = PAGE; renderHistory(); };
  const items = [
    { label: "All apps", icon: appFilter ? null : "check", hint: entries.length.toLocaleString(), action: choose("") },
    ...[...appCounts].sort((a, b) => b[1] - a[1] || byText(a[0], b[0])).map(([name, n]) => (
      { label: name, icon: name === appFilter ? "check" : null, hint: n.toLocaleString(), action: choose(name) })),
  ];
  const r = $("[data-app-filter]").getBoundingClientRect();
  openMenu(r.right, r.bottom + 6, items, true);
}

// History is drawn a page at a time; "Show more" adds the next page below.
const PAGE = 100;
let limit = PAGE;
let list = { shown: [], rendered: 0, re: null, lastDay: null, group: null };

function renderHistory() {
  const box = $("[data-history]");
  const query = $("[data-search]").value.trim();
  const re = query ? new RegExp(query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi") : null;
  renderAppFilter();
  const shown = entries.filter((e) => e.time !== pending?.entry.time
    && (!appFilter || appName(e.app) === appFilter) && (!re || e.text.search(re) >= 0));
  box.replaceChildren();
  list = { shown, rendered: 0, re, lastDay: null, group: null };

  if (!shown.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    const where = appFilter ? ` in ${appFilter}` : "";
    empty.innerHTML = query || appFilter
      ? `<div class="empty-title">No matches</div><div class="empty-sub">${query
        ? `Nothing you've dictated${esc(where)} contains "${esc(query)}".` : `Nothing dictated${esc(where)}.`}</div>`
      : `<div class="logo">${LOGO}</div>
         <div class="empty-title">No dictations yet</div>
         <div class="empty-sub">What you dictate shows up here, so you can copy it again.</div>`;
    box.append(empty);
    return;
  }

  appendRows(limit);
}

// Draws rows up to `upTo`, carrying on the day groups where the last page stopped. Each day is
// a section, so its label stays at the top while its rows scroll under it.
function appendRows(upTo) {
  const box = $("[data-history]");
  $(".more", box)?.remove();
  const page = list.shown.slice(list.rendered, upTo);
  page.forEach((e, i) => {
    const when = new Date(e.time);
    const day = when.toDateString();
    if (day !== list.lastDay) {
      list.lastDay = day;
      const section = document.createElement("section");
      section.className = "day-group";
      const label = document.createElement("div");
      label.className = "day";
      label.textContent = dayLabel(when);
      list.group = document.createElement("div");
      list.group.className = "entries";
      section.append(label, list.group);
      box.append(section);
    }
    list.group.append(entryRow(e, when, i, list.re));
  });
  list.rendered += page.length;

  const left = list.shown.length - list.rendered;
  if (left > 0) {
    const more = document.createElement("div");
    more.className = "more";
    more.innerHTML = `<button class="btn">Show more</button><span></span>`;
    $("span", more).textContent = `${left.toLocaleString()} older ${left === 1 ? "dictation" : "dictations"}`;
    $("button", more).onclick = (ev) => {
      const next = list.rendered;
      limit = next + PAGE;
      appendRows(limit);
      // From the keyboard, carry on at the first new row.
      if (ev.detail === 0) $$(".entry", box)[next]?.focus();
    };
    box.append(more);
  }
}

// Text with what the search matched in <mark>s. Every piece is escaped.
function marked(text, re) {
  if (!re) return esc(text);
  let out = "", at = 0;
  for (const m of text.matchAll(re)) {
    out += `${esc(text.slice(at, m.index))}<mark>${esc(m[0])}</mark>`;
    at = m.index + m[0].length;
  }
  return out + esc(text.slice(at));
}

// What a fix starts from: the text selected in `el`, or else the word under the pointer. Without
// the punctuation around it ("Rohid," is Rohid).
function fixTarget(el, x, y) {
  const sel = getSelection();
  let text = "";
  if (sel.rangeCount && !sel.isCollapsed && el.contains(sel.anchorNode) && el.contains(sel.focusNode)) {
    text = String(sel);
  } else if (x != null) {
    const r = document.caretRangeFromPoint?.(x, y);
    const node = r?.startContainer;
    if (node?.nodeType === Node.TEXT_NODE && el.contains(node)) {
      const t = node.textContent, inWord = (c) => /[\p{L}\p{N}'’-]/u.test(c || "");
      let a = r.startOffset, b = r.startOffset;
      while (a > 0 && inWord(t[a - 1])) a--;
      while (b < t.length && inWord(t[b])) b++;
      text = t.slice(a, b);
    }
  }
  text = tidy(text).replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu, "");
  return text.length <= 200 ? text : "";
}

// A row. Copying is the button on the row, Enter, or the menu: a click on the row itself does
// nothing, so selecting a word (to fix it) never replaces what's on the clipboard. Delete is
// behind the "More" icon or a right-click, so it always takes two steps.
function entryRow(e, when, i, re) {
  const row = document.createElement("div");
  row.className = "entry";
  row.tabIndex = 0;
  row.style.animationDelay = `${Math.min(i, 12) * 18}ms`;
  row.innerHTML = `
    <div class="entry-time"></div>
    <div><div class="entry-text"></div><div class="entry-meta"></div></div>
    <div class="entry-actions">
      <button class="icon-btn" data-act="copy" title="Copy" tabindex="-1">${svg("copy", 16)}</button>
      <button class="icon-btn" data-act="more" title="More" tabindex="-1">${svg("more", 18)}</button>
    </div>`;
  $(".entry-time", row).textContent = when.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  const textEl = $(".entry-text", row);
  textEl.innerHTML = marked(e.text, re);
  const meta = [appName(e.app), e.audioMs ? duration(e.audioMs) : ""].filter(Boolean);
  $(".entry-meta", row).textContent = meta.join(" · ");

  const copyBtn = $('[data-act="copy"]', row);
  const copy = (text = e.text) => {
    bridge.copy(text);
    copyBtn.classList.add("done");
    copyBtn.innerHTML = svg("check", 16);
    toast("Copied to clipboard");
    clearTimeout(row.copiedTimer);
    row.copiedTimer = setTimeout(() => { copyBtn.classList.remove("done"); copyBtn.innerHTML = svg("copy", 16); }, 1400);
  };
  const del = { label: "Delete", icon: "trash", danger: true, action: () => removeEntry(e, row) };
  const fixItem = (word, x, y) => ({
    label: word ? `Fix “${short(word)}”…` : "Fix a word…", icon: "edit", action: () => openFix(x, y, word),
  });
  const menu = (x, y, alignRight, word) => {
    const sel = String(getSelection()).trim();
    const selected = sel && textEl.contains(getSelection().anchorNode);
    openMenu(x, y, [
      selected ? { label: "Copy selection", icon: "copy", action: () => copy(sel) } : { label: "Copy", icon: "copy", action: () => copy() },
      fixItem(word, x, y),
      del,
    ], alignRight);
  };

  copyBtn.addEventListener("click", () => copy());
  $('[data-act="more"]', row).addEventListener("click", (ev) => {
    const r = ev.currentTarget.getBoundingClientRect();
    menu(r.right, r.bottom + 6, true, fixTarget(textEl));
  });
  row.addEventListener("contextmenu", (ev) => {
    ev.preventDefault();
    menu(ev.clientX, ev.clientY, false, fixTarget(textEl, ev.clientX, ev.clientY));
  });
  row.addEventListener("keydown", (ev) => {
    if (ev.target !== row) return;
    if (ev.key === "Enter") { ev.preventDefault(); copy(); }
    if (ev.key === "ContextMenu" || (ev.shiftKey && ev.key === "F10")) {
      ev.preventDefault();
      const r = row.getBoundingClientRect();
      menu(r.right - 12, r.top + 12, true, fixTarget(textEl));
    }
  });
  return row;
}

// Deleting waits until the toast has gone, so its Undo can put the row back. Deleting another
// entry first finishes the one waiting.
let pending = null; // { entry, row, timer }

function removeEntry(e, row) {
  commitDelete();
  pending = { entry: e, row, timer: setTimeout(commitDelete, 4000) };
  row.classList.add("removing");
  setTimeout(() => {
    if (pending?.row !== row) return;
    // Close the gap it leaves, then hide it (and its day, if it was the day's last).
    row.animate([{ height: `${row.offsetHeight}px` }, { height: "0px", paddingTop: "0px", paddingBottom: "0px" }],
      { duration: 200, easing: "ease-out" }).onfinish = () => {
      if (pending?.row !== row) return;
      row.hidden = true;
      syncDay(row);
    };
  }, 200);
  toast("Deleted", { icon: "trash", action: "Undo", onAction: undoDelete });
}

function commitDelete() {
  if (!pending) return;
  const { entry } = pending;
  clearTimeout(pending.timer);
  pending = null;
  entries = entries.filter((x) => x.time !== entry.time);
  bridge.deleteEntry(entry.time);
}

function undoDelete() {
  if (!pending) return;
  const { row } = pending;
  clearTimeout(pending.timer);
  pending = null;
  hideToast();
  if (!row.isConnected) { renderHistory(); return; } // the list was redrawn meanwhile
  row.getAnimations().forEach((a) => a.cancel());
  row.hidden = false;
  syncDay(row);
  row.classList.remove("removing");
}

function syncDay(row) {
  const group = row.parentElement;
  group.parentElement.hidden = [...group.children].every((r) => r.hidden);
}

// A small menu at a point (or, with alignRight, ending at it). An item may have a `hint` on its
// right, like a count.
function openMenu(x, y, items, alignRight = false) {
  closeFix();
  const menu = $("[data-menu]");
  menu.replaceChildren(...items.map((item) => {
    const b = document.createElement("button");
    if (item.danger) b.className = "danger";
    b.innerHTML = `${item.icon ? svg(item.icon, 16) : '<span class="menu-gap"></span>'}<span class="menu-label">${esc(item.label)}</span>`
      + (item.hint ? `<span class="menu-hint">${esc(item.hint)}</span>` : "");
    b.onclick = () => { closeMenu(); item.action(); };
    return b;
  }));
  menu.hidden = false;
  place(menu, x, y, alignRight);
  menu.classList.remove("open");
  requestAnimationFrame(() => menu.classList.add("open"));
  menu.querySelector("button").focus();
}

// Puts a floating box at a point, kept inside the window.
function place(el, x, y, alignRight = false) {
  const { width, height } = el.getBoundingClientRect();
  const left = alignRight ? x - width : x;
  el.style.left = `${Math.max(8, Math.min(left, innerWidth - width - 8))}px`;
  el.style.top = `${Math.max(8, Math.min(y, innerHeight - height - 8))}px`;
}

function closeMenu() {
  const menu = $("[data-menu]");
  if (!menu.hidden) { menu.hidden = true; menu.classList.remove("open"); }
}

// Home: fixing a word from History. It goes in Words like one added there: "Rohid" -> "Rohit"
// is a word with a "heard as", and a word that was only cased wrong ("json" -> "JSON") is a word
// on its own, which Murmur listens for and writes as given.

let fixFocus = null; // what had focus before, to go back to

function openFix(x, y, heard) {
  closeMenu();
  const pop = $("[data-fix]");
  fixFocus = document.activeElement;
  $("[data-fix-heard]").value = heard;
  $("[data-fix-word]").value = heard;
  pop.hidden = false;
  place(pop, x, y);
  pop.classList.remove("open");
  requestAnimationFrame(() => pop.classList.add("open"));
  const field = heard ? $("[data-fix-word]") : $("[data-fix-heard]");
  field.focus();
  field.select();
}

function closeFix(refocus = false) {
  const pop = $("[data-fix]");
  if (pop.hidden) return;
  pop.hidden = true;
  pop.classList.remove("open");
  if (refocus && fixFocus?.isConnected) fixFocus.focus();
}

function wireFix() {
  const pop = $("[data-fix]"), heardIn = $("[data-fix-heard]"), wordIn = $("[data-fix-word]");
  pop.addEventListener("submit", (e) => {
    e.preventDefault();
    const heard = tidy(heardIn.value), word = tidy(wordIn.value);
    if (!heard) { heardIn.focus(); return; }
    if (!word) { wordIn.focus(); return; }
    putWord(word, [heard]);
    closeFix(true);
    toast(`Added “${short(word)}” to Words`, { action: "View", onAction: () => { showPage("words"); flashWord(word); } });
  });
  $("[data-fix-cancel]").onclick = () => closeFix(true);
  pop.addEventListener("keydown", (e) => { if (e.key === "Escape") { e.preventDefault(); closeFix(true); } });
}

// Settings: the shortcut.

let recording = false;

function setRecording(on) {
  recording = on;
  $("[data-shortcut-idle]").hidden = on;
  $("[data-shortcut-recording]").hidden = !on;
  $("[data-shortcut-card]").classList.toggle("recording", on);
  $("[data-reset]").hidden = state.isDefaultHotkey || on;
}

function showError(text) {
  $("[data-error-text]").textContent = text || "";
  $("[data-shortcut-error]").hidden = !text;
}

function onRecorded(json) {
  const r = JSON.parse(json);
  if (!recording) return;
  setRecording(false);
  if (r.error) showError(r.error);
  else if (r.ok) { showError(""); toast(`Shortcut set to ${r.hotkeyText}`); }
}

// About: speed test.

let speedRunning = false;

function onSpeed(text) {
  speedRunning = false;
  $("[data-speed-result]").textContent = text;
  $("[data-speed-progress]").hidden = true;
  $("[data-speed]").disabled = state.status !== "ready";
}

// Settings: the microphone, remembered by name. One that isn't plugged in stays chosen (it's
// used again when it's back), and dictation uses the default meanwhile.

let mics = { default: null, devices: [] };

function loadMics(then) {
  bridge.microphones((json) => { mics = JSON.parse(json); showMic(); if (then) then(); });
}

function showMic() {
  const chosen = state.options?.microphone || "";
  const missing = chosen && !mics.devices.includes(chosen);
  $("[data-mic-name]").textContent = chosen || "System default";
  $("[data-mic]").title = chosen || mics.default || "";
  if (micTest.on) return; // the test is saying how it's going
  $("[data-mic-desc]").textContent = missing
    ? "Not connected right now, so Murmur is using the system default."
    : chosen ? "Murmur listens to this microphone." : "System default follows your Windows sound settings.";
  $("[data-mic-desc]").classList.toggle("warn", !!missing);
}

function pickMic() {
  const chosen = state.options.microphone || "";
  const pick = (name) => () => {
    setOption("microphone", name);
    showMic();
    if (micTest.on) startMicTest(); // listen to the new one
  };
  const items = [
    { label: mics.default ? `System default (${mics.default})` : "System default", icon: chosen ? null : "check", action: pick("") },
    ...mics.devices.map((name) => ({ label: name, icon: name === chosen ? "check" : null, action: pick(name) })),
  ];
  if (chosen && !mics.devices.includes(chosen)) {
    items.push({ label: `${chosen} (not connected)`, icon: "check", action: pick(chosen) });
  }
  const r = $("[data-mic]").getBoundingClientRect();
  openMenu(r.right, r.bottom + 6, items, true);
}

// Settings: start with Windows. Making the shortcut takes a moment, so the switch moves at once
// and waits (disabled) for the result.

function setStartup(on) {
  $$("[data-startup]").forEach((b) => { setSwitch(b, on); b.disabled = true; });
  bridge.setStartup(on);
}

function onStartup(error) {
  $$("[data-startup]").forEach((b) => (b.disabled = false));
  if (error) toast("Couldn't change the startup shortcut", { icon: "alert" });
  loadState();
}

// Words: the vocabulary and the dictionary as one list. A word is what Murmur writes; its
// "heard as" are the dictionary entries that write it. A word on its own is a vocabulary term,
// listened for and written exactly as given. Both settings stay as they were underneath, so
// this only changes how they're shown and edited.

const MAX_TERM = 100; // settings._terms

function wordList(o = state.options) {
  const words = new Map();
  const get = (w) => words.get(w) || words.set(w, { word: w, heard: [], term: false }).get(w);
  o.vocabulary.forEach((t) => (get(t).term = true));
  o.dictionary.forEach(([h, w]) => get(w).heard.push(h));
  return [...words.values()].sort((a, b) => byText(a.word, b.word));
}

// Adds a word, or saves `old` changed. A word that's there already in another case is taken
// in (its spelling is corrected, its "heard as" kept), and a "heard as" another word had moves
// here: Murmur can only write one thing for it.
function putWord(word, heard, old = null) {
  const o = state.options, lower = word.toLowerCase();
  const all = wordList(o);
  const absorbed = all.filter((e) => e.word === old?.word || e.word.toLowerCase() === lower);
  const unique = new Map();
  [...heard, ...absorbed.filter((e) => e.word !== old?.word).flatMap((e) => e.heard)].forEach((h) => {
    const k = phraseKey(h);
    if (k && k !== phraseKey(word) && !unique.has(k)) unique.set(k, tidy(h));
  });
  const heardAs = [...unique.values()];
  const gone = new Set(absorbed.map((e) => e.word));
  const vocabulary = o.vocabulary.filter((t) => !gone.has(t));
  if (absorbed.some((e) => e.term) || !heardAs.length) vocabulary.push(word);
  const dictionary = o.dictionary.filter(([h, w]) => !gone.has(w) && !unique.has(phraseKey(h)))
    .concat(heardAs.map((h) => [h, word]));
  // A word whose only "heard as" moved stays, as a word on its own.
  all.forEach((e) => {
    if (!gone.has(e.word) && !e.term && !dictionary.some(([, w]) => w === e.word) && e.word.length <= MAX_TERM) {
      vocabulary.push(e.word);
    }
  });
  commitWords(vocabulary, dictionary);
}

function commitWords(vocabulary, dictionary) {
  // The vocabulary first, so a word moving into it from the dictionary is never in neither.
  if (!sameList(vocabulary, state.options.vocabulary)) setOption("vocabulary", vocabulary);
  if (!sameList(dictionary, state.options.dictionary)) setOption("dictionary", dictionary);
  renderWords(true);
}

function removeWord(e) {
  const before = [state.options.vocabulary, state.options.dictionary];
  commitWords(state.options.vocabulary.filter((t) => t !== e.word), state.options.dictionary.filter(([, w]) => w !== e.word));
  toast(`Removed “${short(e.word)}”`, { icon: "trash", action: "Undo", onAction: () => { commitWords(...before); flashWord(e.word); } });
}

// Lists aren't redrawn under a row being edited (state comes again after every dictation).
function renderWords(force = false) {
  const list = $("[data-word-list]");
  if (!force && $(".editing", list)) return;
  const learned = new Set(state.learnedWords || []);
  const words = wordList();
  list.replaceChildren(...words.map((e) => wordRow(e, learned.has(e.word))));
  list.hidden = !words.length;
}

function heardText(heard) {
  return heard.length ? `heard as ${heard.map((h) => `“${h}”`).join(", ")}` : "";
}

function wordRow(e, learned) {
  const row = document.createElement("div");
  row.className = "word";
  row.dataset.word = e.word;
  row.innerHTML = `
    <div class="word-main"><span class="word-text"></span>${learned ? '<span class="badge" title="Learned from a fix you made">Learned</span>' : ""}</div>
    <div class="word-heard"></div>
    <div class="row-actions">
      <button class="icon-btn" data-act="edit" title="Edit">${svg("edit", 16)}</button>
      <button class="icon-btn danger" data-act="remove" title="Remove">${svg("trash", 16)}</button>
    </div>`;
  $(".word-text", row).textContent = e.word;
  $(".word-heard", row).textContent = heardText(e.heard);
  row.title = e.word;
  $('[data-act="edit"]', row).setAttribute("aria-label", `Edit ${e.word}`);
  $('[data-act="remove"]', row).setAttribute("aria-label", `Remove ${e.word}`);
  $('[data-act="edit"]', row).onclick = () => editWord(row, e);
  $('[data-act="remove"]', row).onclick = () => removeWord(e);
  row.addEventListener("dblclick", (ev) => { if (!ev.target.closest("button")) editWord(row, e); });
  return row;
}

function editWord(row, e) {
  renderWords(true); // one row edited at a time
  row = $(`.word[data-word="${CSS.escape(e.word)}"]`, $("[data-word-list]"));
  const form = document.createElement("form");
  form.className = "word editing";
  form.innerHTML = `
    <input class="field" data-word maxlength="${MAX_TERM}" spellcheck="false" aria-label="Word or name">
    <input class="field" data-heard maxlength="200" spellcheck="false" placeholder="Heard as (optional)" aria-label="Heard as, optional" title="Separate several with commas.">
    <div class="row-actions"><button type="button" class="btn ghost" data-act="cancel">Cancel</button><button type="submit" class="btn">Save</button></div>`;
  const wordIn = $("[data-word]", form), heardIn = $("[data-heard]", form);
  wordIn.value = e.word;
  heardIn.value = e.heard.join(", ");
  const done = () => { renderWords(true); flashWord(e.word, false); };
  form.addEventListener("submit", (ev) => {
    ev.preventDefault();
    const word = tidy(wordIn.value);
    if (!word) { wordIn.focus(); return; }
    putWord(word, heardIn.value.split(",").map(tidy).filter(Boolean), e);
    flashWord(word);
  });
  $('[data-act="cancel"]', form).onclick = done;
  form.addEventListener("keydown", (ev) => { if (ev.key === "Escape") { ev.preventDefault(); ev.stopPropagation(); done(); } });
  row.replaceWith(form);
  wordIn.focus();
  wordIn.select();
}

// Shows where a word is in the list (after adding it, say), with a brief highlight.
function flashWord(word, highlight = true) {
  const row = $$(".word", $("[data-word-list]")).find((r) => r.dataset.word === word);
  if (!row) return;
  row.scrollIntoView({ block: "nearest" });
  $('[data-act="edit"]', row)?.focus({ preventScroll: true });
  if (highlight) { row.classList.remove("flash"); void row.offsetWidth; row.classList.add("flash"); }
}

function wireWords() {
  const form = $("[data-word-form]"), wordIn = $("[data-word]", form), heardIn = $("[data-heard]", form);
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const word = tidy(wordIn.value);
    if (!word) { wordIn.focus(); return; }
    putWord(word, heardIn.value.split(",").map(tidy).filter(Boolean));
    wordIn.value = heardIn.value = "";
    flashWord(word);
    wordIn.focus();
  });
}

// Words: snippets, [say, type] pairs. Saying a phrase that's already there replaces it.

function putSnippet(say, text, old = null) {
  const k = phraseKey(say);
  const pairs = state.options.snippets.filter(([f]) => phraseKey(f) !== k && f !== old?.[0]).concat([[say, text]]);
  setOption("snippets", pairs);
  renderSnippets(true);
}

function removeSnippet(pair) {
  const before = state.options.snippets;
  setOption("snippets", before.filter((p) => p !== pair));
  renderSnippets(true);
  toast(`Removed “${short(pair[0])}”`, { icon: "trash", action: "Undo", onAction: () => { setOption("snippets", before); renderSnippets(true); } });
}

function renderSnippets(force = false) {
  const list = $("[data-pair-list]", $("[data-snippets]"));
  if (!force && $(".editing", list)) return;
  const pairs = [...state.options.snippets].sort((a, b) => byText(a[0], b[0]));
  list.replaceChildren(...pairs.map((pair) => snippetRow(pair)));
  list.hidden = !pairs.length;
}

function snippetRow(pair) {
  const [say, text] = pair;
  const row = document.createElement("div");
  row.className = "pair";
  row.innerHTML = `<span class="pair-from"></span><span class="pair-arrow">${svg("arrow", 14)}</span><span class="pair-to"></span>
    <div class="row-actions">
      <button class="icon-btn" data-act="edit" title="Edit">${svg("edit", 16)}</button>
      <button class="icon-btn danger" data-act="remove" title="Remove">${svg("trash", 16)}</button>
    </div>`;
  $(".pair-from", row).textContent = say;
  $(".pair-to", row).textContent = text;
  $('[data-act="edit"]', row).setAttribute("aria-label", `Edit ${say}`);
  $('[data-act="remove"]', row).setAttribute("aria-label", `Remove ${say}`);
  $('[data-act="edit"]', row).onclick = () => editSnippet(row, pair);
  $('[data-act="remove"]', row).onclick = () => removeSnippet(pair);
  row.addEventListener("dblclick", (ev) => { if (!ev.target.closest("button")) editSnippet(row, pair); });
  return row;
}

function editSnippet(row, pair) {
  const list = $("[data-pair-list]", $("[data-snippets]"));
  const at = $$(".pair", list).indexOf(row);
  renderSnippets(true);
  row = $$(".pair", list)[at];
  const form = document.createElement("form");
  form.className = "pair editing";
  form.innerHTML = `<input class="field" data-from maxlength="200" spellcheck="false" aria-label="When I say">
    <span class="pair-arrow">${svg("arrow", 14)}</span>
    <textarea class="field" data-to rows="1" maxlength="5000" spellcheck="false" aria-label="Type"></textarea>
    <div class="row-actions"><button type="button" class="btn ghost" data-act="cancel">Cancel</button><button type="submit" class="btn" title="Save (Ctrl+Enter)">Save</button></div>`;
  const from = $("[data-from]", form), to = $("[data-to]", form);
  from.value = pair[0];
  to.value = pair[1];
  const save = () => {
    const say = tidy(from.value), text = to.value.trim();
    if (!say) { from.focus(); return; }
    if (!text) { to.focus(); return; }
    putSnippet(say, text, pair);
  };
  form.addEventListener("submit", (e) => { e.preventDefault(); save(); });
  wireSnippetText(to, save);
  $('[data-act="cancel"]', form).onclick = () => renderSnippets(true);
  form.addEventListener("keydown", (e) => { if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); renderSnippets(true); } });
  row.replaceWith(form);
  to.dispatchEvent(new Event("input"));
  from.focus();
}

// A snippet's text can have line breaks: Enter adds one there, and Ctrl+Enter saves.
function wireSnippetText(to, save) {
  to.addEventListener("keydown", (e) => { if (e.key === "Enter" && e.ctrlKey) { e.preventDefault(); save(); } });
  to.addEventListener("input", () => { to.style.height = "auto"; to.style.height = `${to.scrollHeight + 2}px`; });
}

function wireSnippets() {
  const card = $("[data-snippets]");
  const form = $("[data-pair-form]", card), from = $("[data-from]", card), to = $("[data-to]", card);
  const add = () => {
    const say = tidy(from.value), text = to.value.trim();
    if (!say) { from.focus(); return; }
    if (!text) { to.focus(); return; }
    putSnippet(say, text);
    from.value = to.value = "";
    to.dispatchEvent(new Event("input"));
    from.focus();
  };
  form.addEventListener("submit", (e) => { e.preventDefault(); add(); });
  from.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); add(); } });
  wireSnippetText(to, add);
}

// Settings: clearing history asks first, in place.

function confirmClear(on, focus = true) {
  $("[data-clear-idle]").hidden = on;
  $("[data-clear-confirm]").hidden = !on;
  const n = entries.length;
  $("[data-clear-desc]").textContent = on
    ? `Delete all ${n.toLocaleString()} ${n === 1 ? "dictation" : "dictations"}? This can't be undone.`
    : "Deletes every dictation saved on this PC. This can't be undone.";
  if (focus) (on ? $("[data-clear-cancel]") : $("[data-clear]")).focus();
}

// The level meter: for the first-run checklist on Home (until it has heard you), and the
// microphone test in Settings (for a few seconds). The mic is only open while one is on screen.

const setup = { mic: false, try: false };
const micTest = { on: false, timer: null, heard: 0 };
const MIC_TEST_MS = 10000;
let micCheck = "off"; // off, starting or on
let micRun = 0; // which start the answer is for

function renderSetup() {
  const card = $("[data-setup]");
  card.hidden = state.options.onboarded !== false;
  const done = { ...setup, startup: !!state.startup };
  $$("[data-step]", card).forEach((step) => {
    const on = done[step.dataset.step];
    step.classList.toggle("done", on);
    $(".step-mark", step).innerHTML = on ? svg("check", 13) : `<span>${$$("[data-step]", card).indexOf(step) + 1}</span>`;
  });
  $("[data-setup-title]").textContent = Object.values(done).every(Boolean) ? "You're all set" : "Get set up";
  syncMicCheck();
}

const pageOn = (name) => $(`[data-page="${name}"]`).classList.contains("active");
const setupListening = () => !$("[data-setup]").hidden && !setup.mic && pageOn("home");

function syncMicCheck(restart = false) {
  const want = document.visibilityState === "visible" && (setupListening() || (micTest.on && pageOn("settings")));
  if (want && (micCheck === "off" || restart)) {
    micCheck = "starting";
    const run = ++micRun;
    bridge.startMicCheck((ok) => {
      if (run !== micRun) return; // stopped or restarted meanwhile; that call says what's next
      micCheck = ok ? "on" : "off";
      if (ok) return;
      const text = "Couldn't open the microphone. Check Windows microphone access.";
      if (setupListening()) $("[data-mic-check]").textContent = text;
      if (micTest.on) { stopMicTest(); $("[data-mic-desc]").textContent = text; $("[data-mic-desc]").classList.add("warn"); }
    });
  } else if (!want && micCheck !== "off") {
    micCheck = "off";
    micRun++;
    bridge.stopMicCheck();
    if (!setup.mic) $("[data-meter]").style.transform = "scaleX(0)";
  }
}

function startMicTest() {
  clearTimeout(micTest.timer);
  micTest.on = true;
  micTest.heard = 0;
  micTest.timer = setTimeout(stopMicTest, MIC_TEST_MS);
  $("[data-mic-test]").textContent = "Stop";
  $("[data-test-meter]").hidden = false;
  $("[data-test-meter] i").style.transform = "scaleX(0)";
  $("[data-test-meter]").classList.remove("good");
  $("[data-mic-desc]").textContent = "Say something. The meter should move as you talk.";
  $("[data-mic-desc]").classList.remove("warn");
  syncMicCheck(true);
}

function stopMicTest() {
  if (!micTest.on) return;
  clearTimeout(micTest.timer);
  micTest.on = false;
  $("[data-mic-test]").textContent = "Test";
  $("[data-test-meter]").hidden = true;
  showMic();
  syncMicCheck();
}

let heard = 0;
function onMicLevel(level) {
  if (micCheck !== "on") return;
  if (micTest.on) {
    $("[data-test-meter] i").style.transform = `scaleX(${Math.max(0.02, level)})`;
    micTest.heard = level > 0.3 ? micTest.heard + 1 : micTest.heard;
    if (micTest.heard === 4) {
      $("[data-mic-desc]").textContent = "Sounds good. Murmur can hear you.";
      $("[data-test-meter]").classList.add("good");
    }
  }
  if (!setupListening()) return;
  $("[data-meter]").style.transform = `scaleX(${Math.max(0.02, level)})`;
  heard = level > 0.3 ? heard + 1 : 0;
  if (heard >= 4) {
    setup.mic = true;
    $("[data-mic-check]").textContent = "Sounds good. Murmur can hear you.";
    $("[data-meter]").style.transform = "scaleX(1)";
    // Let the meter settle, then let go of the mic.
    setTimeout(renderSetup, 1200);
  }
}

// Navigation and wiring.

const PAGES = ["home", "words", "settings", "about"];

function showPage(name) {
  closeMenu();
  closeFix();
  if (name !== "settings") { confirmClear(false, false); stopMicTest(); }
  if (name === "settings") loadMics();
  if (recording && name !== "settings") { bridge.cancelHotkey(); setRecording(false); }
  $$("[data-nav]").forEach((b) => b.classList.toggle("active", b.dataset.nav === name));
  $$("[data-page]").forEach((p) => p.classList.toggle("active", p.dataset.page === name));
  $("main").scrollTop = 0;
  syncMicCheck();
}

function wire() {
  $$("[data-window]").forEach((b) => (b.onclick = () => bridge.window(b.dataset.window)));
  addEventListener("blur", () => document.documentElement.classList.add("inactive"));
  addEventListener("focus", () => document.documentElement.classList.remove("inactive"));
  $$("[data-nav]").forEach((b) => (b.onclick = () => showPage(b.dataset.nav)));
  let debounce;
  const search = () => { limit = PAGE; renderHistory(); };
  $("[data-search]").addEventListener("input", () => { clearTimeout(debounce); debounce = setTimeout(search, 120); });
  $("[data-search]").addEventListener("keydown", (e) => {
    if (e.key === "Escape") { e.target.value = ""; search(); e.target.blur(); }
  });
  $("[data-app-filter]").onclick = pickApp;
  document.addEventListener("keydown", (e) => {
    if (e.ctrlKey && e.key.toLowerCase() === "f") {
      e.preventDefault();
      showPage("home");
      $("[data-search]").focus();
    }
    // Ctrl+1 to 4 go to the pages in the sidebar.
    const page = e.ctrlKey && !e.shiftKey && !e.altKey && PAGES[Number(e.key) - 1];
    if (page) {
      e.preventDefault();
      showPage(page);
    }
    if (e.ctrlKey && e.key.toLowerCase() === "z" && toast.onUndo && !e.target.closest("input, textarea")) {
      e.preventDefault();
      const undo = toast.onUndo;
      hideToast();
      undo();
    }
  });
  $("[data-change]").onclick = () => { showError(""); setRecording(true); bridge.recordHotkey(); };
  $("[data-cancel]").onclick = () => { bridge.cancelHotkey(); setRecording(false); };
  $("[data-reset]").onclick = () => { showError(""); bridge.resetHotkey(); toast("Shortcut set to Right Ctrl"); };
  $("[data-speed]").onclick = () => {
    speedRunning = true;
    $("[data-speed]").disabled = true;
    $("[data-speed-progress]").hidden = false;
    $("[data-speed-result]").textContent = "Transcribing a sample recording…";
    bridge.speedTest();
  };
  wireRadios($('[data-radios="theme"]'), (theme) => bridge.setTheme(theme));
  $$("[data-startup]").forEach((b) => (b.onclick = () => setStartup(!isOn(b))));
  $("[data-mic]").onclick = () => loadMics(pickMic);
  $("[data-mic-test]").onclick = () => (micTest.on ? stopMicTest() : startMicTest());
  wireRadios($('[data-radios="keep_history"]'), (v) => setOption("keep_history", v));
  wireWords();
  wireSnippets();
  wireFix();
  $("[data-export]").onclick = () => bridge.exportHistory((message) => { if (message) toast(message); });
  $("[data-clear]").onclick = () => confirmClear(true);
  $("[data-clear-cancel]").onclick = () => confirmClear(false);
  $("[data-clear-yes]").onclick = () => {
    if (pending) { clearTimeout(pending.timer); pending = null; }
    bridge.clearHistory();
    confirmClear(false);
    toast("History cleared");
  };
  $$("[data-option]").forEach((b) => (b.onclick = () => { setSwitch(b, !isOn(b)); setOption(b.dataset.option, isOn(b)); }));
  $("[data-folder]").onclick = () => bridge.openDataFolder();
  $("[data-log]").onclick = () => bridge.openLog();
  $$("[data-link]").forEach((b) => (b.onclick = () => bridge.openLink(b.dataset.link)));
  $("[data-resume]").onclick = () => bridge.setPaused(false);
  $("[data-setup-close]").onclick = () => { setOption("onboarded", true); renderSetup(); };
  document.addEventListener("visibilitychange", () => syncMicCheck());
  $("[data-greeting]").textContent = greeting();
  // The try-it box is one line and grows with what's dictated into it.
  const tryBox = $("[data-try]");
  tryBox.addEventListener("input", () => {
    tryBox.style.height = "auto";
    tryBox.style.height = `${tryBox.scrollHeight}px`;
    if (tryBox.value.trim() && !setup.try) { setup.try = true; renderSetup(); }
  });
  // The row menu and the fix box close on any click outside them, Esc, scrolling or leaving the
  // window.
  document.addEventListener("mousedown", (e) => {
    if (!e.target.closest("[data-menu]")) closeMenu();
    if (!e.target.closest("[data-fix], [data-menu]")) closeFix();
  });
  document.addEventListener("keydown", (e) => {
    const menu = $("[data-menu]");
    if (menu.hidden) return;
    if (e.key === "Escape") { e.preventDefault(); closeMenu(); }
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      const buttons = $$("button", menu);
      const at = buttons.indexOf(document.activeElement);
      buttons[(at + (e.key === "ArrowDown" ? 1 : buttons.length - 1)) % buttons.length].focus();
    }
  });
  $("main").addEventListener("scroll", () => { closeMenu(); closeFix(); });
  window.addEventListener("blur", closeMenu);
  // No browser context menu or file drops in an app window.
  document.addEventListener("contextmenu", (e) => { if (!e.target.closest("textarea, input")) e.preventDefault(); });
  document.addEventListener("dragover", (e) => e.preventDefault());
  document.addEventListener("drop", (e) => e.preventDefault());
}

function connect(b) {
  bridge = b;
  b.stateChanged.connect(loadState);
  b.historyChanged.connect(loadHistory);
  b.hotkeyRecorded.connect(onRecorded);
  b.speedResult.connect(onSpeed);
  b.startupChanged.connect(onStartup);
  b.micLevel.connect(onMicLevel);
  b.maximizedChanged.connect((on) => {
    document.documentElement.classList.toggle("maximized", on);
    $('[data-window="maximize"]').title = on ? "Restore" : "Maximize";
  });
  loadState();
  loadHistory();
}

// Outside Murmur (opened in a browser while designing), use sample data.
function sampleBridge() {
  const signal = () => {
    const slots = [];
    return { connect: (f) => slots.push(f), emit: (...a) => slots.forEach((f) => f(...a)) };
  };
  const stateChanged = signal(), startupChanged = signal(), micLevel = signal();
  let micTimer = null;
  const light = matchMedia("(prefers-color-scheme: light)");
  const params = new URLSearchParams(location.search);
  let theme = "system", startup = false, paused = params.has("paused");
  const options = {
    remove_fillers: true, digits: true, voice_commands: true, sounds: false, save_memory: false, show_bar: true, microphone: "", onboarded: !params.has("setup"), keep_history: "forever",
    vocabulary: ["Kubernetes", "Wispr Flow", "Supabase", "QWebEngine", "JSON"], learn_fixes: true,
    dictionary: [["sherpa onnx", "sherpa-onnx"], ["rohid", "Rohit"], ["anirud", "Anirudh"], ["a nirudh", "Anirudh"]],
    snippets: [["my email", "rohit@example.com"], ["sign off", "Thanks,\nRohit"]],
  };
  const resolved = () => (theme === "system" ? (light.matches ? "light" : "dark") : theme);
  light.addEventListener("change", () => stateChanged.emit());
  const now = Date.now(), m = 60000, d = 86400000;
  const sample = params.has("setup") ? [] : [
    [now - 2 * m, "Can you send me the slides before the meeting at 3:30 PM? I want to go through them once.", 7200, "chrome.exe"],
    [now - 15 * m, "The build is failing because the model path is wrong. Let me fix it and push again.", 6100, "Code.exe"],
    [now - 50 * m, "Book a table for four at 8 PM tomorrow.", 2900, "WhatsApp.exe"],
    [now - d - 8 * m, "Remind me to pay the electricity bill of ₹2,450 on Monday.", 4100, "chrome.exe"],
    [now - d - 70 * m, "Hey, I pushed the Windows version of Murmur to GitHub. Try it out and tell me what you think, Anirud.", 6500, "Discord.exe"],
    [now - 3 * d, "Meeting notes: ship the settings page, then the shortcut picker, then the new bar.", 6800, "notepad.exe"],
  ].map(([time, text, audioMs, app]) => ({ time, text, audioMs, app }));
  const stats = () => (sample.length
    ? { words: 1842, wpm: 152, dictations: 64, streak: 2, timesFaster: 3.8, minutesSaved: 34 }
    : { words: 0, wpm: 0, dictations: 0, streak: 0, timesFaster: 0, minutesSaved: 0 });
  return {
    stateChanged, historyChanged: signal(), hotkeyRecorded: signal(), speedResult: signal(), maximizedChanged: signal(), startupChanged, micLevel,
    state: (cb) => cb(JSON.stringify({
      hotkey: ["Right Ctrl"], hotkeyText: "Right Ctrl", isDefaultHotkey: true, status: "ready", statusText: "Ready",
      version: "0.3.0", model: "NVIDIA Parakeet TDT 0.6B v2 (int8)", loadSecs: 2.7, lastLatencyMs: 140,
      dataDir: "C:\\Users\\you\\.murmur", theme, resolvedTheme: resolved(), startup, options, paused,
      learnedWords: ["Rohit", "JSON"].filter((w) => options.vocabulary.includes(w) || options.dictionary.some(([, x]) => x === w)),
    })),
    setOption(key, value) { options[key] = JSON.parse(value); stateChanged.emit(); },
    setTheme(t) { theme = t; stateChanged.emit(); },
    themeShown() {}, window() {},
    setPaused(p) { paused = p; stateChanged.emit(); },
    // A pretend voice for the mic check: a few seconds of quiet, then talking.
    startMicCheck(cb) {
      clearInterval(micTimer);
      const t0 = Date.now();
      micTimer = setInterval(() => {
        const t = (Date.now() - t0) / 1000;
        micLevel.emit(t < 2 ? 0.02 : 0.25 + 0.35 * Math.abs(Math.sin(t * 5)));
      }, 50);
      cb(true);
    },
    stopMicCheck() { clearInterval(micTimer); },
    setStartup(on) { setTimeout(() => { startup = on; startupChanged.emit(""); }, 400); },
    history: (cb) => cb(JSON.stringify({ entries: sample, stats: stats() })),
    microphones: (cb) => cb(JSON.stringify({
      default: "Microphone Array (Realtek(R) Audio)",
      devices: ["Microphone Array (Realtek(R) Audio)", "Headset Microphone (Jabra Evolve2 65)"],
    })),
    exportHistory: (cb) => setTimeout(() => cb(`Exported ${sample.length} dictations`), 300),
    clearHistory() { sample.length = 0; this.historyChanged.emit(); },
    copy() {}, deleteEntry() {}, recordHotkey() {}, cancelHotkey() {}, resetHotkey() {},
    speedTest() {}, openDataFolder() {}, openLog() {}, openLink() {},
  };
}

paintIcons();
wire();
if (window.qt && window.QWebChannel) new QWebChannel(qt.webChannelTransport, (ch) => connect(ch.objects.murmur));
else connect(sampleBridge());
