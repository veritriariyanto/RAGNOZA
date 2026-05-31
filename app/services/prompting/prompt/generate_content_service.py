# app/services/prompting/prompt/generate_content_service.py

import logging
from app.core.llm_provider import llm
from app.schemas.prompting.generate_content import MaterialRequest, MaterialResponse
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.output_parsers import JsonOutputParser

logger = logging.getLogger(__name__)

class MaterialGeneratorService:
    def __init__(self):
        self.engine = llm
        # Parser otomatis mengenali struktur baru MaterialResponse yang dipakai blok UI legal task agents
        self.json_parser = JsonOutputParser(pydantic_object=MaterialResponse)

    async def generate_legal_material(self, data: MaterialRequest) -> MaterialResponse:
        """
        Menghasilkan output JSON untuk blok:
        Summary, Clause Search, Legal Q&A, Risk Review, Timeline Extraction, dan Comparison.
        """

        # 1. System Prompt: Mengunci peran, format output, dan gaya bahasa formal.
        system_prompt = (
            "Anda adalah Legal Task Agent untuk dokumen hukum Indonesia yang bertugas menganalisis skenario secara objektif dan berbasis fakta.\n\n"
            "CRITICAL RULES (WAJIB DIPATUHI):\n"
            "1. STRICTLY CONTEXT-BOUND: Analisis HANYA boleh bersumber dari 'Konieks teks Dokumen Hukum' yang diberikan. Jangan berasumsi, menyimpulkan nama Undang-Undang (seperti KUHP/UU ITE), atau mengarang nomor pasal/ayat jika tidak tertulis eksplisit di dalam konteks.\n"
            "2. NO HALUCINATION ON COMPARISON: Pada blok Comparison, Anda HANYA boleh membandingkan dua ketentuan yang benar-benar tertulis di dalam konteks teks. Jika tidak ada elemen pembanding di dalam konteks, isi bidang comparison dengan array kosong []. DILARANG MENGARANG pasal pembanding (seperti Pasal 27B).\n"
            "3. ACCURATE CLAUSE MAPPING: Pastikan teks kutipan (excerpt) atau isi ringkasan benar-benar cocok dengan pasal/ayat aslinya. Jangan mencampuradukkan isi ayat satu dengan ayat lainnya.\n"
            "4. TIMELINE STRICTNESS: Bidang 'date_or_period' pada Timeline Extraction WAJIB berisi durasi waktu, tanggal, tenggat masa berlaku, atau periode hukuman (misal: '2 tahun', '4 tahun') yang ada di teks, BUKAN diisi nama pasal.\n"
            "5. Jika konteks tidak memadai untuk mengisi suatu blok, kosongkan blok tersebut (gunakan array kosong atau '-' sesuai schema Pydantic) tanpa mengarang informasi.\n\n"
            "Gunakan gaya bahasa formal, tegas, lugas, patuhi PUEBI. Output HARUS valid JSON tanpa markdown, tanpa penjelasan tambahan, dan wajib mengikuti schema."
        )

        # 2. Human Prompt: Berisi konteks hukum, skenario, dan struktur jawaban yang diharapkan.
        human_prompt = (
            f"Konieks teks Dokumen Hukum (Referensi):\n{data.context_text}\n\n"
            f"Skenario Tindakan Pengguna (Kasus):\n{data.user_scenario}\n\n"
            "Instruksi Output:\n"
            "1. Isi Summary dengan ringkasan isi dokumen hukum secara presisi, poin penting, dan kesimpulan singkat.\n"
            "2. Isi Clause Search dengan memetakan klausul/pasal/ayat yang paling relevan. Pastikan teks ekskrip (excerpt) murni menyalin dari konteks tanpa tertukar.\n"
            "3. Isi Legal Q&A dengan 3 sampai 5 pertanyaan dan jawaban yang benar-benar berbasis konteks untuk menjawab kasus pengguna.\n"
            "4. Isi Risk Review dengan status, skor (0-100), analisis risiko, mitigasi, dan rekomendasi berdasarkan kasus pengguna.\n"
            "5. Isi Timeline Extraction dengan urutan waktu/peristiwa. Catatan: 'date_or_period' harus mengekstrak elemen waktu (seperti masa hukuman penjara, batas waktu pengaduan), BUKAN nama pasal. Jika tidak ada elemen waktu, kosongkan.\n"
            "6. Isi Comparison HANYA jika terdapat dua ketentuan atau lebih di dalam teks konteks yang bisa diperbandingkan secara nyata. JIKA TIDAK ADA, isi dengan array kosong [].\n"
            "7. Jika data tidak tersedia atau tidak memadai untuk salah satu blok, gunakan array kosong atau nilai default '-' tanpa melakukan karangan di luar teks.\n\n"
            f"{self.json_parser.get_format_instructions()}"
        )

        try:
            # Menggunakan Pipe Operator LangChain
            chain = self.engine | self.json_parser
            
            response = await chain.ainvoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=human_prompt)
            ])

            return MaterialResponse.model_validate(response)

        except Exception as e:
            logger.error(f"MaterialGeneratorService Error: {str(e)}")
            # Fallback aman, pastikan semua key di MaterialResponse terpenuhi.
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
                    "analysis": f"Gagal memproses analisis hukum karena kendala teknis. Detail: {str(e)}",
                    "risks": ["Tidak dapat mengevaluasi risiko karena kegagalan sistem"],
                    "mitigation_steps": ["Coba ulang proses setelah sistem kembali stabil"],
                    "recommendation": "Ulangi permintaan setelah perbaikan sistem.",
                },
                timeline_extraction=[],
                comparison=[],
                referensi_uu=[],
            )

# Singleton instance aman digunakan oleh router
material_service = MaterialGeneratorService()