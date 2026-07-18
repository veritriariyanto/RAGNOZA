# streamlit_app/components/material_renderers.py
"""
Shared rendering functions for legal analysis material sections.
Used by history_detail.py and 1_Hasil_Generate.py to display
RAG-generated material in collapsible styled sections.
"""

import streamlit as st


# =============================================================================
# CSS / JS INJECTION (shared)
# =============================================================================

def inject_collapsible_js():
    """Inject JS helper for collapsible sections (safe to call multiple times)."""
    st.markdown(
        """
        <script>
        function toggleSection(id) {
            const body = document.getElementById('body-' + id);
            const arrow = document.getElementById('arrow-' + id);
            if (!body) return;
            const isOpen = body.style.display !== 'none';
            body.style.display = isOpen ? 'none' : 'block';
            if (arrow) arrow.style.transform = isOpen ? 'rotate(-90deg)' : 'rotate(0deg)';
        }
        function toggleRagasExplain() {
            const el = document.getElementById('ragas-explain');
            if (!el) return;
            el.style.display = el.style.display === 'none' ? 'block' : 'none';
        }
        </script>
        """,
        unsafe_allow_html=True,
    )


# =============================================================================
# HELPER HTML ATOMS
# =============================================================================

def _section_id(name: str) -> str:
    """Generate a safe HTML id from a section name."""
    return name.replace(" ", "-").lower()


def _section_wrap(icon: str, title: str, body_html: str,
                  count: int | None = None, open_default: bool = True,
                  empty: bool = False) -> str:
    """
    Renders a collapsible section card.
    - open_default: whether section starts expanded
    - empty: if True, shows muted 'Tidak tersedia' badge and starts collapsed
    """
    sid = _section_id(title)
    display = "block" if (open_default and not empty) else "none"
    arrow_rotate = "rotate(0deg)" if (
        open_default and not empty) else "rotate(-90deg)"

    count_html = ""
    if empty:
        count_html = (
            '<span style="font-size:11px;color:var(--text-muted);background:rgba(255,255,255,0.04);'
            'border-radius:12px;padding:2px 8px;border:0.5px solid var(--border-soft);">Tidak tersedia</span>'
        )
    elif count is not None:
        count_html = (
            f'<span style="font-size:11px;color:var(--text-muted);background:var(--surface-3);'
            f'border-radius:12px;padding:2px 8px;">{count} item</span>'
        )

    return (
        f'<div style="margin-bottom:12px;border:0.5px solid rgba(240,237,232,0.1);border-radius:10px;overflow:hidden;">'
        f'<div onclick="toggleSection(\'{sid}\')" style="display:flex;align-items:center;gap:8px;'
        f'padding:10px 14px;background:var(--surface-2);cursor:pointer;user-select:none;" '
        f'onmouseover="this.style.background=\'var(--surface-3)\'" '
        f'onmouseout="this.style.background=\'var(--surface-2)\'">'
        f'<span style="font-size:15px;flex-shrink:0;">{icon}</span>'
        f'<span style="font-size:13px;font-weight:500;color:var(--text-primary);flex:1;">{title}</span>'
        f'{count_html}'
        f'<span id="arrow-{sid}" style="font-size:11px;color:var(--text-muted);'
        f'transition:transform .2s;transform:{arrow_rotate};">▾</span>'
        f'</div>'
        f'<div id="body-{sid}" style="display:{display};padding:14px 16px;'
        f'background:var(--surface-1);border-top:0.5px solid rgba(240,237,232,0.06);">'
        f'{body_html}'
        f'</div>'
        f'</div>'
    )


def _empty_state(icon: str, message: str) -> str:
    return (
        f'<div style="padding:14px;text-align:center;">'
        f'<div style="font-size:22px;margin-bottom:6px;opacity:.35;">{icon}</div>'
        f'<div style="font-size:12.5px;color:var(--text-muted);line-height:1.6;">{message}</div>'
        f'</div>'
    )


def _field_block(label: str, content_html: str) -> str:
    return (
        f'<div style="margin-bottom:10px;padding-bottom:10px;'
        f'border-bottom:0.5px solid rgba(240,237,232,0.07);">'
        f'<div style="font-size:10.5px;color:var(--text-muted);'
        f'letter-spacing:.07em;text-transform:uppercase;margin-bottom:5px;font-weight:600;">{label}</div>'
        f'{content_html}</div>'
    )


def _text_val(text: str | None) -> str:
    if text and str(text).strip() not in ("-", "—", ""):
        return f'<div style="font-size:13px;color:var(--text-secondary);line-height:1.65;">{text}</div>'
    return '<span style="font-size:13px;color:var(--text-muted);font-style:italic;">—</span>'


