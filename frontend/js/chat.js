// ═══════════════════════════════════════════════════════════════════════════
// RAGNOZA — chat.js  |  Generate tab: messages, send, source panel, audio
// ═══════════════════════════════════════════════════════════════════════════

// ─── RENDER ALL MESSAGES (session restore) ────────────────────────────────────
function renderAllMessages() {
  const container = document.getElementById('messages');
  container.innerHTML = '';
  messages.forEach(m => {
    if (m.role === 'user') appendUserBubble(m.content);
    else appendBotBubble(m.content, m.sources, m.time, false);
  });
  scrollBottom();
}

// ─── TYPING INDICATOR ─────────────────────────────────────────────────────────
function appendTyping() {
  const el = document.createElement('div');
  el.id = 'typing-indicator';
  el.className = 'msg-bot';
  el.innerHTML = `
    <div class="bot-avatar"><i class="ti ti-scale"></i></div>
    <div class="bot-content">
      <div class="bot-name">AI Ragnoza Assistant</div>
      <div class="bot-bubble">
        <div class="typing-dots">
          <div class="dot"></div><div class="dot"></div><div class="dot"></div>
        </div>
      </div>
    </div>`;
  document.getElementById('messages').appendChild(el);
  scrollBottom();
}

function removeTyping() {
  document.getElementById('typing-indicator')?.remove();
}

// ─── BUBBLES ──────────────────────────────────────────────────────────────────
function appendUserBubble(text) {
  const now = new Date().toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' });
  const el = document.createElement('div');
  el.className = 'msg-user';
  el.innerHTML = `
    <div class="msg-user-inner">
      <div class="msg-user-bubble">${escHtml(text)}</div>
      <div class="msg-meta">${now} <i class="ti ti-user" style="font-size:11px"></i></div>
    </div>`;
  document.getElementById('messages').appendChild(el);
  scrollBottom();
}

function appendBotBubble(answer, sources, time, animate = true) {
  const now = time || new Date().toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' });
  const el = document.createElement('div');
  el.className = 'msg-bot';

  let refsHtml = '';
  if (sources && sources.length > 0) {
    const rows = sources.map(src => {
      const pct = Math.round((src.score || 0) * 100);
      const srcJson = escHtml(JSON.stringify(src));
      return `
        <div class="ref-row" onclick="openSourcePanel('${srcJson}')">
          <span>${escHtml(src.pasal || src.chunk_id?.slice(0, 8) || '-')}</span>
          <span class="ref-link">${escHtml(src.bab || src.source || '-')}</span>
          <div class="score-bar">
            <div class="bar-track"><div class="bar-fill" style="width:${pct}%"></div></div>
            <span class="score-num">${(src.score || 0).toFixed(2)}</span>
          </div>
        </div>`;
    }).join('');

    refsHtml = `
      <div class="ref-table">
        <div class="ref-head"><i class="ti ti-file-text"></i> Referensi (Sumber)</div>
        <div class="ref-cols">
          <span>Pasal / Bab</span><span>Konteks</span><span>Similarity</span>
        </div>
        ${rows}
      </div>`;
  }

  el.innerHTML = `
    <div class="bot-avatar"><i class="ti ti-scale"></i></div>
    <div class="bot-content">
      <div class="bot-name">AI Ragnoza Assistant · ${now}</div>
      <div class="bot-bubble">
        <div class="bot-answer">${formatAnswer(answer)}</div>
        ${refsHtml}
        <div class="bot-actions">
          <button onclick="copyText(this, '${escJs(answer)}')" title="Salin">
            <i class="ti ti-copy"></i>
          </button>
          <button onclick="this.style.color='var(--primary)'" title="Suka">
            <i class="ti ti-thumb-up"></i>
          </button>
          <button onclick="this.style.color='var(--danger)'" title="Tidak Suka">
            <i class="ti ti-thumb-down"></i>
          </button>
        </div>
      </div>
    </div>`;
  document.getElementById('messages').appendChild(el);
  scrollBottom();
}

function formatAnswer(text) {
  text = escHtml(text);
  text = text.replace(/&quot;([^&]+)&quot;/g, '<span class="bot-quote">"$1"</span>');
  text = text.replace(/\n/g, '<br>');
  return text;
}

