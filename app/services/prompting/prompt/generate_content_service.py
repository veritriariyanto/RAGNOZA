import logging
from app.core.llm_provider import llm
from app.schemas.prompting.generate_content import MaterialRequest, MaterialResponse
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.output_parsers import JsonOutputParser

logger = logging.getLogger(__name__)

class MaterialGeneratorService:
    def __init__(self):
        self.engine = llm
        # Parser otomatis mengenali struktur baru dari MaterialResponse (SPK)
        self.json_parser = JsonOutputParser(pydantic_object=MaterialResponse)

    async def generate_legal_material(self, data: MaterialRequest) -> MaterialResponse:
        """
        Menghasilkan rekomendasi keputusan hukum berdasarkan analisis UU (SPK).
        """
        
        # 1. System Prompt: Mengunci peran & gaya bahasa formal secara internal
        system_prompt = (
            "Anda adalah Sistem Penunjang Keputusan (SPK) Hukum Senior di Indonesia. "
            "Tugas Anda adalah menganalisis skenario tindakan pengguna secara objektif dan ketat "
            "berdasarkan konteks dokumen hukum yang diberikan. "
            "Sampaikan hasil analisis dengan gaya bahasa yang formal, tegas, lugas, dan patuhi PUEBI. "
            "Tentukan status keputusan dengan jelas dan hitung skor kepatuhannya (1-100). "
            "Jangan pernah melakukan halusinasi pasal. Jika tidak diatur di teks sumber, katakan data tidak memadai."
        )

        # 2. Human Prompt: Bersih dari data.style, berfokus penuh pada skenario dan konteks
        human_prompt = (
            f"Konto teks Dokumen Hukum (Referensi):\n{data.context_text}\n\n"
            f"Skenario Tindakan Pengguna (Kasus):\n{data.user_scenario}\n\n"
            "Instruksi Analisis:\n"
            "1. Evaluasi apakah skenario pengguna melanggar atau mematuhi konteks hukum.\n"
            "2. Berikan skor kepatuhan, analisis risiko sanksi, dan rekomendasi mitigasinya.\n\n"
            f"{self.json_parser.get_format_instructions()}"
        )

        try:
            # Menggunakan Pipe Operator LangChain
            chain = self.engine | self.json_parser
            
            response = await chain.ainvoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=human_prompt)
            ])

            return MaterialResponse(**response)

        except Exception as e:
            logger.error(f"MaterialGeneratorService Error: {str(e)}")
            # Fallback aman, pastikan semua key di MaterialResponse (SPK) terpenuhi
            return MaterialResponse(
                decision_status="ERROR_SISTEM",
                compliance_score=0,
                recommendation=f"Gagal memproses keputusan hukum karena kendala teknis. Detail: {str(e)}",
                risk_analysis=["Tidak dapat mengevaluasi risiko karena kegagalan sistem"],
                legal_basis=[]
            )

# Singleton instance aman digunakan oleh router
material_service = MaterialGeneratorService()