def _render_html(html: str):
    st.markdown(html, unsafe_allow_html=True)


# =============================================================================
# SECTION RENDERERS
# =============================================================================

def _render_summary(summary: dict):
    title = summary.get("title") or ""
    overview = summary.get("overview") or ""
    key_pts = summary.get("key_points") or []
    conclusion = summary.get("conclusion") or ""

    pts_html = (
        "".join(
            f'<div style="display:flex;gap:7px;align-items:flex-start;margin-bottom:5px;">'
            f'<span style="color:var(--text-muted);margin-top:5px;font-size:8px;flex-shrink:0;">●</span>'
            f'<span style="font-size:13px;color:var(--text-secondary);line-height:1.6;">{p}</span></div>'
            for p in key_pts
        ) if key_pts else '<span style="font-size:13px;color:var(--text-muted);font-style:italic;">—</span>'
    )

    conc_html = (
        f'<div style="background:var(--gold-glow);border:1px solid rgba(212,168,83,0.22);'
        f'border-radius:8px;padding:10px 13px;font-size:13px;'
        f'color:var(--gold-light);line-height:1.65;margin-top:2px;">💡 {conclusion}</div>'
        if conclusion.strip() else '<span style="font-size:13px;color:var(--text-muted);font-style:italic;">—</span>'
    )

    title_html = (
        f'<div style="font-family:\'DM Serif Display\',serif;font-size:1.05rem;'
        f'color:var(--text-primary);margin-bottom:2px;">{title}</div>'
        if title else ""
    )

    body = (
        (title_html if title_html else "")
        + _field_block("Gambaran umum", _text_val(overview))
        + _field_block("Poin-poin penting", pts_html)
        + f'<div><div style="font-size:10.5px;color:var(--text-muted);letter-spacing:.07em;'
        f'text-transform:uppercase;margin-bottom:5px;font-weight:600;">Kesimpulan</div>{conc_html}</div>'
    )
    _render_html(_section_wrap("📌", "Ringkasan", body, open_default=True))


def _render_legal_qa(qa_list: list):
    if not qa_list:
        body = _empty_state(
            "❓", "Tidak ada Q&A yang dihasilkan untuk pertanyaan ini.")
        _render_html(_section_wrap("❓", "Legal Q&A", body, empty=True))
        return

    rows = []
    for i, qa in enumerate(qa_list):
        q = qa.get("question") or "—"
        a = qa.get("answer") or "—"
        sep = "" if i == len(
            qa_list) - 1 else "border-bottom:0.5px solid rgba(240,237,232,0.07);"
        rows.append(
            f'<div style="padding:10px 0;{sep}">'
            f'<div style="font-size:13px;font-weight:500;color:var(--text-primary);'
            f'margin-bottom:5px;display:flex;gap:8px;">'
            f'<span style="font-size:11px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;'
            f'color:var(--gold-dim);flex-shrink:0;margin-top:2px;line-height:1.5;">T</span>{q}</div>'
            f'<div style="font-size:13px;color:var(--text-secondary);'
            f'line-height:1.65;padding-left:26px;">{a}</div></div>'
        )
    body = "".join(rows)
    _render_html(_section_wrap("❓", "Legal Q&A", body,
                 count=len(qa_list), open_default=True))


