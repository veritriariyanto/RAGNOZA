# app/services/prompting/prompt/generate_content_service.py

import logging
from app.core.llm_provider import llm
from app.schemas.prompting.generate_content import MaterialRequest, MaterialResponse
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.output_parsers import JsonOutputParser

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Intent Classification
# ---------------------------------------------------------------------------

INTENT_KEYWORDS: dict[str, list[str]] = {
    "konsultasi": [
        # Pernyataan tindakan diri sendiri
        "saya melakukan", "saya ingin", "saya telah", "saya sudah",
        "saya mendirikan", "saya membuat", "saya menjalankan",
        "saya berencana", "saya sedang",
        "kami melakukan", "kami berencana", "kami ingin",
        "kami mendirikan", "kami membuat",
        # Frasa risiko hukum personal
        "tindakan saya", "perbuatan saya", "kegiatan saya",
        "apakah saya bisa dituntut", "apakah saya bisa dipidana",
        "apakah saya melanggar", "apakah tindakan saya",
        "apakah perbuatan saya", "apakah kegiatan saya",
        "bisakah saya dituntut", "dapatkah saya dipidana",
        "apakah saya dapat dibubarkan", "apakah saya dapat ditindak",
        # Frasa implisit konsultasi
        "tanpa izin", "tanpa mengurus izin", "tidak berizin",
        "belum memiliki izin", "belum mengurus",
    ],
    "informatif": [
        "apakah", "apa itu", "apa yang dimaksud",
        "bagaimana", "bagaimana cara", "bagaimana ketentuan",
        "bolehkah", "bisakah", "dapatkah",
        "jelaskan", "definisi", "pengertian",
        "siapa yang", "kapan", "berapa lama",
    ],
}


def classify_intent(raw_text: str, repaired_text: str = "") -> str:
    """
    Mengklasifikasikan intent dari kombinasi raw_text dan repaired_text.

    Strategi:
    - Prioritaskan raw_text karena masih mengandung frasa orisinal pengguna
      (belum diparafrase oleh repair step).
    - Fallback ke repaired_text jika raw_text kosong.
    - Konsultasi dicek lebih dahulu karena lebih spesifik dan berisiko tinggi.

    Returns:
        'konsultasi' | 'informatif'
    """
    # Gabungkan raw + repaired agar tidak ada sinyal yang terlewat
    combined = f"{raw_text} {repaired_text}".strip().lower()

    for keyword in INTENT_KEYWORDS["konsultasi"]:
        if keyword in combined:
            logger.debug(f"classify_intent: keyword konsultasi ditemukan → '{keyword}'")
            return "konsultasi"

    return "informatif"


# ---------------------------------------------------------------------------
# Conditional Output Instructions
# ---------------------------------------------------------------------------

