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
        "saya melakukan", "saya ingin", "saya telah", "saya sudah",
        "kami melakukan", "kami berencana", "kami ingin",
        "tindakan saya", "perbuatan saya",
        "apakah saya bisa dituntut", "apakah saya bisa dipidana",
        "apakah saya melanggar", "apakah tindakan saya",
        "bisakah saya dituntut", "dapatkah saya dipidana",
    ],
    "informatif": [
        "apakah", "apa itu", "apa yang dimaksud",
        "bagaimana", "bagaimana cara", "bagaimana ketentuan",
        "bolehkah", "bisakah", "dapatkah",
        "jelaskan", "definisi", "pengertian",
        "siapa yang", "kapan", "berapa lama",
    ],
}


def classify_intent(scenario: str) -> str:
    """
    Mengklasifikasikan query pengguna menjadi salah satu dari:
    - 'konsultasi' : pengguna mendeskripsikan tindakan yang dilakukan/direncanakan
    - 'informatif' : pengguna bertanya tentang ketentuan hukum secara umum (default)
    """
    s = scenario.lower()
    # Cek konsultasi lebih dahulu karena lebih spesifik dan berisiko lebih tinggi
    for keyword in INTENT_KEYWORDS["konsultasi"]:
        if keyword in s:
            return "konsultasi"
    return "informatif"


# ---------------------------------------------------------------------------
# Conditional Output Instructions
# ---------------------------------------------------------------------------