def _render_risk_review(risk: dict):
    status = risk.get("status") or ""
    score_raw = risk.get("score")
    analysis = risk.get("analysis") or ""
    risks = risk.get("risks") or []
    mitigations = risk.get("mitigation_steps") or []
    recom = risk.get("recommendation") or ""

    is_empty = (
        status.strip() in ("", "-", "—")
        and not analysis.strip()
        and not risks
        and not mitigations
        and not recom.strip()
    )

    if is_empty:
        body = (
            f'<div style="background:rgba(255,255,255,0.03);border:1px solid var(--border-soft);'
            f'border-radius:8px;padding:16px;text-align:center;">'
            f'<div style="font-size:20px;margin-bottom:6px;opacity:.4;">🔍</div>'
            f'<div style="font-size:13px;color:var(--text-muted);line-height:1.6;">'
            f'Sistem tidak mendeteksi risiko spesifik dari konteks hukum ini.<br>'
            f'<span style="font-size:12px;">Hal ini normal ketika pertanyaan bersifat informatif, '
            f'bukan berupa kasus atau kontrak yang perlu dievaluasi.</span>'
            f'</div></div>'
        )
        _render_html(_section_wrap(
            "⚠️", "Risk Review", body, open_default=True))
        return

    score = int(min(score_raw or 0, 100))
    status_lower = status.lower()
    if any(w in status_lower for w in ("risiko", "berisiko", "tinggi")):
        status_color = "var(--red)"
    elif any(w in status_lower for w in ("aman", "rendah")):
        status_color = "var(--green)"
    elif status.strip() in ("", "-", "—"):
        status_color = "var(--text-muted)"
    else:
        status_color = "var(--orange)"

    bar_color = (
        "var(--red)" if score >= 70 else
        "var(--orange)" if score >= 40 else
        "var(--green)"
    )

    score_grid = (
        f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:14px;">'
        f'<div style="background:var(--surface-2);border-radius:8px;padding:10px 12px;text-align:center;">'
        f'<div style="font-size:10px;font-weight:600;letter-spacing:.07em;text-transform:uppercase;'
        f'color:var(--text-muted);margin-bottom:4px;">Status</div>'
        f'<div style="font-size:15px;font-weight:500;color:{status_color};">'
        f'{"Tidak terdeteksi" if status.strip() in ("", "-", "—") else status}</div></div>'
        f'<div style="background:var(--surface-2);border-radius:8px;padding:10px 12px;text-align:center;">'
        f'<div style="font-size:10px;font-weight:600;letter-spacing:.07em;text-transform:uppercase;'
        f'color:var(--text-muted);margin-bottom:4px;">Skor risiko</div>'
        f'<div style="font-size:20px;font-weight:500;color:var(--text-primary);">'
        f'{score}<span style="font-size:13px;color:var(--text-muted);"> / 100</span></div></div></div>'
        f'<div style="height:5px;border-radius:3px;background:var(--surface-3);margin-bottom:14px;">'
        f'<div style="height:5px;border-radius:3px;background:{bar_color};width:{score}%;"></div></div>'
    )

    def _bullet_list(items: list, color: str) -> str:
        if not items:
            return '<span style="font-size:13px;color:var(--text-muted);font-style:italic;">—</span>'
        return "".join(
            f'<div style="display:flex;gap:7px;margin-bottom:4px;font-size:13px;'
            f'color:var(--text-secondary);line-height:1.55;">'
            f'<span style="color:{color};flex-shrink:0;font-size:9px;margin-top:5px;">●</span>{item}</div>'
            for item in items
        )

    recom_html = (
        f'<div style="background:rgba(93,190,138,0.08);border:1px solid rgba(93,190,138,0.2);'
        f'border-radius:8px;padding:9px 12px;font-size:13px;color:var(--green);line-height:1.6;">'
        f'✅ {recom}</div>'
        if recom.strip() else '<span style="font-size:13px;color:var(--text-muted);font-style:italic;">—</span>'
    )

    body = (
        score_grid
        + _field_block("Analisis", _text_val(analysis))
        + _field_block("Risiko", _bullet_list(risks, "var(--red)"))
        + _field_block("Langkah mitigasi",
                       _bullet_list(mitigations, "var(--green)"))
        + f'<div><div style="font-size:10.5px;color:var(--text-muted);letter-spacing:.07em;'
        f'text-transform:uppercase;margin-bottom:5px;font-weight:600;">Rekomendasi</div>{recom_html}</div>'
    )
    _render_html(_section_wrap("⚠️", "Risk Review", body, open_default=True))


