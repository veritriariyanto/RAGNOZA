# app/services/evaluation/formatter.py

from app.schemas.prompting.generate_content import MaterialResponse


def material_to_text(material: MaterialResponse) -> str:
    """
    Mengonversi seluruh objek MaterialResponse (beserta seluruh nested object-nya) 
    menjadi satu string teks tunggal berskala besar (Flat Teks).

    Fungsi ini digunakan untuk menyediakan cadangan log teks lengkap (backward compatibility)
    dan sebagai representasi 'answer' global bagi penilai luar.
    """
    # 1. Ambil objek utama dengan fallback aman
    summary = material.summary
    risk = material.risk_review

    # 2. Format blok teks tunggal (jika tidak ada data, beri fallback "-")
    overview = summary.overview if (summary and summary.overview) else "-"
    conclusion = summary.conclusion if (
        summary and summary.conclusion) else "-"

    risk_status = risk.status if (risk and risk.status) else "-"
    risk_score = risk.score if (risk and risk.score is not None) else "-"
    risk_analysis = risk.analysis if (risk and risk.analysis) else "-"
    recommendation = risk.recommendation if (
        risk and risk.recommendation) else "-"

    # 3. Format data list/array dengan pengecekan kosong (empty check)
    key_points = ' | '.join(str(p) for p in summary.key_points) if (
        summary and summary.key_points) else "-"
    risks_list = ' | '.join(str(r) for r in risk.risks) if (
        risk and risk.risks) else "-"
    mitigation_steps = ' | '.join(str(m) for m in risk.mitigation_steps) if (
        risk and risk.mitigation_steps) else "-"

    # 4. Format objek list bersarang (Nested Object List)
    clause_search = ' | '.join(
        [f'{item.clause_topic} => {item.article}' for item in material.clause_search]) if material.clause_search else "-"
    legal_qa = ' | '.join(
        [f'{item.question} => {item.answer}' for item in material.legal_qa]) if material.legal_qa else "-"

    # Sesuai aturan baru, jika LLM mengosongkan array ini, output otomatis jadi "-"
    referensi_uu = ' | '.join(
        [f'{item.source_name} Pasal {item.article}' for item in material.referensi_uu]) if material.referensi_uu else "-"

    return f"""
    Resume:
    {overview}

    Poin Penting:
    {key_points}

    Kesimpulan:
    {conclusion}

    Clause Search:
    {clause_search}

    Legal Q&A:
    {legal_qa}

    Status Kepatuhan:
    {risk_status}

    Skor Kepatuhan:
    {risk_score}

    Analisis Kepatuhan:
    {risk_analysis}

    Risiko Analisis:
    {risks_list}

    Langkah Mitigasi:
    {mitigation_steps}

    Rekomendasi Tindakan:
    {recommendation}

    Referensi UU:
    {referensi_uu}
    """

def _is_placeholder_value(val) -> bool:
    """Cek apakah nilai adalah placeholder kosong."""
    return val is None or str(val).strip() in ("-", "", "none", "None")

def extract_segments_for_ragas(material: MaterialResponse) -> dict:
    """
    FUNGSI STRATEGIS (FIX #2): Memecah struktur besar MaterialResponse menjadi 3 klaster 
    segmen teks terisolasi sesuai peruntukan metrik RAGAS-nya masing-masing.

    Tujuan utamanya: Mencegah LLM Evaluator mengalami bias, kebingungan konteks, atau
    overload token saat membaca jawaban hukum yang terlalu panjang.
    """

     # ── KLASTER 1: SUMMARY ──────────────────────────────────────────────────
    summary = material.summary
    overview    = summary.overview   if (summary and summary.overview)   else "-"
    conclusion  = summary.conclusion if (summary and summary.conclusion) else "-"
    key_points  = ' | '.join(str(p) for p in summary.key_points) if (summary and summary.key_points) else "-"

    segment_summary = f"Overview: {overview}\nPoin Penting: {key_points}\nKesimpulan: {conclusion}"

    # ── KLASTER PENDUKUNG: LEGAL REFERENCES (harus sebelum segment_faithfulness) ──
    segment_reference = (
        " | ".join(
            f"{item.source_name} Pasal {item.article}"
            for item in material.referensi_uu
        )
        if material.referensi_uu
        else "-"
    )

    # ── CLAUSE SEARCH — pakai excerpt verbatim, masuk ke faithfulness ────────
    clause_search_text = ' | '.join(
        [
            f'{item.article}: {item.excerpt}'
            for item in material.clause_search
            if item.excerpt
        ]
    ) if material.clause_search else "-"

    # ── segment_faithfulness: summary + clause + reference (satu definisi saja) ──
    segment_faithfulness = "\n".join([
        segment_summary,
        f"Clause Search: {clause_search_text}",
        f"Legal Reference: {segment_reference}"
    ])

    # ── KLASTER 2: QA — hanya teks jawaban ──────────────────────────────────
    legal_qa_answers = ' '.join(
        [item.answer for item in material.legal_qa if item.answer]
    ) if material.legal_qa else "-"

    segment_qa = legal_qa_answers

    # ── KLASTER 3: RISK REVIEW ───────────────────────────────────────────────
    risk = material.risk_review
    # SESUDAH
    risk_status   = risk.status        if (risk and not _is_placeholder_value(risk.status))      else None
    risk_analysis = risk.analysis      if (risk and not _is_placeholder_value(risk.analysis))    else None
    risks_list    = ' | '.join(str(r) for r in risk.risks) if (risk and risk.risks) else None
    recommendation = risk.recommendation if (risk and not _is_placeholder_value(risk.recommendation)) else None

    if all(v is None for v in [risk_status, risk_analysis, risks_list, recommendation]):
        segment_risk = "-"   # ← sekarang kasus informatif akan masuk sini
    else:
        segment_risk = (
            f"Status Kepatuhan: {risk_status or '-'}\n"
            f"Analisis: {risk_analysis or '-'}\n"
            f"Risiko: {risks_list or '-'}\n"
            f"Rekomendasi: {recommendation or '-'}"
        )

    return {
        "faithfulness": segment_faithfulness,
        "qa": segment_qa,
        "risk": segment_risk,
    }
