# app/services/evaluation/formatter.py

from app.schemas.prompting.generate_content import MaterialResponse

def material_to_text(material: MaterialResponse) -> str:
    # 1. Ambil objek utama dengan fallback aman
    summary = material.summary
    risk = material.risk_review

    # 2. Format blok teks tunggal (jika tidak ada data, beri fallback "-")
    overview = summary.overview if (summary and summary.overview) else "-"
    conclusion = summary.conclusion if (summary and summary.conclusion) else "-"
    
    risk_status = risk.status if (risk and risk.status) else "-"
    risk_score = risk.score if (risk and risk.score is not None) else "-"
    risk_analysis = risk.analysis if (risk and risk.analysis) else "-"
    recommendation = risk.recommendation if (risk and risk.recommendation) else "-"

    # 3. Format data list/array dengan pengecekan kosong (empty check)
    key_points = ' | '.join(str(p) for p in summary.key_points) if (summary and summary.key_points) else "-"
    risks_list = ' | '.join(str(r) for r in risk.risks) if (risk and risk.risks) else "-"
    mitigation_steps = ' | '.join(str(m) for m in risk.mitigation_steps) if (risk and risk.mitigation_steps) else "-"

    # 4. Format objek list bersarang (Nested Object List)
    clause_search = ' | '.join([f'{item.clause_topic} => {item.article}' for item in material.clause_search]) if material.clause_search else "-"
    legal_qa = ' | '.join([f'{item.question} => {item.answer}' for item in material.legal_qa]) if material.legal_qa else "-"
    
    # Sesuai aturan baru, jika LLM mengosongkan array ini, output otomatis jadi "-"
    timeline_extraction = ' | '.join([f'{item.date_or_period} => {item.event}' for item in material.timeline_extraction]) if material.timeline_extraction else "-"
    comparison = ' | '.join([f'{item.aspect} => {item.conclusion}' for item in material.comparison]) if material.comparison else "-"
    referensi_uu = ' | '.join([f'{item.source_name} Pasal {item.article}' for item in material.referensi_uu]) if material.referensi_uu else "-"

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

    Timeline Extraction:
    {timeline_extraction}

    Comparison:
    {comparison}

    Referensi UU:
    {referensi_uu}
    """

def extract_segments_for_ragas(material: MaterialResponse) -> dict:
    """
    FUNGSI BARU: Memecah MaterialResponse menjadi segmen terpisah 
    agar evaluasi Ragas tidak bias dan overload.
    """

    # =====================================================
    # SUMMARY
    # =====================================================

    summary = material.summary


    # 1. Segmen Summary (Untuk Uji Halusinasi / Faithfulness)
    overview = summary.overview if (summary and summary.overview) else "-"
    conclusion = summary.conclusion if (summary and summary.conclusion) else "-"
    key_points = ' | '.join(str(p) for p in summary.key_points) if (summary and summary.key_points) else "-"
    
    segment_summary = f"Overview: {overview}\nPoin Penting: {key_points}\nKesimpulan: {conclusion}"

    # =====================================================
    # CLAUSE SEARCH + LEGAL QA
    # =====================================================
    # 2. Segmen QA & Search (Untuk Uji Relevansi Jawaban / Answer Relevancy)
    clause_search = ' | '.join([f'{item.clause_topic} => {item.article}' for item in material.clause_search]) if material.clause_search else "-"
    legal_qa = ' | '.join([f'{item.question} => {item.answer}' for item in material.legal_qa]) if material.legal_qa else "-"
    
    segment_qa = f"Clause Search: {clause_search}\nLegal Q&A: {legal_qa}"

    # =====================================================
    # RISK REVIEW
    # =====================================================

    risk = material.risk_review

    # 3. Segmen Risiko (Untuk Uji Penalaran Asisten / Aspect Critic / Relevancy)
    risk_status = risk.status if (risk and risk.status) else "-"
    risk_analysis = risk.analysis if (risk and risk.analysis) else "-"
    risks_list = ' | '.join(str(r) for r in risk.risks) if (risk and risk.risks) else "-"
    recommendation = risk.recommendation if (risk and risk.recommendation) else "-"
    
    segment_risk = f"Status Kepatuhan: {risk_status}\nAnalisis: {risk_analysis}\nRisiko: {risks_list}\nRekomendasi: {recommendation}"

    # =====================================================
    # TIMELINE
    # =====================================================

    segment_timeline = (
        " | ".join(
            str(item)
            for item in material.timeline_extraction
        )
        if material.timeline_extraction
        else "-"
    )

    # =====================================================
    # COMPARISON
    # =====================================================

    segment_comparison = (
        " | ".join(
            str(item)
            for item in material.comparison
        )
        if material.comparison
        else "-"
    )

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

    segment_faithfulness = "\n".join([
    segment_summary,
    f"Timeline: {segment_timeline}",
    f"Comparison: {segment_comparison}",
    f"Legal Reference: {segment_reference}"
])

    return {
        "faithfulness": segment_faithfulness,
        "qa": segment_qa,
        "risk": segment_risk
}