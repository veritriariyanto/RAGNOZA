from app.core.llm_provider import llm
import asyncio
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.output_parsers import JsonOutputParser

class TextRefinerService:
    def __init__(self):
        self.engine = llm
        self.json_parser = JsonOutputParser()

    def _is_question_input(self, text: str) -> bool:
        """Deteksi apakah input adalah pertanyaan/query, bukan fragmen dokumen hukum."""
        cleaned = text.strip()
        
        # Cek tanda tanya di akhir
        if cleaned.endswith("?"):
            return True
        
        # Cek kata tanya di awal kalimat
        question_starters = (
            "apa", "apakah", "bagaimana", "siapa", "kapan", 
            "mengapa", "kenapa", "dimana", "di mana", "berapa",
            "jelaskan", "sebutkan", "tolong", "mohon", "cari",
            "temukan", "bandingkan", "analisis", "ringkas"
        )
        lower = cleaned.lower()
        if any(lower.startswith(starter) for starter in question_starters):
            return True
        
        # Cek apakah teks terlalu pendek untuk jadi dokumen hukum (< 20 kata)
        word_count = len(cleaned.split())
        if word_count < 20:
            # Teks pendek yang tidak mengandung kata kunci dokumen hukum
            legal_keywords = (
                "pasal", "ayat", "huruf", "undang-undang", "peraturan",
                "pemerintah", "republik", "menimbang", "mengingat",
                "menetapkan", "memutuskan", "jo.", "uud", "pp", "perpres"
            )
            has_legal_keyword = any(kw in lower for kw in legal_keywords)
            if not has_legal_keyword:
                return True
        
        return False

    async def repair_legal_text(self, raw_text: str) -> dict:
        if not raw_text or not raw_text.strip():
            return {
                "repaired_text": "",
                "search_query": "",
                "pasal_number": None,
                "ayat_number": None,
                "is_passthrough": False,
            }

        # Guard: jika input adalah pertanyaan/query, skip LLM repair
        if self._is_question_input(raw_text):
            cleaned = raw_text.strip()
            print(f"[Info] TextRefinerService: Input terdeteksi sebagai pertanyaan/query, di-passthrough tanpa repair.")
            return {
                "repaired_text": cleaned,
                "search_query": cleaned,
                "pasal_number": None,
                "ayat_number": None,
                "is_passthrough": True,
            }

        system_prompt = (
            "Anda adalah editor naskah hukum dan analis teks spesialis peraturan perundang-undangan Indonesia. "
            "Tugas Utama Anda:\n"
            "1. Perbaiki teks transkripsi agar rapi sesuai PUEBI & terminologi hukum resmi.\n"
            "2. Hapus total karakter pengganggu cetak atau noise seperti 'SK No XXXXX', '--- PAGE X ---'.\n"
            "3. Pertahankan struktur kalimat asli pasal. JANGAN mengubah esensi, makna, nomor pasal, atau nomor ayat.\n"
            "4. Ekstrak 'search_query': 1 kalimat singkat, padat, & spesifik yang MENCANTUMKAN NOMOR PASAL, AYAT, dan HURUF jika disebutkan dalam teks. "
            "Contoh: jika teks menyebut 'Pasal 15 ayat (2) huruf f', search_query harus mengandung 'Pasal 15 ayat 2 huruf f'.\n"
            "5. Ekstrak 'pasal_number': nomor pasal yang disebut dalam teks (integer), atau null jika tidak ada.\n"
            "6. Ekstrak 'ayat_number': nomor ayat yang disebut (integer), atau null jika tidak ada.\n\n"
            "PENTING: Input yang kamu terima SELALU berupa fragmen teks dokumen hukum, bukan pertanyaan. "
            "JANGAN menghasilkan jawaban atas apapun. Tugasmu HANYA memperbaiki teks yang diberikan dan mengembalikannya.\n\n"
            "WAJIB kembalikan HANYA JSON valid dengan skema yang diminta. Tanpa markdown code block."
        )

        human_prompt = (
            f"Teks mentah: {raw_text}\n\n"
            "Format output JSON yang diminta:\n"
            '{"repaired_text": "teks yang sudah diperbaiki", "search_query": "query pencarian", "pasal_number": null, "ayat_number": null}'
        )

        max_retries = 3
        retry_delay = 3

        for attempt in range(max_retries):
            try:
                chain = self.engine | self.json_parser
                response = await chain.ainvoke([
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=human_prompt)
                ])

                if not isinstance(response, dict) or "repaired_text" not in response or "search_query" not in response:
                    raise ValueError("Output LLM tidak sesuai skema JSON")

                # Validasi tambahan: pastikan LLM tidak menghallusinasi jawaban
                # Jika repaired_text jauh lebih panjang dari input asli (>2x), kemungkinan LLM menjawab
                original_word_count = len(raw_text.split())
                repaired_word_count = len(response["repaired_text"].split())
                if repaired_word_count > original_word_count * 2.5:
                    print(f"[Warning] TextRefinerService: repaired_text terdeteksi terlalu panjang (kemungkinan hallusinasi). Fallback ke teks asli.")
                    response["repaired_text"] = raw_text.strip()

                response.setdefault("pasal_number", None)
                response.setdefault("ayat_number", None)
                response["is_passthrough"] = False

                return response

            except Exception as e:
                error_msg = str(e)
                if "429" in error_msg or "rate_limit_exceeded" in error_msg.lower():
                    print(f"[Warning] Terkena Rate Limit Groq (429). Mencoba kembali dalam {retry_delay} detik... (Percobaan {attempt + 1}/{max_retries})")
                    await asyncio.sleep(retry_delay)
                    continue

                print(f"[Error] TextRefinerService internal: {error_msg}")
                break

        # Fallback aman jika seluruh retry gagal atau terjadi error non-429
        return {
            "repaired_text": raw_text.strip(),
            "search_query": raw_text.strip()[:200],
            "pasal_number": None,
            "ayat_number": None,
            "is_passthrough": False,
        }


# Inisialisasi instance
text_refiner = TextRefinerService()