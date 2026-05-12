// ═══════════════════════════════════════════════════════════════════════════
// RAGNOZA — app.js  |  Core: config, state, init, theme, tabs, helpers
// ═══════════════════════════════════════════════════════════════════════════

// ─── CONFIG ───────────────────────────────────────────────────────────────────
const API_BASE = 'http://localhost:8000';

// ─── GLOBAL STATE ─────────────────────────────────────────────────────────────
let sessions         = JSON.parse(localStorage.getItem('ragnoza_sessions') || '[]');
let currentSessionId = null;
let messages         = [];
let isLoading        = false;
let isRecording      = false;
let mediaRecorder    = null;
let recordedChunks   = [];

// ─── INIT ─────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  renderHistory();
  updateSessionCount();

  if (sessions.length > 0) loadSession(sessions[0].id);
  else newChat();

  if (localStorage.getItem('ragnoza_theme') === 'dark') enableDark();

  document.getElementById('searchInput').addEventListener('input', e => {
    renderHistory(e.target.value);
  });

  document.getElementById('kbCollection')?.addEventListener('change', () => {
    loadKbStats();
    loadDocuments();
  });

  setTimeout(() => { loadKbStats(); loadDocuments(); }, 150);
});

// ─── THEME ────────────────────────────────────────────────────────────────────
document.getElementById('themeToggle').addEventListener('click', () => {
  const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
  if (isDark) {
    document.documentElement.removeAttribute('data-theme');
    document.getElementById('themeIcon').className = 'ti ti-moon';
    localStorage.setItem('ragnoza_theme', 'light');
  } else {
    enableDark();
  }
});

function enableDark() {
  document.documentElement.setAttribute('data-theme', 'dark');
  document.getElementById('themeIcon').className = 'ti ti-sun';
  localStorage.setItem('ragnoza_theme', 'dark');
}

// ─── TABS ─────────────────────────────────────────────────────────────────────
function switchTab(id, el) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  el.classList.add('active');
  document.getElementById('tab-' + id).classList.add('active');
  if (id === 'kb') { loadKbStats(); loadDocuments(); }
}

// ─── SESSION / HISTORY ────────────────────────────────────────────────────────
function newChat() {
  currentSessionId = 'sess_' + Date.now();
  messages = [];
  sessions.unshift({
    id: currentSessionId,
    title: 'Sesi Baru',
    time: new Date().toLocaleString('id-ID'),
    messages: []
  });
  saveSessions();
  renderHistory();
  updateSessionCount();
  const msgEl   = document.getElementById('messages');
  const inputEl = document.getElementById('chatInput');
  if (msgEl)   msgEl.innerHTML = '';
  if (inputEl) inputEl.value  = '';
  closeSourcePanel();
}

function loadSession(id) {
  const sess = sessions.find(s => s.id === id);
  if (!sess) return;
  currentSessionId = id;
  messages = sess.messages || [];
  renderAllMessages();
  renderHistory();
}

function renderHistory(filter = '') {
  const list       = document.getElementById('historyList');
  const today      = new Date(); today.setHours(0, 0, 0, 0);
  const yesterday  = new Date(today); yesterday.setDate(yesterday.getDate() - 1);
  const twoDaysAgo = new Date(today); twoDaysAgo.setDate(twoDaysAgo.getDate() - 2);

  const groups = { 'Hari Ini': [], 'Kemarin': [], '2 Hari Lalu': [], 'Lebih Lama': [] };

  sessions
    .filter(s => !filter || s.title.toLowerCase().includes(filter.toLowerCase()))
    .forEach(s => {
      const d = new Date(s.time); d.setHours(0, 0, 0, 0);
      if      (d >= today)      groups['Hari Ini'].push(s);
      else if (d >= yesterday)  groups['Kemarin'].push(s);
      else if (d >= twoDaysAgo) groups['2 Hari Lalu'].push(s);
      else                      groups['Lebih Lama'].push(s);
    });

  list.innerHTML = '';
  Object.entries(groups).forEach(([label, items]) => {
    if (!items.length) return;
    const lbl = document.createElement('div');
    lbl.className   = 'sidebar-label';
    lbl.textContent = label;
    list.appendChild(lbl);
    items.forEach(s => {
      const el      = document.createElement('div');
      el.className  = 'chat-item' + (s.id === currentSessionId ? ' active' : '');
      el.innerHTML  = `<i class="ti ti-message"></i><span>${escHtml(s.title)}</span>`;
      el.onclick    = () => loadSession(s.id);
      list.appendChild(el);
    });
  });
}

function saveSessions() {
  const sess = sessions.find(s => s.id === currentSessionId);
  if (sess) sess.messages = messages;
  localStorage.setItem('ragnoza_sessions', JSON.stringify(sessions.slice(0, 50)));
}

function updateSessionCount() {
  document.getElementById('sessionCount').textContent = sessions.length;
}

// ─── HELPERS ──────────────────────────────────────────────────────────────────
function handleKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
}

function autoResize(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 120) + 'px';
}

function scrollBottom() {
  const m = document.getElementById('messages');
  if (m) setTimeout(() => m.scrollTop = m.scrollHeight, 50);
}

function copyText(btn, text) {
  navigator.clipboard.writeText(text).then(() => {
    btn.innerHTML = '<i class="ti ti-check" style="color:var(--success)"></i>';
    setTimeout(() => btn.innerHTML = '<i class="ti ti-copy"></i>', 1500);
    showToast('Teks disalin!');
  });
}

function showToast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2200);
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function escJs(str) {
  return String(str)
    .replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/\n/g, '\\n');
}

function formatBytes(bytes) {
  if (bytes < 1024)         return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / 1024 / 1024).toFixed(1) + ' MB';
}