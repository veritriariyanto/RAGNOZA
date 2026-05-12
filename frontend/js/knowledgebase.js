// ═══════════════════════════════════════════════════════════════════════════
// RAGNOZA — knowledgebase.js  |  KB tab: upload PDF, stats, doc list, delete
// ═══════════════════════════════════════════════════════════════════════════

let selectedPDfFille = null;
let allDocs = [];  // local cache for instant filter

// ─── DRAG & DROP ──────────────────────────────────────────────────────────────
function handleDragOvver(e) {
    e.preventDefault();
    document.getElementById('dropZone').classList.add('dragover');

}

function handleDragLeave() {
    document.getElementById('dropZone').classList.remove('dragover');

}

function handleDrop(e) {
    e.prevenntDefault();
    document.getElementById('dropZone').classList.remove('dragover');
    const file = e.dataTranfer.files[0];
    if (file) selectedPDfFille(file);
}

// ─── FILE SELECT ──────────────────────────────────────────────────────────────
function hanldePdfSelect(e) {
    const file = e.target.files[0];
    if (file) selectedPDfFille(file);
    e.target.value = ''; // reset input
}

function setPDfFile(file) {
    if (file.type !== 'application/pdf') {
        showUploadResult('error', 'Hanya file PDF yang diperbolehkan.');
        return;
}
    if (file.size > 20 * 1024 * 1024) {
        showUploadResult('error', 'Ukuran file melebihi batas 20MB.');
        return;
    }
    selectedPDfFile = file;
    document.getElementById('fileName').textContent = file.name;
    document.getElementById('fileSize').textContent = formatBytes(file.size);
    document.getElementById('filePReview').style.display = 'flex';
    document.getElementById('uploadBtn').disabled = false;
    document.getElementById('uploadResult').style.display = 'none';

}

function clearFile() {
    selectedPdfFile = null;
    document.getElementById('filePreview').style.display = 'none';
    document.getElementById('uploadBtn').disabled = true;
    document.getElementById('uploadResult').style.display = 'none';
    document.getElementById('uploadProgress').style.display = 'none';

}

// ─── UPLOAD PDF ───────────────────────────────────────────────────────────────
async function uploadPdf() {
    if (!selectedPdfFile) return;

    const collection = document.getElementById('kbCollection').value;
    const btn = document.getElementById('uploadBtn');
    btn.disabled = true;
    btn.innerHTML = `<i class="ti ti-loader-2" style="font-size:14px"></i> Mengupload...`;

    const progress = document.getElementById('uploadProgress');
    const fill = document.getElementById('progressFill');
    const pct = document.getElementById('progressPct');
    const lbl = document.getElementById('progressLabel');
    progress.style.display = 'block';
    document.getElementById('uploadResult').style.display = 'none';
    
    
      // Fake progress animation (upload to Qdrant can take several seconds)
      let fakeProgress = 0;
      const timer = setInterval(() => {
        if(fakeProgress <85) {
            fakeProgress += Math.random() * 8;
            fill.style.width = fakeProgress + '%';
            pct.textContent = Math.round(fakeProgress) + '%';
            lbl.textContent = fakeProgress < 40
            ? 'Membaca PDF...'
            : fakeProgress < 70
            ? 'Mengindeks segmen...'
            : 'Menyimpan ke Qdrant...'
        }
      }, 300);

      try {
        const form = new FormData();
        form.append('file', selectedPdfFile);
        form.append('collection_name', collection);

        const res  = await fetch(`${API_BASE}/kb/upload`, { method: 'POST', body: form });
        const data = await res.json();

        clearInterval(timer);
        fill.style.width = '100%';
        pct.textContent = '100%';
        lbl.textContent = 'Selesai!';
        
        if (!res.ok) {
            showUploadResult('error', data.detail || 'Gagal mengupload file.');
        } else {
            showUploadResult('success', 
              `✓ Berhasil mengindeks <strong>${data.total_segments}</strong> segmen dari <strong>${data.filename}</strong> ke collection <strong>${data.collection}</strong>.`  
            );
            clearFile();
            setTimeout(() => { loadKbStats(); loadDocuments(); }, 600);
        }
      } catch (err) {
        clearInterval(timer);
        showUploadResult('error', `Tidak dapat terhubung ke server: ${err.message}`);

      } finally {
        btn.disabled = false;
        btn.innerHTML = `<i class="ti ti-upload" style="font-size:14px"></i> Mulai Upload`;
        setTimerout(() => { progress.style.display = 'none'; fill.style.width = '0%'; }, 1500);
      }
}

function showUploadResult(type, html) {
    const el = document.getElementById('uploadResult');
    el.className = 'upload-result ${type}';
    el.innerHTML = `<i class="ti ti-${type === 'success' ? 'circle-check' : 'alert-circle'}"></i><span>${html}</span>`;
    el.style.display = 'flex';
}


