# streamlit_app/components/knowledgebase_tab.py
"""
Dashboard Knowledge Base:
 - Tab 1 : Monitoring  — daftar KB + statistik koleksi
 - Tab 2 : Upload PDF  — cleaning preview (before/after) + chunking preview (parent/child)
"""

import re

import streamlit as st

from api.knowledge.knowledge_api import (
    get_knowledgebase_list,
    upload_and_clean,
    upload_and_clean_multi,
    process_and_chunk,
    process_and_chunk_multi,
    delete_knowledgebase,
    get_knowledgebase_preview,
    get_kb_monitor_data,
    search_similarity,
)

# ── CSS khusus KB tab ──────────────────────────────────────────────────────────
_KB_CSS = """
<style>
/* ── Before / After cards ── */
.ba-card {
    background: var(--surface-2);
    border: 1px solid var(--border-soft);
    border-radius: 10px;
    padding: 14px 16px;
    margin-bottom: 10px;
    font-family: 'DM Sans', sans-serif;
}
.ba-label {
    font-size: 10px;
    font-weight: 700;
    letter-spacing: .1em;
    text-transform: uppercase;
    margin-bottom: 8px;
}
.ba-label-before { color: var(--orange); }
.ba-label-after  { color: var(--green);  }
.ba-text {
    font-size: 12.5px;
    color: var(--text-secondary);
    line-height: 1.7;
    white-space: pre-wrap;
    word-break: break-word;
    max-height: 200px;
    overflow-y: auto;
    background: var(--surface-1);
    border-radius: 6px;
    padding: 10px 12px;
    border: 1px solid var(--border-soft);
}

/* ── Chunk cards ── */
.chunk-parent {
    background: rgba(212,168,83,0.08);
    border: 1px solid rgba(212,168,83,0.28);
    border-radius: 10px;
    padding: 12px 14px;
    margin-bottom: 8px;
    font-family: 'DM Sans', sans-serif;
}
.chunk-child {
    background: var(--surface-2);
    border: 1px solid var(--border-soft);
    border-left: 3px solid rgba(93,190,138,0.5);
    border-radius: 0 8px 8px 0;
    padding: 10px 14px;
    margin-bottom: 6px;
    margin-left: 16px;
    font-family: 'DM Sans', sans-serif;
}
.chunk-id {
    font-size: 10px;
    font-weight: 700;
    letter-spacing: .06em;
    text-transform: uppercase;
    margin-bottom: 4px;
}
.chunk-id-parent { color: var(--gold-dim); }
.chunk-id-child  { color: var(--green); }
.chunk-section {
    display: inline-block;
    font-size: 10px;
    font-weight: 600;
    padding: 1px 8px;
    border-radius: 4px;
    margin-bottom: 6px;
    background: rgba(255,255,255,0.06);
    color: var(--text-muted);
}
.chunk-text {
    font-size: 12.5px;
    color: var(--text-secondary);
    line-height: 1.65;
    white-space: pre-wrap;
    word-break: break-word;
}
.chunk-title {
    font-size: 13px;
    font-weight: 600;
    color: var(--text-primary);
    margin-bottom: 4px;
}

/* ── KB stat card ── */
.kb-stat-card {
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 14px 16px;
    text-align: center;
}
.kb-stat-value {
    font-family: 'DM Serif Display', serif;
    font-size: 1.8rem;
    color: var(--text-primary);
    line-height: 1.1;
}
.kb-stat-label {
    font-size: 10px;
    font-weight: 700;
    letter-spacing: .08em;
    text-transform: uppercase;
    color: var(--text-muted);
    margin-top: 4px;
}

/* ── Step badge ── */
.step-badge {
    display: inline-block;
    background: var(--gold-glow);
    border: 1px solid rgba(212,168,83,.35);
    color: var(--gold-light);
    border-radius: 6px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: .05em;
    margin-bottom: 10px;
}

/* ── Similarity cards ── */
.sim-card {
    background: var(--surface-2);
    border: 1px solid var(--border-soft);
    border-radius: 10px;
    padding: 16px;
    margin-bottom: 12px;
    font-family: 'DM Sans', sans-serif;
}
.sim-score-badge {
    float: right;
    background: rgba(93,190,138,0.12);
    border: 1px solid rgba(93,190,138,0.3);
    color: var(--green);
    font-size: 11px;
    font-weight: 700;
    padding: 2px 8px;
    border-radius: 6px;
}
.sim-meta {
    font-size: 11px;
    color: var(--text-muted);
    margin-bottom: 8px;
}
.sim-label {
    font-size: 10px;
    font-weight: 700;
    letter-spacing: .06em;
    text-transform: uppercase;
    margin-top: 8px;
    margin-bottom: 4px;
}
.sim-label-parent { color: var(--gold-dim); }
.sim-label-child  { color: var(--green); }
.sim-divider {
    border-top: 1px dashed var(--border-soft);
    margin: 10px 0;
}

/* ── Repair Stats panel ── */
.repair-panel {
    background: rgba(93,190,138,0.05);
    border: 1px solid rgba(93,190,138,0.22);
    border-radius: 10px;
    padding: 14px 16px;
    margin-bottom: 10px;
    font-family: 'DM Sans', sans-serif;
}
.repair-panel-none {
    background: rgba(255,255,255,0.03);
    border: 1px dashed rgba(255,255,255,0.10);
    border-radius: 10px;
    padding: 10px 16px;
    margin-bottom: 10px;
    font-family: 'DM Sans', sans-serif;
    display: flex;
    align-items: center;
    gap: 8px;
}
.repair-title {
    font-size: 10px;
    font-weight: 700;
    letter-spacing: .1em;
    text-transform: uppercase;
    color: var(--green);
    margin-bottom: 10px;
}
.repair-total-badge {
    display: inline-block;
    background: rgba(93,190,138,0.15);
    border: 1px solid rgba(93,190,138,0.35);
    color: var(--green);
    font-size: 11px;
    font-weight: 700;
    padding: 2px 10px;
    border-radius: 6px;
    margin-left: 8px;
    vertical-align: middle;
}
.repair-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 8px;
    margin-top: 8px;
}
.repair-item {
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 8px;
    padding: 8px 10px;
    text-align: center;
}
.repair-item-value {
    font-family: 'DM Serif Display', serif;
    font-size: 1.4rem;
    color: var(--green);
    line-height: 1.1;
}
.repair-item-zero {
    color: var(--text-muted) !important;
}
.repair-item-label {
    font-size: 9.5px;
    font-weight: 600;
    letter-spacing: .06em;
    text-transform: uppercase;
    color: var(--text-muted);
    margin-top: 3px;
}
.repair-item-icon {
    font-size: 14px;
    margin-bottom: 2px;
}
</style>
"""


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _card_stat(value, label: str, color: str = "var(--text-primary)"):
    return (
        f'<div class="kb-stat-card">'
        f'<div class="kb-stat-value" style="color:{color};">{value}</div>'
        f'<div class="kb-stat-label">{label}</div>'
        f'</div>'
    )


