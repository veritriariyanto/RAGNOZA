from app.core.llm_provider import llm
import asyncio
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.output_parsers import JsonOutputParser
# Jika kamu menggunakan ChatGroq bawaan langchain_groq
# pastikan modul di-import dengan benar jika diperlukan

class TextRefinerService:
    def __init__(self):
        self.engine = llm
        self.json_parser = JsonOutputParser()

    async def repair_legal_text(self, raw_text: str) -> dict:
        if not raw_text or not raw_text.strip():
            return {"repaired_text": "", "search_query": ""}

        system_prompt = (
            "Anda adalah editor naskah hukum dan analis teks spesialis peraturan perundang-undangan Indonesia. "
            "Tugas Utama Anda:\n"
            "1. Perbaiki teks transkripsi agar rapi sesuai PUEBI & terminologi hukum resmi.\n"
            "2. Hapus total karakter pengganggu cetak atau noise seperti 'SK No XXXXX', '--- PAGE X ---'.\n"
            "3. Pertahankan struktur kalimat asli pasal. JANGAN mengubah esensi, makna, nomor pasal, atau nomor ayat.\n"
            "4. Ekstrak 'search_query': 1 kalimat singkat, padat, & spesifik yang mencerminkan materi hukum pada potongan teks tersebut.\n\n"
            "WAJIB kembalikan HANYA JSON valid dengan skema yang diminta. Tanpa markdown code block."
        )

        human_prompt = (
            f"Teks mentah: {raw_text}\n\n"
            "Format output JSON yang diminta:\n"
            '{"repaired_text": "teks yang sudah diperbaiki", "search_query": "query pencarian"}'
        )

        max_retries = 3
        retry_delay = 3  # Detik jeda sebelum mencoba kembali jika terkena rate-limit

        for attempt in range(max_retries):
            try:
                chain = self.engine | self.json_parser
                response = await chain.ainvoke([
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=human_prompt)
                ])

                if not isinstance(response, dict) or "repaired_text" not in response or "search_query" not in response:
                    raise ValueError("Output LLM tidak sesuai skema JSON")

                return response

            except Exception as e:
                error_msg = str(e)
                # Cek apakah error disebabkan oleh Rate Limit (429)
                if "429" in error_msg or "rate_limit_exceeded" in error_msg.lower():
                    print(f"[Warning] Terkena Rate Limit Groq (429). Mencoba kembali dalam {retry_delay} detik... (Percobaan {attempt + 1}/{max_retries})")
                    await asyncio.sleep(retry_delay)
                    continue  # Lanjutkan ke iterasi loop berikutnya untuk mencoba lagi
                
                # Jika error jenis lain, langsung cetak error dan keluar dari loop untuk memicu fallback
                print(f"[Error] TextRefinerService internal: {error_msg}")
                break

        # Fallback aman jika seluruh retry gagal atau terjadi error non-429
        return {
            "repaired_text": raw_text.strip(),
            "search_query": raw_text.strip()[:200]
        }

# Inisialisasi instance
text_refiner = TextRefinerService()