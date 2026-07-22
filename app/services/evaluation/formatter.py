# app/services/evaluation/formatter.py

from app.schemas.prompting.generate_content import MaterialResponse


def material_to_text(material: MaterialResponse) -> str:
    """
    Mengonversi objek MaterialResponse baru menjadi satu string teks tunggal berskala besar (Flat Teks).
    Fungsi ini digunakan untuk menyediakan cadangan log teks lengkap (backward compatibility)
    dan sebagai representasi 'answer' global bagi penilai luar.
    """
    # 1. Format dasar hukum
    dasar_hukum_list = []
    for item in material.dasar_hukum:
        catatan = f" (Catatan: {item.catatan_validasi})" if item.catatan_validasi and item.catatan_validasi != "-" else ""
        dasar_hukum_list.append(f"- {item.nama_peraturan} {item.pasal} {item.ayat or ''}{catatan}".strip())
    dasar_hukum_text = "\n".join(dasar_hukum_list) if dasar_hukum_list else "-"

    # 2. Format ringkasan (kalimat pembuka + poin-poin)
    ringkasan_list = [f"- {item.poin}" for item in material.ringkasan]
    ringkasan_points_text = "\n".join(ringkasan_list) if ringkasan_list else "-"
    pembuka = material.ringkasan_pembuka or "-"
    ringkasan_text = (
        f"{pembuka}\n{ringkasan_points_text}" if pembuka != "-" else ringkasan_points_text
    )

    # 3. Konteks tambahan
    konteks_tambahan_text = material.konteks_tambahan or "-"

    # 4. Analisa risiko (contoh pelanggaran)
    risiko_list = []
    for item in material.analisa_risiko:
        risiko_list.append(f"Skenario: {item.skenario}\nPenjelasan: {item.penjelasan}")
    risiko_text = "\n\n".join(risiko_list) if risiko_list else "-"

    # 5. Q&A
    qa_list = [f"Pertanyaan: {item.pertanyaan}\nJawaban: {item.jawaban}" for item in material.qa]
    qa_text = "\n\n".join(qa_list) if qa_list else "-"

    return f"""
    Dasar Hukum:
    {dasar_hukum_text}

    Ringkasan:
    {ringkasan_text}

    Konteks Tambahan:
    {konteks_tambahan_text}

    Analisa Risiko (Contoh Pelanggaran):
    {risiko_text}

    Tanya Jawab (Q&A):
    {qa_text}
    """


def extract_segments_for_ragas(material: MaterialResponse) -> dict:
    """
    Memecah struktur baru MaterialResponse menjadi 3 klaster segmen teks terisolasi
    untuk dikirimkan ke mesin evaluasi RAGAS (faithfulness, qa, risk).
    Mencegah LLM Evaluator mengalami bias atau token overload.
    """
    # ── KLASTER 1: FAITHFULNESS (dasar hukum, ringkasan, konteks tambahan) ──
    dasar_hukum_list = [f"{item.nama_peraturan} {item.pasal} {item.ayat or ''}".strip() for item in material.dasar_hukum]
    dasar_hukum_text = " | ".join(dasar_hukum_list) if dasar_hukum_list else "-"
    ringkasan_text = " | ".join(item.poin for item in material.ringkasan) if material.ringkasan else "-"
    konteks_tambahan_text = material.konteks_tambahan or "-"
    pembuka_text = material.ringkasan_pembuka or "-"

    segment_faithfulness = (
        f"Dasar Hukum: {dasar_hukum_text}\n"
        f"Ringkasan Pembuka: {pembuka_text}\n"
        f"Ringkasan: {ringkasan_text}\n"
        f"Konteks Tambahan: {konteks_tambahan_text}"
    )

    # ── KLASTER 2: QA — hanya teks jawaban ──
    qa_answers = " ".join(item.jawaban for item in material.qa if item.jawaban) if material.qa else "-"
    segment_qa = qa_answers

    # ── KLASTER 3: RISK REVIEW — analisa risiko (contoh pelanggaran) ──
    risiko_list = [f"Skenario: {item.skenario} - Penjelasan: {item.penjelasan}" for item in material.analisa_risiko]
    segment_risk = " | ".join(risiko_list) if risiko_list else "-"

    return {
        "faithfulness": segment_faithfulness,
        "qa": segment_qa,
        "risk": segment_risk,
    }
