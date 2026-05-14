from app.core.llm_provider import llm
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.output_parsers import JsonOutputParser
import json
import re

class TextRefinerService:
    def __init__(self):
        self.engine = llm
        # Parser bawaan LangChain untuk menjamin output JSON terstruktur
        self.json_parser = JsonOutputParser()

    async def repair_legal_text(self, raw_text: str) -> dict:
        """
        Memperbaiki teks transkripsi & menghasilkan search_query dalam format JSON.
        Returns: {"repaired_text": str, "search_query": str}
        """
        if not raw_text or not raw_text.strip():
            return {"repaired_text": "", "search_query": ""}

        system_prompt = (
            "Anda adalah editor naskah hukum dan analis teks. "
            "Tugas: "
            "1. Perbaiki teks sesuai PUEBI & terminologi hukum Indonesia. "
            "   Koreksi kapitalisasi resmi (UUD 1945, Pasal, Ayat, Mahkamah Konstitusi, dll). "
            "   Hapus filler words (anu, eh, hm, apa, dll). "
            "   JANGAN mengubah makna atau menambahkan fakta baru. "
            "2. Ekstrak 'search_query': 1 kalimat singkat, padat, & spesifik yang mewakili "
            "   inti persoalan hukum untuk pencarian di database vektor (Qdrant). "
            "WAJIB kembalikan HANYA JSON valid. Tanpa penjelasan, tanpa markdown code block, tanpa teks tambahan."
        )

        human_prompt = (
            f"Teks mentah: {raw_text}\n\n"
            "Format output JSON yang diminta:\n"
            '{"repaired_text": "teks yang sudah diperbaiki", "search_query": "query pencarian"}'
        )

        try:
            # Rantai LLM + JSON Parser
            chain = self.engine | self.json_parser
            
            # Note: Jika LLM Anda mendukung, tambahkan .bind(response_format={"type": "json_object"})
            response = await chain.ainvoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=human_prompt)
            ])

            # Validasi struktur JSON
            if not isinstance(response, dict) or "repaired_text" not in response or "search_query" not in response:
                raise ValueError("Output LLM tidak sesuai skema JSON yang diminta")

            return response

        except Exception as e:
            print(f"[Error] TextRefinerService: {str(e)}")
            # Fallback aman agar pipeline tidak crash
            return {
                "repaired_text": raw_text.strip(),
                "search_query": raw_text.strip()[:200]
            }

# Inisialisasi instance
text_refiner = TextRefinerService()