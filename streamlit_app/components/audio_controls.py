"""
streamlit_app/components/audio_controls.py  (updated - UI Redesign)

Perubahan dari versi lama:
- Tambah tombol "Proses RAG & Evaluasi" yang memanggil integration pipeline
- Tampilkan hasil material SPK hukum setelah pipeline selesai
- Jalankan evaluasi RAGAS otomatis setelah material diterima
- Tampilkan RAGAS strip kecil di bawah material
- Simpan semua hasil ke session_state agar Tab Evaluasi bisa auto-populate
- UI/UX redesign: elegant, refined, professional legal-tech aesthetic
"""

import streamlit as st
import requests
from streamlit_mic_recorder import mic_recorder
from api.knowledge.knowledge_api import get_knowledgebase_list

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

from api.evaluasi.evaluation_api import run_ragas_evaluation
from config.settings import settings
from api.prompting.integration_api import process_audio_integrated


BASE_URL = settings.API_BASE_URL

# ── Session State Keys ────────────────────────────────────────────────────────
_KEY_UPLOAD_BYTES  = "_audio_upload_bytes"
_KEY_UPLOAD_NAME   = "_audio_upload_name"
_KEY_RECORD_BYTES  = "_audio_record_bytes"
_KEY_TRANSCRIPTION = "_audio_transcription"


