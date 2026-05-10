# app/services/text_service.py
from app.core.llm_provider import llm
from langchain_core.messages import SystemMessage, HumanMessage

class TextRefinerService:
    def __init__(self):
        self.engine = llm

    async def repair_legal_text(self, raw_text: str) -> str:
        """
        Membersihkan teks transkripsi agar sesuai standar hukum dan PUEBI.
        """
        if not raw_text or not raw_text.strip():
            return ""

        # Prompt diperkuat agar LLM tidak berhalusinasi atau menambah teks sendiri
        repair_prompt = (
            "Perbaiki teks berikut sesuai standar PUEBI dan terminologi hukum Indonesia. "
            "Koreksi kapitalisasi pada istilah seperti 'UUD 1945', 'Pasal', 'Ayat', 'Mahkamah Konstitusi'. "
            "Hapus filler words (seperti: 'anu', 'apa', 'eh', 'hm'). "
            "Jangan mengubah makna atau menambahkan informasi baru.\n\n"
            f"Teks: {raw_text}"
        )

        try:
            response = await self.engine.ainvoke([
                SystemMessage(content="Anda adalah editor naskah hukum. Berikan hasil perbaikan teks saja tanpa pembukaan, penutup, atau tanda kutip."),
                HumanMessage(content=repair_prompt)
            ])
            
            # Memastikan hasil yang dikembalikan adalah string
            result = str(response.content).strip()
            return result if result else raw_text
            
        except Exception as e:
            print(f"[Error] TextRefinerService: {str(e)}")
            return raw_text

# Inisialisasi instance
text_refiner = TextRefinerService()