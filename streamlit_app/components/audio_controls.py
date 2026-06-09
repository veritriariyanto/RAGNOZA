"""
streamlit_app/components/audio_controls.py  (updated - UI Redesign)

Perubahan dari versi lama:
- Tambah tombol "Proses RAG & Evaluasi" yang memanggil integration pipeline
- Tampilkan hasil material SPK hukum setelah pipeline selesai
- Jalankan evaluasi RAGAS otomatis setelah material diterima
- Tampilkan RAGAS strip kecil di bawah material
- Simpan semua hasil ke session_state agar Tab Evaluasi bisa auto-populate
- UI/UX redesign: elegant, refined, professional legal-tech aesthetic

[PATCH] Fix 5 bug UI vs schema MaterialResponse:
  BUG-1: Timeline — ganti item["article_reference"] → item["relevance"]
  BUG-2: Comparison — tambah render similarities & differences
  BUG-3: Clause Search — tambah render source_name & relevance
  BUG-4: Referensi UU — tambah render excerpt & relevance
  WARN-1: Comparison — hapus fallback option_a/option_b, pakai source_a/source_b langsung
"""

from pathlib import Path
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

#CSS

def _inject_styles():
    css_path = Path("streamlit_app/assets/styles/main.css")

    with open(css_path, "r", encoding="utf-8") as f:
        css = f.read()

    st.markdown(
        f"<style>{css}</style>",
        unsafe_allow_html=True
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

    faith    = metrics.get("faithfulness")
    relev    = metrics.get("answer_relevancy")
    risk_f   = metrics.get("risk_faithfulness")
    overall  = metrics.get("overall_score")
    coverage = metrics.get("coverage_pct")
    segments = metrics.get("answer_faithfulness_segment", [])
    ts       = ragas_result.get("timestamp", "")

    def _fmt(v):
        return f"{v:.2f}" if v is not None else "N/A"

    seg_html = ""
    if segments:
        seg_labels = {"faithfulness": "Summary", "qa": "QA", "risk": "Risk"}
        seg_html = " ".join(
            f'<span style="background:rgba(212,168,83,0.12);color:#D4A853;'
            f'padding:2px 7px;border-radius:4px;font-size:10.5px;">'
            f'{seg_labels.get(s, s)}</span>'
            for s in segments
        )

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
            <span class="{_badge_class(risk_f)}">
                {_score_emoji(risk_f)} Risk Faith &nbsp;{_fmt(risk_f)}
            </span>
            <span class="{_badge_class(overall)}">
                {_score_emoji(overall)} Overall &nbsp;{_fmt(overall)}
            </span>
            {'<span class="ragas-label" style="margin-left:8px;">Coverage</span>' if coverage is not None else ''}
            {'<span class="badge badge-gray">' + f'{coverage*100:.0f}%' + '</span>' if coverage is not None else ''}
            {'<span class="ragas-label" style="margin-left:8px;">Segmen</span>' + seg_html if seg_html else ''}
            <span class="ragas-meta">Detail → Tab Evaluasi &nbsp;·&nbsp; {ts}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ── Helper: render hasil material SPK ────────────────────────────────────────
def _render_material_result(material: dict, rag_info: dict):
    sources_count = rag_info.get("sources_count", 0)
    has_context   = rag_info.get("has_context", False)
    query_used    = rag_info.get("query_used", "")

    st.markdown('<div class="ac-divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="result-header">📋 Hasil Analisis Hukum</div>', unsafe_allow_html=True)

    # Meta pills
    st.markdown(
        f"""
        <div style="margin-bottom:14px;">
            <span class="info-pill">🔍 {query_used or '—'}</span>
            <span class="info-pill">📚 {sources_count} chunk ditemukan</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not has_context or not material:
        st.warning("⚠️ Tidak ditemukan referensi hukum yang relevan.")
        return

    # ── Summary ──────────────────────────────────────────────────────────────
    summary = material.get("summary", {}) or {}
    if summary:
        st.markdown('<div class="section-label">📌 Ringkasan</div>', unsafe_allow_html=True)
        st.markdown(
            f"<p style='font-family:DM Serif Display,serif;font-size:1.1rem;color:white;margin:0 0 8px 0;'>"
            f"{summary.get('title', 'Ringkasan')}</p>",
            unsafe_allow_html=True,
        )
        if summary.get("overview"):
            st.write(summary["overview"])

        key_points = summary.get("key_points", [])
        if key_points:
            with st.expander("📋 Poin-Poin Penting", expanded=True):
                for point in key_points:
                    st.markdown(f"- {point}")
        if summary.get("conclusion"):
            st.info(f"💡 **Kesimpulan:** {summary['conclusion']}")

    # ── Legal Q&A ─────────────────────────────────────────────────────────────
    legal_qa = material.get("legal_qa", [])
    if legal_qa:
        st.markdown('<div class="section-label">❓ Legal Q&A</div>', unsafe_allow_html=True)
        for qa in legal_qa:
            with st.expander(f"Q: {qa.get('question', '')}", expanded=True):
                st.write(qa.get("answer", "-"))

    # ── Risk Review ───────────────────────────────────────────────────────────
    risk        = material.get("risk_review", {}) or {}
    risk_status = risk.get("status", "-") or "-"
    if risk and risk_status not in ("-", "", "ERROR_SISTEM"):
        st.markdown('<div class="section-label">⚠️ Risk Review</div>', unsafe_allow_html=True)
        score = risk.get("score", 0) or 0

        col_s, col_sc = st.columns(2)
        with col_s:
            st.metric("Status", risk_status)
        with col_sc:
            st.metric("Skor Risiko", f"{score} / 100")
        st.progress(min(int(score), 100) / 100)

        if risk.get("analysis"):
            st.write(risk["analysis"])
        if risk.get("risks"):
            with st.expander("🔴 Risiko"):
                for r in risk["risks"]:
                    st.markdown(f"- {r}")
        if risk.get("mitigation_steps"):
            with st.expander("🛡️ Langkah Mitigasi"):
                for step in risk["mitigation_steps"]:
                    st.markdown(f"- {step}")
        if risk.get("recommendation"):
            st.success(f"✅ **Rekomendasi:** {risk['recommendation']}")

    # ── Clauses ───────────────────────────────────────────────────────────────
    # [BUG-3 FIX] Tambah render source_name & relevance
    clauses = material.get("clause_search", [])
    if clauses:
        with st.expander(f"📜 Pasal Terkait ({len(clauses)} ditemukan)"):
            for clause in clauses:
                st.markdown(
                    f"**{clause.get('article', '')}** — {clause.get('clause_topic', '')}"
                )
                if clause.get("source_name"):
                    st.caption(f"🏛️ Sumber: {clause['source_name']}")
                if clause.get("excerpt"):
                    st.caption(clause["excerpt"])
                if clause.get("relevance"):
                    st.info(f"📎 Relevansi: {clause['relevance']}")
                st.divider()

    # ── Timeline ──────────────────────────────────────────────────────────────
    # [BUG-1 FIX] Ganti item["article_reference"] → item["relevance"]
    timeline = material.get("timeline_extraction", [])
    if timeline:
        with st.expander("🕐 Timeline Hukum"):
            for item in timeline:
                st.markdown(
                    f"- **{item.get('date_or_period', '')}** — "
                    f"{item.get('event', '')}"
                )
                if item.get("relevance"):
                    st.caption(f"📎 {item['relevance']}")

    # ── Comparisons ───────────────────────────────────────────────────────────
    # [BUG-2 FIX] Tambah render similarities & differences
    # [WARN-1 FIX] Hapus fallback option_a/option_b, pakai source_a/source_b langsung
    comparisons = material.get("comparison", [])
    if comparisons:
        with st.expander("⚖️ Perbandingan Ketentuan"):
            for comp in comparisons:
                st.markdown(f"**Aspek: {comp.get('aspect', '')}**")

                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("**Ketentuan A**")
                    st.write(comp.get("source_a", "-"))
                with col2:
                    st.markdown("**Ketentuan B**")
                    st.write(comp.get("source_b", "-"))

                similarities = comp.get("similarities", [])
                if similarities:
                    with st.expander("🟰 Persamaan", expanded=False):
                        for s in similarities:
                            st.markdown(f"- {s}")

                differences = comp.get("differences", [])
                if differences:
                    with st.expander("↔️ Perbedaan", expanded=False):
                        for d in differences:
                            st.markdown(f"- {d}")

                if comp.get("conclusion"):
                    st.caption(f"Kesimpulan: {comp['conclusion']}")
                st.divider()

    # ── Referensi UU ──────────────────────────────────────────────────────────
    # [BUG-4 FIX] Tambah render excerpt & relevance
    referensi = material.get("referensi_uu", [])
    if referensi:
        with st.expander("📚 Referensi Undang-Undang"):
            for ref in referensi:
                st.markdown(
                    f"**{ref.get('source_name', '')}** — Pasal {ref.get('article', '')}"
                )
                if ref.get("excerpt"):
                    st.caption(f'"{ref["excerpt"]}"')
                if ref.get("relevance"):
                    st.info(f"📎 {ref['relevance']}")
                st.divider()


# ── MAIN RENDER ───────────────────────────────────────────────────────────────
def render_audio_controls():
    _inject_styles()

    # ── Section Header ────────────────────────────────────────────────────────
    st.markdown(
        """
        <div style="margin-top: 8px; margin-bottom: 4px;">
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
                    "🚀  Proses RAG & Evaluasi",
                    use_container_width=True,
                    key="btn_rag_upload",
                    type="primary",
                    help="STT → RAG → Generate Material → Evaluasi RAGAS otomatis",
                )

            with col_stt:
                transcribe_only = st.button(
                    "📝  Transkripsi Saja",
                    use_container_width=True,
                    key="btn_transcribe_upload",
                )

            with col_clear:
                if st.button("🗑️", use_container_width=True, key="btn_clear_upload", help="Hapus file"):
                    st.session_state.pop(_KEY_UPLOAD_BYTES, None)
                    st.session_state.pop(_KEY_UPLOAD_NAME,  None)
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
        st.markdown("<div class='white-caption'>Klik **Start** untuk mulai merekam, **Stop** untuk menyelesaikan.</div>", unsafe_allow_html=True)

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
                    "🚀  Proses RAG & Evaluasi",
                    use_container_width=True,
                    key="btn_rag_record",
                    type="primary",
                )

            with col_stt:
                transcribe_record = st.button(
                    "📝  Transkripsi Saja",
                    use_container_width=True,
                    key="btn_transcribe_record",
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

    # ── Hasil transkripsi saja (flow lama) ────────────────────────────────────
    transcription = st.session_state.get(_KEY_TRANSCRIPTION)
    if transcription is not None:
        _handle_transcription_success(transcription)

    # ── Hasil RAG + RAGAS strip ───────────────────────────────────────────────
    rag_result = get_last_rag_result()
    if rag_result:
        _render_material_result(
            material=rag_result.get("generated_material"),
            rag_info={
                "has_context":  rag_result.get("has_context", False),
                "sources_count": rag_result.get("sources_count", 0),
                "query_used":   rag_result.get("query_used", ""),
            },
        )

        ragas_result = get_last_ragas_result()
        if is_ragas_evaluating():
            st.info("⏳ Evaluasi RAGAS sedang berjalan...")
        elif ragas_result:
            _render_ragas_strip(ragas_result)

        st.markdown(
            """
            <div style="
                font-family:'DM Sans',sans-serif;
                font-size:11.5px;
                color:#6B6460;
                text-align:center;
                margin-top:10px;
                letter-spacing:0.03em;
            ">
                💡 Buka <strong style="color:#A89F93;">Tab Evaluasi</strong> untuk detail lengkap 4 metrik &amp; tambah ground truth
            </div>
            """,
            unsafe_allow_html=True,
        )


# ── CORE: pipeline RAG + RAGAS otomatis ──────────────────────────────────────
def _run_rag_pipeline(
    audio_bytes: bytes,
    filename: str,
    provider: str,
    knowledge_base: str,
):
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