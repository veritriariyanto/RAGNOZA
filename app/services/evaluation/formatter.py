# formatter.py

from app.schemas.prompting.generate_content import MaterialResponse

def material_to_text(material: MaterialResponse) -> str:
    return f"""
    Resume:
    {material.summary.overview}

    Poin Penting:
    {' | '.join(material.summary.key_points)}

    Kesimpulan:
    {material.summary.conclusion}

    Clause Search:
    {' | '.join([f'{item.clause_topic} => {item.article}' for item in material.clause_search])}

    Legal Q&A:
    {' | '.join([f'{item.question} => {item.answer}' for item in material.legal_qa])}

    Status Kepatuhan:
    {material.risk_review.status}

    Skor Kepatuhan:
    {material.risk_review.score}

    Analisis Kepatuhan:
    {material.risk_review.analysis}

    Risiko Analisis:
    {' | '.join(material.risk_review.risks)}

    Langkah Mitigasi:
    {' | '.join(material.risk_review.mitigation_steps)}

    Rekomendasi Tindakan:
    {material.risk_review.recommendation}

    Timeline Extraction:
    {' | '.join([f'{item.date_or_period} => {item.event}' for item in material.timeline_extraction])}

    Comparison:
    {' | '.join([f'{item.aspect} => {item.conclusion}' for item in material.comparison])}

    Referensi UU:
    {' | '.join([f'{item.source_name} Pasal {item.article}' for item in material.referensi_uu])}
    """