def _render_before_after(raw_snippet: str, clean_snippet: str):
    """Render side-by-side before/after teks cleaning."""
    col_b, col_a = st.columns(2)
    with col_b:
        st.markdown(
            '<div class="ba-card">'
            '<div class="ba-label ba-label-before">⚠ Before — Teks Mentah (PDF)</div>'
            '<div class="ba-text">' + _esc(raw_snippet) + '</div>'
            '</div>',
            unsafe_allow_html=True,
        )
    with col_a:
        st.markdown(
            '<div class="ba-card">'
            '<div class="ba-label ba-label-after">✓ After — Teks Bersih</div>'
            '<div class="ba-text">' + _esc(clean_snippet) + '</div>'
            '</div>',
            unsafe_allow_html=True,
        )


def _extract_pasal_from_query(query: str):
    """
    Deteksi otomatis nomor pasal dari teks query bebas (mis. 'Tolong bedah
    Pasal 5' -> '5'), supaya tab similarity test merepresentasikan perilaku
    pipeline integrasi (yang otomatis ekstrak pasal_number lewat
    repair_legal_text) alih-alih murni semantic search yang bisa kalah saing
    dari pasal lain untuk query panjang/multi-topik.

    Return (pasal_number, all_matches):
      - Tepat 1 nomor pasal terdeteksi -> pasal_number diisi, dipakai sebagai filter.
      - 0 atau >1 nomor pasal terdeteksi -> pasal_number None (ragu/ambigu — mis.
        query menyebut beberapa pasal sekaligus). TIDAK dipaksakan jadi filter
        supaya tidak diam-diam salah pilih salah satunya; tetap fokus ke
        similarity semantik murni. all_matches tetap dikembalikan untuk
        keperluan pesan info di UI.
    """
    matches = re.findall(r"pasal\s+(\d+)", query, re.IGNORECASE)
    pasal_number = matches[0] if len(matches) == 1 else None
    return pasal_number, matches


# Pola "kalimat ajaib" — kalau muncul di query, anggap user sendiri ragu dengan
# nomor pasal yang ia sebutkan, jadi filter pasal otomatis TIDAK dipaksakan
# meski cuma 1 nomor pasal yang terdeteksi.
_DOUBT_PATTERN = re.compile(
    r"\b(ragu|kurang\s*yakin|tidak\s*yakin|ga\s*yakin|nggak\s*yakin|gak\s*yakin|"
    r"mungkin\s*salah|entah\s*pasal|lupa\s*pasal|tidak\s*ingat\s*pasal)\b",
    re.IGNORECASE,
)


def _has_doubt_phrase(query: str) -> bool:
    """Deteksi kalimat ajaib yang menandakan user ragu dengan pasal yang ia sebutkan."""
    return bool(_DOUBT_PATTERN.search(query))


