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


def extract_segments_for_ragas(material: MaterialResponse) -> dict:
    """
    FUNGSI STRATEGIS (FIX #2): Memecah struktur besar MaterialResponse menjadi 3 klaster 
    segmen teks terisolasi sesuai peruntukan metrik RAGAS-nya masing-masing.

    Tujuan utamanya: Mencegah LLM Evaluator mengalami bias, kebingungan konteks, atau
    overload token saat membaca jawaban hukum yang terlalu panjang.
    """

    # =========================================================================
    # KLASTER 1: SUMMARY SEGMENTATION
    # =========================================================================

    summary = material.summary

    # 1. Segmen Summary (Untuk Uji Halusinasi / Faithfulness)
    overview = summary.overview if (summary and summary.overview) else "-"
    conclusion = summary.conclusion if (
        summary and summary.conclusion) else "-"
    key_points = ' | '.join(str(p) for p in summary.key_points) if (
        summary and summary.key_points) else "-"

    segment_summary = f"Overview: {overview}\nPoin Penting: {key_points}\nKesimpulan: {conclusion}"

    # =========================================================================
    # KLASTER 2: CLAUSE SEARCH + LEGAL QA
    # =========================================================================
    # Ekstraksi bagian interaktif (Tanya-Jawab dan Pencarian Klausul).
    # Segmen ini dikelompokkan khusus untuk menguji akurasi relevansi jawaban ('answer_relevancy').
    # 2. Segmen QA & Search (Untuk Uji Relevansi Jawaban / Answer Relevancy)
    clause_search = ' | '.join(
        [f'{item.clause_topic} => {item.article}' for item in material.clause_search]) if material.clause_search else "-"
    legal_qa = ' | '.join(
        [f'{item.question} => {item.answer}' for item in material.legal_qa]) if material.legal_qa else "-"

    segment_qa = f"Clause Search: {clause_search}\nLegal Q&A: {legal_qa}"

    # =========================================================================
    # KLASTER 3: RISK REVIEW
    # =========================================================================

    risk = material.risk_review

    # Ekstraksi segmen analisis risiko hukum.
    # Diisolasi secara ketat agar RAGAS dapat menilai 'risk_faithfulness' secara objektif
    # guna meminimalisir halusinasi analisis hukum (aspek paling fatal dalam sistem legal-AI)
    risk_status = risk.status if (risk and risk.status) else None
    risk_analysis = risk.analysis if (risk and risk.analysis) else None
    risks_list = ' | '.join(str(r) for r in risk.risks) if (
        risk and risk.risks) else None
    recommendation = risk.recommendation if (
        risk and risk.recommendation) else None

    if all(v is None for v in [risk_status, risk_analysis, risks_list, recommendation]):
        segment_risk = "-"
    else:
        segment_risk = (
            f"Status Kepatuhan: {risk_status or '-'}\n"
            f"Analisis: {risk_analysis or '-'}\n"
            f"Risiko: {risks_list or '-'}\n"
            f"Rekomendasi: {recommendation or '-'}"
        )

    # =========================================================================
    # KLASTER PENDUKUNG METRIK FAITHFULNESS (References)
    # =========================================================================
    # Bagian-bagian ini dikonversi menjadi string datar untuk memperkuat basis pengujian kesetiaan data.

    # =====================================================
    # LEGAL REFERENCES
    # =====================================================

    segment_reference = (
        " | ".join(
            f"{item.source_name} Pasal {item.article}"
            for item in material.referensi_uu
        )
        if material.referensi_uu
        else "-"
    )

    # Menyusun gabungan teks besar (Kombinasi Klaster 1 + Data Pendukung)
    # khusus untuk menguji apakah seluruh klaim fakta teks ini 100% berbasis pada dokumen referensi asli.
    segment_faithfulness = "\n".join([
        segment_summary,
        f"Legal Reference: {segment_reference}"
    ])

    # 6. Mengembalikan output dalam bentuk objek dictionary Python.
    # Struktur inilah yang nantinya dibaca oleh 'trigger_auto_evaluation' untuk dikirim ke port :8001
    return {
        "faithfulness": segment_faithfulness,
        "qa": segment_qa,
        "risk": segment_risk
    }