# ── CSS Injection ─────────────────────────────────────────────────────────────
def _inject_styles():
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@300;400;500;600&display=swap');

        /* ── Root Variables — Dark Theme ── */
        :root {
            --gold:        #D4A853;
            --gold-light:  #F0CC80;
            --gold-dim:    #C49A3C;
            --gold-glow:   rgba(212,168,83,0.18);
            --text-primary:   #F0EDE8;
            --text-secondary: #A89F93;
            --text-muted:     #6B6460;
            --surface-0:   #0D0D0D;
            --surface-1:   #161616;
            --surface-2:   #1E1E1E;
            --surface-3:   #272727;
            --border:      rgba(212,168,83,0.22);
            --border-soft: rgba(240,237,232,0.08);
            --shadow:      0 4px 24px rgba(0,0,0,0.5);
            --shadow-lg:   0 12px 48px rgba(0,0,0,0.7);
            --green:       #5DBE8A;
            --orange:      #E8934A;
            --red:         #E06070;
            --green-bg:    rgba(93,190,138,0.12);
            --orange-bg:   rgba(232,147,74,0.12);
            --red-bg:      rgba(224,96,112,0.12);
            --radius: 12px;
        }

        /* ── Section Header ── */
        .ac-header {
            font-family: 'DM Serif Display', Georgia, serif;
            font-size: 1.55rem;
            color: var(--text-primary);
            letter-spacing: -0.02em;
            margin-bottom: 2px;
            line-height: 1.2;
        }
        .ac-subheader {
            font-family: 'DM Sans', sans-serif;
            font-size: 0.82rem;
            color: var(--text-secondary);
            font-weight: 400;
            margin-bottom: 18px;
            letter-spacing: 0.01em;
        }

        /* ── Divider ── */
        .ac-divider {
            height: 1px;
            background: linear-gradient(90deg, transparent, var(--gold), transparent);
            margin: 20px 0;
            opacity: 0.6;
        }

        /* ── Card wrapper ── */
        .ac-card {
            background: var(--surface-1);
            border: 1px solid var(--border);
            border-radius: var(--radius);
            padding: 20px 22px;
            box-shadow: var(--shadow);
            margin-bottom: 16px;
        }

        /* ── Select label override ── */
        .ac-label {
            font-family: 'DM Sans', sans-serif;
            font-size: 0.72rem;
            font-weight: 600;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            color: var(--gold-dim);
            margin-bottom: 4px;
        }

        /* ── Action buttons ── */
        div[data-testid="stButton"] > button {
            font-family: 'DM Sans', sans-serif !important;
            font-weight: 500 !important;
            letter-spacing: 0.02em !important;
            border-radius: 8px !important;
            transition: all 0.18s ease !important;
        }
        div[data-testid="stButton"] > button[kind="primary"] {
            background: linear-gradient(135deg, #D4A853 0%, #B8873A 100%) !important;
            border: none !important;
            color: #0D0D0D !important;
            font-weight: 700 !important;
            box-shadow: 0 2px 16px rgba(212,168,83,0.4) !important;
        }
        div[data-testid="stButton"] > button[kind="primary"]:hover {
            box-shadow: 0 4px 28px rgba(212,168,83,0.6) !important;
            transform: translateY(-1px) !important;
        }
        div[data-testid="stButton"] > button:not([kind="primary"]) {
            background: var(--surface-2) !important;
            border: 1px solid var(--border-soft) !important;
            color: var(--text-secondary) !important;
        }
        div[data-testid="stButton"] > button:not([kind="primary"]):hover {
            border-color: var(--gold) !important;
            color: var(--text-primary) !important;
            background: var(--surface-3) !important;
        }

        /* ── Tabs ── */
        div[data-testid="stTabs"] button[role="tab"] {
            font-family: 'DM Sans', sans-serif !important;
            font-size: 0.82rem !important;
            font-weight: 500 !important;
            letter-spacing: 0.04em !important;
            color: var(--text-muted) !important;
        }
        div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
            color: var(--gold-light) !important;
            border-bottom: 2px solid var(--gold) !important;
        }

        /* ── Analysis section header ── */
        .result-header {
            font-family: 'DM Serif Display', serif;
            font-size: 1.25rem;
            color: var(--text-primary);
            letter-spacing: -0.01em;
            padding: 14px 0 6px 0;
            border-bottom: 1px solid var(--border);
            margin-bottom: 14px;
        }

        /* ── RAGAS strip ── */
        .ragas-strip {
            background: var(--surface-2);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 10px 16px;
            margin-top: 12px;
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            gap: 8px;
            font-family: 'DM Sans', sans-serif;
            font-size: 12px;
        }
        .ragas-label {
            color: var(--text-secondary);
            font-weight: 600;
            letter-spacing: 0.05em;
            margin-right: 4px;
        }
        .badge {
            padding: 3px 10px;
            border-radius: 6px;
            font-weight: 600;
            font-size: 11.5px;
            letter-spacing: 0.02em;
        }
        .badge-green  { background: var(--green-bg);  color: var(--green);  border: 1px solid rgba(93,190,138,0.25); }
        .badge-orange { background: var(--orange-bg); color: var(--orange); border: 1px solid rgba(232,147,74,0.25); }
        .badge-red    { background: var(--red-bg);    color: var(--red);    border: 1px solid rgba(224,96,112,0.25); }
        .badge-gray   { background: rgba(255,255,255,0.06); color: var(--text-secondary); border: 1px solid var(--border-soft); }
        .ragas-meta {
            color: var(--text-muted);
            margin-left: auto;
            font-size: 10.5px;
        }

        /* ── Metric cards ── */
        .metric-row {
            display: flex;
            gap: 12px;
            margin: 12px 0;
        }
        .metric-card {
            flex: 1;
            background: var(--surface-2);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 12px 14px;
            text-align: center;
        }
        .metric-card .metric-label {
            font-family: 'DM Sans', sans-serif;
            font-size: 10px;
            font-weight: 600;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            color: var(--text-muted);
            margin-bottom: 4px;
        }
        .metric-card .metric-value {
            font-family: 'DM Serif Display', serif;
            font-size: 1.4rem;
            color: var(--text-primary);
        }

        /* ── Section label inside results ── */
        .section-label {
            font-family: 'DM Sans', sans-serif;
            font-size: 10.5px;
            font-weight: 700;
            letter-spacing: 0.1em;
            text-transform: uppercase;
            color: var(--gold);
            margin: 16px 0 6px 0;
        }

        /* ── Info pill ── */
        .info-pill {
            display: inline-block;
            background: var(--gold-glow);
            border: 1px solid rgba(212,168,83,0.35);
            color: var(--gold-light);
            border-radius: 20px;
            padding: 3px 12px;
            font-family: 'DM Sans', sans-serif;
            font-size: 11.5px;
            font-weight: 500;
            margin-right: 6px;
            margin-bottom: 4px;
        }

        /* ── Expander override ── */
        details summary {
            font-family: 'DM Sans', sans-serif !important;
            font-weight: 500 !important;
            font-size: 0.88rem !important;
            color: var(--text-secondary) !important;
        }

        /* ── Text area ── */
        div[data-testid="stTextArea"] textarea {
            font-family: 'DM Sans', sans-serif !important;
            font-size: 0.9rem !important;
            border-radius: 8px !important;
            border-color: var(--border-soft) !important;
            background: var(--surface-2) !important;
            color: var(--text-primary) !important;
        }
        div[data-testid="stTextArea"] textarea:focus {
            border-color: var(--gold) !important;
            box-shadow: 0 0 0 2px rgba(212,168,83,0.2) !important;
        }

        /* ── File uploader ── */
        div[data-testid="stFileUploader"] {
            border-radius: var(--radius) !important;
        }
        div[data-testid="stFileUploadDropzone"] {
            border: 2px dashed rgba(212,168,83,0.3) !important;
            border-radius: var(--radius) !important;
            background: var(--surface-1) !important;
            transition: border-color 0.2s, background 0.2s !important;
        }
        div[data-testid="stFileUploadDropzone"]:hover {
            border-color: var(--gold) !important;
            background: var(--gold-glow) !important;
        }

        /* ── Selectbox ── */
        div[data-testid="stSelectbox"] > div > div {
            border-radius: 8px !important;
            border-color: var(--border-soft) !important;
            background-color: var(--surface-2) !important;
            color: var(--text-primary) !important;
            font-family: 'DM Sans', sans-serif !important;
        }

        /* ── Progress bar ── */
        div[data-testid="stProgress"] > div > div {
            background: linear-gradient(90deg, var(--gold), var(--gold-dim)) !important;
            border-radius: 4px !important;
        }
        div[data-testid="stProgress"] > div {
            background: var(--surface-3) !important;
            border-radius: 4px !important;
        }

        /* ── Caption override ── */
        div[data-testid="stCaptionContainer"] p {
            font-family: 'DM Sans', sans-serif !important;
            font-size: 0.78rem !important;
            color: var(--text-muted) !important;
        }

        /* ── Audio player ── */
        div[data-testid="stAudio"] audio {
            border-radius: 8px !important;
            width: 100% !important;
        }

        /* ── Alert boxes ── */
        div[data-testid="stAlert"] {
            border-radius: 10px !important;
            font-family: 'DM Sans', sans-serif !important;
            border-left-color: var(--gold) !important;
        }

        /* ── Metric widget ── */
        div[data-testid="stMetric"] label {
            color: var(--text-muted) !important;
            font-family: 'DM Sans', sans-serif !important;
            font-size: 0.75rem !important;
            letter-spacing: 0.06em !important;
            text-transform: uppercase !important;
        }
        div[data-testid="stMetricValue"] {
            color: var(--text-primary) !important;
            font-family: 'DM Serif Display', serif !important;
        }

        /* ── Spinner ── */
        div[data-testid="stSpinner"] p {
            color: var(--text-secondary) !important;
            font-family: 'DM Sans', sans-serif !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ── Helper: transkripsi saja (endpoint lama, tetap dipakai) ───────────────────
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
    except Exception as e:
        return None, str(e)


# ── Helper: warna & badge RAGAS ───────────────────────────────────────────────
def _score_color(score: float | None) -> str:
    if score is None:
        return "gray"
    if score >= 0.8:
        return "green"
    if score >= 0.6:
        return "orange"
    return "red"


def _score_emoji(score: float | None) -> str:
    if score is None:
        return "⬜"
    if score >= 0.8:
        return "🟢"
    if score >= 0.6:
        return "🟡"
    return "🔴"


def _badge_class(score: float | None) -> str:
    if score is None:
        return "badge badge-gray"
    if score >= 0.8:
        return "badge badge-green"
    if score >= 0.6:
        return "badge badge-orange"
    return "badge badge-red"


# ── Helper: render RAGAS strip di bawah material ──────────────────────────────
def _render_ragas_strip(ragas_result: dict):
    if not ragas_result or ragas_result.get("status") == "error":
        st.warning(f"⚠️ Evaluasi RAGAS gagal: {ragas_result.get('error', 'Unknown error')}")
        return

    metrics = ragas_result.get("metrics", {})
    if not metrics:
        return

    faith   = metrics.get("faithfulness")
    relev   = metrics.get("answer_relevancy")
    overall = metrics.get("overall_score")
    ts      = ragas_result.get("timestamp", "")

    def _fmt(v):
        return f"{v:.2f}" if v is not None else "N/A"

    st.markdown(
        f"""
        <div class="ragas-strip">
            <span class="ragas-label">📊 Kualitas RAG</span>
            <span class="{_badge_class(faith)}">
                {_score_emoji(faith)} Faithfulness &nbsp;{_fmt(faith)}
            </span>
            <span class="{_badge_class(relev)}">
                {_score_emoji(relev)} Relevancy &nbsp;{_fmt(relev)}
            </span>
            <span class="{_badge_class(overall)}">
                {_score_emoji(overall)} Overall &nbsp;{_fmt(overall)}
            </span>
            <span class="ragas-meta">Detail lengkap → Tab Evaluasi &nbsp;·&nbsp; {ts}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ── Helper: render hasil material SPK ────────────────────────────────────────
def _render_material_result(material: dict, rag_info: dict):
    """Tampilkan hasil generate material dari pipeline RAG."""
    st.markdown("---")
    st.markdown("### 📋 Hasil Analisis Hukum (SPK)")

    # Info sumber
    sources_count = rag_info.get("sources_count", 0)
    has_context = rag_info.get("has_context", False)
    query_used = rag_info.get("query_used", "")

    col_a, col_b = st.columns(2)
    with col_a:
        st.caption(f"🔍 Query: *{query_used}*")
    with col_b:
        st.caption(f"📚 Sumber ditemukan: {sources_count} chunk")

    if not has_context or not material:
        st.warning("⚠️ Tidak ditemukan referensi hukum yang relevan.")
        return

    # Kartu material
    decision = material.get("decision_status", "-")
    score = material.get("compliance_score", 0)
    recommendation = material.get("recommendation", "-")
    risk_analysis = material.get("risk_analysis", [])
    legal_basis = material.get("legal_basis", [])

    # Status keputusan
    status_color = "success" if "MATUHI" in decision.upper() else "error"
    if status_color == "success":
        st.success(f"✅ **{decision}**")
    else:
        st.error(f"❌ **{decision}**")

    # Skor kepatuhan
    st.metric("Skor Kepatuhan", f"{score} / 100")
    st.progress(min(int(score), 100) / 100)

    # Rekomendasi
    with st.expander("💡 Rekomendasi Tindakan", expanded=True):
        st.write(recommendation)

    # Analisis risiko
    if risk_analysis:
        with st.expander("⚠️ Analisis Risiko"):
            for risk in risk_analysis:
                st.markdown(f"- {risk}")

    # Dasar hukum
    if legal_basis:
        with st.expander("📜 Dasar Hukum"):
            for basis in legal_basis:
                st.markdown(f"- {basis}")


# ── MAIN RENDER ───────────────────────────────────────────────────────────────
def render_audio_controls():

    st.divider()
    st.subheader("🎙️ Audio ke Analisis Hukum")
    st.caption("Upload atau rekam audio — sistem akan mentranskrip, mencari referensi hukum, dan menghasilkan analisis SPK otomatis.")

    # ── Provider & Knowledge Base ─────────────────────────────────────────────
    col_provider, col_kb = st.columns([1, 2])

    with col_provider:
        st.markdown('<div class="ac-label">Provider STT</div>', unsafe_allow_html=True)
        provider = st.selectbox(
            "Provider STT",
            ["whisper", "elevenlabs"],
            label_visibility="collapsed",
            help="Whisper (Groq) — cepat & gratis. ElevenLabs — akurasi tinggi.",
        )

    with col_kb:
        st.markdown('<div class="ac-label">Knowledge Base</div>', unsafe_allow_html=True)
        st.session_state["kb_list"] = get_knowledgebase_list()
        kb_list = st.session_state["kb_list"]
        kb_list = get_knowledgebase_list()

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
            if st.button("🔄", use_container_width=True, key="btn_refresh_kb", help="Refresh Knowledge Base"):
                st.session_state["kb_list"] = get_knowledgebase_list()
                st.rerun()

    st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

    # ── Tabs: Upload / Record ─────────────────────────────────────────────────
    tab_upload, tab_record = st.tabs(["  📂  Upload File  ", "  🔴  Rekam Langsung  "])

    # ── TAB UPLOAD ────────────────────────────────────────────────────────────
    with tab_upload:
        st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)
        uploaded_audio = st.file_uploader(
            "Seret & lepas file audio di sini, atau klik untuk memilih",
            type=["mp3", "wav", "m4a", "ogg", "webm"],
            label_visibility="visible",
            key="audio_file_uploader",
        )

        if uploaded_audio is not None:
            st.session_state[_KEY_UPLOAD_BYTES] = uploaded_audio.read()
            st.session_state[_KEY_UPLOAD_NAME]  = uploaded_audio.name

        upload_bytes = st.session_state.get(_KEY_UPLOAD_BYTES)
        upload_name  = st.session_state.get(_KEY_UPLOAD_NAME, "audio.wav")

        if upload_bytes:
            st.markdown("<div style='height:4px;'></div>", unsafe_allow_html=True)
            st.audio(upload_bytes)
            st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

            col_rag, col_stt, col_clear = st.columns([3, 2, 1])

            with col_rag:
                process_rag = st.button(
                    "🚀 Proses RAG & Evaluasi",
                    use_container_width=True,
                    key="btn_rag_upload",
                    type="primary",
                    help="STT → RAG → Generate Material → Evaluasi RAGAS otomatis",
                )

            with col_stt:
                # Tombol lama — hanya transkripsi
                transcribe_only = st.button(
                    "📝 Transkripsi Saja",
                    use_container_width=True,
                    key="btn_transcribe_upload",
                )

            with col_clear:
                if st.button("🗑️", use_container_width=True, key="btn_clear_upload"):
                    st.session_state.pop(_KEY_UPLOAD_BYTES, None)
                    st.session_state.pop(_KEY_UPLOAD_NAME, None)
                    st.session_state.pop(_KEY_TRANSCRIPTION, None)
                    st.rerun()

            # ── Proses RAG lengkap ─────────────────────────────────────────
            if process_rag:
                _run_rag_pipeline(upload_bytes, upload_name, provider, knowledge_base)

            # ── Transkripsi saja (flow lama) ───────────────────────────────
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
            start_prompt="🔴  Start Rekam",
            stop_prompt="⏹️  Stop Rekam",
            just_once=True,
            use_container_width=True,
            key="mic_recorder",
        )

        if audio_data and audio_data.get("bytes"):
            st.session_state[_KEY_RECORD_BYTES] = audio_data["bytes"]
            st.session_state.pop(_KEY_TRANSCRIPTION, None)

        record_bytes = st.session_state.get(_KEY_RECORD_BYTES)

        if record_bytes:
            st.markdown("<div style='height:4px;'></div>", unsafe_allow_html=True)
            st.audio(record_bytes, format="audio/wav")
            st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

            col_rag, col_stt, col_clear = st.columns([3, 2, 1])

            with col_rag:
                process_rag_rec = st.button(
                    "🚀 Proses RAG & Evaluasi",
                    use_container_width=True,
                    key="btn_rag_record",
                    type="primary",
                )

            with col_stt:
                transcribe_record = st.button(
                    "📝 Transkripsi Saja",
                    use_container_width=True,
                    key="btn_transcribe_record",
                )

            with col_clear:
                if st.button("🗑️", use_container_width=True, key="btn_clear_record"):
                    st.session_state.pop(_KEY_RECORD_BYTES, None)
                    st.session_state.pop(_KEY_TRANSCRIPTION, None)
                    st.rerun()

            if process_rag_rec:
                _run_rag_pipeline(record_bytes, "recording.wav", provider, knowledge_base)


    # ── Hasil transkripsi saja (flow lama) ────────────────────────────────────
    transcription = st.session_state.get(_KEY_TRANSCRIPTION)
    if transcription is not None:
        _handle_transcription_success(transcription)

    # ── Tampilkan hasil RAG + RAGAS strip (jika ada) ──────────────────────────
    rag_result = get_last_rag_result()
    if rag_result:
        _render_material_result(
            material=rag_result.get("generated_material"),
            rag_info={"has_context": rag_result.get("has_context", False),
                      "sources_count": rag_result.get("sources_count", 0), 
                      "query_used": rag_result.get("query_used", "")
                    },
        )

        # RAGAS strip
        ragas_result = get_last_ragas_result()
        if is_ragas_evaluating():
            st.info("⏳ Evaluasi RAGAS sedang berjalan...")
        elif ragas_result:
            _render_ragas_strip(ragas_result)

        st.caption(
            f"💡 Lihat **Tab Evaluasi** untuk detail lengkap 4 metrik + tambah ground truth."
        )


# ── CORE: pipeline RAG + RAGAS otomatis ──────────────────────────────────────
def _run_rag_pipeline(
    audio_bytes: bytes,
    filename: str,
    provider: str,
    knowledge_base: str,
):
    print(f"[RAG DEBUG] knowledge_base dikirim: '{knowledge_base}'")  # ← tambah ini
    """
    1. Panggil integration endpoint (STT → RAG → Material)
    2. Simpan hasil ke session_state
    3. Jalankan evaluasi RAGAS
    4. Simpan hasil RAGAS ke session_state
    5. Rerun untuk tampilkan hasil
    """
    # Step 1: RAG pipeline
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

    transcription   = rag_response.get("transcription", {})
    material        = rag_response.get("generated_material")
    context         = rag_response.get("raw_context", "")
    rag_meta        = rag_response.get("rag", {})
    question        = transcription.get("repaired", transcription.get("raw", ""))
    answer_text     = _material_to_text(material) if material else ""

    # Debug log — hapus setelah fix dikonfirmasi
    print(f"[DEBUG] has_context: {rag_meta.get('has_context')}")
    print(f"[DEBUG] sources_count: {rag_meta.get('sources_count')}")
    print(f"[DEBUG] context length: {len(context)}")
    print(f"[DEBUG] material: {material}")

    # Step 2: Simpan hasil RAG ke session_state
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

    # Step 3 & 4: Evaluasi RAGAS (jika ada context dan material)
    if context and answer_text:
        set_ragas_evaluating(True)
        with st.spinner("📊 Mengevaluasi kualitas RAG dengan RAGAS..."):
            ragas_response = run_ragas_evaluation(
                question=question,
                context=context,
                answer=answer_text,
                ground_truth=None,  # proxy otomatis dari context di backend
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

    st.rerun()


# ── HELPER: transkripsi berhasil (flow lama) ──────────────────────────────────
def _handle_transcription_success(transcription: str):
    st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
    st.success("✅ Transkripsi berhasil!")

    st.text_area(
        "Hasil Transkripsi:",
        value=transcription,
        height=150,
        key="transcription_preview",
    )