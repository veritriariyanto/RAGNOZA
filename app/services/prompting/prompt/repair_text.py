import re
from app.core.llm_provider import llm
import asyncio
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.output_parsers import JsonOutputParser

# Pola "kalimat ajaib" — sama seperti di streamlit_app/components/knowledgebase_tab.py,
# menandakan user sendiri ragu dengan nomor pasal yang ia sebutkan. Kalau muncul,
# pasal_number/ayat_number TIDAK dipaksakan jadi filter meski regex/LLM berhasil
# mengekstrak angkanya — supaya tidak salah menyaring hasil pencarian.
_DOUBT_PATTERN = re.compile(
    r"\b(ragu|kurang\s*yakin|tidak\s*yakin|ga\s*yakin|nggak\s*yakin|gak\s*yakin|"
    r"mungkin\s*salah|entah\s*pasal|lupa\s*pasal|tidak\s*ingat\s*pasal)\b",
    re.IGNORECASE,
)

# PERBAIKAN: pola lama (`(?:pasal|ps\.?)\s*(\d+)`) HANYA menangkap angka yang
# didahului kata "pasal"/"ps" setiap kemunculan — jadi "Pasal 5 dan Pasal 10"
# terdeteksi 2 angka (ambigu), tapi ucapan natural "Pasal 5 dan 10" atau
# "Pasal 5, 8, dan 10" (kata "pasal" tidak diulang tiap angka) cuma menangkap
# "5" saja, dianggap tunggal, TIDAK ambigu. Solusinya: cari kemunculan pertama
# "pasal N", lalu lanjutkan konsumsi angka berikutnya yang dipisah koma/kata
# sambung (boleh gabungan keduanya, mis. ", dan ") tanpa perlu kata "pasal" lagi.
_PASAL_ANCHOR_PATTERN = re.compile(r"(?:pasal|ps\.?)\s*(\d+)", re.IGNORECASE)
_PASAL_CONNECTOR_PATTERN = re.compile(
    r"^\s*(?:,\s*(?:dan|atau|serta|&|/)?|(?:dan|atau|serta|&|/))\s*",
    re.IGNORECASE,
)
_NUMBER_PATTERN = re.compile(r"^\d+")
_AYAT_FINDALL_PATTERN = re.compile(r"ayat\s*\(?(\d+)\)?", re.IGNORECASE)

# Penanda transkrip lisan gagap/berpikir (hm, eh, anu, apa ya, ...) — sinyal
# kuat ini transkrip STT mentah yang butuh repair, BUKAN pertanyaan tertulis,
# meski teksnya pendek & tidak menyebut kata kunci hukum eksplisit apapun.
_FILLER_PATTERN = re.compile(
    r"\b(?:hm+|e+m+|eh+|anu|apa\s*ya|gimana\s*ya)\b",
    re.IGNORECASE,
)


def _all_pasal_numbers(text: str) -> list[str]:
    """Ambil SEMUA nomor pasal yang disebut di teks, termasuk daftar singkat
    tanpa mengulang kata 'pasal' tiap angka (mis. 'Pasal 5, 8, dan 10')."""
    numbers: list[str] = []
    for anchor in _PASAL_ANCHOR_PATTERN.finditer(text):
        numbers.append(anchor.group(1))
        pos = anchor.end()
        while True:
            conn = _PASAL_CONNECTOR_PATTERN.match(text[pos:])
            if not conn or conn.end() == 0:
                break
            rest = text[pos + conn.end():]
            num = _NUMBER_PATTERN.match(rest)
            if not num:
                break
            numbers.append(num.group(0))
            pos += conn.end() + num.end()
    return numbers


def _all_ayat_numbers(text: str) -> list[str]:
    """Ambil SEMUA nomor ayat yang disebut di teks (mis. 'ayat (2)', 'ayat 2')."""
    return _AYAT_FINDALL_PATTERN.findall(text)


