# streamlit_app/components/audio_controls.py

import logging
from pathlib import Path

import requests
import streamlit as st
from streamlit_mic_recorder import mic_recorder

from api.knowledge.knowledge_api import get_knowledgebase_list
from api.evaluasi.evaluation_api import run_ragas_evaluation
from api.prompting.integration_api import process_audio_integrated
from config.settings import settings
from utils.session import (
    get_current_session,
    set_pending_audio_text,
    set_last_rag_result,
    set_last_ragas_result,
    get_last_rag_result,
    get_last_ragas_result,
    get_rag_session_id,
    set_rag_session_id,
    set_ragas_evaluating,
    is_ragas_evaluating,
)

logger = logging.getLogger(__name__)

BASE_URL = settings.API_BASE_URL

_KEY_UPLOAD_BYTES  = "_audio_upload_bytes"
_KEY_UPLOAD_NAME   = "_audio_upload_name"
_KEY_RECORD_BYTES  = "_audio_record_bytes"
_KEY_TRANSCRIPTION = "_audio_transcription"


# =============================================================================
# CSS
# =============================================================================

def _inject_styles():
    css_path = Path("streamlit_app/assets/styles/main.css")
    with open(css_path, "r", encoding="utf-8") as f:
        css = f.read()
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)

    # Inject JS helper for collapsible sections
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
# HELPERS
# =============================================================================

def _transcribe(audio_bytes: bytes, filename: str, provider: str) -> tuple[str | None, str | None]:
    try:
        response = requests.post(
            f"{BASE_URL}/prompting/audio/process",
            files={"file": (filename, audio_bytes)},
            data={"provider": provider},
            timeout=60,
        )
        data = response.json()
        if response.status_code != 200:
            detail = data.get("detail", data.get("error", response.text))
            return None, f"Server error {response.status_code}: {detail}"
        if "error" in data:
            return None, data["error"]
        return data.get("transcription", ""), None
    except requests.exceptions.ConnectionError:
        return None, "Tidak dapat terhubung ke server. Pastikan backend berjalan."
    except requests.exceptions.Timeout:
        return None, "Request timeout. Coba file yang lebih pendek."
    except Exception as exc:
        return None, str(exc)


def _score_emoji(score: float | None) -> str:
    if score is None: return "—"
    if score >= 0.8:  return "⬤"
    if score >= 0.6:  return "⬤"
    return "⬤"


def _badge_class(score: float | None) -> str:
    if score is None: return "badge badge-gray"
    if score >= 0.8:  return "badge badge-green"
    if score >= 0.6:  return "badge badge-orange"
    return "badge badge-red"


def _fmt(v: float | None) -> str:
    return f"{v:.2f}" if v is not None else "N/A"


def _section_id(name: str) -> str:
    """Generate a safe HTML id from a section name."""
    return name.replace(" ", "-").lower()


# =============================================================================
# COLLAPSIBLE SECTION WRAPPER
# =============================================================================

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
    arrow_rotate = "rotate(0deg)" if (open_default and not empty) else "rotate(-90deg)"

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

        # Header / toggle button
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

        # Body
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


# =============================================================================
# RAGAS STRIP (improved with explain toggle)
# =============================================================================