def build_output_instructions(intent: str) -> str:
    """
    Membangun instruksi output kondisional berdasarkan intent query.
    """
    instructions = (
        "Instruksi Output (ikuti sesuai urutan dan tipe query):\n\n"
        "1. SUMMARY\n"
        "   - Awali dengan 1 kalimat yang langsung menjawab pertanyaan/skenario pengguna.\n"
        "   - overview: Ringkasan yang MENCANTUMKAN ANALISIS PENYEBAB — jelaskan secara "
        "konkret MENGAPA tindakan yang dideskripsikan pengguna melanggar atau tidak "
        "melanggar hukum, dengan merujuk langsung ke pasal/ayat spesifik dari konteks. "
        "Contoh: 'Berdasarkan Pasal 20 ayat (1) huruf b UU 2/2002, suami Anda sebagai "
        "PNS Polri berhak atas ketentuan kepegawaian. Penahanan gaji tanpa prosedur "
        "sidang disiplin bertentangan dengan ketentuan yang berlaku karena...'\n"
        "   - key_points: Sertakan poin-poin fakta hukum yang menjadi dasar analisis.\n"
        "   - conclusion: Kesimpulan singkat dari analisis penyebab dan implikasinya "
        "bagi pengguna.\n\n"
        "2. CLAUSE SEARCH\n"
        "   - Petakan pasal/ayat yang PALING RELEVAN dengan pertanyaan pengguna.\n"
        "   - Teks excerpt WAJIB menyalin verbatim dari konteks — dilarang mengubah "
        "atau mencampurkan isi antar ayat.\n"
        "   - VALIDASI PASAL: Jika pengguna menyebut nomor pasal tertentu dalam query:\n"
        "     a) Verifikasi apakah pasal tersebut ADA dalam konteks yang diberikan.\n"
        "     b) Jika TIDAK ADA: nyatakan di field 'relevance' bahwa pasal tersebut "
        "tidak ditemukan, lalu cari dan tampilkan pasal LAIN yang paling relevan "
        "dengan TINDAKAN yang dideskripsikan pengguna.\n"
        "     c) Jika pasal ADA namun pengguna menyebut ayat/huruf yang keliru: "
        "koreksi dan tunjukkan pasal/ayat yang tepat beserta alasannya.\n"
        "     d) DILARANG mengarang isi pasal yang tidak ada di konteks.\n"
        "   - CLAUSE HONESTY: Jika tidak ada pasal yang secara spesifik mengatur hal "
        "yang ditanyakan, pilih pasal terdekat dan nyatakan secara eksplisit di field "
        "'relevance' bahwa ini merupakan ketentuan umum/terdekat yang tersedia, "
        "bukan pasal yang secara langsung mengatur.\n"
        "   - PASAL SALAH ≠ BEBAS RISIKO: Ketidakhadiran nomor pasal yang disebutkan "
        "pengguna dalam konteks BUKAN berarti tindakan pengguna aman atau patuh. "
        "Evaluasi TINDAKAN yang dideskripsikan tetap wajib dilakukan berdasarkan "
        "pasal lain yang relevan dari konteks. Risk Review TIDAK BOLEH bernilai "
        "'Patuh' atau score tinggi semata karena pasal yang disebutkan tidak ditemukan.\n\n"
        "3. LEGAL Q&A\n"
        "   - Jawab HANYA pertanyaan yang secara eksplisit diajukan pengguna.\n"
        "   - DILARANG mengarang pertanyaan turunan yang tidak diminta.\n"
        "   - Jumlah Q&A maksimal 1–2 pasang, berbasis konteks.\n\n"
    )

    if intent == "konsultasi":
        instructions += (
            "4. RISK REVIEW\n"
            "   - Query bersifat KONSULTASI TINDAKAN — wajib diisi lengkap.\n"
            "   - Isi dengan:\n"
            "     • status: ringkasan status risiko (misal: 'BERISIKO TINGGI')\n"
            "     • score: skor risiko numerik 0–100\n"
            "     • analysis: analisis risiko hukum atas tindakan yang dideskripsikan "
            "pengguna, berbasis konteks yang diberikan\n"
            "     • risks: daftar risiko konkret yang dapat dialami pengguna\n"
            "     • mitigation_steps: SOLUSI — 3-5 langkah konkret, praktis, dan "
            "terstruktur yang dapat dilakukan pengguna untuk mengatasi masalah, "
            "termasuk: a) tindakan internal (lapor atasan/HRD/inspektorat), "
            "b) tindakan eksternal (lapor Komnas HAM/Ombudsman/PTUN), "
            "c) dasar hukum setiap langkah, d) perkiraan prosedur/langkah "
            "yang harus ditempuh.\n"
            "     • recommendation: rekomendasi tindakan akhir yang konkret, "
            "ringkas, dan actionable bagi pengguna.\n"
            "   - DILARANG mengosongkan Risk Review untuk query konsultasi.\n\n"
        )
    else:
        instructions += (
            "4. RISK REVIEW\n"
            "   - Query bersifat INFORMATIF — kosongkan Risk Review sepenuhnya.\n"
            "   - Isi: status='-', score=0, analysis='-', risks=[], "
            "mitigation_steps=[], recommendation='-'.\n"
            "   - DILARANG memberikan skor risiko atas pertanyaan edukatif.\n\n"
        )

    instructions += (
        "5. KETENTUAN UMUM\n"
        "   - Untuk semua blok yang tidak memiliki data cukup: gunakan [] atau '-'.\n"
        "   - DILARANG mengarang informasi di luar konteks yang diberikan.\n\n"

        "6. CLAUSE RELEVANCE GATE\n"
        "   Sebelum mengaitkan pasal manapun dengan Risk Review atau Clause Search, "
        "ajukan pertanyaan: 'Apakah pasal ini secara LANGSUNG mengatur kewajiban/"
        "larangan yang relevan dengan TINDAKAN yang dideskripsikan pengguna?'\n"
        "   Jika TIDAK — meskipun pasal itu mengandung kata kunci yang mirip "
        "(misal sama-sama soal 'keamanan', 'izin', 'pidana') — DILARANG "
        "menjadikannya dasar kesimpulan pelanggaran atau skor risiko tinggi.\n"
        "   Pasal yang HANYA mengatur tugas/wewenang internal lembaga (Polri, "
        "Pemerintah, dll) TIDAK BOLEH dijadikan dasar untuk menyimpulkan bahwa "
        "TINDAKAN WARGA SIPIL melanggar hukum, kecuali pasal tersebut secara "
        "eksplisit menyebut kewajiban/larangan bagi pihak di luar lembaga tersebut.\n"
        "   Jika TIDAK ADA pasal yang relevan secara substansi dalam konteks: "
        "nyatakan secara jujur bahwa konteks yang tersedia tidak memuat ketentuan "
        "yang secara langsung mengatur hal ini. Risk Review boleh menyatakan "
        "'BELUM DAPAT DIPASTIKAN' (bukan dipaksa 'berisiko tinggi' ATAU 'patuh') "
        "dengan skor netral (~50) serta rekomendasi untuk konsultasi lebih lanjut "
        "atau menelusuri regulasi turunan (PP/Perkap) yang mungkin lebih spesifik.\n\n"

        "7. OUTPUT HONESTY\n"
        "   Kejujuran lebih penting daripada 'kelengkapan' artifisial. Lebih baik "
        "mengakui keterbatasan konteks daripada memaksakan korelasi yang tidak "
        "sah secara hukum. Output yang salah justru merugikan pengguna.\n"
    )

    return instructions


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