// ─── SEND MESSAGE ─────────────────────────────────────────────────────────────
async function sendMessage(overrideText) {
  const input = document.getElementById('chatInput');
  const prompt = overrideText || input.value.trim();
  if (!prompt || isLoading) return;

  isLoading = true;
  const sendBtn = document.getElementById('sendBtn');
  sendBtn.disabled = true;
  input.value = '';
  autoResize(input);

  const collection = document.getElementById('collectionSelect').value;
  const time = new Date().toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' });

  // Update session title jika masih default
  const sess = sessions.find(s => s.id === currentSessionId);
  if (sess && (sess.title === 'Sesi Baru' || !sess.title)) {
    sess.title = prompt.slice(0, 40);
  }

  messages.push({ role: 'user', content: prompt, time });
  appendUserBubble(prompt);
  appendTyping();
  renderHistory();

  try {
    const res = await fetch(`${API_BASE}/rag/ask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt, collection_name: collection })
    });

    if (!res.ok) throw new Error(`Server error: ${res.status}`);
    const data = await res.json();

    removeTyping();
    const answerTime = new Date().toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' });
    const answer  = data.answer || data.result || data.response || JSON.stringify(data);
    const sources = data.sources || data.contexts || [];

    messages.push({ role: 'assistant', content: answer, sources, time: answerTime });
    appendBotBubble(answer, sources, answerTime);
    saveSessions();
    if (sources.length > 0) openSourcePanel(sources[0]);

  } catch (err) {
    removeTyping();
    const errEl = document.createElement('div');
    errEl.className = 'msg-bot';
    errEl.innerHTML = `
      <div class="bot-avatar"><i class="ti ti-scale"></i></div>
      <div class="bot-content">
        <div class="error-bubble">
          <i class="ti ti-alert-circle"></i> Gagal: ${escHtml(err.message)}
        </div>
      </div>`;
    document.getElementById('messages').appendChild(errEl);
    scrollBottom();
  } finally {
    isLoading = false;
    sendBtn.disabled = false;
  }
}

// ─── CLEAR CHAT ───────────────────────────────────────────────────────────────
function clearChat() {
  messages = [];
  document.getElementById('messages').innerHTML = '';
  const sess = sessions.find(s => s.id === currentSessionId);
  if (sess) sess.messages = [];
  saveSessions();
  closeSourcePanel();
  showToast('Chat dikosongkan!');
}

// ─── SOURCE PANEL ─────────────────────────────────────────────────────────────
function openSourcePanel(src) {
  if (typeof src === 'string') {
    try { src = JSON.parse(src); } catch (e) { return; }
  }
  document.getElementById('sourcePanel').classList.remove('hidden');

  document.getElementById('sp-title').textContent =
    src.pasal || src.chunk_id?.slice(0, 10) || 'Sumber';
  document.getElementById('sp-bab').textContent =
    src.bab || src.source || '-';

  const score = src.score || 0;
  document.getElementById('sp-score').textContent = score.toFixed(2);
  document.getElementById('sp-bar').style.width = (score * 100) + '%';

  document.getElementById('sp-context').innerHTML = `
    <p style="font-weight:600;margin-bottom:4px">${escHtml(src.pasal || '-')}</p>
    <p>${escHtml(src.text || src.content || src.konteks || '-')}</p>`;

  const meta = src.metadata || {};
  document.getElementById('sp-meta').innerHTML = [
    ['Pasal',      src.pasal      || meta.pasal      || '-'],
    ['Bab',        src.bab        || meta.bab        || '-'],
    ['Halaman',    src.halaman    || meta.halaman    || '-'],
    ['Sumber',     src.source     || meta.source     || 'article_UUD45'],
    ['Chunk ID',   (src.chunk_id  || meta.chunk_id   || '-').slice(0, 12) + '...'],
    ['Tgl Upload', meta.upload_date || meta.tanggal  || '-'],
  ].map(([k, v]) => `<tr><td>${k}</td><td>${escHtml(String(v))}</td></tr>`).join('');
}

function closeSourcePanel() {
  document.getElementById('sourcePanel').classList.add('hidden');
}

// ─── AUDIO ────────────────────────────────────────────────────────────────────
function uploadAudio() {
  document.getElementById('audioFile').click();
}

async function handleAudioFile(e) {
  const file = e.target.files[0];
  if (!file) return;
  showToast('Mengunggah audio...');
  const form = new FormData();
  form.append('file', file);
  try {
    const res  = await fetch(`${API_BASE}/api/v1/prompting/audio/process`, { method: 'POST', body: form });
    const data = await res.json();
    const text = data.text || data.transcript || '';
    if (text) {
      const input = document.getElementById('chatInput');
      input.value = text;
      autoResize(input);
      showToast('Transkripsi berhasil!');
    }
  } catch {
    showToast('Gagal mengunggah audio');
  }
  e.target.value = '';
}

async function toggleRecord() {
  if (!isRecording) {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaRecorder  = new MediaRecorder(stream);
      recordedChunks = [];
      mediaRecorder.ondataavailable = e => recordedChunks.push(e.data);
      mediaRecorder.onstop = sendRecording;
      mediaRecorder.start();
      isRecording = true;
      document.getElementById('recordBtn').classList.add('recording');
      document.getElementById('recordIcon').className = 'ti ti-player-stop-filled';
      document.getElementById('recordLabel').textContent = 'Stop Recording';
    } catch {
      showToast('Izin mikrofon ditolak');
    }
  } else {
    mediaRecorder.stop();
    mediaRecorder.stream.getTracks().forEach(t => t.stop());
    isRecording = false;
    document.getElementById('recordBtn').classList.remove('recording');
    document.getElementById('recordIcon').className = 'ti ti-microphone';
    document.getElementById('recordLabel').textContent = 'Record Audio';
  }
}

async function sendRecording() {
  const blob = new Blob(recordedChunks, { type: 'audio/webm' });
  const form = new FormData();
  form.append('file', blob, 'recording.webm');
  showToast('Memproses rekaman...');
  try {
    const res  = await fetch(`${API_BASE}/api/v1/prompting/audio/process`, { method: 'POST', body: form });
    const data = await res.json();
    const text = data.text || data.transcript || '';
    if (text) {
      const input = document.getElementById('chatInput');
      input.value = text;
      autoResize(input);
      showToast('Transkripsi berhasil!');
    }
  } catch {
    showToast('Gagal memproses rekaman');
  }
}