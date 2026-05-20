# formatter.py

from app.schemas.prompting.generate_content import MaterialResponse

def material_to_text(material: MaterialResponse) -> str:
    return f"""
    Status Keputusan:
    {material.decision_status}

    Skor Kepatuhan:
    {material.compliance_score}

    Rekomendasi Tindakan:
    {material.recommendation}

    Analisis Resiko:
    {' | '.join(material.risk_analysis)}

    Dasar Hukum:
    {' | '.join(material.legal_basis)}
    """