def build_output_instructions(intent: str) -> str:
    """
    Membangun instruksi output yang disesuaikan dengan intent query.
    Disesuaikan agar LLM tidak over-compliant dan mengosongkan blok penting.
    """
    instructions = (
        "Instruksi Output (ikuti sesuai urutan dan tipe query):\n"
        "1. SUMMARY: Awali dengan 1 kalimat yang langsung menjawab pertanyaan/skenario "
        "pengguna. Lanjutkan dengan ringkasan konteks hukum pendukung secara presisi, "
        "poin-poin penting, dan kesimpulan singkat.\n"
        "2. CLAUSE SEARCH: Petakan pasal/ayat yang paling relevan dengan pertanyaan. "
        "Teks excerpt WAJIB menyalin verbatim dari konteks tanpa diubah atau dicampur.\n"
        "3. LEGAL Q&A: Jawab HANYA pertanyaan yang secara eksplisit diajukan pengguna. "
        "Jumlah Q&A maksimal 1-2 pasang, berbasis konteks.\n"
    )

    if intent == "konsultasi":
        instructions += (
            "4. RISK REVIEW: Isi dengan skor risiko (0-100) di mana semakin melanggar hukum "
            "skornya semakin rendah mendekati 0. Isi analisis risiko tindakan, "
            "daftar risiko potensial, langkah mitigasi konkret, dan rekomendasi.\n"
        )
    else:
        instructions += (
            "4. RISK REVIEW: Kosongkan Risk Review — isi status dengan '-', skor dengan 0, "
            "dan semua field lainnya dengan nilai default.\n"
        )

    instructions += (
        "5. TIMELINE EXTRACTION: Ekstrak semua elemen kronologi waktu, tanggal kejadian yang "
        "disebutkan oleh pengguna di dalam skenario, ATAU batasan waktu/durasi hukuman pidana "
        "(contoh: 'paling lama 6 tahun', 'tanggal 1 Juni') yang terdapat di dalam teks dokumen "
        "maupun skenario. WAJIB diisi jika ada informasi waktu sekecil apa pun.\n"
        
        "6. COMPARISON: Blok ini WAJIB DIISI dan TIDAK BOLEH KOSONG jika: (a) Pengguna meminta "
        "perbandingan/perbedaan/pengandaian secara eksplisit, ATAU (b) Terdapat lebih dari satu ayat/pasal "
        "di dalam Konteks Dokumen Hukum yang saling berkaitan. "
        "Lakukan komparasi objek secara terstruktur yang membandingkan perbedaan unsur perbuatan, "
        "kondisi prasyarat, dampak, atau sanksi pidana antar pasal/ayat tersebut (contoh: bandingkan Pasal 5 ayat 1 "
        "tentang pemindahan data biasa dengan Pasal 5 ayat 2 tentang pemindahan data yang merugikan perbankan).\n"
        
        "7. Gunakan nilai default atau array kosong [] HANYA jika benar-benar tidak ada data "
        "hukum maupun skenario yang berkaitan sama sekali.\n"
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
        Summary, Clause Search, Legal Q&A, Risk Review, Timeline Extraction, Comparison.

        Alur:
        1. Klasifikasikan intent query (informatif vs konsultasi).
        2. Bangun instruksi output kondisional berdasarkan intent.
        3. Invoke LLM dengan system + human prompt.
        4. Parse dan validasi respons ke MaterialResponse.
        """

        # --- 1. Klasifikasi intent ---
        intent = classify_intent(data.user_scenario)
        logger.info(f"MaterialGeneratorService: intent terdeteksi = '{intent}'")

        # --- 2. System Prompt ---
        # Mengunci peran, format output, gaya bahasa formal, dan anti-hallucination rules.
        system_prompt = (
            "Anda adalah Legal Task Agent untuk dokumen hukum Indonesia yang bertugas "
            "menganalisis skenario secara objektif dan berbasis fakta.\n\n"
            "CRITICAL RULES (WAJIB DIPATUHI):\n"
            "1. STRICTLY CONTEXT-BOUND: Analisis HANYA boleh bersumber dari "
            "'Konteks teks Dokumen Hukum' yang diberikan. Jangan berasumsi, "
            "menyimpulkan nama Undang-Undang (seperti KUHP/UU ITE), atau mengarang "
            "nomor pasal/ayat jika tidak tertulis eksplisit di dalam konteks.\n"
           "2. MANDATORY COMPARISON ON CONTEXT: Pada blok Comparison, Anda DIWAJIBKAN "
            "menyusun analisis komparatif apabila teks referensi menyediakan lebih dari satu ayat/pasal "
            "atau jika pengguna menanyakan perbedaan dampak/situasi. Menyimpulkan perbedaan sanksi "
            "(misal: 5 tahun vs 8 tahun) atau perbedaan dampak (biasa vs sistem perbankan) berdasarkan "
            "teks yang tersedia adalah tugas utama Anda dan BUKANLAH halusinasi.\n"
            "3. ACCURATE CLAUSE MAPPING: Pastikan teks kutipan (excerpt) benar-benar "
            "cocok dengan pasal/ayat aslinya. Jangan mencampuradukkan isi ayat satu "
            "dengan ayat lainnya.\n"
            "4. TIMELINE STRICTNESS: Field 'date_or_period' WAJIB berisi durasi waktu, "
            "tanggal, tenggat, atau periode hukuman (contoh: '2 tahun', '4 tahun') "
            "yang ada di teks. BUKAN diisi nama pasal atau label lainnya.\n"
            "5. INTENT-AWARE OUTPUT: Ikuti instruksi output sesuai tipe query yang "
            "diberikan. Jika tipe query adalah 'informatif', JANGAN mengisi Risk Review "
            "dengan skor risiko — pengguna hanya bertanya, bukan mengaku melakukan "
            "tindakan.\n"
            "6. Jika konteks tidak memadai untuk mengisi suatu blok, kosongkan blok "
            "tersebut (array kosong atau '-' sesuai schema) tanpa mengarang informasi.\n\n"
            "Gunakan gaya bahasa formal, tegas, lugas, dan patuhi PUEBI. "
            "Output HARUS valid JSON tanpa markdown, tanpa penjelasan tambahan, "
            "dan wajib mengikuti schema yang diberikan."
        )

        # --- 3. Human Prompt ---
        # Berisi konteks hukum, query/skenario, tipe intent, dan instruksi output kondisional.
        human_prompt = (
            f"Konteks teks Dokumen Hukum (Referensi):\n{data.context_text}\n\n"
            f"Pertanyaan/Skenario Pengguna:\n{data.user_scenario}\n\n"
            f"Tipe Query: {intent}\n\n"
            + build_output_instructions(intent)
            + f"\n{self.json_parser.get_format_instructions()}"
        )

        try:
            chain = self.engine | self.json_parser

            response = await chain.ainvoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=human_prompt),
            ])

            return MaterialResponse.model_validate(response)

        except Exception as e:
            logger.error(f"MaterialGeneratorService Error: {str(e)}")
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
                        f"Detail: {str(e)}"
                    ),
                    "risks": ["Tidak dapat mengevaluasi risiko karena kegagalan sistem"],
                    "mitigation_steps": [
                        "Coba ulang proses setelah sistem kembali stabil"
                    ],
                    "recommendation": "Ulangi permintaan setelah perbaikan sistem.",
                },
                timeline_extraction=[],
                comparison=[],
                referensi_uu=[],
            )


# Singleton instance aman digunakan oleh router
material_service = MaterialGeneratorService()