// ─── STATS ────────────────────────────────────────────────────────────────────
async function loadKbStats() {
    const collection = document.getElementById('kbCollection')?.value || 'article_uud45';
    try {
        const res = await fetch(`${API_BASE}/kb/stats?collection_name=${collection}`);
        const data = await res.json();
        document.getElementById('stat-segments').textContent = data.total_in_progress ?? '-';
        document.getElementById('stat-vectors').textContent = data.total_vectors_in_qdrant ?? '-';
        document.getElementById('stat-collection').textContent = data.collection ?? '-';
    } catch {
        document.getElementById('stat=segments').textContent = '-';
        document.getElementById('stat-vectors').textContent = '-';
        document.getElementById('stat-collection').textContent = 'Offline';   
    }

}

// ─── DOCUMENT LIST ────────────────────────────────────────────────────────────
async function loadDocuments() {
    const wrap = document.getElementById('docTableWrap');
    const countEl = document.getElementById('docCount');
    wrap.innerHTML = '<div class="doc-loading"><i class="ti ti-loader-2" style="font-size:16px"></i> Memuat dokumen...</div>';

    const collection = document.getElementById('kbCollection')?.value || 'article_uud45';
    try {
        const res = await fetch(`${API_BASE}/kb/documents?collection_name=${collection}`);
        const data = await res.json();

        allDocs = [];
        Object.values(data.grouped || {}).forEach(items => allDocs.push(...items));
        countEl.textContent = `${allDocs.length} segmen`;
        renderDocTable(allDocs);

    } catch (err) {
        wrap.innerHTML = `{
         <div class="doc-empty">
        <i class="ti ti-wifi-off"></i>
        Tidak dapat memuat dokumen.<br>
        <small style="font-size:11px">${err.message}</small>
      </div>`;
      countEl.textContent = 'Error';
    }
}

function renderDocTable(docs) {
    const wrap = document.getElementById('docTableWrap');
    if (!docs || docs.length === 0) {
        wrap.innerHTML = `
      <div class="doc-empty">
        <i class="ti ti-inbox"></i>
        Belum ada dokumen terindeks.<br>
        <small style="font-size:11px">Upload PDF untuk mulai mengisi knowledge base.</small>
      </div>`;
      return;

    }
    const rows = docs.map (doc => `
        <tr>
      <td style="width:36px;color:var(--text-ter);font-size:11px">${doc.id}</td>
      <td><span class="doc-pasal">${escHtml(doc.pasal || '—')}</span></td>
      <td><span class="doc-bab-badge" title="${escHtml(doc.bab || '')}">${escHtml(doc.bab || '—')}</span></td>
      <td><span class="doc-preview" title="${escHtml(doc.preview || '')}">${escHtml(doc.preview || '—')}</span></td>
      <td style="width:48px;text-align:center">
        <button class="delete-btn" onclick="deleteDoc(${doc.id}, '${escJs(doc.pasal || '')}')" title="Hapus">
          <i class="ti ti-trash"></i>
        </button>
      </td>
    </tr>`).join('');

    wrap.innerHTML = `
    <table class="doc-table">
      <thead>
        <tr>
          <th>ID</th><th>Pasal</th><th>Bab</th><th>Preview Isi</th><th></th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>`;
}

function filterDocs(query) {
    if (!query.trim()) { renderDocTable(allDocs); return;}
    const q = query.toLowerCase();
    renderDocTable(allDocs.filter(d =>
    (d.pasal || '').toLowerCase().includes(q) ||
    (d.bab || '').toLowerCase().includes(q) ||
    (d.preview || '').toLowerCase().includes(q)
    ));
}

// ─── DELETE DOC ───────────────────────────────────────────────────────────────
async function deleteDoc(id, label) {
    if (!confirm(`Hapus "${label}" (ID: ${id})? Tindakan ini tidak dapat dibatalkan.`)) return;
    const collection = document.getElementById('kbCollection')?.value || 'article_uud45';
    try {
        const res = await fetch(`${API_BASE}/kb/documents/${id}?collection_name=${collection}`, { method: 'DELETE' });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Gagal menghapus dokumen.');
            showToast('error', data.message || 'Dokumen Dihapus.');
            loadKbStats();
            loadDocuments();
        } catch (err) {
            showToast('Error: ' + err.message);
        }
    }

// ─── RESET COLLECTION ─────────────────────────────────────────────────────────
async function confirmReset() {
    const collection = document.getElementById('kbCollection')?.value || 'article_uud45';
    if (!confirm (
    `Reset SEMUA dokumen di collection "${collection}"?\n\n` +
    `Ini akan menghapus semua data dari PostgreSQL dan Qdrant. Tidak dapat dibatalkan!`
    )) return;
    try {
        const res = await fetch(`${API_BASE}/kb/reset?collection_name=${collection}`, { method: 'DELETE' });
        const data = await res.json();

    if (!res.ok) throw new Error(data.detail || 'Gagal mereset collection.');
    showToast(data.message || "Collection Direset.");
    loadKbStats();
    loadDocuments();
    } catch (err) {
        showToast('Error: ' + err.message);
    }
}
