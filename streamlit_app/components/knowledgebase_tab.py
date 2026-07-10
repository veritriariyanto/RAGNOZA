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
    process_and_chunk,
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
    grid-template-columns: repeat(4, 1fr);
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
    """
    match = re.search(r"pasal\s+(\d+)", query, re.IGNORECASE)
    return match.group(1) if match else None


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
    spcd         = repair_stats.get("spaced_char_fixes", 0)
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
        ("⠿", str(spcd), "Spaced Chars",       "Karakter terpisah spasi"),
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

    # ── Upload widget ────────────────────────────────────────────────────────
    uploaded = st.file_uploader(
        "Upload file PDF Undang-Undang",
        type=["pdf"],
        key="kb_pdf_uploader",
        help="Unggah file PDF dokumen hukum Indonesia (UU, PP, Perpres, dll.)",
    )

    if uploaded is None:
        st.markdown(
            '<div style="text-align:center;padding:24px 0 8px 0;">'
            '<div style="font-size:11px;color:var(--text-muted);letter-spacing:.04em;">'
            'Upload PDF untuk melihat preview cleaning &amp; chunking sebelum diindeks ke Qdrant.'
            '</div></div>',
            unsafe_allow_html=True,
        )
        return

    pdf_bytes = uploaded.getvalue()
    filename  = uploaded.name
    size_kb   = len(pdf_bytes) // 1024

    st.markdown(
        f'<div class="info-pill">📄 {filename}</div>'
        f'<div class="info-pill">💾 {size_kb:,} KB</div>',
        unsafe_allow_html=True,
    )
    st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)

    # ── Config ───────────────────────────────────────────────────────────────
    col_cfg1, col_cfg2 = st.columns(2)
    with col_cfg1:
        st.markdown('<div class="ac-label">Nama Collection (opsional)</div>', unsafe_allow_html=True)
        custom_col = st.text_input(
            "Collection", value="", placeholder="auto (dari nama file)",
            label_visibility="collapsed", key="kb_collection_name"
        )
    with col_cfg2:
        st.markdown('<div class="ac-label">Embed & Index ke Qdrant</div>', unsafe_allow_html=True)
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
            help="Ekstrak & bersihkan teks PDF — tampilkan before/after"
        )
    with col_btn2:
        btn_chunk = st.button(
            "⚙️ Cleaning + Chunking",
            use_container_width=True, key="btn_full_process",
            type="primary",
            help="Cleaning → Chunking → tampilkan parent/child chunks"
        )

    # ── CLEANING ONLY ────────────────────────────────────────────────────────
    if btn_clean:
        with st.spinner("🧹 Mengekstrak & membersihkan teks PDF…"):
            res = upload_and_clean(pdf_bytes, filename)

        if not res.get("success"):
            st.error(f"❌ Cleaning gagal: {res.get('error')}")
            return

        resp = res["data"]
        doc_data = resp.get("data", {})
        doc_id   = resp.get("document_id", "—")

        st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)
        st.markdown(
            f'<div class="step-badge">✅ Step 1 — Cleaning Selesai</div>',
            unsafe_allow_html=True,
        )

        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown(
                _card_stat(doc_data.get("total_pages", "—"), "Halaman"),
                unsafe_allow_html=True,
            )
        with c2:
            st.markdown(
                _card_stat(f'{doc_data.get("total_words", 0):,}', "Kata (bersih)", color="var(--green)"),
                unsafe_allow_html=True,
            )
        with c3:
            st.markdown(
                _card_stat(doc_id[:12] + "…" if len(str(doc_id)) > 12 else doc_id, "Doc ID", color="var(--text-muted)"),
                unsafe_allow_html=True,
            )

        # Simpan ke session untuk ditampilkan before/after
        st.session_state["_kb_clean_result"] = res

    # Tampilkan before/after jika ada di session (dari cleaning maupun chunking)
    _render_clean_preview()

    # ── CLEANING + CHUNKING ──────────────────────────────────────────────────
    if btn_chunk:
        with st.spinner("⚙️ Cleaning → Chunking (mungkin 10–60 detik)…"):
            res = process_and_chunk(
                pdf_bytes, filename,
                include_raw_chunks=True,
                embed=do_embed,
                collection=collection_name,
            )

        if not res.get("success"):
            st.error(f"❌ Chunking gagal: {res.get('error')}")
            return

        resp      = res["data"]
        doc_id    = resp.get("document_id", "—")
        data_body = resp.get("data", {})
        cl_stats  = data_body.get("cleaning_stats", {})
        ck_stats  = data_body.get("chunking_stats", {})
        raw_chunks = data_body.get("raw_chunks", [])
        embed_info = data_body.get("embedding")
        index_info = data_body.get("indexing")

        # Simpan raw_chunks ke session
        st.session_state["_kb_chunk_result"] = raw_chunks
        st.session_state["_kb_chunk_stats"]  = ck_stats
        st.session_state["_kb_clean_stats"]  = cl_stats
        st.session_state["_kb_embed_done"]   = bool(embed_info and do_embed)
        # Hapus clean-only result agar tidak tumpang tindih
        st.session_state.pop("_kb_clean_result", None)

    # Tampilkan hasil chunking jika ada
    _render_chunk_preview()


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


def _tab_similarity_test():
    st.markdown(
        '<div class="ac-label-step">UJI COBA RETRIEVAL & SIMILARITY</div>'
        '<div class="ac-subheader" style="margin-bottom:6px;">'
        'Uji pencarian dokumen menggunakan model embedding dan vector store secara langsung.'
        '</div>',
        unsafe_allow_html=True,
    )
    st.caption("🤖 Model aktif: `paraphrase-multilingual-MiniLM-L12-v2` — mendukung Bahasa Indonesia & 50+ bahasa lainnya")
    st.markdown("")

    # Ambil daftar KB
    kb_list = get_knowledgebase_list()
    if not kb_list:
        st.info("ℹ Belum ada Knowledge Base yang tersedia. Silakan upload & proses dokumen terlebih dahulu.")
        return

    # Form pencarian
    col_kb, col_lim = st.columns([3, 1])
    with col_kb:
        selected_kb = st.selectbox(
            "Pilih Knowledge Base", kb_list, key="kb_sim_selected"
        )
    with col_lim:
        limit = st.number_input("Limit Hasil", min_value=1, max_value=20, value=5, step=1, key="kb_sim_limit")

    query = st.text_input("Query Pencarian (Pertanyaan / Topik)", placeholder="Contoh: Apa kewenangan kepolisian?", key="kb_sim_query")

    # Filter Opsional (Expander)
    with st.expander("Filter Tambahan (Opsional)"):
        col_sec, col_pasal = st.columns(2)
        with col_sec:
            section_type = st.selectbox(
                "Filter Bagian", ["Semua", "Konsiderans", "Batang Tubuh", "Penjelasan"], key="kb_sim_sec"
            )
        with col_pasal:
            pasal_type = st.text_input(
                "Filter Pasal (Angka saja)",
                placeholder="Auto-terdeteksi dari query jika kosong",
                key="kb_sim_pasal",
                help="Kosongkan agar nomor pasal dideteksi otomatis dari teks query (mis. 'Pasal 5'), "
                     "sama seperti perilaku pipeline integrasi. Isi manual untuk override.",
            )
        st.markdown("---")
        score_threshold = st.slider(
            "Score Threshold (Minimum Similarity)",
            min_value=0.0, max_value=1.0, value=0.15, step=0.01,
            key="kb_sim_threshold",
            help="Turunkan nilai ini jika tidak ada hasil. Model MiniLM-L6 umumnya menghasilkan skor 0.1–0.5 untuk teks Bahasa Indonesia."
        )

    # Tombol Cari
    if st.button("🔍 Jalankan Pencarian", use_container_width=True, key="kb_sim_search_btn"):
        if not query.strip():
            st.warning("⚠️ Masukkan query pencarian terlebih dahulu!")
            return

        # Kalau "Filter Pasal" tidak diisi manual, deteksi otomatis dari teks query —
        # tanpa ini, hasil similarity test bisa berbeda dari pipeline integrasi (yang
        # otomatis mengekstrak nomor pasal lewat repair_legal_text), karena tanpa
        # filter pasal, exact-match boost & retry di QdrantService tidak pernah aktif.
        effective_pasal = pasal_type.strip() if pasal_type.strip() else _extract_pasal_from_query(query)
        if not pasal_type.strip() and effective_pasal:
            st.caption(
                f"🔎 Pasal terdeteksi otomatis dari query: **Pasal {effective_pasal}** "
                f"— isi 'Filter Pasal' di atas untuk override manual."
            )

        with st.spinner("Mencari chunk paling relevan di Qdrant..."):
            res = search_similarity(
                base_name=selected_kb,
                query=query,
                section_type=section_type if section_type != "Semua" else None,
                pasal_type=effective_pasal,
                limit=int(limit),
                score_threshold=score_threshold,
            )

        if not res.get("success"):
            st.error(f"❌ Gagal mencari similarity: {res.get('error')}")
            return

        data = res.get("data", {})
        results = data.get("results", [])
        pasal_not_found = data.get("pasal_not_found", False)

        if not results:
            st.warning("⚠️ Tidak ada hasil yang ditemukan. Coba turunkan **Score Threshold** di Filter Tambahan (mis. ke 0.05).")
            return

        # Tampilkan kalau backend melakukan retry tanpa filter pasal — supaya
        # user tahu hasil di bawah ini BUKAN exact match pasal yang di-filter
        # (baik dari input manual maupun auto-detect), melainkan hasil koreksi
        # dari pencarian semantik murni karena filter pasal aslinya skornya
        # terlalu rendah / tidak ditemukan sama sekali.
        if effective_pasal and pasal_not_found:
            st.warning(
                f"⚠️ Filter **Pasal {effective_pasal}** tidak menghasilkan kecocokan yang cukup "
                f"relevan (skor terlalu rendah atau pasal tidak ditemukan). Hasil di bawah ini "
                f"adalah pencarian semantik **tanpa filter pasal** — periksa apakah pasal yang "
                f"benar-benar cocok sudah muncul di sini."
            )

        st.caption(f"Ditemukan **{len(results)}** hasil retrieval untuk query: `{query}`")
        st.markdown("---")

        # Render setiap hasil dengan Streamlit native components
        for idx, item in enumerate(results):
            score = item.get("score", 0.0)
            child = item.get("child", {})
            parent = item.get("parent", {})

            child_id    = child.get("chunk_id") or "—"
            child_sec   = child.get("section") or "—"
            child_pasal = child.get("pasal")
            child_ayat  = child.get("ayat")
            child_text  = child.get("content") or "—"

            parent_id    = parent.get("chunk_id") or "—"
            parent_title = parent.get("title") or parent_id
            parent_text  = parent.get("content") or "—"

            # ── Score header ──────────────────────────────────────
            col_lbl, col_score = st.columns([5, 1])
            with col_lbl:
                st.markdown(f"**Hasil #{idx + 1}**")
            with col_score:
                # Warna badge berdasarkan skor
                if score >= 0.4:
                    badge_color = "#2eb87a"
                elif score >= 0.2:
                    badge_color = "#d4a853"
                else:
                    badge_color = "#888"
                st.markdown(
                    f'<span style="background:{badge_color};color:#fff;font-size:11px;'
                    f'font-weight:700;padding:3px 10px;border-radius:6px;">'
                    f'{score:.4f}</span>',
                    unsafe_allow_html=True,
                )

            # ── Child chunk ───────────────────────────────────────
            with st.container(border=True):
                meta_parts = [child_sec]
                if child_pasal:
                    meta_parts.append(f"Pasal {child_pasal}")
                if child_ayat:
                    meta_parts.append(f"Ayat {child_ayat}")
                st.markdown(
                    f"🟢 **Child Chunk**  \n"
                    f"<small style='color:#888;'>ID: `{child_id}` &nbsp;|&nbsp; {' · '.join(meta_parts)}</small>",
                    unsafe_allow_html=True,
                )
                st.text(child_text[:600] + ("…" if len(child_text) > 600 else ""))

                st.markdown("<hr style='margin:8px 0;opacity:.3;'>", unsafe_allow_html=True)

                # ── Parent chunk ──────────────────────────────────
                st.markdown(
                    f"🟡 **Parent Chunk (Context)**  \n"
                    f"<small style='color:#888;'>ID: `{parent_id}` &nbsp;|&nbsp; {parent_title}</small>",
                    unsafe_allow_html=True,
                )
                st.text(parent_text[:800] + ("…" if len(parent_text) > 800 else ""))

            st.markdown("")  # spacing


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

    tab_mon, tab_up, tab_sim = st.tabs([
        "  📊  Monitoring  ", 
        "  📤  Upload & Proses  ", 
        "  🔍  Similarity Test  "
    ])

    with tab_mon:
        _tab_monitoring()

    with tab_up:
        _tab_upload()

    with tab_sim:
        _tab_similarity_test()