class TextRefinerService:
    def __init__(self):
        self.engine = llm
        self.json_parser = JsonOutputParser()

    # ── Regex extraction helpers ─────────────────────────────────────────────

    @staticmethod
    def _has_doubt_phrase(text: str) -> bool:
        """Deteksi kalimat yang menandakan user ragu dengan pasal yang ia sebutkan."""
        return bool(_DOUBT_PATTERN.search(text))

    @staticmethod
    def _basic_disfluency_cleanup(text: str) -> str:
        """Bersihkan filler ('hm', 'eh', 'anu', ...) & elipsis secara
        deterministik (regex, TANPA LLM). Dipakai sebagai jaring pengaman
        terakhir kalau LLM repair gagal berulang kali — supaya user tidak
        pernah melihat '...'/'hm'/'eh' mentah, meski hasilnya tidak serapi
        restrukturisasi LLM (nomor pasal/ayat dijamin tidak hilang karena
        cuma noise yang dibuang, bukan kalimat yang ditulis ulang)."""
        cleaned = _FILLER_PATTERN.sub(" ", text)
        cleaned = re.sub(r"\.{2,}", " ", cleaned)
        cleaned = re.sub(r"\s+([,.;:!?])", r"\1", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        cleaned = re.sub(r"^[,.\s]+", "", cleaned)
        return cleaned

    @staticmethod
    def _has_filler_disfluency(text: str) -> bool:
        """Deteksi tanda gagap/berpikir ('hm', 'eh', 'anu', 'apa ya', atau
        banyak elipsis '...') — dipakai untuk mencegah transkrip lisan mentah
        salah dianggap 'pertanyaan' hanya karena pendek & tanpa kata kunci
        hukum eksplisit (lihat _is_question_input)."""
        if _FILLER_PATTERN.search(text):
            return True
        return text.count("...") >= 3

    @staticmethod
    def _is_ambiguous_pasal(text: str) -> bool:
        """True kalau teks menyebut lebih dari satu nomor pasal yang berbeda."""
        return len(set(_all_pasal_numbers(text))) > 1

    @staticmethod
    def _extract_pasal_number(text: str) -> int | None:
        """
        Ekstrak nomor pasal yang disebut dalam teks — HANYA kalau tepat 1 nomor
        pasal berbeda yang terdeteksi. Cocok: 'Pasal 15', 'pasal 15 ayat (2)',
        'ps 15', maupun daftar singkat seperti 'Pasal 5 dan 10'.
        Kalau 0 atau >1 nomor pasal berbeda terdeteksi (ambigu), kembalikan None
        supaya tidak diam-diam memaksakan filter ke salah satu yang mungkin salah.
        """
        numbers = _all_pasal_numbers(text)
        unique = set(numbers)
        if len(unique) == 1:
            return int(numbers[0])
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
    def _clean_query(text: str, max_chars: int = 300) -> str:
        """
        Bersihkan teks untuk dijadikan search_query.
        - Hapus tanda tanya di akhir kalimat
        - Hapus kata tanya di awal kalimat (apa, bagaimana, dll)
        - Normalisasi whitespace
        - Potong ke max_chars karakter
        """
        cleaned = text.strip()
        
        # Hapus tanda tanya di akhir
        cleaned = re.sub(r"\?+$", "", cleaned)
        
        # Hapus kata tanya di awal kalimat
        cleaned = re.sub(
            r"^(apa|apakah|bagaimana|siapa|kapan|mengapa|kenapa|dimana|di mana|berapa|jelaskan|sebutkan|tolong|mohon|cari|temukan|bandingkan|analisis|ringkas)\s+",
            "", cleaned, flags=re.IGNORECASE
        ).strip()
        
        # Normalisasi whitespace
        cleaned = re.sub(r"\s+", " ", cleaned)
        
        # Potong jika terlalu panjang
        if len(cleaned) > max_chars:
            cleaned = cleaned[:max_chars].rsplit(" ", 1)[0]
        
        return cleaned

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
            "temukan", "bandingkan", "analisis", "analisa", "ringkas",
            "saya ingin", "saya mau", "coba", "bisa", "boleh", "minta",
        )
        lower = cleaned.lower()
        if any(lower.startswith(starter) for starter in question_starters):
            return True
        
        # Cek apakah teks terlalu pendek untuk jadi dokumen hukum (< 20 kata)
        word_count = len(cleaned.split())
        if word_count < 20:
            # Transkrip lisan gagap/berpikir ("hm... apa ya... eh...") — meski
            # pendek & tanpa kata kunci hukum eksplisit, ini BUKAN pertanyaan
            # tertulis, jadi tetap harus lewat repair LLM, bukan di-passthrough.
            if self._has_filler_disfluency(cleaned):
                return False

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

    def _apply_doubt_bypass(self, raw_text: str, pasal_number, ayat_number):
        """
        Kalau raw_text mengandung kalimat ragu, atau menyebut >1 nomor pasal
        berbeda (ambigu), paksa pasal_number & ayat_number jadi None supaya
        tidak salah memfilter pencarian. Berlaku terlepas dari sumber
        ekstraksi (regex atau LLM) — sama seperti perilaku di similarity test
        tab (streamlit_app/components/knowledgebase_tab.py).
        """
        if self._has_doubt_phrase(raw_text):
            print("[Info] TextRefinerService: Kalimat keraguan terdeteksi — "
                  "pasal_number/ayat_number di-bypass.")
            return None, None
        if self._is_ambiguous_pasal(raw_text):
            print("[Info] TextRefinerService: >1 nomor pasal berbeda terdeteksi "
                  "(ambigu) — pasal_number/ayat_number di-bypass.")
            return None, None
        return pasal_number, ayat_number

    async def repair_legal_text(self, raw_text: str) -> dict:
        if not raw_text or not raw_text.strip():
            return {
                "repaired_text": "",
                "search_query": "",
                "pasal_number": None,
                "ayat_number": None,
                "huruf": None,
                "is_passthrough": False,
            }

        # Guard: jika input adalah pertanyaan/query, skip LLM repair
        if self._is_question_input(raw_text):
            cleaned = raw_text.strip()
            # PERBAIKAN: passthrough sebelumnya tidak membersihkan filler/elipsis
            # sama sekali (cuma .strip()) — pertanyaan lisan yang gagap ("anu...
            # eh...") jadi ikut ke-embed apa adanya sebagai search_query. Cleanup
            # ini murni regex deterministik (bukan LLM), aman diterapkan ke
            # pertanyaan tanpa risiko LLM "menjawab" alih-alih membersihkan.
            if self._has_filler_disfluency(cleaned):
                cleaned = self._basic_disfluency_cleanup(cleaned)
            # Ekstrak pasal/ayat/huruf via regex agar tetap relevan meski tanpa LLM
            pasal_number = self._extract_pasal_number(cleaned)
            ayat_number = self._extract_ayat_number(cleaned)
            huruf = self._extract_huruf(cleaned)
            pasal_number, ayat_number = self._apply_doubt_bypass(raw_text, pasal_number, ayat_number)
            # search_query = cleaned tanpa noise (tanda tanya, kata tanya, dll)
            search_query = self._clean_query(cleaned)
            print(
                f"[Info] TextRefinerService: Input terdeteksi sebagai pertanyaan/query, "
                f"di-passthrough tanpa repair. "
                f"search_query='{search_query[:80]}...' pasal={pasal_number} ayat={ayat_number} huruf={huruf}"
            )
            return {
                "repaired_text": cleaned,
                "search_query": search_query,
                "pasal_number": pasal_number,
                "ayat_number": ayat_number,
                "huruf": huruf,
                "is_passthrough": True,
            }

        # ── Non-passthrough: jalankan LLM repair ─────────────────────────────
        # Fallback regex jika LLM gagal
        pasal_fallback = self._extract_pasal_number(raw_text)
        ayat_fallback = self._extract_ayat_number(raw_text)
        pasal_fallback, ayat_fallback = self._apply_doubt_bypass(raw_text, pasal_fallback, ayat_fallback)
        huruf_fallback = self._extract_huruf(raw_text)

        system_prompt = (
            "Anda adalah editor naskah hukum dan analis teks spesialis peraturan perundang-undangan Indonesia. "
            "Tugas Utama Anda:\n"
            "1. Perbaiki teks transkripsi agar rapi sesuai PUEBI & terminologi hukum resmi.\n"
            "2. Hapus total karakter pengganggu cetak atau noise seperti 'SK No XXXXX', '--- PAGE X ---'.\n"
            "3. Pertahankan struktur kalimat asli pasal. JANGAN mengubah esensi, makna, nomor pasal, atau nomor ayat.\n"
            "4. Ekstrak 'search_query': 1 kalimat singkat, padat, & spesifik yang MENCANTUMKAN NOMOR PASAL, AYAT, dan HURUF jika disebutkan dalam teks. "
            "Contoh: jika teks menyebut 'Pasal 15 ayat (2) huruf f', search_query harus mengandung 'Pasal 15 ayat (2) huruf f'.\n"
            "5. Ekstrak 'pasal_number': nomor pasal yang disebut dalam teks (integer), atau null jika tidak ada.\n"
            "6. Ekstrak 'ayat_number': nomor ayat yang disebut (integer), atau null jika tidak ada.\n\n"
            "PENTING SOAL KOREKSI DIRI LISAN: pembicara sering mengoreksi diri saat "
            "menyebut nomor pasal/ayat, mis. 'pasal berapa ya... oh iya pasal 19' atau "
            "'pasal 5... eh maksud saya pasal 6'. Pola koreksi diri itu BUKAN noise "
            "yang boleh dibuang begitu saja — nomor FINAL yang disebut (yang terakhir/"
            "dikonfirmasi) WAJIB tetap muncul di 'repaired_text' sebagai bagian dari "
            "kalimat utuh, BUKAN cuma dimasukkan ke 'search_query' saja.\n"
            "   Contoh input: 'Di pasal berapa ya... oh iya pasal 15 yang mengatur "
            "soal wewenang... pejabat berwenang melakukan penyelidikan.'\n"
            "   Contoh repaired_text BENAR: 'Pasal 15 mengatur bahwa pejabat "
            "berwenang melakukan penyelidikan.' (nomor pasal tetap ada)\n"
            "   Contoh repaired_text SALAH: 'Pejabat berwenang melakukan "
            "penyelidikan.' (nomor pasal hilang meski sempat disebut di input)\n\n"
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

                # Validasi tambahan: pastikan LLM tidak menghallusinasi jawaban.
                # Jika repaired_text jauh lebih panjang dari input asli (>2x),
                # kemungkinan LLM menjawab — minta LLM coba ulang (raise → retry)
                # alih-alih diam-diam dipakai apa adanya.
                original_word_count = len(raw_text.split())
                repaired_word_count = len(response["repaired_text"].split())
                if repaired_word_count > original_word_count * 2.5:
                    raise ValueError(
                        "repaired_text terlalu panjang dari asli (kemungkinan hallusinasi)"
                    )

                # Validasi tambahan: pastikan LLM TIDAK membuang referensi pasal/
                # ayat yang eksplisit ada di teks asli. Model kecil (8B) kadang
                # "merapikan" kalimat yang strukturnya patah-patah (banyak jeda/
                # gagap) dengan cara menghapus klausa pasal/ayat supaya kalimatnya
                # terdengar mulus — melanggar instruksi #3 di system prompt. Di-raise
                # (bukan langsung fallback diam-diam) supaya dapat kesempatan retry
                # dulu — percobaan lain sering berhasil mempertahankan referensinya.
                raw_pasal_nums = set(_all_pasal_numbers(raw_text))
                raw_ayat_nums = set(_all_ayat_numbers(raw_text))
                repaired_pasal_nums = set(_all_pasal_numbers(response["repaired_text"]))
                repaired_ayat_nums = set(_all_ayat_numbers(response["repaired_text"]))
                if (raw_pasal_nums and not raw_pasal_nums.issubset(repaired_pasal_nums)) or \
                   (raw_ayat_nums and not raw_ayat_nums.issubset(repaired_ayat_nums)):
                    raise ValueError(
                        "repaired_text kehilangan referensi pasal/ayat asli "
                        f"(pasal={raw_pasal_nums - repaired_pasal_nums}, "
                        f"ayat={raw_ayat_nums - repaired_ayat_nums})"
                    )

                # Bersihkan search_query dengan langsung mengambil dari repaired_text
                # agar format tanda kurung dst tetap terjaga identik.
                response["search_query"] = self._clean_query(response["repaired_text"])

                response.setdefault("pasal_number", None)
                response.setdefault("ayat_number", None)
                # Fallback regex kalau LLM gagal/lupa mengisi pasal_number/ayat_number,
                # padahal nomornya eksplisit ada di teks (mis. "Pasal 39 tentang ...").
                if response["pasal_number"] is None:
                    response["pasal_number"] = self._extract_pasal_number(response["repaired_text"])
                if response["ayat_number"] is None:
                    response["ayat_number"] = self._extract_ayat_number(response["repaired_text"])
                # Override kalau user ragu/ambigu — berlaku juga untuk pasal_number
                # yang LLM sendiri berhasil isi (bukan cuma hasil fallback regex),
                # karena LLM tidak diinstruksikan menangani kalimat keraguan user.
                response["pasal_number"], response["ayat_number"] = self._apply_doubt_bypass(
                    raw_text, response["pasal_number"], response["ayat_number"]
                )
                # Ekstrak huruf dari repaired_text sebagai fallback
                response.setdefault("huruf", self._extract_huruf(response["repaired_text"]))
                response["is_passthrough"] = False

                return response

            except Exception as e:
                error_msg = str(e)
                if "429" in error_msg or "rate_limit_exceeded" in error_msg.lower():
                    print(f"[Warning] Terkena Rate Limit Groq (429). Mencoba kembali dalam {retry_delay} detik... (Percobaan {attempt + 1}/{max_retries})")
                    await asyncio.sleep(retry_delay)
                    continue

                # PERBAIKAN: dulu non-429 langsung `break` (menyerah di percobaan
                # pertama, max_retries jadi tidak berlaku sama sekali untuk error
                # jenis ini). Padahal output LLM tidak deterministik walau
                # temperature rendah — percobaan ulang sering berhasil. Sekarang
                # retry juga, sama seperti kasus rate limit.
                print(
                    f"[Warning] TextRefinerService: percobaan {attempt + 1}/{max_retries} "
                    f"gagal ({error_msg})."
                    + (" Mencoba ulang..." if attempt < max_retries - 1 else "")
                )
                continue

        # Fallback aman jika seluruh retry gagal atau terjadi error non-429.
        # Kalau teks asli mengandung tanda gagap/elipsis, bersihkan dulu secara
        # deterministik (regex) — supaya user TIDAK PERNAH melihat "..."/"hm"/
        # "eh" mentah walau LLM repair gagal total. Bukan serapi hasil LLM,
        # tapi nomor pasal/ayat dijamin utuh karena cuma noise yang dibuang.
        print(f"[Warning] TextRefinerService: Seluruh retry gagal. Fallback ke regex extraction.")
        fallback_text = raw_text.strip()
        if self._has_filler_disfluency(fallback_text):
            fallback_text = self._basic_disfluency_cleanup(fallback_text)
        return {
            "repaired_text": fallback_text,
            # PERBAIKAN: search_query WAJIB diturunkan dari fallback_text yang
            # sudah dibersihkan (sama seperti jalur sukses LLM di baris ~330:
            # `_clean_query(response["repaired_text"])`), BUKAN dari
            # `search_fallback` yang dihitung sebelum pembersihan disfluensi —
            # kalau tidak, query yang di-embed untuk pencarian Qdrant tetap
            # mengandung "...", "eh", dll meski repaired_text sudah bersih.
            "search_query": self._clean_query(fallback_text),
            "pasal_number": pasal_fallback,
            "ayat_number": ayat_fallback,
            "huruf": huruf_fallback,
            "is_passthrough": False,
        }


# Inisialisasi instance
text_refiner = TextRefinerService()