def _esc(text: str) -> str:
    """Escape HTML special chars."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _render_repair_stats(repair_stats: dict):
    """Render panel statistik text repair — tampilkan jika ada perbaikan, badge kecil jika tidak."""
    if not repair_stats:
        return

    was_repaired = repair_stats.get("was_repaired", False)
    total        = repair_stats.get("total_fixes", 0)
    hyph         = repair_stats.get("hyphenation_fixes", 0)
    ocr          = repair_stats.get("ocr_noise_fixes", 0)
    brkn         = repair_stats.get("broken_sentence_fixes", 0)

    if not was_repaired:
        st.markdown(
            '<div class="repair-panel-none">'
            '<span style="font-size:15px;">✔️</span>'
            '<span style="font-size:11px;color:var(--text-muted);">'
            '<b style="color:var(--text-secondary);">Text Repair</b>'
            ' — Tidak ada artefak yang perlu diperbaiki pada dokumen ini.'
            '</span>'
            '</div>',
            unsafe_allow_html=True,
        )
        return

    items = [
        ("✂️", str(hyph), "Hyphenation",       "Suku kata terpotong"),
        ("🔧", str(ocr),  "OCR Noise",          "Karakter noise / placeholder"),
        ("📎", str(brkn), "Broken Sentences",   "Kalimat terpecah baris"),
    ]

    def _item_html(icon: str, val: str, label: str) -> str:
        extra_cls = " repair-item-zero" if int(val) == 0 else ""
        return (
            '<div class="repair-item">'
            '<div class="repair-item-icon">' + icon + '</div>'
            '<div class="repair-item-value' + extra_cls + '">' + val + '</div>'
            '<div class="repair-item-label">' + label + '</div>'
            '</div>'
        )

    items_html = "".join(_item_html(icon, val, label) for icon, val, label, _ in items)

    st.markdown(
        '<div class="repair-panel">'
        '<div class="repair-title">🔨 Text Repair Dilakukan'
        f'<span class="repair-total-badge">{total} perbaikan</span>'
        '</div>'
        f'<div class="repair-grid">{items_html}</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    # Tooltip detail per kategori
    with st.expander("📋 Detail repair per kategori", expanded=False):
        for icon, val, label, desc in items:
            st.markdown(
                f"**{icon} {label}** — `{val}` perbaikan  "
                f"<small style='color:var(--text-muted);'>({desc})</small>",
                unsafe_allow_html=True,
            )


def _render_chunk_card(chunk: dict):
    ctype = chunk.get("type", "child")
    cid   = chunk.get("chunk_id", "")
    sec   = chunk.get("section", "")
    title = chunk.get("title", "")
    text  = chunk.get("text", "")
    pid   = chunk.get("parent_id", "")

    # potong text preview max 300 char
    preview = text[:300] + ("…" if len(text) > 300 else "")

    if ctype == "parent":
        # Bangun title_html di luar f-string untuk menghindari backslash Python <3.12
        title_html = ('<div class="chunk-title">' + _esc(title) + "</div>") if title else ""
        st.markdown(
            '<div class="chunk-parent">'
            + '<div class="chunk-id chunk-id-parent">\U0001F4E6 ' + _esc(cid) + '</div>'
            + '<span class="chunk-section">' + _esc(sec) + '</span>'
            + title_html
            + '<div class="chunk-text">' + _esc(preview) + '</div>'
            + '</div>',
            unsafe_allow_html=True,
        )
    else:
        parent_info = ('<div style="font-size:10px;color:var(--text-muted);margin-bottom:4px;">' + '\u21b3 parent: ' + _esc(pid) + '</div>') if pid else ""
        st.markdown(
            '<div class="chunk-child">'
            + '<div class="chunk-id chunk-id-child">\U0001F517 ' + _esc(cid) + '</div>'
            + parent_info
            + '<span class="chunk-section">' + _esc(sec) + '</span>'
            + '<div class="chunk-text" style="margin-top:4px;">' + _esc(preview) + '</div>'
            + '</div>',
            unsafe_allow_html=True,
        )


# ─────────────────────────────────────────────────────────────────────────────
# TAB: MONITORING
# ─────────────────────────────────────────────────────────────────────────────

def _tab_monitoring():
    # Banner peringatan jika model embedding pernah diganti
    st.info(
        "ℹ️ **Model Embedding Aktif:** `paraphrase-multilingual-MiniLM-L12-v2` (Multilingual)  \n"
        "Jika KB ini di-index dengan model lama (`all-MiniLM-L6-v2`), hasil pencarian tidak akan relevan. "
        "**Hapus dan re-ingest KB** tersebut via tab *Upload & Proses*."
    )
    st.markdown('<div class="diff-bar"></div>', unsafe_allow_html=True)

    # ── Pilih KB ──────────────────────────────────────────────────────────────
    kb_list = get_knowledgebase_list()

    if not kb_list:
        st.markdown(
            '<div style="text-align:center;padding:40px 0;">'
            '<div style="font-size:32px;opacity:.3;margin-bottom:8px;">📭</div>'
            '<div style="font-size:13px;color:var(--text-muted);">Belum ada Knowledge Base tersedia.<br>'
            'Upload PDF di tab <b style="color:var(--gold-dim);">Upload &amp; Proses</b> untuk memulai.</div>'
            '</div>',
            unsafe_allow_html=True,
        )
        return

    col_sel, col_ref = st.columns([5, 1], vertical_alignment="bottom")
    with col_sel:
        st.markdown('<div class="ac-label">Pilih Knowledge Base</div>', unsafe_allow_html=True)
        selected_kb = st.selectbox(
            "KB", kb_list, label_visibility="collapsed", key="kb_monitor_select"
        )
    with col_ref:
        if st.button("🔄", use_container_width=True, key="btn_refresh_monitor", help="Refresh"):
            st.rerun()

    if not selected_kb:
        return

    # ── Slider jumlah cuplikan ────────────────────────────────────────────────
    limit_preview = st.slider("Jumlah cuplikan per koleksi", 2, 20, 5, key="kb_monitor_limit_preview")

    # ── Satu request ke endpoint /monitor ────────────────────────────────────
    with st.spinner("Mengambil data monitoring dari Qdrant..."):
        mon = get_kb_monitor_data(selected_kb, preview_limit=limit_preview)

    if not mon.get("success"):
        st.error(f"❌ Gagal mengambil data: {mon.get('error')}")
        return

    d = mon["data"]
    status      = d.get("status", "unknown")
    p_col       = d.get("parent_collection", f"{selected_kb}_parent")
    c_col       = d.get("child_collection",  f"{selected_kb}_child")
    p_count     = d.get("parent_count", 0)
    c_count     = d.get("child_count",  0)
    p_preview   = d.get("parent_preview", [])
    c_preview   = d.get("child_preview",  [])
    errors      = d.get("errors", [])

    st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)

    # ── Dua kolom koleksi Qdrant ──────────────────────────────────────────────
    col_p, col_c = st.columns(2)

    with col_p:
        st.markdown(
            '<div style="border:1px solid rgba(212,168,83,0.3);border-radius:10px;padding:16px;background:rgba(212,168,83,0.04);">'
            '<h4 style="margin:0 0 8px 0;color:var(--gold-light);font-size:14px;">📦 Parent Collection</h4>'
            '<code style="font-size:11px;color:var(--text-muted);">' + p_col + '</code>'
            '<div style="margin-top:12px;">' + _card_stat(p_count, "Point Count", "var(--gold-light)") + '</div>'
            '</div>',
            unsafe_allow_html=True,
        )

    with col_c:
        st.markdown(
            '<div style="border:1px solid rgba(93,190,138,0.3);border-radius:10px;padding:16px;background:rgba(93,190,138,0.04);">'
            '<h4 style="margin:0 0 8px 0;color:var(--green);font-size:14px;">🔗 Child Collection</h4>'
            '<code style="font-size:11px;color:var(--text-muted);">' + c_col + '</code>'
            '<div style="margin-top:12px;">' + _card_stat(c_count, "Point Count", "var(--green)") + '</div>'
            '</div>',
            unsafe_allow_html=True,
        )

    if errors:
        for err in errors:
            st.warning(f"⚠️ {err}")

    st.markdown('<div class="ac-divider"></div>', unsafe_allow_html=True)

    # ── Preview JSON Terpisah ─────────────────────────────────────────────────
    st.markdown(
        '<div class="ac-label" style="color:var(--gold-dim);margin-bottom:8px;">🔍 Cuplikan Point / Chunk di Qdrant (JSON)</div>',
        unsafe_allow_html=True,
    )

    col_jp, col_jc = st.columns(2)
    with col_jp:
        st.markdown('<div class="ba-label ba-label-before">📦 Chunks (Parent)</div>', unsafe_allow_html=True)
        st.json(p_preview)
    with col_jc:
        st.markdown('<div class="ba-label ba-label-after">🔗 Chunks (Child)</div>', unsafe_allow_html=True)
        st.json(c_preview)

    # ── Hapus KB ──────────────────────────────────────────────────────────────
    st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)
    with st.expander("⚠️ Hapus Knowledge Base ini", expanded=False):
        st.warning(
            f"Tindakan ini akan menghapus collection **{p_col}** "
            f"dan **{c_col}** secara permanen dari Qdrant."
        )
        confirm = st.text_input(
            f"Ketik `{selected_kb}` untuk konfirmasi",
            key="kb_delete_confirm",
            placeholder=selected_kb,
        )
        if st.button("🗑️ Hapus Permanen", type="primary", key="btn_delete_kb"):
            if confirm.strip() == selected_kb:
                with st.spinner("Menghapus…"):
                    res = delete_knowledgebase(selected_kb)
                if res.get("success"):
                    st.success("✅ Knowledge Base berhasil dihapus.")
                    st.rerun()
                else:
                    st.error(f"❌ Gagal: {res.get('error')}")
            else:
                st.error("Nama konfirmasi tidak cocok.")


# ─────────────────────────────────────────────────────────────────────────────
# TAB: UPLOAD & PROSES
# ─────────────────────────────────────────────────────────────────────────────

def _tab_upload():
    st.markdown('<div class="diff-bar"></div>', unsafe_allow_html=True)

    # ── Upload widget (multi-file) ───────────────────────────────────────────
    st.markdown(
        '<div class="ac-label">Upload File PDF (bisa lebih dari satu)</div>',
        unsafe_allow_html=True,
    )
    uploaded_files = st.file_uploader(
        "Upload file PDF Undang-Undang",
        type=["pdf"],
        accept_multiple_files=True,
        key="kb_pdf_uploader",
        help="Unggah satu atau beberapa file PDF dokumen hukum Indonesia (UU, PP, Perpres, dll.)",
        label_visibility="collapsed",
    )

    if not uploaded_files:
        st.markdown(
            '<div style="text-align:center;padding:24px 0 8px 0;">'
            '<div style="font-size:11px;color:var(--text-muted);letter-spacing:.04em;">'
            'Upload satu atau beberapa PDF untuk melihat preview cleaning &amp; chunking sebelum diindeks ke Qdrant.'
            '</div></div>',
            unsafe_allow_html=True,
        )
        return

    # ── Ringkasan file yang dipilih ─────────────────────────────────────────
    total_size = sum(len(f.getvalue()) for f in uploaded_files)
    st.markdown(
        f'<div class="info-pill">📂 {len(uploaded_files)} file dipilih</div>'
        f'<div class="info-pill">💾 {total_size // 1024:,} KB total</div>',
        unsafe_allow_html=True,
    )
    st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

    # Tabel ringkasan file
    with st.expander(f"📋 Daftar {len(uploaded_files)} File yang Dipilih", expanded=len(uploaded_files) <= 5):
        rows_html = "".join(
            f"<tr>"
            f"<td style='padding:5px 10px;font-size:12px;color:var(--text-primary);'>{i+1}. {f.name}</td>"
            f"<td style='padding:5px 10px;font-size:12px;color:var(--text-muted);text-align:right;'>{len(f.getvalue())//1024:,} KB</td>"
            f"</tr>"
            for i, f in enumerate(uploaded_files)
        )
        st.markdown(
            f'<table style="width:100%;border-collapse:collapse;">'
            f'<thead><tr>'
            f'<th style="padding:5px 10px;font-size:10px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--text-muted);text-align:left;">Nama File</th>'
            f'<th style="padding:5px 10px;font-size:10px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--text-muted);text-align:right;">Ukuran</th>'
            f'</tr></thead>'
            f'<tbody>{rows_html}</tbody>'
            f'</table>',
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:4px;'></div>", unsafe_allow_html=True)

    # ── Config ───────────────────────────────────────────────────────────────
    col_cfg1, col_cfg2 = st.columns(2)
    with col_cfg1:
        st.markdown('<div class="ac-label">Nama Collection (opsional)</div>', unsafe_allow_html=True)
        custom_col = st.text_input(
            "Collection", value="", placeholder="auto (dari nama file)",
            label_visibility="collapsed", key="kb_collection_name"
        )
    with col_cfg2:
        st.markdown('<div class="ac-label">Embed &amp; Index ke Qdrant</div>', unsafe_allow_html=True)
        do_embed = st.toggle(
            "Simpan ke Qdrant setelah chunking",
            value=False, key="kb_do_embed",
            help="Jika aktif, chunk akan di-embed dan diindeks langsung ke Qdrant."
        )

    collection_name = custom_col.strip() or None

    st.markdown("<div style='height:4px;'></div>", unsafe_allow_html=True)

    col_btn1, col_btn2, _ = st.columns([2, 2, 3])
    with col_btn1:
        btn_clean = st.button(
            "🧹 Preview Cleaning",
            use_container_width=True, key="btn_cleaning_only",
            help="Ekstrak &amp; bersihkan teks PDF — tampilkan before/after per file"
        )
    with col_btn2:
        btn_chunk = st.button(
            "⚙️ Cleaning + Chunking",
            use_container_width=True, key="btn_full_process",
            type="primary",
            help="Cleaning → Chunking → tampilkan parent/child chunks per file"
        )

    is_multi = len(uploaded_files) > 1

    # ── CLEANING ONLY ────────────────────────────────────────────────────────
    if btn_clean:
        if is_multi:
            # Mode multi-file
            files_data = [(f.name, f.getvalue()) for f in uploaded_files]
            with st.spinner(f"🧹 Mengekstrak & membersihkan {len(uploaded_files)} file PDF…"):
                res = upload_and_clean_multi(files_data)

            if not res.get("success"):
                st.error(f"❌ Request gagal: {res.get('error')}")
            else:
                batch = res["data"]
                _render_multi_clean_results(batch)

        else:
            # Mode single-file (behaviour lama)
            f = uploaded_files[0]
            pdf_bytes = f.getvalue()
            with st.spinner("🧹 Mengekstrak & membersihkan teks PDF…"):
                res = upload_and_clean(pdf_bytes, f.name)

            if not res.get("success"):
                st.error(f"❌ Cleaning gagal: {res.get('error')}")
            else:
                resp     = res["data"]
                doc_data = resp.get("data", {})
                doc_id   = resp.get("document_id", "—")

                st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)
                st.markdown(
                    '<div class="step-badge">✅ Step 1 — Cleaning Selesai</div>',
                    unsafe_allow_html=True,
                )

                c1, c2, c3 = st.columns(3)
                with c1:
                    st.markdown(_card_stat(doc_data.get("total_pages", "—"), "Halaman"), unsafe_allow_html=True)
                with c2:
                    st.markdown(_card_stat(f'{doc_data.get("total_words", 0):,}', "Kata (bersih)", color="var(--green)"), unsafe_allow_html=True)
                with c3:
                    doc_id_short = doc_id[:12] + "…" if len(str(doc_id)) > 12 else doc_id
                    st.markdown(_card_stat(doc_id_short, "Doc ID", color="var(--text-muted)"), unsafe_allow_html=True)

                st.session_state["_kb_clean_result"] = res

    # Tampilkan before/after jika ada di session (single-file cleaning)
    _render_clean_preview()

    # ── CLEANING + CHUNKING ──────────────────────────────────────────────────
    if btn_chunk:
        if is_multi:
            # Mode multi-file
            files_data = [(f.name, f.getvalue()) for f in uploaded_files]
            with st.spinner(f"⚙️ Memproses {len(uploaded_files)} file PDF (cleaning → chunking)…"):
                res = process_and_chunk_multi(
                    files_data,
                    include_raw_chunks=True,
                    embed=do_embed,
                    collection=collection_name,
                )

            if not res.get("success"):
                st.error(f"❌ Request gagal: {res.get('error')}")
            else:
                batch = res["data"]
                _render_multi_chunk_results(batch, do_embed)

        else:
            # Mode single-file (behaviour lama)
            f = uploaded_files[0]
            pdf_bytes = f.getvalue()
            with st.spinner("⚙️ Cleaning → Chunking (mungkin 10–60 detik)…"):
                res = process_and_chunk(
                    pdf_bytes, f.name,
                    include_raw_chunks=True,
                    embed=do_embed,
                    collection=collection_name,
                )

            if not res.get("success"):
                st.error(f"❌ Chunking gagal: {res.get('error')}")
            else:
                resp       = res["data"]
                data_body  = resp.get("data", {})
                cl_stats   = data_body.get("cleaning_stats", {})
                ck_stats   = data_body.get("chunking_stats", {})
                raw_chunks = data_body.get("raw_chunks", [])
                embed_info = data_body.get("embedding")

                st.session_state["_kb_chunk_result"] = raw_chunks
                st.session_state["_kb_chunk_stats"]  = ck_stats
                st.session_state["_kb_clean_stats"]  = cl_stats
                st.session_state["_kb_embed_done"]   = bool(embed_info and do_embed)
                st.session_state.pop("_kb_clean_result", None)

    # Tampilkan hasil chunking single-file jika ada
    _render_chunk_preview()


# ─────────────────────────────────────────────────────────────────────────────
# MULTI-FILE RESULT RENDERERS
# ─────────────────────────────────────────────────────────────────────────────

def _render_multi_clean_results(batch: dict):
    """Tampilkan hasil cleaning untuk batch multi-file."""
    total   = batch.get("total_files", 0)
    success = batch.get("success_count", 0)
    failed  = batch.get("failed_count", 0)
    results = batch.get("results", [])

    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)

    # Ringkasan agregat
    col_s1, col_s2, col_s3 = st.columns(3)
    with col_s1:
        st.markdown(_card_stat(total, "Total File"), unsafe_allow_html=True)
    with col_s2:
        st.markdown(_card_stat(success, "Berhasil", color="var(--green)"), unsafe_allow_html=True)
    with col_s3:
        color_fail = "var(--orange)" if failed > 0 else "var(--text-muted)"
        st.markdown(_card_stat(failed, "Gagal", color=color_fail), unsafe_allow_html=True)

    st.markdown('<div class="ac-divider"></div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="step-badge">✅ Cleaning Selesai — Detail Per File</div>',
        unsafe_allow_html=True,
    )

    for item in results:
        fname   = item.get("filename", "—")
        ok      = item.get("success", False)
        err     = item.get("error")
        data    = item.get("data") or {}
        doc_id  = item.get("document_id", "—")

        icon = "✅" if ok else "❌"
        with st.expander(f"{icon} {fname}", expanded=not ok):
            if not ok:
                st.error(f"❌ {err}")
                continue

            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown(_card_stat(data.get("total_pages", "—"), "Halaman"), unsafe_allow_html=True)
            with c2:
                st.markdown(_card_stat(f'{data.get("total_words", 0):,}', "Kata (bersih)", color="var(--green)"), unsafe_allow_html=True)
            with c3:
                short_id = str(doc_id)[:12] + "…" if len(str(doc_id)) > 12 else str(doc_id)
                st.markdown(_card_stat(short_id, "Doc ID", color="var(--text-muted)"), unsafe_allow_html=True)

            _render_repair_stats(data.get("repair_stats", {}))
            raw_snip = data.get("raw_snippet", "")
            cln_snip = data.get("clean_snippet", "")
            if raw_snip or cln_snip:
                st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)
                _render_before_after(raw_snip or "(tidak tersedia)", cln_snip or "(tidak tersedia)")


def _render_multi_chunk_results(batch: dict, do_embed: bool):
    """Tampilkan hasil cleaning+chunking untuk batch multi-file."""
    total   = batch.get("total_files", 0)
    success = batch.get("success_count", 0)
    failed  = batch.get("failed_count", 0)
    results = batch.get("results", [])

    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)

    # Hitung total chunk keseluruhan
    total_chunks = sum(
        (item.get("data") or {}).get("chunking_stats", {}).get("total_chunks", 0)
        for item in results if item.get("success")
    )
    total_embedded = sum(
        (((item.get("data") or {}).get("embedding") or {}).get("embedded_chunks", 0))
        for item in results if item.get("success")
    )

    # Ringkasan agregat
    col_s1, col_s2, col_s3, col_s4 = st.columns(4)
    with col_s1:
        st.markdown(_card_stat(total, "Total File"), unsafe_allow_html=True)
    with col_s2:
        st.markdown(_card_stat(success, "Berhasil", color="var(--green)"), unsafe_allow_html=True)
    with col_s3:
        color_fail = "var(--orange)" if failed > 0 else "var(--text-muted)"
        st.markdown(_card_stat(failed, "Gagal", color=color_fail), unsafe_allow_html=True)
    with col_s4:
        st.markdown(_card_stat(total_chunks, "Total Chunks", color="var(--gold-light)"), unsafe_allow_html=True)

    if do_embed and total_embedded > 0:
        st.success(f"✅ {total_embedded:,} chunk berhasil di-embed dan diindeks ke Qdrant di semua file.")

    st.markdown('<div class="ac-divider"></div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="step-badge">✅ Chunking Selesai — Detail Per File</div>',
        unsafe_allow_html=True,
    )

    for item in results:
        fname    = item.get("filename", "—")
        ok       = item.get("success", False)
        err      = item.get("error")
        data     = item.get("data") or {}
        doc_id   = item.get("document_id", "—")
        ck_stats = data.get("chunking_stats", {})
        cl_stats = data.get("cleaning_stats", {})
        raw_chunks = data.get("raw_chunks", [])
        embed_info = data.get("embedding")
        index_info = data.get("indexing")

        icon        = "✅" if ok else "❌"
        label_extra = f" — {ck_stats.get('total_chunks', 0)} chunks" if ok else ""
        with st.expander(f"{icon} {fname}{label_extra}", expanded=not ok):
            if not ok:
                st.error(f"❌ {err}")
                continue

            # Stat cards
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.markdown(_card_stat(cl_stats.get("total_pages", "—"), "Halaman"), unsafe_allow_html=True)
            with c2:
                st.markdown(_card_stat(ck_stats.get("total_chunks", len(raw_chunks)), "Total Chunks"), unsafe_allow_html=True)
            with c3:
                st.markdown(_card_stat(ck_stats.get("parent_count", 0), "Parent", color="var(--gold-light)"), unsafe_allow_html=True)
            with c4:
                st.markdown(_card_stat(ck_stats.get("child_count", 0), "Child", color="var(--green)"), unsafe_allow_html=True)

            # Embedding/indexing info
            if do_embed:
                if embed_info and not embed_info.get("error"):
                    emb_count = embed_info.get("embedded_chunks", 0)
                    st.success(f"✅ {emb_count} chunk di-embed ke Qdrant.")
                elif embed_info and embed_info.get("error"):
                    st.error(f"❌ Embed gagal: {embed_info['error']}")
                if index_info and index_info.get("error"):
                    st.warning(f"⚠️ Index: {index_info['error']}")

            # Repair stats & before/after
            _render_repair_stats(cl_stats.get("repair_stats", {}))
            raw_snip = cl_stats.get("raw_snippet", "")
            cln_snip = cl_stats.get("clean_snippet", "")
            if raw_snip or cln_snip:
                st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)
                _render_before_after(raw_snip or "(tidak tersedia)", cln_snip or "(tidak tersedia)")

            # Chunk preview
            if raw_chunks:
                st.markdown('<div class="ac-divider"></div>', unsafe_allow_html=True)
                sections_avail = sorted({c.get("section", "") for c in raw_chunks if c.get("section")})
                col_f1, col_f2, col_f3 = st.columns([3, 2, 2])
                safe_key = fname.replace(".", "_").replace(" ", "_")
                with col_f1:
                    st.markdown('<div class="ac-label">Filter Bagian</div>', unsafe_allow_html=True)
                    filter_sec = st.selectbox(
                        "Bagian", ["Semua"] + sections_avail,
                        label_visibility="collapsed",
                        key=f"kb_chunk_filter_sec_{safe_key}",
                    )
                with col_f2:
                    st.markdown('<div class="ac-label">Filter Tipe</div>', unsafe_allow_html=True)
                    filter_type = st.selectbox(
                        "Tipe", ["Semua", "parent", "child"],
                        label_visibility="collapsed",
                        key=f"kb_chunk_filter_type_{safe_key}",
                    )
                with col_f3:
                    max_show = st.slider(
                        "Maks chunk",
                        min_value=2, max_value=30, value=6,
                        key=f"kb_chunk_max_{safe_key}",
                    )

                filtered = [
                    c for c in raw_chunks
                    if (filter_sec == "Semua" or c.get("section") == filter_sec)
                    and (filter_type == "Semua" or c.get("type") == filter_type)
                ]
                st.markdown(
                    f'<div style="font-size:11px;color:var(--text-muted);margin-bottom:8px;">'
                    f'Menampilkan {min(max_show, len(filtered))} dari {len(filtered)} chunk'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                st.json(filtered[:max_show])


def _render_clean_preview():
    """Ambil cuplikan before/after dari session_state (jika ada)."""
    result = st.session_state.get("_kb_clean_result")
    if not result:
        return

    resp         = result.get("data", {})
    doc_data     = resp.get("data", {})
    raw_snip     = doc_data.get("raw_snippet", "")
    cln_snip     = doc_data.get("clean_snippet", "")
    metadata     = resp.get("metadata", {})
    repair_stats = resp.get("repair_stats", {})
    source       = metadata.get("source_label", "")

    if not raw_snip and not cln_snip:
        return

    # Bangun label di luar f-string (hindari backslash Python <3.12)
    src_span = ("  \u2014  <span style='color:var(--text-muted);'>" + source + "</span>") if source else ""
    lbl_html = '<div class="ac-label" style="color:var(--gold-dim);margin-bottom:8px;">\U0001F4DD Before &amp; After Cleaning' + src_span + '</div>'
    st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)
    st.markdown('<div class="ac-divider"></div>', unsafe_allow_html=True)
    st.markdown(lbl_html, unsafe_allow_html=True)

    # ── Repair Stats Panel ──────────────────────────────────────────────────
    _render_repair_stats(repair_stats)

    st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)
    _render_before_after(raw_snip or "(tidak tersedia)", cln_snip or "(tidak tersedia)")



def _render_chunk_preview():
    """Render statistik + preview parent/child chunks dari session_state."""
    raw_chunks = st.session_state.get("_kb_chunk_result")
    if not raw_chunks:
        return

    ck_stats = st.session_state.get("_kb_chunk_stats", {})
    cl_stats = st.session_state.get("_kb_clean_stats", {})

    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)
    st.markdown(
        '<div class="step-badge">✅ Step 2 — Chunking Selesai</div>',
        unsafe_allow_html=True,
    )

    # ── Stat cards ──────────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(
            _card_stat(cl_stats.get("total_pages", "—"), "Halaman"),
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            _card_stat(ck_stats.get("total_chunks", len(raw_chunks)), "Total Chunks"),
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            _card_stat(ck_stats.get("parent_count", 0), "Parent", color="var(--gold-light)"),
            unsafe_allow_html=True,
        )
    with c4:
        st.markdown(
            _card_stat(ck_stats.get("child_count", 0), "Child", color="var(--green)"),
            unsafe_allow_html=True,
        )

    # ── Embed/index info ─────────────────────────────────────────────────────
    embed_ok = st.session_state.get("_kb_embed_done")
    if embed_ok:
        st.success("✅ Chunk berhasil di-embed dan diindeks ke Qdrant.")

    st.markdown('<div class="ac-divider"></div>', unsafe_allow_html=True)

    # ── Before / After snippet ───────────────────────────────────────────────
    meta = cl_stats.get("metadata", {})
    source_label = meta.get("source_label", "")
    repair_stats = cl_stats.get("repair_stats", {})

    # Bangun label di luar f-string (hindari backslash Python <3.12)
    src_span2 = ("  \u2014  <span style='color:var(--text-muted);'>" + source_label + "</span>") if source_label else ""
    label2_html = '<div class="ac-label" style="color:var(--gold-dim);margin-bottom:6px;">\U0001F4DD Before &amp; After Cleaning' + src_span2 + '</div>'
    st.markdown(label2_html, unsafe_allow_html=True)

    # ── Repair Stats Panel ──────────────────────────────────────────────────
    _render_repair_stats(repair_stats)

    st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)

    # Ambil before/after dari cleaning_stats (dikembalikan backend)
    raw_snip  = cl_stats.get("raw_snippet", "")
    cln_snip  = cl_stats.get("clean_snippet", "")

    if raw_snip or cln_snip:
        _render_before_after(
            raw_snip or "(tidak tersedia)",
            cln_snip or "(tidak tersedia)",
        )
    else:
        # Fallback: teks dari parent chunk pertama sebagai clean snippet
        first_parent = next((c for c in raw_chunks if c.get("type") == "parent"), None)
        if first_parent:
            fallback_raw = (
                "[ Teks mentah PDF mengandung artefak:\n"
                "  - Nomor halaman, header/footer berulang\n"
                "  - Ligature (ﬁ, ﬂ, dll.) & spasi ganda\n\n"
                "Contoh isi setelah cleaning (lihat sebelah kanan) ]"
            )
            _render_before_after(fallback_raw, first_parent["text"][:400])


    # ── Filter & Chunk Preview ───────────────────────────────────────────────
    st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

    # Filter section
    sections_avail = sorted({c.get("section", "") for c in raw_chunks if c.get("section")})
    col_f1, col_f2 = st.columns([3, 2])
    with col_f1:
        st.markdown('<div class="ac-label">Filter Bagian</div>', unsafe_allow_html=True)
        filter_sec = st.selectbox(
            "Bagian", ["Semua"] + sections_avail,
            label_visibility="collapsed", key="kb_chunk_filter_sec"
        )
    with col_f2:
        st.markdown('<div class="ac-label">Filter Tipe</div>', unsafe_allow_html=True)
        filter_type = st.selectbox(
            "Tipe", ["Semua", "parent", "child"],
            label_visibility="collapsed", key="kb_chunk_filter_type"
        )

    # max preview
    max_show = st.slider("Jumlah chunk ditampilkan", 2, 30, 6, key="kb_chunk_max_show")

    filtered = [
        c for c in raw_chunks
        if (filter_sec == "Semua" or c.get("section") == filter_sec)
        and (filter_type == "Semua" or c.get("type") == filter_type)
    ]

    st.markdown(
        f'<div style="font-size:11px;color:var(--text-muted);margin-bottom:8px;">'
        f'Menampilkan {min(max_show, len(filtered))} dari {len(filtered)} chunk'
        f'</div>',
        unsafe_allow_html=True,
    )

    st.json(filtered[:max_show])

# ─────────────────────────────────────────────────────────────────────────────
# MAIN RENDER
# ─────────────────────────────────────────────────────────────────────────────

def render_knowledgebase_tab():
    # Inject CSS tema
    st.markdown(_KB_CSS, unsafe_allow_html=True)

    # Header
    st.markdown(
        '<div class="ac-header">📚 Knowledge Base</div>'
        '<div class="ac-subheader">Kelola koleksi dokumen hukum — monitoring, upload, cleaning &amp; chunking.</div>',
        unsafe_allow_html=True,
    )
    st.markdown('<div class="ac-divider"></div>', unsafe_allow_html=True)

    tab_mon, tab_up,  = st.tabs([
        "  📊  Monitoring  ", 
        "  📤  Upload & Proses  ", 
    ])

    with tab_mon:
        _tab_monitoring()

    with tab_up:
        _tab_upload()