def _render_clauses(clauses: list):
    if not clauses:
        body = _empty_state(
            "📜",
            "Tidak ada pasal yang ditemukan dalam dokumen.<br>"
            "<span style='font-size:11.5px;'>Pastikan knowledge base memuat teks lengkap undang-undang yang relevan.</span>"
        )
        _render_html(_section_wrap("📜", "Pasal terkait", body, empty=True))
        return

    rows = []
    for i, clause in enumerate(clauses):
        article = clause.get("article") or None
        topic = clause.get("clause_topic") or "—"
        source = clause.get("source_name") or ""
        excerpt = clause.get("excerpt") or ""
        relev = clause.get("relevance") or ""
        sep = "" if i == len(
            clauses) - 1 else "border-bottom:0.5px solid rgba(240,237,232,0.07);"

        if article:
            art_html = (
                f'<span style="font-size:13px;font-weight:500;color:var(--text-primary);">{article}</span>'
            )
        else:
            art_html = (
                f'<span style="background:rgba(232,147,74,0.1);color:var(--orange);'
                f'font-size:11px;padding:2px 8px;border-radius:5px;display:inline-block;margin-bottom:4px;">'
                f'⚠ Nomor pasal perlu diverifikasi</span>'
            )

        source_html = (
            f'<div style="font-size:11.5px;color:var(--text-muted);margin-bottom:3px;">'
            f'Sumber: {source}</div>'
        ) if source else ""

        excerpt_html = (
            f'<div style="font-size:12px;color:var(--text-muted);font-style:italic;margin-bottom:4px;">'
            f'&ldquo;{excerpt}&rdquo;</div>'
        ) if excerpt else ""

        relev_html = (
            f'<div style="font-size:12px;color:var(--text-secondary);background:var(--surface-2);'
            f'border-radius:6px;padding:5px 9px;line-height:1.55;">Relevansi: {relev}</div>'
        ) if relev else ""

        note_html = ""
        if not article:
            note_html = (
                f'<div style="font-size:11px;color:var(--text-muted);margin-top:6px;">'
                f'💡 Nomor pasal tidak ditemukan dalam dokumen. Lengkapi knowledge base dengan teks lengkap UU.</div>'
            )

        rows.append(
            f'<div style="padding:10px 0;{sep}">'
            f'<div style="margin-bottom:3px;">{art_html}</div>'
            f'<div style="font-size:13px;color:var(--text-primary);font-weight:500;margin-bottom:4px;">{topic}</div>'
            f'{source_html}{excerpt_html}{relev_html}{note_html}</div>'
        )
    body = "".join(rows)
    _render_html(_section_wrap("📜", "Pasal terkait", body,
                 count=len(clauses), open_default=True))


def _render_timeline(timeline: list):
    if not timeline:
        body = _empty_state(
            "🕐",
            "Tidak ada data kronologi untuk pertanyaan ini.<br>"
            "<span style='font-size:11.5px;'>Timeline muncul ketika konteks dokumen memuat kejadian atau tanggal yang bisa diurutkan.</span>"
        )
        _render_html(_section_wrap("🕐", "Timeline hukum", body, empty=True))
        return

    rows = []
    for i, item in enumerate(timeline):
        date = item.get("date_or_period") or "—"
        event = item.get("event") or "—"
        relev = item.get("relevance") or ""
        sep = "" if i == len(
            timeline) - 1 else "border-bottom:0.5px solid rgba(240,237,232,0.07);"
        relev_html = (
            f'<div style="font-size:11px;color:var(--text-muted);margin-top:3px;">{relev}</div>'
        ) if relev else ""
        rows.append(
            f'<div style="display:flex;gap:12px;padding:8px 0;{sep}align-items:flex-start;">'
            f'<div style="width:7px;height:7px;border-radius:50%;background:var(--gold-dim);'
            f'flex-shrink:0;margin-top:5px;"></div>'
            f'<div><div style="font-size:11.5px;font-weight:600;color:var(--gold-dim);margin-bottom:2px;">{date}</div>'
            f'<div style="font-size:13px;color:var(--text-secondary);line-height:1.6;">{event}</div>'
            f'{relev_html}</div></div>'
        )
    body = "".join(rows)
    _render_html(_section_wrap("🕐", "Timeline hukum", body,
                 count=len(timeline), open_default=True))


