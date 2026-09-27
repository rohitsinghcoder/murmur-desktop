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
function toast(text, { icon = "check", action = null, onAction = null, ms = action ? 4000 : 1600 } = {}) {
  const t = $("[data-toast]");
  $("[data-toast-icon]").innerHTML = svg(icon, SIZES.toast);
  $("[data-toast-text]").textContent = text;
  const button = $("[data-toast-action]");
  button.hidden = !action;
  button.textContent = action || "";
  button.onclick = () => { hideToast(); onAction(); };
  t.classList.toggle("neutral", icon !== "check");
  t.classList.toggle("has-action", !!action);
  t.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(hideToast, ms);
}

function hideToast() {
  clearTimeout(toast.timer);
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
  $("[data-hint]").hidden = !!s.paused;
  $("[data-paused-hint]").hidden = !s.paused;
  $("[data-try]").placeholder = `Try it: click here, hold ${s.hotkeyText} and speak`;
  $("[data-version]").textContent = `Version ${s.version} · Private voice typing for Windows`;
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
  $$("[data-pairs]").forEach((card) => renderPairs(card, s.options[card.dataset.pairs]));
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
  const root = document.documentElement;
  if (root.dataset.theme !== resolved) {
    root.classList.add("theming");
    root.dataset.theme = resolved;
    clearTimeout(applyTheme.timer);
    applyTheme.timer = setTimeout(() => root.classList.remove("theming"), 350);
  }
  setRadios($('[data-radios="theme"]'), setting);
  // The sidebar toggle shows where it will take you.
  const toggle = $("[data-theme-toggle]");
  const next = resolved === "dark" ? "light" : "dark";
  toggle.title = `Switch to ${next} mode`;
  if (toggle.dataset.next !== next) {
    const first = !toggle.dataset.next;
    toggle.dataset.next = next;
    toggle.innerHTML = svg(next === "light" ? "sun" : "moon", 17);
    toggle.classList.remove("turn");
    if (!first) { void toggle.offsetWidth; toggle.classList.add("turn"); }
  }
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
  countUp($('[data-stat="words"]'), s.words);
  countUp($('[data-stat="wpm"]'), s.wpm);
  countUp($('[data-stat="dictations"]'), s.dictations);
  countUp($('[data-stat="streak"]'), s.streak);
  $("[data-streak-label]").textContent = s.streak === 1 ? "Day in a row" : "Days in a row";
  // Compared with typing at 40 words per minute. Only worth saying once speaking was faster.
  $("[data-saved]").hidden = !(s.timesFaster > 1);
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

// History is drawn a page at a time; "Show more" adds the next page below.
const PAGE = 100;
let limit = PAGE;
let list = { shown: [], rendered: 0, re: null, lastDay: null, group: null };

function renderHistory() {
  const box = $("[data-history]");
  const query = $("[data-search]").value.trim();
  const re = query ? new RegExp(query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi") : null;
  const shown = entries.filter((e) => e.time !== pending?.entry.time && (!re || e.text.search(re) >= 0));
  box.replaceChildren();
  list = { shown, rendered: 0, re, lastDay: null, group: null };

  if (!shown.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.innerHTML = query
      ? `<div class="empty-title">No matches</div><div class="empty-sub">Nothing you've dictated contains "${esc(query)}".</div>`
      : `<div class="logo">${LOGO}</div>
         <div class="empty-title">No dictations yet</div>
         <div class="empty-sub">Hold ${keycaps(state.hotkey || ["Right Ctrl"])} in any app and start talking.</div>`;
    box.append(empty);
    return;
  }

  appendRows(limit);
}

// Draws rows up to `upTo`, carrying on the day groups where the last page stopped.
function appendRows(upTo) {
  const box = $("[data-history]");
  $(".more", box)?.remove();
  const page = list.shown.slice(list.rendered, upTo);
  page.forEach((e, i) => {
    const when = new Date(e.time);
    const day = when.toDateString();
    if (day !== list.lastDay) {
      list.lastDay = day;
      const label = document.createElement("div");
      label.className = "day";
      label.textContent = dayLabel(when);
      list.group = document.createElement("div");
      list.group.className = "entries";
      box.append(label, list.group);
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

// A row: click anywhere (or the copy icon) to copy. Delete is behind the "More" icon or a
// right-click, so it always takes two steps and can't be hit instead of copy.
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
  $(".entry-text", row).innerHTML = marked(e.text, re);
  const meta = [appName(e.app), e.audioMs ? duration(e.audioMs) : ""].filter(Boolean);
  $(".entry-meta", row).textContent = meta.join(" · ");

  const copyBtn = $('[data-act="copy"]', row);
  const copy = () => {
    bridge.copy(e.text);
    copyBtn.classList.add("done");
    copyBtn.innerHTML = svg("check", 16);
    toast("Copied to clipboard");
    clearTimeout(row.copiedTimer);
    row.copiedTimer = setTimeout(() => { copyBtn.classList.remove("done"); copyBtn.innerHTML = svg("copy", 16); }, 1400);
  };
  const del = { label: "Delete", icon: "trash", danger: true, action: () => removeEntry(e, row) };

  row.addEventListener("click", (ev) => {
    if (ev.target.closest('[data-act="more"]')) return;
    if (String(getSelection()).trim()) return; // selecting text, not copying it
    copy();
  });
  $('[data-act="more"]', row).addEventListener("click", (ev) => {
    const r = ev.currentTarget.getBoundingClientRect();
    openMenu(r.right, r.bottom + 6, [del], true);
  });
  const items = [{ label: "Copy", icon: "copy", action: copy }, del];
  row.addEventListener("contextmenu", (ev) => { ev.preventDefault(); openMenu(ev.clientX, ev.clientY, items); });
  row.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") { ev.preventDefault(); copy(); }
    if (ev.key === "ContextMenu" || (ev.shiftKey && ev.key === "F10")) {
      ev.preventDefault();
      const r = row.getBoundingClientRect();
      openMenu(r.right - 12, r.top + 12, items, true);
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
  group.previousElementSibling.hidden = [...group.children].every((r) => r.hidden);
}

// A small menu at a point (or, with alignRight, ending at it).
function openMenu(x, y, items, alignRight = false) {
  const menu = $("[data-menu]");
  menu.replaceChildren(...items.map((item) => {
    const b = document.createElement("button");
    if (item.danger) b.className = "danger";
    b.innerHTML = `${item.icon ? svg(item.icon, 16) : '<span class="menu-gap"></span>'}<span>${esc(item.label)}</span>`;
    b.onclick = () => { closeMenu(); item.action(); };
    return b;
  }));
  menu.hidden = false;
  const { width, height } = menu.getBoundingClientRect();
  const left = alignRight ? x - width : x;
  menu.style.left = `${Math.max(8, Math.min(left, innerWidth - width - 8))}px`;
  menu.style.top = `${Math.max(8, Math.min(y, innerHeight - height - 8))}px`;
  menu.classList.remove("open");
  requestAnimationFrame(() => menu.classList.add("open"));
  menu.querySelector("button").focus();
}

function closeMenu() {
  const menu = $("[data-menu]");
  if (!menu.hidden) { menu.hidden = true; menu.classList.remove("open"); }
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
  $("[data-mic-desc]").textContent = missing
    ? "Not connected right now, so Murmur is using the system default."
    : chosen ? "Murmur listens to this microphone." : "System default follows your Windows sound settings.";
  $("[data-mic-desc]").classList.toggle("warn", !!missing);
}

function pickMic() {
  const chosen = state.options.microphone || "";
  const pick = (name) => () => { setOption("microphone", name); showMic(); };
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

// Settings: dictionary and snippets, lists of [heard, write] pairs. Adding a phrase that's
// already there replaces it.

function renderPairs(card, pairs) {
  const list = $("[data-pair-list]", card);
  list.replaceChildren(...pairs.map(([from, to], i) => {
    const row = document.createElement("div");
    row.className = "pair";
    row.innerHTML = `<span class="pair-from"></span><span class="pair-arrow">${svg("arrow", 14)}</span>
      <span class="pair-to"></span><button class="icon-btn danger" title="Remove">${svg("trash", 16)}</button>`;
    $(".pair-from", row).textContent = from;
    $(".pair-to", row).textContent = to;
    $("button", row).onclick = () => {
      const next = pairs.filter((_, j) => j !== i);
      setOption(card.dataset.pairs, next);
      renderPairs(card, next);
      $("[data-from]", card).focus();
    };
    return row;
  }));
  list.hidden = !pairs.length;
}

function wirePairs(card) {
  const form = $("[data-pair-form]", card), from = $("[data-from]", card), to = $("[data-to]", card);
  const add = () => {
    const heard = from.value.trim().replace(/\s+/g, " "), write = to.value.trim();
    if (!heard) { from.focus(); return; }
    if (!write) { to.focus(); return; }
    const key = heard.toLowerCase();
    const pairs = [...state.options[card.dataset.pairs].filter(([f]) => f.toLowerCase() !== key), [heard, write]];
    setOption(card.dataset.pairs, pairs);
    renderPairs(card, pairs);
    from.value = to.value = "";
    to.dispatchEvent(new Event("input"));
    from.focus();
  };
  form.addEventListener("submit", (e) => { e.preventDefault(); add(); });
  // A snippet's text can have line breaks: Enter adds one there, and Ctrl+Enter adds the snippet.
  to.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.ctrlKey || to.tagName !== "TEXTAREA")) { e.preventDefault(); add(); }
  });
  if (to.tagName === "TEXTAREA") {
    to.addEventListener("input", () => { to.style.height = "auto"; to.style.height = `${to.scrollHeight + 2}px`; });
  }
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

// Home: the first-run checklist, until it's dismissed. The mic check listens only while the card
// is on screen, and stops soon after it has heard you.

const setup = { mic: false, try: false };
let micCheck = "off"; // off, starting or on

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

function syncMicCheck() {
  const want = !$("[data-setup]").hidden && !setup.mic && document.visibilityState === "visible"
    && $('[data-page="home"]').classList.contains("active");
  if (want && micCheck === "off") {
    micCheck = "starting";
    bridge.startMicCheck((ok) => {
      if (micCheck !== "starting") { if (ok) bridge.stopMicCheck(); return; }
      micCheck = ok ? "on" : "off";
      if (!ok) $("[data-mic-check]").textContent = "Couldn't open the microphone. Check Windows microphone access.";
    });
  } else if (!want && micCheck !== "off") {
    micCheck = "off";
    bridge.stopMicCheck();
    if (!setup.mic) $("[data-meter]").style.transform = "scaleX(0)";
  }
}

let heard = 0;
function onMicLevel(level) {
  if (micCheck !== "on" || setup.mic) return;
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

function showPage(name) {
  if (name !== "settings") confirmClear(false, false);
  if (name === "settings") loadMics();
  if (recording && name !== "settings") { bridge.cancelHotkey(); setRecording(false); }
  $$("[data-nav]").forEach((b) => b.classList.toggle("active", b.dataset.nav === name));
  $$("[data-page]").forEach((p) => p.classList.toggle("active", p.dataset.page === name));
  $("main").scrollTop = 0;
  syncMicCheck();
}

function wire() {
  $$("[data-nav]").forEach((b) => (b.onclick = () => showPage(b.dataset.nav)));
  let debounce;
  const search = () => { limit = PAGE; renderHistory(); };
  $("[data-search]").addEventListener("input", () => { clearTimeout(debounce); debounce = setTimeout(search, 120); });
  $("[data-search]").addEventListener("keydown", (e) => {
    if (e.key === "Escape") { e.target.value = ""; search(); e.target.blur(); }
  });
  document.addEventListener("keydown", (e) => {
    if (e.ctrlKey && e.key.toLowerCase() === "f") {
      e.preventDefault();
      showPage("home");
      $("[data-search]").focus();
    }
    // Ctrl+1, 2 and 3 go to the pages in the sidebar.
    const page = e.ctrlKey && !e.shiftKey && !e.altKey && { 1: "home", 2: "settings", 3: "about" }[e.key];
    if (page) {
      e.preventDefault();
      showPage(page);
    }
    if (e.ctrlKey && e.key.toLowerCase() === "z" && pending && !e.target.closest("input, textarea")) {
      e.preventDefault();
      undoDelete();
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
  $("[data-theme-toggle]").onclick = () => bridge.setTheme(state.resolvedTheme === "dark" ? "light" : "dark");
  $$("[data-startup]").forEach((b) => (b.onclick = () => setStartup(!isOn(b))));
  $("[data-mic]").onclick = () => loadMics(pickMic);
  wireRadios($('[data-radios="keep_history"]'), (v) => setOption("keep_history", v));
  $$("[data-pairs]").forEach(wirePairs);
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
  $("[data-resume]").onclick = () => bridge.setPaused(false);
  $("[data-setup-close]").onclick = () => { setOption("onboarded", true); renderSetup(); };
  document.addEventListener("visibilitychange", syncMicCheck);
  $("[data-repo]").onclick = () => bridge.openRepo();
  $("[data-greeting]").textContent = greeting();
  // The try-it box is one line and grows with what's dictated into it.
  const tryBox = $("[data-try]");
  tryBox.addEventListener("input", () => {
    tryBox.style.height = "auto";
    tryBox.style.height = `${tryBox.scrollHeight}px`;
    if (tryBox.value.trim() && !setup.try) { setup.try = true; renderSetup(); }
  });
  // The row menu closes on any click outside it, Esc, scrolling or leaving the window.
  document.addEventListener("mousedown", (e) => { if (!e.target.closest("[data-menu]")) closeMenu(); });
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
  $("main").addEventListener("scroll", closeMenu);
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
  let theme = "system", startup = false, paused = false;
  const options = {
    remove_fillers: true, digits: true, voice_commands: true, sounds: false, show_bar: true, microphone: "", onboarded: new URLSearchParams(location.search).has("setup") ? false : true, keep_history: "forever",
    dictionary: [["sherpa onnx", "sherpa-onnx"], ["rohit", "Rohit"]],
    snippets: [["my email", "rohit@example.com"], ["sign off", "Thanks,\nRohit"]],
  };
  const resolved = () => (theme === "system" ? (light.matches ? "light" : "dark") : theme);
  light.addEventListener("change", () => stateChanged.emit());
  const now = Date.now(), m = 60000, d = 86400000;
  const sample = [
    [now - 2 * m, "Can you send me the slides before the meeting at 3:30 PM? I want to go through them once.", 7200, "chrome.exe"],
    [now - 15 * m, "The build is failing because the model path is wrong. Let me fix it and push again.", 6100, "Code.exe"],
    [now - 50 * m, "Book a table for four at 8 PM tomorrow.", 2900, "WhatsApp.exe"],
    [now - d - 8 * m, "Remind me to pay the electricity bill of ₹2,450 on Monday.", 4100, "chrome.exe"],
    [now - d - 70 * m, "Hey, I pushed the Windows version of Murmur to GitHub. Try it out and tell me what you think.", 6500, "Discord.exe"],
    [now - 3 * d, "Meeting notes: ship the settings page, then the shortcut picker, then the new bar.", 6800, "notepad.exe"],
  ].map(([time, text, audioMs, app]) => ({ time, text, audioMs, app }));
  return {
    stateChanged, historyChanged: signal(), hotkeyRecorded: signal(), speedResult: signal(), startupChanged, micLevel,
    state: (cb) => cb(JSON.stringify({
      hotkey: ["Right Ctrl"], hotkeyText: "Right Ctrl", isDefaultHotkey: true, status: "ready", statusText: "Ready",
      version: "0.3.0", model: "NVIDIA Parakeet TDT 0.6B v2 (int8)", loadSecs: 2.7, lastLatencyMs: 140,
      dataDir: "C:\\Users\\you\\.murmur", theme, resolvedTheme: resolved(), startup, options, paused,
    })),
    setOption(key, value) { options[key] = JSON.parse(value); stateChanged.emit(); },
    setTheme(t) { theme = t; stateChanged.emit(); },
    setPaused(p) { paused = p; stateChanged.emit(); },
    // A pretend voice for the mic check: a few seconds of quiet, then talking.
    startMicCheck(cb) {
      const t0 = Date.now();
      micTimer = setInterval(() => {
        const t = (Date.now() - t0) / 1000;
        micLevel.emit(t < 2 ? 0.02 : 0.25 + 0.35 * Math.abs(Math.sin(t * 5)));
      }, 50);
      cb(true);
    },
    stopMicCheck() { clearInterval(micTimer); },
    setStartup(on) { setTimeout(() => { startup = on; startupChanged.emit(""); }, 400); },
    history: (cb) => cb(JSON.stringify({ entries: sample, stats: { words: 1842, wpm: 152, dictations: 64, streak: 2, timesFaster: 3.8, minutesSaved: 34 } })),
    microphones: (cb) => cb(JSON.stringify({
      default: "Microphone Array (Realtek(R) Audio)",
      devices: ["Microphone Array (Realtek(R) Audio)", "Headset Microphone (Jabra Evolve2 65)"],
    })),
    exportHistory: (cb) => setTimeout(() => cb(`Exported ${sample.length} dictations`), 300),
    clearHistory() { sample.length = 0; this.historyChanged.emit(); },
    copy() {}, deleteEntry() {}, recordHotkey() {}, cancelHotkey() {}, resetHotkey() {},
    speedTest() {}, openDataFolder() {}, openLog() {}, openRepo() {},
  };
}

paintIcons();
wire();
if (window.qt && window.QWebChannel) new QWebChannel(qt.webChannelTransport, (ch) => connect(ch.objects.murmur));
else connect(sampleBridge());