def _is_insufficient_context(context_text: str) -> bool:
    """
    Deteksi apakah konteks yang di-retrieve terlalu tipis untuk dianalisis.
    Threshold: < 300 karakter atau < 2 pasal teridentifikasi.
    """
    if not context_text or len(context_text.strip()) < 300:
        return True
    pasal_count = context_text.lower().count("pasal")
    if pasal_count < 2:
        return True
    return False


class MaterialGeneratorService:
    def __init__(self):
        self.engine = llm
        self.json_parser = JsonOutputParser(pydantic_object=MaterialResponse)

    async def generate_legal_material(self, data: MaterialRequest) -> MaterialResponse:
        """
        Menghasilkan output JSON untuk blok UI legal task agents:
        Summary, Clause Search, Legal Q&A, Risk Review.

        Alur:
        1. Klasifikasikan intent dari raw_transcribe + user_scenario (repaired).
        2. Bangun instruksi output kondisional berdasarkan intent.
        3. Invoke LLM dengan system + human prompt.
        4. Parse dan validasi respons ke MaterialResponse.

        FIX: classify_intent kini menerima raw_transcribe agar frasa orisinal
        pengguna (sebelum diparafrase repair step) tidak hilang dari deteksi intent.
        """

        # --- 1. Klasifikasi intent ---
        # PERBAIKAN KRITIS: gunakan raw_transcribe sebagai sumber utama intent,
        # repaired text sebagai fallback tambahan.
        raw_text = getattr(data, "raw_transcribe", "") or ""
        intent = classify_intent(
            raw_text=raw_text,
            repaired_text=data.user_scenario,
        )
        logger.info(
            f"MaterialGeneratorService: intent='{intent}' | "
            f"raw_snippet='{raw_text[:80]}...'"
        )

        # --- 2. System Prompt ---
        system_prompt = (
            "Anda adalah Legal Task Agent untuk dokumen hukum Indonesia yang bertugas "
            "menganalisis skenario secara objektif dan berbasis fakta.\n\n"

            "CRITICAL RULES (WAJIB DIPATUHI):\n\n"

            "1. STRICTLY CONTEXT-BOUND\n"
            "   Analisis HANYA boleh bersumber dari 'Konteks teks Dokumen Hukum' "
            "yang diberikan. Jangan berasumsi, menyimpulkan nama Undang-Undang "
            "(seperti KUHP/UU ITE), atau mengarang nomor pasal/ayat jika tidak "
            "tertulis eksplisit di dalam konteks.\n\n"

            "2. ACCURATE CLAUSE MAPPING\n"
            "   Pastikan teks kutipan (excerpt) benar-benar cocok dengan pasal/ayat "
            "aslinya. Jangan mencampuradukkan isi ayat satu dengan ayat lainnya.\n\n"

            "3. PASAL VALIDATION\n"
            "   Jika pengguna menyebut nomor pasal tertentu:\n"
            "   a) Verifikasi keberadaannya di dalam konteks.\n"
            "   b) Jika tidak ditemukan: informasikan dan rekomendasikan pasal yang tepat.\n"
            "   c) Jika pasal ada tapi ayat/huruf keliru: koreksi dengan penjelasan.\n"
            "   d) DILARANG mengarang isi pasal yang tidak ada di konteks.\n\n"

            "4. INTENT-AWARE OUTPUT\n"
            "   Ikuti instruksi output sesuai Tipe Query yang diberikan.\n"
            "   - Tipe 'konsultasi': Risk Review WAJIB diisi lengkap dengan analisis "
            "risiko, skor, mitigasi, dan rekomendasi.\n"
            "   - Tipe 'informatif': Risk Review WAJIB dikosongkan — pengguna hanya "
            "bertanya, bukan mengaku melakukan tindakan.\n\n"

            "5. COMPLETENESS ENFORCEMENT\n"
            "   Untuk tipe 'konsultasi', DILARANG mengembalikan Risk Review kosong "
            "atau bernilai default '-'. Ini adalah pelanggaran instruksi.\n\n"

            "6. PASAL SALAH ≠ TINDAKAN AMAN\n"
            "   Jika pengguna menyebut nomor pasal yang TIDAK ADA dalam konteks:\n"
            "   a) Nyatakan pasal tersebut tidak ditemukan di konteks yang diberikan.\n"
            "   b) JANGAN simpulkan bahwa tindakan pengguna 'patuh' atau 'tidak berisiko' "
            "hanya karena pasal yang disebutkan tidak ada.\n"
            "   c) TETAP evaluasi tindakan yang dideskripsikan pengguna berdasarkan pasal "
            "LAIN yang relevan dari konteks yang tersedia.\n"
            "   d) Risk Review WAJIB mencerminkan risiko atas TINDAKAN, bukan atas "
            "ketepatan nomor pasal yang disebutkan.\n"
            "   CATATAN PENYEIMBANG: Poin (c) BUKAN berarti memaksakan korelasi ke pasal "
            "yang tidak relevan secara substansi. Jika pasal pengganti yang ditemukan "
            "TIDAK benar-benar mengatur tindakan yang ditanyakan — meskipun mengandung "
            "kata kunci yang mirip — jangan dipaksakan. Nyatakan ketidakpastian dengan "
            "jujur (lihat Rule 7 dan 8).\n\n"

            "7. CLAUSE RELEVANCE GATE\n"
            "   Sebelum mengaitkan pasal manapun dengan Risk Review atau Clause Search, "
            "ajukan pertanyaan: 'Apakah pasal ini secara LANGSUNG mengatur kewajiban/"
            "larangan yang relevan dengan TINDAKAN yang dideskripsikan pengguna?'\n"
            "   Jika TIDAK — meskipun pasal itu mengandung kata kunci yang mirip "
            "(misal sama-sama soal 'keamanan', 'izin', 'pidana') — DILARANG "
            "menjadikannya dasar kesimpulan pelanggaran atau skor risiko tinggi.\n"
            "   Pasal yang HANYA mengatur tugas/wewenang internal lembaga (Polri, "
            "Pemerintah, dll) TIDAK BOLEH dijadikan dasar untuk menyimpulkan bahwa "
            "TINDAKAN WARGA SIPIL melanggar hukum, kecuali pasal tersebut secara "
            "eksplisit menyebut kewajiban/larangan bagi pihak di luar lembaga tersebut.\n"
            "   Jika TIDAK ADA pasal yang relevan secara substansi dalam konteks: "
            "nyatakan secara jujur bahwa konteks yang tersedia tidak memuat ketentuan "
            "yang secara langsung mengatur hal ini. Risk Review boleh menyatakan "
            "'BELUM DAPAT DIPASTIKAN' dengan skor netral (~50) serta rekomendasi "
            "untuk konsultasi lebih lanjut atau menelusuri regulasi turunan "
            "(PP/Perkap) yang mungkin lebih spesifik.\n\n"

            "8. OUTPUT HONESTY\n"
            "   Kejujuran lebih penting daripada 'kelengkapan' artifisial. Lebih baik "
            "mengakui keterbatasan konteks daripada memaksakan korelasi yang tidak "
            "sah secara hukum. Output yang salah justru merugikan pengguna.\n\n"

            "Gunakan gaya bahasa formal, tegas, lugas, dan patuhi PUEBI. "
            "Output HARUS valid JSON tanpa markdown, tanpa penjelasan tambahan, "
            "dan wajib mengikuti schema yang diberikan."
        )

        # --- 3. Human Prompt ---
        human_prompt = (
            f"Konteks teks Dokumen Hukum (Referensi):\n{data.context_text}\n\n"
            f"Pertanyaan/Skenario Pengguna:\n{data.user_scenario}\n\n"
            f"Tipe Query: {intent}\n\n"
            + build_output_instructions(intent)
            + f"\n{self.json_parser.get_format_instructions()}"
        )

        # ── Retry logic: coba 2 kali jika gagal ─────────────────────────────
        max_attempts = 2
        last_error = None

        for attempt in range(1, max_attempts + 1):
            try:
                chain = self.engine | self.json_parser

                response = await chain.ainvoke([
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=human_prompt),
                ])

                # --- Validasi respons LLM ---
                if response is None:
                    raise ValueError(
                        "LLM mengembalikan respons kosong/tidak valid. "
                        "Kemungkinan model tidak dapat menghasilkan JSON yang sesuai schema."
                    )

                validated = MaterialResponse.model_validate(response)

                if intent == "konsultasi":
                    rr = validated.risk_review
                    # Jika score=100 dan status=Patuh tapi summary menyebut "tidak ada" pasal
                    summary_text = ((validated.summary.overview or "") + 
                                    (validated.summary.conclusion or "")).lower()
                    false_safe_signals = [
                        "tidak ada dalam konteks",
                        "pasal tersebut tidak ada",
                        "tidak ditemukan dalam konteks",
                    ]
                    is_false_safe = (
                        rr.score >= 90 and
                        any(sig in summary_text for sig in false_safe_signals)
                    )
                    if is_false_safe:
                        logger.warning(
                            "MaterialGeneratorService: Terdeteksi FALSE SAFE — LLM menyimpulkan "
                            "'Patuh' karena pasal yang disebutkan tidak ada, bukan karena "
                            "tindakan dinilai aman. Kemungkinan perlu re-evaluate. "
                            f"raw_snippet='{raw_text[:80]}'"
                        )

                return validated

            except Exception as e:
                last_error = e
                logger.warning(
                    f"MaterialGeneratorService: Attempt {attempt}/{max_attempts} gagal. "
                    f"Error: {str(e)}"
                )
                # Lanjut ke attempt berikutnya

        # ── Semua attempt gagal ─────────────────────────────────────────────
        logger.error(
            f"MaterialGeneratorService: Semua {max_attempts} attempt gagal. "
            f"Error terakhir: {str(last_error)}"
        )
        # ── Cek apakah konteks terlalu tipis ────────────────────────────────
        is_thin_context = _is_insufficient_context(data.context_text)

        if is_thin_context:
            fallback_summary = {
                "title": "Konteks Tidak Mencukupi",
                "overview": (
                    "Konteks dokumen hukum yang tersedia terlalu sedikit untuk "
                    "menghasilkan analisis yang akurat."
                ),
                "key_points": [
                    "Dokumen hukum yang diunggah mungkin belum mencakup pasal yang relevan.",
                    "Coba tambahkan lebih banyak dokumen atau perluas cakupan knowledge base.",
                    "Pastikan query Anda sesuai dengan isi dokumen yang tersedia.",
                ],
                "conclusion": (
                    "Analisis tidak dapat dilakukan karena konteks hukum yang ditemukan "
                    "tidak mencukupi. Silakan tambahkan dokumen pendukung."
                ),
            }
            fallback_risk = {
                "status": "KONTEKS_TIDAK_CUKUP",
                "score": 0,
                "analysis": (
                    "Sistem tidak dapat mengevaluasi risiko karena konteks dokumen hukum "
                    "yang tersedia terlalu sedikit atau tidak relevan dengan pertanyaan Anda. "
                    "Tambahkan lebih banyak dokumen hukum ke knowledge base untuk hasil yang lebih akurat."
                ),
                "risks": [
                    "Analisis risiko tidak dapat dilakukan tanpa konteks hukum yang memadai."
                ],
                "mitigation_steps": [
                    "Tambahkan dokumen hukum yang relevan ke knowledge base.",
                    "Pastikan knowledge base mencakup UU atau peraturan yang Anda tanyakan.",
                    "Coba reformulasi pertanyaan agar lebih sesuai dengan dokumen yang tersedia.",
                ],
                "recommendation": (
                    "Lengkapi knowledge base dengan dokumen hukum yang relevan, "
                    "kemudian ulangi pertanyaan Anda."
                ),
            }
        else:
            fallback_summary = {
                "title": "Summary",
                "overview": "Terjadi kegagalan sistem saat menyusun ringkasan hukum.",
                "key_points": ["Proses generate gagal dijalankan"],
                "conclusion": "Data tidak dapat diproses saat ini.",
            }
            fallback_risk = {
                "status": "ERROR_SISTEM",
                "score": 0,
                "analysis": (
                    f"Gagal memproses analisis hukum karena kendala teknis. "
                    f"Detail: {str(last_error)}"
                ),
                "risks": ["Tidak dapat mengevaluasi risiko karena kegagalan sistem"],
                "mitigation_steps": [
                    "Coba ulang proses setelah sistem kembali stabil"
                ],
                "recommendation": "Ulangi permintaan setelah perbaikan sistem.",
            }

        return MaterialResponse(
            summary=fallback_summary,
            clause_search=[],
            legal_qa=[],
            risk_review=fallback_risk,
            referensi_uu=[],
        )


# Singleton instance aman digunakan oleh router
material_service = MaterialGeneratorService()