"use strict";

// ICONS comes from icons.js (Phosphor, regular weight).
const SIZES = { "try-icon": 19, search: 15, btn: 16, toast: 16, "row-lock": 22 };

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

function toast(text) {
  const t = $("[data-toast]");
  $("[data-toast-text]").textContent = text;
  t.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => t.classList.remove("show"), 1600);
}

function greeting() {
  const h = new Date().getHours();
  return h < 5 ? "Working late?" : h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
}

// State from Murmur.

function applyState(s) {
  state = s;
  $$("[data-hotkey]").forEach((el) => (el.innerHTML = keycaps(s.hotkey)));
  const status = $("[data-status]");
  status.className = `status ${s.status}`;
  $("[data-status-text]").textContent = s.statusText;
  $("[data-try]").placeholder = `Try it: click here, hold ${s.hotkeyText} and speak`;
  $("[data-version]").textContent = `Version ${s.version} · Private voice typing for Windows`;
  $("[data-model]").textContent = s.model;
  $("[data-load]").textContent = s.loadSecs ? `${s.loadSecs.toFixed(1)} s` : "Loading…";
  $("[data-latency]").textContent = s.lastLatencyMs == null ? "None yet" : `Text ready ${s.lastLatencyMs} ms after you stopped`;
  $("[data-datadir]").textContent = s.dataDir;
  $("[data-reset]").hidden = s.isDefaultHotkey || recording;
  $("[data-speed]").disabled = s.status !== "ready" || speedRunning;
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

const MAX_SHOWN = 300;

function renderHistory() {
  const box = $("[data-history]");
  const query = $("[data-search]").value.trim().toLowerCase();
  const shown = query ? entries.filter((e) => e.text.toLowerCase().includes(query)) : entries;
  box.replaceChildren();

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

  let group = null, lastDay = null;
  shown.slice(0, MAX_SHOWN).forEach((e, i) => {
    const when = new Date(e.time);
    const day = when.toDateString();
    if (day !== lastDay) {
      lastDay = day;
      const label = document.createElement("div");
      label.className = "day";
      label.textContent = dayLabel(when);
      group = document.createElement("div");
      group.className = "entries";
      box.append(label, group);
    }
    group.append(entryRow(e, when, i));
  });
  if (shown.length > MAX_SHOWN) {
    const more = document.createElement("div");
    more.className = "more";
    more.textContent = `Showing the latest ${MAX_SHOWN}. Search to find older dictations.`;
    box.append(more);
  }
}

// A row: click anywhere (or the copy icon) to copy. Delete is behind the "More" icon or a
// right-click, so it always takes two steps and can't be hit instead of copy.
function entryRow(e, when, i) {
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
  $(".entry-text", row).textContent = e.text;
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
  const remove = () => {
    row.classList.add("removing");
    setTimeout(() => { entries = entries.filter((x) => x.time !== e.time); bridge.deleteEntry(e.time); }, 250);
    toast("Deleted");
  };
  const del = { label: "Delete", icon: "trash", danger: true, action: remove };

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

// A small menu at a point (or, with alignRight, ending at it).
function openMenu(x, y, items, alignRight = false) {
  const menu = $("[data-menu]");
  menu.replaceChildren(...items.map((item) => {
    const b = document.createElement("button");
    if (item.danger) b.className = "danger";
    b.innerHTML = `${svg(item.icon, 16)}<span>${esc(item.label)}</span>`;
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

// Navigation and wiring.

function showPage(name) {
  if (recording && name !== "settings") { bridge.cancelHotkey(); setRecording(false); }
  $$("[data-nav]").forEach((b) => b.classList.toggle("active", b.dataset.nav === name));
  $$("[data-page]").forEach((p) => p.classList.toggle("active", p.dataset.page === name));
  $("main").scrollTop = 0;
}

function wire() {
  $$("[data-nav]").forEach((b) => (b.onclick = () => showPage(b.dataset.nav)));
  let debounce;
  $("[data-search]").addEventListener("input", () => { clearTimeout(debounce); debounce = setTimeout(renderHistory, 120); });
  $("[data-search]").addEventListener("keydown", (e) => {
    if (e.key === "Escape") { e.target.value = ""; renderHistory(); e.target.blur(); }
  });
  document.addEventListener("keydown", (e) => {
    if (e.ctrlKey && e.key.toLowerCase() === "f") {
      e.preventDefault();
      showPage("home");
      $("[data-search]").focus();
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
  $("[data-folder]").onclick = () => bridge.openDataFolder();
  $("[data-repo]").onclick = () => bridge.openRepo();
  $("[data-greeting]").textContent = greeting();
  // The try-it box is one line and grows with what's dictated into it.
  const tryBox = $("[data-try]");
  tryBox.addEventListener("input", () => { tryBox.style.height = "auto"; tryBox.style.height = `${tryBox.scrollHeight}px`; });
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
  loadState();
  loadHistory();
}

// Outside Murmur (opened in a browser while designing), use sample data.
function sampleBridge() {
  const signal = () => ({ connect() {} });
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
    stateChanged: signal(), historyChanged: signal(), hotkeyRecorded: signal(), speedResult: signal(),
    state: (cb) => cb(JSON.stringify({
      hotkey: ["Right Ctrl"], hotkeyText: "Right Ctrl", isDefaultHotkey: true, status: "ready", statusText: "Ready",
      version: "0.3.0", model: "NVIDIA Parakeet TDT 0.6B v2 (int8)", loadSecs: 2.7, lastLatencyMs: 140,
      dataDir: "C:\\Users\\you\\.murmur",
    })),
    history: (cb) => cb(JSON.stringify({ entries: sample, stats: { words: 89, wpm: 152, dictations: 6, streak: 2 } })),
    copy() {}, deleteEntry() {}, recordHotkey() {}, cancelHotkey() {}, resetHotkey() {},
    speedTest() {}, openDataFolder() {}, openRepo() {},
  };
}

paintIcons();
wire();
if (window.qt && window.QWebChannel) new QWebChannel(qt.webChannelTransport, (ch) => connect(ch.objects.murmur));
else connect(sampleBridge());
