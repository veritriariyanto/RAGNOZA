import logging
from app.core.llm_provider import llm
from app.schemas.prompting.generate_content import MaterialRequest, MaterialResponse
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.output_parsers import JsonOutputParser

logger = logging.getLogger(__name__)

class MaterialGeneratorService:
    def __init__(self):
        self.engine = llm
        # Parser otomatis mengenali struktur dari MaterialResponse
        self.json_parser = JsonOutputParser(pydantic_object=MaterialResponse)

    async def generate_legal_material(self, data: MaterialRequest) -> MaterialResponse:
        """
        Menghasilkan materi edukasi hukum dengan pemisahan instruksi logika dan format.
        """
        
        # 1. System Prompt: Fokus pada "Otak" / Peran / Logika Hukum
        system_prompt = (
            "Anda adalah Spesialis Konten Hukum senior di Indonesia. "
            "Tugas Anda adalah menyusun materi edukasi yang akurat, terstruktur, "
            "dan mudah dipahami berdasarkan fakta hukum yang diberikan. "
            "Gunakan terminologi hukum yang tepat dan patuhi PUEBI."
        )

        # 2. Human Prompt: Fokus pada "Data" + "Format Otomatis"
        # Kita panggil self.json_parser.get_format_instructions() agar LangChain
        # yang menuliskan aturan JSON-nya secara teknis untuk kita.
        human_prompt = (
            f"Konteks Teks Sumber:\n{data.context_text}\n\n"
            f"Gaya Bahasa yang Diminta: {data.style}\n\n"
            "Instruksi Tambahan: Buatlah materi yang informatif.\n\n"
            f"{self.json_parser.get_format_instructions()}"
        )

        try:
            # Gunakan Pipe Operator LangChain
            chain = self.engine | self.json_parser
            
            response = await chain.ainvoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=human_prompt)
            ])

            # Karena response sudah divalidasi parser, kita bisa langsung bungkus ke model
            return MaterialResponse(**response)

        except Exception as e:
            logger.error(f"MaterialGeneratorService Error: {str(e)}")
            # Fallback yang aman agar sistem tidak crash
            return MaterialResponse(
                title="Gagal Menghasilkan Materi",
                content=f"Terjadi kendala teknis saat memproses materi hukum. Detail: {str(e)}",
                key_points=["Gagal memuat poin penting"],
                legal_basis=[]
            )

# Singleton instance
material_service = MaterialGeneratorService()