def _render_ragas_strip(ragas_result: dict):
    if not ragas_result or ragas_result.get("status") == "error":
        st.warning(f"⚠️ Evaluasi RAGAS gagal: {ragas_result.get('error', 'Unknown error')}")
        return

    metrics = ragas_result.get("metrics", {})
    if not metrics:
        return

    faith  = metrics.get("faithfulness")
    relev  = metrics.get("answer_relevancy")
    risk_f = metrics.get("risk_faithfulness")
    segments = metrics.get("evaluated_segments", [])
    ts     = ragas_result.get("timestamp", "")

    # ── Badge strip ──────────────────────────────────────────────────────────
    seg_labels = {"faithfulness": "Summary", "qa": "QA", "risk": "Risk"}
    seg_html = " ".join(
        f'<span style="background:var(--color-background-info,rgba(93,190,138,.12));'
        f'color:var(--color-text-info,#5dbe8a);padding:2px 7px;border-radius:4px;font-size:10.5px;">'
        f'{seg_labels.get(s, s)}</span>'
        for s in segments
    ) if segments else ""

    seg_part = (
        f'<span class="ragas-label" style="margin-left:4px;">Segmen</span>{seg_html} '
        if seg_html else ""
    )

    st.markdown(
        f'<div class="ragas-strip">'
        f'<span class="ragas-label">📊 Kualitas RAG</span>'
        f'<span class="{_badge_class(faith)}">{_score_emoji(faith)} Faithfulness &nbsp;{_fmt(faith)}</span>'
        f'<span class="{_badge_class(relev)}">{_score_emoji(relev)} Relevancy &nbsp;{_fmt(relev)}</span>'
        f'<span class="{_badge_class(risk_f)}">{_score_emoji(risk_f)} Risk Faith &nbsp;{_fmt(risk_f)}</span>'
        f'{seg_part}'
        f'<span class="ragas-meta" style="margin-left:auto;">{ts}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── Explain section — pakai st.expander (native, tidak butuh JS) ─────────
    explain_parts = []
    if faith is not None and faith < 0.6:
        explain_parts.append(
            f"**Faithfulness {faith:.2f}** — jawaban kurang mengacu pada dokumen hukum. "
            "Ini normal ketika konteks dokumen terbatas atau pertanyaan sangat umum."
        )
    elif faith is not None:
        explain_parts.append(
            f"**Faithfulness {faith:.2f}** — jawaban cukup mengacu pada konteks. "
            "Tambah ground truth untuk evaluasi lebih akurat."
        )

    if relev is not None:
        explain_parts.append(
            f"**Relevancy {relev:.2f}** — seberapa relevan jawaban terhadap pertanyaan asal."
        )

    if not explain_parts:
        explain_parts.append(
            "Tambahkan *ground truth* di Tab Evaluasi untuk hasil evaluasi lebih akurat."
        )

    with st.expander("ℹ️ Apa ini?", expanded=False):
        for part in explain_parts:
            st.markdown(part)
        st.caption("💡 Buka Tab Evaluasi untuk menambah ground truth.")


# =============================================================================
# MATERIAL RESULT (improved UX)
# =============================================================================

def _render_material_result(material: dict, rag_info: dict):
    sources_count = rag_info.get("sources_count", 0)
    has_context   = rag_info.get("has_context", False)
    query_used    = rag_info.get("query_used", "")

    st.markdown('<div class="ac-divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="result-header">📋 Hasil Analisis Hukum</div>', unsafe_allow_html=True)
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
        st.warning("⚠️ Tidak ditemukan referensi hukum yang relevan. Pastikan knowledge base sudah berisi dokumen hukum yang sesuai.")
        return

    _render_summary(material.get("summary") or {})
    _render_legal_qa(material.get("legal_qa") or [])
    _render_risk_review(material.get("risk_review") or {})
    _render_clauses(material.get("clause_search") or [])
    _render_timeline(material.get("timeline_extraction") or [])
    _render_comparisons(material.get("comparison") or [])
    _render_referensi(material.get("referensi_uu") or [])


# =============================================================================
# HELPER HTML ATOMS
# =============================================================================

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
# SUB-RENDER FUNCTIONS
# =============================================================================

def _render_summary(summary: dict):
    title      = summary.get("title") or ""
    overview   = summary.get("overview") or ""
    key_pts    = summary.get("key_points") or []
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
        body = _empty_state("❓", "Tidak ada Q&A yang dihasilkan untuk pertanyaan ini.")
        _render_html(_section_wrap("❓", "Legal Q&A", body, empty=True))
        return

    rows = []
    for i, qa in enumerate(qa_list):
        q = qa.get("question") or "—"
        a = qa.get("answer") or "—"
        sep = "" if i == len(qa_list) - 1 else "border-bottom:0.5px solid rgba(240,237,232,0.07);"
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
    _render_html(_section_wrap("❓", "Legal Q&A", body, count=len(qa_list), open_default=True))


def _render_risk_review(risk: dict):
    status      = risk.get("status") or ""
    score_raw   = risk.get("score")
    analysis    = risk.get("analysis") or ""
    risks       = risk.get("risks") or []
    mitigations = risk.get("mitigation_steps") or []
    recom       = risk.get("recommendation") or ""

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
        _render_html(_section_wrap("⚠️", "Risk Review", body, open_default=True))
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
        "var(--red)"    if score >= 70 else
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
        + _field_block("Langkah mitigasi", _bullet_list(mitigations, "var(--green)"))
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
        topic   = clause.get("clause_topic") or "—"
        source  = clause.get("source_name") or ""
        excerpt = clause.get("excerpt") or ""
        relev   = clause.get("relevance") or ""
        sep     = "" if i == len(clauses) - 1 else "border-bottom:0.5px solid rgba(240,237,232,0.07);"

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

        source_html  = (
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
    _render_html(_section_wrap("📜", "Pasal terkait", body, count=len(clauses), open_default=True))


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
        date  = item.get("date_or_period") or "—"
        event = item.get("event") or "—"
        relev = item.get("relevance") or ""
        sep   = "" if i == len(timeline) - 1 else "border-bottom:0.5px solid rgba(240,237,232,0.07);"
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
    _render_html(_section_wrap("🕐", "Timeline hukum", body, count=len(timeline), open_default=True))


def _render_comparisons(comparisons: list):
    if not comparisons:
        body = _empty_state(
            "⚖️",
            "Tidak ada perbandingan ketentuan yang dihasilkan.<br>"
            "<span style='font-size:11.5px;'>Bagian ini aktif ketika terdapat dua atau lebih undang-undang yang bisa dibandingkan.</span>"
        )
        _render_html(_section_wrap("⚖️", "Perbandingan ketentuan", body, empty=True))
        return

    rows = []
    for i, comp in enumerate(comparisons):
        aspect = comp.get("aspect") or "—"
        src_a  = comp.get("source_a") or "—"
        src_b  = comp.get("source_b") or "—"
        sims   = comp.get("similarities") or []
        diffs  = comp.get("differences") or []
        conc   = comp.get("conclusion") or ""
        sep    = (
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
    _render_html(_section_wrap("⚖️", "Perbandingan ketentuan", body, count=len(comparisons), open_default=True))


def _render_referensi(referensi: list):
    if not referensi:
        body = _empty_state(
            "📚",
            "Tidak ada referensi undang-undang spesifik yang ditemukan.<br>"
            "<span style='font-size:11.5px;'>Pastikan knowledge base memuat dokumen hukum yang relevan.</span>"
        )
        _render_html(_section_wrap("📚", "Referensi undang-undang", body, empty=True))
        return

    rows = []
    for i, ref in enumerate(referensi):
        source  = ref.get("source_name") or "—"
        article = ref.get("article") or "—"
        excerpt = ref.get("excerpt") or ""
        relev   = ref.get("relevance") or ""
        sep     = "" if i == len(referensi) - 1 else "border-bottom:0.5px solid rgba(240,237,232,0.07);"

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
    _render_html(_section_wrap("📚", "Referensi undang-undang", body, count=len(referensi), open_default=True))


# =============================================================================
# MAIN RENDER
# =============================================================================

def render_audio_controls():
    _inject_styles()

    st.markdown(
        """
        <div style="margin-top:8px;margin-bottom:4px;">
            <div class="ac-header">🎙️ Audio ke Analisis Hukum</div>
            <div class="ac-subheader">
                Upload atau rekam audio — sistem akan mentranskrip, mencari referensi hukum,
                dan menghasilkan analisis SPK secara otomatis.
            </div>
        </div>
        <div class="ac-divider"></div>
        """,
        unsafe_allow_html=True,
    )

    col_provider, col_kb = st.columns([1, 2])

    with col_provider:
        st.markdown('<div class="ac-label">Provider STT</div>', unsafe_allow_html=True)
        provider = st.selectbox(
            "Provider STT", ["whisper", "elevenlabs"],
            label_visibility="collapsed",
            help="Whisper (Groq) — cepat & gratis. ElevenLabs — akurasi tinggi.",
        )

    with col_kb:
        st.markdown('<div class="ac-label">Knowledge Base</div>', unsafe_allow_html=True)
        kb_list = get_knowledgebase_list()
        st.session_state["kb_list"] = kb_list

        kb_col, refresh_col = st.columns([4, 1], vertical_alignment="bottom")
        with kb_col:
            knowledge_base = st.selectbox(
                "Knowledge Base",
                options=kb_list if kb_list else [],
                index=0 if kb_list else None,
                placeholder="Tidak ada KB tersedia" if not kb_list else None,
                label_visibility="collapsed",
                help="Pilih collection Qdrant yang relevan.",
            )
        with refresh_col:
            if st.button("🔄", use_container_width=True, key="btn_refresh_kb", help="Refresh KB"):
                st.session_state["kb_list"] = get_knowledgebase_list()
                st.rerun()

    st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

    tab_upload, tab_record = st.tabs(["  📂  Upload File  ", "  🔴  Rekam Langsung  "])

    # ── TAB UPLOAD ────────────────────────────────────────────────────────────
    with tab_upload:
        st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)
        uploaded_audio = st.file_uploader(
            "Seret & lepas file audio di sini, atau klik untuk memilih",
            type=["mp3", "wav", "m4a", "ogg", "webm"],
            key="audio_file_uploader",
        )
        if uploaded_audio is not None:
            st.session_state[_KEY_UPLOAD_BYTES] = uploaded_audio.read()
            st.session_state[_KEY_UPLOAD_NAME]  = uploaded_audio.name

        upload_bytes = st.session_state.get(_KEY_UPLOAD_BYTES)
        upload_name  = st.session_state.get(_KEY_UPLOAD_NAME, "audio.wav")

        if upload_bytes:
            st.audio(upload_bytes)
            col_rag, col_stt, col_clear = st.columns([3, 2, 1])
            with col_rag:
                process_rag = st.button(
                    "🚀  Proses RAG & Evaluasi", use_container_width=True,
                    key="btn_rag_upload", type="primary",
                    help="STT → RAG → Generate Material → Evaluasi RAGAS otomatis",
                )
            with col_stt:
                transcribe_only = st.button(
                    "📝  Transkripsi Saja", use_container_width=True, key="btn_transcribe_upload",
                )
            with col_clear:
                if st.button("🗑️", use_container_width=True, key="btn_clear_upload", help="Hapus file"):
                    st.session_state.pop(_KEY_UPLOAD_BYTES, None)
                    st.session_state.pop(_KEY_UPLOAD_NAME, None)
                    st.session_state.pop(_KEY_TRANSCRIPTION, None)
                    st.rerun()

            if process_rag:
                _run_rag_pipeline(upload_bytes, upload_name, provider, knowledge_base)
            if transcribe_only:
                st.session_state.pop(_KEY_TRANSCRIPTION, None)
                with st.spinner("Sedang memproses transkripsi..."):
                    transcription, error = _transcribe(upload_bytes, upload_name, provider)
                if error:
                    st.error(f"⚠️ {error}")
                else:
                    st.session_state[_KEY_TRANSCRIPTION] = transcription
                    st.rerun()

    # ── TAB RECORD ────────────────────────────────────────────────────────────
    with tab_record:
        st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)
        st.caption("Klik **Start** untuk mulai merekam, **Stop** untuk menyelesaikan.")

        audio_data = mic_recorder(
            start_prompt="🔴  Start Rekam", stop_prompt="⏹️  Stop Rekam",
            just_once=True, use_container_width=True, key="mic_recorder",
        )
        if audio_data and audio_data.get("bytes"):
            st.session_state[_KEY_RECORD_BYTES] = audio_data["bytes"]
            st.session_state.pop(_KEY_TRANSCRIPTION, None)

        record_bytes = st.session_state.get(_KEY_RECORD_BYTES)
        if record_bytes:
            st.audio(record_bytes, format="audio/wav")
            col_rag, col_stt, col_clear = st.columns([3, 2, 1])
            with col_rag:
                process_rag_rec = st.button(
                    "🚀  Proses RAG & Evaluasi", use_container_width=True,
                    key="btn_rag_record", type="primary",
                )
            with col_stt:
                transcribe_record = st.button(
                    "📝  Transkripsi Saja", use_container_width=True, key="btn_transcribe_record",
                )
            with col_clear:
                if st.button("🗑️", use_container_width=True, key="btn_clear_record", help="Hapus rekaman"):
                    st.session_state.pop(_KEY_RECORD_BYTES, None)
                    st.session_state.pop(_KEY_TRANSCRIPTION, None)
                    st.rerun()

            if process_rag_rec:
                _run_rag_pipeline(record_bytes, "recording.wav", provider, knowledge_base)
            if transcribe_record:
                st.session_state.pop(_KEY_TRANSCRIPTION, None)
                with st.spinner("Sedang memproses transkripsi rekaman..."):
                    transcription, error = _transcribe(record_bytes, "recording.wav", provider)
                if error:
                    st.error(f"⚠️ {error}")
                else:
                    st.session_state[_KEY_TRANSCRIPTION] = transcription
                    st.rerun()

    # ── Hasil transkripsi ─────────────────────────────────────────────────────
    transcription = st.session_state.get(_KEY_TRANSCRIPTION)
    if transcription is not None:
        _handle_transcription_success(transcription)

    # ── Hasil RAG + RAGAS strip ───────────────────────────────────────────────
    rag_result = get_last_rag_result()
    if rag_result:
        _render_material_result(
            material=rag_result.get("generated_material"),
            rag_info={
                "has_context":   rag_result.get("has_context", False),
                "sources_count": rag_result.get("sources_count", 0),
                "query_used":    rag_result.get("query_used", ""),
            },
        )

        ragas_result = get_last_ragas_result()
        if is_ragas_evaluating():
            st.info("⏳ Evaluasi RAGAS sedang berjalan di latar belakang...")
        elif ragas_result:
            _render_ragas_strip(ragas_result)

        st.caption("💡 Buka **Tab Evaluasi** untuk detail lengkap 4 metrik & tambah ground truth")


# =============================================================================
# CORE PIPELINE
# =============================================================================

def _run_rag_pipeline(audio_bytes: bytes, filename: str, provider: str, knowledge_base: str):
    with st.spinner("⏳ Memproses audio → RAG → Material... (30–90 detik)"):
        rag_response = process_audio_integrated(
            audio_bytes=audio_bytes,
            filename=filename,
            provider=provider,
            knowledge_base=knowledge_base,
            auto_evaluate=False,
            session_id=get_rag_session_id(),
        )

    if rag_response["status"] == "error":
        st.error(f"❌ Pipeline RAG gagal: {rag_response['error']}")
        return

    transcription = rag_response.get("transcription", {})
    material      = rag_response.get("generated_material")
    rag_meta      = rag_response.get("rag", {})
    context       = rag_response.get("raw_context", "")
    question      = transcription.get("repaired") or transcription.get("raw", "")

    set_last_rag_result(
        question=question,
        context=context,
        generated_material=material,
        transcription_raw=transcription.get("raw", ""),
        knowledge_base=knowledge_base,
        sources_count=rag_meta.get("sources_count", 0),
        has_context=rag_meta.get("has_context", False),
        query_used=rag_meta.get("query_used", question),
        history_id=rag_response.get("history_id"),
        session_id=rag_response.get("session_id"),
    )
    set_rag_session_id(rag_response.get("session_id") or get_rag_session_id())

    if context and material:
        set_ragas_evaluating(True)
        with st.spinner("📊 Mengevaluasi kualitas RAG dengan RAGAS..."):
            ragas_response = run_ragas_evaluation(
                question=question,
                context=context,
                material_dict=material,
                ground_truth=None,
                history_id=rag_response.get("history_id"),
            )
        set_last_ragas_result(ragas_response)
        set_ragas_evaluating(False)
    else:
        st.warning(
            "⚠️ Evaluasi RAGAS dilewati — "
            + ("context kosong. " if not context else "")
            + ("material kosong." if not material else "")
        )
        set_ragas_evaluating(False)

    st.session_state["_force_refresh_history"] = True
    st.session_state.pop("_db_history_cache", None)
    st.rerun()


# =============================================================================
# HELPER
# =============================================================================

def _handle_transcription_success(transcription: str):
    st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
    st.success("✅ Transkripsi berhasil!")
    st.text_area("Hasil Transkripsi:", value=transcription, height=150, key="transcription_preview")