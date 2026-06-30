import re
from app.core.llm_provider import llm
import asyncio
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.output_parsers import JsonOutputParser

class TextRefinerService:
    def __init__(self):
        self.engine = llm
        self.json_parser = JsonOutputParser()

    # ── Regex extraction helpers ─────────────────────────────────────────────

    @staticmethod
    def _extract_pasal_number(text: str) -> int | None:
        """
        Ekstrak nomor pasal pertama yang disebut dalam teks.
        Cocok: 'Pasal 15', 'pasal 15 ayat (2)', 'ps 15'
        """
        m = re.search(r"(?:pasal|ps\.?)\s*(\d+)", text, re.IGNORECASE)
        if m:
            return int(m.group(1))
        return None

    @staticmethod
    def _extract_ayat_number(text: str) -> int | None:
        """
        Ekstrak nomor ayat pertama yang disebut dalam teks.
        Cocok: 'ayat (2)', 'ayat 2', 'Ayat (1)'
        """
        m = re.search(r"ayat\s*\(?(\d+)\)?", text, re.IGNORECASE)
        if m:
            return int(m.group(1))
        return None

    @staticmethod
    def _extract_huruf(text: str) -> str | None:
        """
        Ekstrak huruf pertama yang disebut dalam teks.
        Cocok: 'huruf f', 'huruf (a)', 'Huruf C'
        """
        m = re.search(r"huruf\s*\(?([a-zA-Z])\)?", text, re.IGNORECASE)
        if m:
            return m.group(1).lower()
        return None

    @staticmethod
    def _build_search_query(text: str) -> str:
        """
        Bangun search_query yang bersih dan spesifik untuk semantic search.
        Strategi:
        1. Ambil fragment yang mengandung pasal/ayat — itu yang paling relevan untuk search.
        2. Jika ada pasal+ayat: "Pasal {N} ayat {M} [tentang ...kata sekitar...]"
        3. Jika hanya pasal: "Pasal {N} [tentang ...kata sekitar...]"
        4. Fallback: 150 karakter pertama yang bersih.
        """
        lower = text.lower()

        # Coba ekstrak kalimat/frasa yang mengandung "pasal"
        pasal_match = re.search(r"[^.]*pasal\s*\d+[^.]*\.?", text, re.IGNORECASE)
        if pasal_match:
            candidate = pasal_match.group(0).strip()
            # Bersihkan noise question words di awal
            question_words = r"^(apa|apakah|bagaimana|siapa|kapan|mengapa|kenapa|dimana|berapa|jelaskan|sebutkan|tolong|mohon|cari|temukan|bandingkan|analisis|ringkas)\s+"
            candidate = re.sub(question_words, "", candidate, flags=re.IGNORECASE).strip()
            if len(candidate) > 10:
                return candidate[:300]

        # Fallback: ambil 150 karakter pertama bersih
        cleaned = re.sub(r"\s+", " ", text).strip()
        return cleaned[:200]

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
            # PERBAIKAN: Ekstrak pasal/ayat/huruf via regex agar search_query tetap
            # relevan meski tanpa LLM repair.
            pasal_number = self._extract_pasal_number(cleaned)
            ayat_number = self._extract_ayat_number(cleaned)
            search_query = self._build_search_query(cleaned)
            print(
                f"[Info] TextRefinerService: Input terdeteksi sebagai pertanyaan/query, "
                f"di-passthrough tanpa repair. "
                f"search_query='{search_query[:80]}...' pasal={pasal_number} ayat={ayat_number}"
            )
            return {
                "repaired_text": cleaned,
                "search_query": search_query,
                "pasal_number": pasal_number,
                "ayat_number": ayat_number,
                "is_passthrough": True,
            }

        # ── Non-passthrough: jalankan LLM repair ─────────────────────────────
        # PERBAIKAN: Gunakan regex sebagai fallback untuk pasal/ayat jika LLM gagal
        pasal_fallback = self._extract_pasal_number(raw_text)
        ayat_fallback = self._extract_ayat_number(raw_text)
        search_fallback = self._build_search_query(raw_text)

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
        # PERBAIKAN: Gunakan regex fallback yang sudah diekstrak
        print(f"[Warning] TextRefinerService: Seluruh retry gagal. Fallback ke regex extraction.")
        return {
            "repaired_text": raw_text.strip(),
            "search_query": search_fallback,
            "pasal_number": pasal_fallback,
            "ayat_number": ayat_fallback,
            "is_passthrough": False,
        }


# Inisialisasi instance
text_refiner = TextRefinerService()