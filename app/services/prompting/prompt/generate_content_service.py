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
            "Anda adalah Legal Task Agent untuk dokumen hukum Indonesia. "
            "Anda harus menyiapkan output terstruktur untuk blok: Summary, Clause Search, Legal Q&A, Risk Review, Timeline Extraction, dan Comparison. "
            "Tugas Anda adalah menganalisis skenario pengguna secara objektif berdasarkan konteks hukum yang diberikan. "
            "Gunakan gaya bahasa formal, tegas, lugas, dan patuhi PUEBI. "
            "Jangan pernah mengarang pasal atau referensi. Jika konteks tidak memadai, nyatakan dengan jelas bahwa data tidak memadai. "
            "Output HARUS valid JSON tanpa markdown, tanpa penjelasan tambahan, dan wajib mengikuti schema yang diberikan."
        )

        # 2. Human Prompt: Berisi konteks hukum, skenario, dan struktur jawaban yang diharapkan.
        human_prompt = (
            f"Konteks teks Dokumen Hukum (Referensi):\n{data.context_text}\n\n"
            f"Skenario Tindakan Pengguna (Kasus):\n{data.user_scenario}\n\n"
            "Instruksi Output:\n"
            "1. Isi Summary dengan ringkasan isi dokumen hukum, poin penting, dan kesimpulan singkat.\n"
            "2. Isi Clause Search dengan pencarian klausul/pasal/ayat yang paling relevan terhadap pertanyaan pengguna.\n"
            "3. Isi Legal Q&A dengan 3 sampai 5 pertanyaan dan jawaban yang benar-benar berbasis konteks.\n"
            "4. Isi Risk Review dengan status, skor, analisis risiko, mitigasi, dan rekomendasi.\n"
            "5. Isi Timeline Extraction dengan tanggal, masa berlaku, tenggat, atau urutan peristiwa hukum yang relevan.\n"
            "6. Isi Comparison dengan perbandingan dua ketentuan, klausul, atau dokumen yang relevan.\n"
            "7. Jika data tidak tersedia untuk salah satu blok, gunakan array kosong atau nilai yang menyatakan data tidak memadai tanpa mengarang.\n\n"
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