def _render_comparisons(comparisons: list):
    if not comparisons:
        body = _empty_state(
            "⚖️",
            "Tidak ada perbandingan ketentuan yang dihasilkan.<br>"
            "<span style='font-size:11.5px;'>Bagian ini aktif ketika terdapat dua atau lebih undang-undang yang bisa dibandingkan.</span>"
        )
        _render_html(_section_wrap(
            "⚖️", "Perbandingan ketentuan", body, empty=True))
        return

    rows = []
    for i, comp in enumerate(comparisons):
        aspect = comp.get("aspect") or "—"
        src_a = comp.get("source_a") or "—"
        src_b = comp.get("source_b") or "—"
        sims = comp.get("similarities") or []
        diffs = comp.get("differences") or []
        conc = comp.get("conclusion") or ""
        sep = (
            "" if i == len(comparisons) - 1
            else "border-bottom:0.5px solid rgba(240,237,232,0.07);padding-bottom:12px;margin-bottom:4px;"
        )

        def _blist(items):
            return "".join(
                f'<div style="font-size:12px;color:var(--text-secondary);margin-bottom:3px;'
                f'display:flex;gap:6px;"><span style="font-size:8px;color:var(--text-muted);'
                f'margin-top:4px;">●</span>{x}</div>'
                for x in items
            ) if items else '<span style="font-size:12px;color:var(--text-muted);font-style:italic;">—</span>'

        conc_html = (
            f'<div style="font-size:12px;color:var(--text-muted);margin-top:6px;">Kesimpulan: {conc}</div>'
        ) if conc else ""

        rows.append(
            f'<div style="{sep}padding-top:8px;">'
            f'<div style="font-size:13px;font-weight:500;color:var(--text-primary);margin-bottom:10px;">{aspect}</div>'
            f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px;">'
            f'<div><div style="font-size:10px;font-weight:600;color:var(--text-muted);text-transform:uppercase;'
            f'letter-spacing:.06em;margin-bottom:4px;">Ketentuan A</div>'
            f'<div style="font-size:13px;color:var(--text-secondary);line-height:1.6;">{src_a}</div></div>'
            f'<div><div style="font-size:10px;font-weight:600;color:var(--text-muted);text-transform:uppercase;'
            f'letter-spacing:.06em;margin-bottom:4px;">Ketentuan B</div>'
            f'<div style="font-size:13px;color:var(--text-secondary);line-height:1.6;">{src_b}</div></div></div>'
            f'<div style="margin-bottom:8px;">'
            f'<div style="font-size:10px;font-weight:600;color:var(--text-muted);text-transform:uppercase;'
            f'letter-spacing:.06em;margin-bottom:4px;">Persamaan</div>{_blist(sims)}</div>'
            f'<div style="margin-bottom:6px;">'
            f'<div style="font-size:10px;font-weight:600;color:var(--text-muted);text-transform:uppercase;'
            f'letter-spacing:.06em;margin-bottom:4px;">Perbedaan</div>{_blist(diffs)}</div>'
            f'{conc_html}</div>'
        )
    body = "".join(rows)
    _render_html(_section_wrap("⚖️", "Perbandingan ketentuan",
                 body, count=len(comparisons), open_default=True))


def _render_referensi(referensi: list):
    if not referensi:
        body = _empty_state(
            "📚",
            "Tidak ada referensi undang-undang spesifik yang ditemukan.<br>"
            "<span style='font-size:11.5px;'>Pastikan knowledge base memuat dokumen hukum yang relevan.</span>"
        )
        _render_html(_section_wrap(
            "📚", "Referensi undang-undang", body, empty=True))
        return

    rows = []
    for i, ref in enumerate(referensi):
        source = ref.get("source_name") or "—"
        article = ref.get("article") or "—"
        excerpt = ref.get("excerpt") or ""
        relev = ref.get("relevance") or ""
        sep = "" if i == len(
            referensi) - 1 else "border-bottom:0.5px solid rgba(240,237,232,0.07);"

        excerpt_html = (
            f'<div style="font-size:12px;color:var(--text-muted);margin-top:3px;'
            f'font-style:italic;">&ldquo;{excerpt}&rdquo;</div>'
        ) if excerpt else ""

        relev_html = (
            f'<div style="font-size:12px;color:var(--text-secondary);margin-top:5px;'
            f'background:var(--surface-2);border-radius:6px;padding:5px 9px;">Relevansi: {relev}</div>'
        ) if relev else ""

        rows.append(
            f'<div style="padding:8px 0;{sep}">'
            f'<div style="font-size:13px;font-weight:500;color:var(--text-primary);">'
            f'{source} — Pasal {article}</div>'
            f'{excerpt_html}{relev_html}</div>'
        )
    body = "".join(rows)
    _render_html(_section_wrap("📚", "Referensi undang-undang",
                 body, count=len(referensi), open_default=True))


# =============================================================================
# MATERIAL RESULT (top-level dispatcher)
# =============================================================================

def render_material_result(material: dict, rag_info: dict):
    """Render full material result with header and all sections."""
    sources_count = rag_info.get("sources_count", 0)
    has_context = rag_info.get("has_context", False)
    query_used = rag_info.get("query_used", "")

    st.markdown('<div class="ac-divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="result-header">📋 Hasil Analisis Hukum</div>',
                unsafe_allow_html=True)
    st.markdown(
        f"""
        <div style="margin-bottom:16px;display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
            <span class="info-pill">🔍 {query_used or '—'}</span>
            <span class="info-pill">📚 {sources_count} chunk ditemukan</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not has_context or not material:
        st.warning(
            "⚠️ Tidak ditemukan referensi hukum yang relevan. "
            "Pastikan knowledge base sudah berisi dokumen hukum yang sesuai."
        )
        return

    _render_summary(material.get("summary") or {})
    _render_legal_qa(material.get("legal_qa") or [])
    _render_risk_review(material.get("risk_review") or {})
    _render_clauses(material.get("clause_search") or [])
    _render_timeline(material.get("timeline_extraction") or [])
    _render_comparisons(material.get("comparison") or [])
    _render_referensi(material.get("referensi_uu") or [])
