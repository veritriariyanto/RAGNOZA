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
        "   - Lanjutkan dengan ringkasan konteks hukum pendukung secara presisi.\n"
        "   - Sertakan poin-poin penting dan kesimpulan singkat.\n\n"
        "2. CLAUSE SEARCH\n"
        "   - Petakan pasal/ayat yang PALING RELEVAN dengan pertanyaan pengguna.\n"
        "   - Teks excerpt WAJIB menyalin verbatim dari konteks — dilarang mengubah "
        "atau mencampurkan isi antar ayat.\n"
        "   - VALIDASI PASAL: Jika pengguna menyebut nomor pasal tertentu dalam query:\n"
        "     a) Verifikasi apakah pasal tersebut ADA dalam konteks yang diberikan.\n"
        "     b) Jika TIDAK ADA: nyatakan di field 'relevance' bahwa pasal tersebut "
        "tidak ditemukan, lalu rekomendasikan pasal yang paling relevan dari konteks.\n"
        "     c) Jika pasal ADA namun pengguna menyebut ayat/huruf yang keliru: "
        "koreksi dan tunjukkan pasal/ayat yang tepat beserta alasannya.\n"
        "     d) DILARANG mengarang isi pasal yang tidak ada di konteks.\n"
        "   - CLAUSE HONESTY: Jika tidak ada pasal yang secara spesifik mengatur hal "
        "yang ditanyakan, pilih pasal terdekat dan nyatakan secara eksplisit di field "
        "'relevance' bahwa ini merupakan ketentuan umum/terdekat yang tersedia, "
        "bukan pasal yang secara langsung mengatur.\n\n"
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
            "     • mitigation_steps: langkah-langkah mitigasi yang dapat diambil\n"
            "     • recommendation: rekomendasi konkret dan actionable\n"
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
        "   - DILARANG mengarang informasi di luar konteks yang diberikan.\n"
    )

    return instructions


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

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

                # --- Post-validation: pastikan risk_review tidak kosong untuk konsultasi ---
                if intent == "konsultasi":
                    rr = validated.risk_review
                    if not rr or rr.analysis in ("-", "", None):
                        logger.warning(
                            "MaterialGeneratorService: Risk Review kosong untuk intent "
                            "'konsultasi' — kemungkinan LLM mengabaikan instruksi. "
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
        return MaterialResponse(
            summary={
                "title": "Summary",
                "overview": "Terjadi kegagalan sistem saat menyusun ringkasan hukum.",
                "key_points": ["Proses generate gagal dijalankan"],
                "conclusion": "Data tidak dapat diproses saat ini.",
            },
            clause_search=[],
            legal_qa=[],
            risk_review={
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
            },
            referensi_uu=[],
        )


# Singleton instance aman digunakan oleh router
material_service = MaterialGeneratorService()