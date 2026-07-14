# app/services/prompting/prompt/generate_content_service.py

import logging
import groq
from app.core.llm_provider import llm
from app.schemas.prompting.generate_content import MaterialRequest, MaterialResponse
# pyrefly: ignore [missing-import]
from langchain_core.messages import SystemMessage, HumanMessage
# pyrefly: ignore [missing-import]
from langchain_core.output_parsers import JsonOutputParser

logger = logging.getLogger(__name__)

# Ditambahkan: konstanta pesan fallback, agar konsumen (mis. dataset_runner_service.py)
# bisa mendeteksi jalur "kegagalan sistem" tanpa menambah field baru ke schema.
SYSTEM_ERROR_FALLBACK_MESSAGE = "Terjadi kegagalan sistem saat memproses permintaan. Silakan coba lagi."

# ---------------------------------------------------------------------------
# Output Instructions (UNIFIED — tidak lagi bergantung pada intent)
# ---------------------------------------------------------------------------

def build_output_instructions() -> str:
    """
    Instruksi output tunggal, berlaku untuk SEMUA jenis query —
    baik user menyebut pasal yang benar, salah, atau tidak menyebut pasal sama sekali.
    """
    return (
        "Instruksi Output (ikuti urutan berikut, WAJIB lengkap untuk semua field):\n\n"

        "1. DASAR HUKUM (dasar_hukum)\n"
        "   - Identifikasi Nama Peraturan, Pasal, dan Ayat yang PALING RELEVAN dengan "
        "pertanyaan/skenario pengguna, berdasarkan konteks yang diberikan.\n"
        "   - VALIDASI PASAL (ATURAN KETAT):\n"
        "     a) Verifikasi apakah nomor pasal yang disebut user ada di dalam 'Konteks teks Dokumen Hukum'.\n"
        "     b) Jika pasal yang disebut user TIDAK ADA di dalam Konteks: DILARANG KERAS mencantumkan pasal salah tersebut di dalam list 'dasar_hukum'. Sebagai gantinya, cantumkan pasal yang PALING RELEVAN dari Konteks yang ada, dan jelaskan kesalahan sebut user pada field 'catatan_validasi' di pasal tersebut (misalnya: 'Pengguna menyebut Pasal 6, namun pasal tersebut tidak ada di dalam dokumen hukum referensi ini. Pasal 5 berikut adalah pasal yang relevan dengan topik tersebut').\n"
        "     c) Jika pasal ada di Konteks tetapi ayat/huruf yang disebut user keliru, cantumkan pasal yang benar dari Konteks, dan koreksi kesalahan ayat tersebut di 'catatan_validasi'.\n"
        "     d) Jika user tidak menyebut nomor pasal sama sekali, isi 'catatan_validasi' = '-'.\n"
        "     e) DILARANG KERAS mengarang, berhalusinasi, atau mencantumkan nomor pasal/ayat/peraturan yang tidak tertulis secara eksplisit di dalam Konteks referensi yang diberikan, meskipun pasal tersebut disebut oleh user.\n"
        "   - Boleh mengisi lebih dari satu entri 'dasar_hukum' jika ada beberapa pasal yang "
        "sama-sama relevan (misal pasal utama + pasal pendukung).\n\n"

        "2. INTI SARI RINGKASAN (ringkasan_pembuka + ringkasan)\n"
        "   - ringkasan_pembuka: WAJIB isi 1-2 kalimat pembuka yang menjelaskan secara UMUM "
        "pasal utama ini membahas/mengatur tentang apa (mis. 'Pasal 5 UU X mengatur tentang "
        "syarat dan tata cara pembentukan Y.'), SEBELUM masuk ke poin-poin detail. Ini adalah "
        "kalimat topik/pengantar, BUKAN pengulangan salah satu poin ringkasan.\n"
        "   - ringkasan: Pecah isi pasal/ayat yang kaku menjadi beberapa poin (bullet points) yang mudah "
        "dipahami orang awam.\n"
        "   - CAKUPAN WAJIB LENGKAP: buat SATU POIN untuk SETIAP ayat/huruf yang ada pada "
        "pasal utama yang teridentifikasi di 'dasar_hukum' (jika pasal itu punya 3 ayat, "
        "'ringkasan' WAJIB berisi 3 poin, satu per ayat) — DILARANG melewatkan ayat manapun "
        "hanya karena dianggap kurang relevan dengan pertanyaan user. Tugas 'ringkasan' "
        "adalah menjelaskan SELURUH ISI pasal tersebut, bukan hanya bagian yang menjawab "
        "pertanyaan.\n"
        "   - WAJIB tetap mempertahankan istilah/kata kunci hukum ASLI dari teks (jangan "
        "diterjemahkan bebas sampai kehilangan makna teknis-nya).\n"
        "   - Setiap poin harus benar-benar didukung oleh konteks, bukan interpretasi bebas.\n\n"

        "3. KONTEKS TAMBAHAN (konteks_tambahan)\n"
        "   - Jika di dalam konteks ada pasal/ayat LAIN (bukan pasal utama) yang berfungsi "
        "sebagai penghubung atau memperjelas pertanyaan user, sebutkan secara singkat di sini.\n"
        "   - Jika tidak ada pasal penghubung yang relevan, isi dengan '-'.\n\n"

        "4. ANALISA RISIKO — CONTOH PENYIMPANGAN (analisa_risiko)\n"
        "   - CAKUPAN WAJIB LENGKAP: buat MINIMAL SATU contoh SKENARIO NARATIF untuk SETIAP "
        "ayat pada pasal utama yang teridentifikasi di 'dasar_hukum' (jika pasal itu punya 3 "
        "ayat, minimal ada 3 contoh, satu per ayat) — bukan menilai tindakan spesifik user, "
        "melainkan ilustrasi edukatif umum. BOLEH lebih dari satu contoh untuk ayat yang sama "
        "jika memang ada beberapa variasi pelanggaran yang BERBEDA dan tetap berdasar pada "
        "ketentuan literal ayat tersebut (jangan menambah hanya untuk mengejar jumlah — setiap "
        "contoh tambahan tetap wajib lolos CLAUSE RELEVANCE GATE dan aturan DASAR PENYIMPANGAN "
        "di bawah). Ayat yang memang tidak punya dasar valid (lihat CLAUSE RELEVANCE GATE) "
        "boleh dilewati SATU ayat itu saja — TIDAK BERARTI seluruh 'analisa_risiko' harus "
        "dikosongkan.\n"
        "   - Untuk tiap contoh, jelaskan secara singkat MENGAPA skenario tersebut menyimpang, "
        "dikaitkan langsung ke ayat/huruf spesifik.\n"
        "   - TIDAK PERLU skor risiko numerik atau status kepatuhan — cukup naratif.\n"
        "   - WAJIB KONKRET, DILARANG VAGUE: skenario HARUS menyebutkan secara eksplisit ISI/"
        "ANGKA/UNSUR/PROSEDUR yang sebenarnya disyaratkan ayat tersebut, DI DALAM kalimat "
        "skenario itu sendiri — DILARANG hanya menulis 'tidak sesuai ayat (X)' atau "
        "'menyimpang dari ketentuan ayat (X)' tanpa menjelaskan APA isi ketentuannya. Skenario "
        "harus bisa dipahami sendiri (self-contained) TANPA perlu membuka teks pasal aslinya.\n"
        "     PERHATIAN — JANGAN DITIRU MENTAH-MENTAH: contoh di bawah ini HANYA ilustrasi "
        "FORMAT/GAYA penulisan (kebetulan tentang Pasal 39 Komisi Kepolisian Nasional). Kalau "
        "pasal yang sedang dianalisis SEKARANG berbeda, DILARANG KERAS menyalin/mengulang "
        "kalimat contoh ini — WAJIB buat skenario BARU yang isinya diambil dari ayat yang "
        "benar-benar ada di konteks saat ini.\n"
        "     Contoh BENAR (pola penulisan, bukan jawaban final): 'Komisi Kepolisian Nasional "
        "dibentuk hanya dengan 5 orang anggota tanpa Wakil Ketua, padahal ayat (1) "
        "mensyaratkan susunan lengkap: seorang Ketua, seorang Wakil Ketua, seorang "
        "Sekretaris, dan 6 anggota (total 9 orang).'\n"
        "     Contoh SALAH (terlalu vague, JANGAN ditiru): 'Komisi dibentuk dengan susunan "
        "yang tidak sesuai ayat (1).'\n"
        "   - DASAR PENYIMPANGAN: setiap contoh WAJIB berupa kondisi di mana ketentuan LITERAL "
        "ayat tersebut TIDAK terpenuhi/tidak sesuai. DILARANG mengarang kewajiban atau konsep "
        "yang sama sekali tidak disebut di teks pasal (mis. 'informasi rahasia', 'wewenang "
        "mengambil keputusan') hanya karena terdengar masuk akal.\n"
        "   - PIHAK YANG MENYIMPANG menyesuaikan dengan siapa yang sebenarnya diatur ayat "
        "tersebut: bisa lembaga/institusi itu sendiri (jika ayat mengatur susunan, komposisi, "
        "pembiayaan, atau tata kerja internal), pejabat yang disebut eksplisit, ATAU warga "
        "sipil/pihak luar (jika ayat memang mengatur kewajiban/larangan bagi mereka). JANGAN "
        "memaksa penyimpangan itu ke warga sipil kalau ayat yang sebenarnya mengatur "
        "lembaga/institusi.\n"
        "   - CLAUSE RELEVANCE GATE: pastikan pasal yang dipakai memang secara LANGSUNG "
        "mengatur ketentuan terkait skenario tersebut — jangan paksakan hanya karena ada "
        "kemiripan kata kunci (mis. sama-sama soal 'izin' atau 'keamanan').\n"
        "   - Jika TIDAK ADA SATU PUN ayat yang punya dasar cukup relevan untuk membuat "
        "contoh penyimpangan yang valid dan berdasar, baru kembalikan list kosong ([]) — "
        "JANGAN memaksakan contoh yang tidak berdasar.\n\n"

        "5. Q&A (qa)\n"
        "   - CAKUPAN WAJIB LENGKAP: buat MINIMAL satu pasang tanya-jawab untuk SETIAP ayat "
        "pada pasal utama yang teridentifikasi di 'dasar_hukum' (jika pasal itu punya 3 ayat, "
        "minimal ada 3 pasang Q&A, satu per ayat) — supaya seluruh ayat tercakup, bukan hanya "
        "bagian yang paling relevan dengan pertanyaan user. Boleh menambah pasangan lain di "
        "luar itu jika relevan berdasarkan konteks (tidak dibatasi jumlahnya, tapi jangan "
        "mengada-ada).\n"
        "   - Prioritaskan pertanyaan yang secara wajar akan muncul dari pembaca awam terkait "
        "pasal ini, dan/atau yang menjawab pertanyaan eksplisit dari user.\n"
        "   - Jawaban harus berbasis konteks, bukan asumsi di luar itu.\n\n"

        "6. KETENTUAN UMUM\n"
        "   - Untuk semua field yang tidak memiliki data cukup: gunakan [] atau '-'.\n"
        "   - DILARANG mengarang informasi di luar konteks yang diberikan.\n"
        "   - Kejujuran lebih penting daripada kelengkapan artifisial: lebih baik mengembalikan "
        "list kosong / '-' daripada memaksakan korelasi yang tidak sah secara hukum.\n"
    )


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

def _is_insufficient_context(context_text: str) -> bool:
    if not context_text or len(context_text.strip()) < 300:
        return True
    if context_text.lower().count("pasal") < 2:
        return True
    return False


class MaterialGeneratorService:
    def __init__(self):
        self.engine = llm
        self.json_parser = JsonOutputParser(pydantic_object=MaterialResponse)

    async def generate_legal_material(self, data: MaterialRequest) -> MaterialResponse:
        """
        Menghasilkan output JSON unifikasi (tanpa intent classification):
        Dasar Hukum, Ringkasan, Konteks Tambahan, Analisa Risiko (naratif), Q&A.
        """

        system_prompt = (
            "Anda adalah Legal Task Agent untuk dokumen hukum Indonesia yang bertugas "
            "menyusun materi edukatif hukum secara objektif dan berbasis fakta.\n\n"

            "CRITICAL RULES (WAJIB DIPATUHI):\n\n"

            "1. STRICTLY CONTEXT-BOUND\n"
            "   Analisis HANYA boleh bersumber dari 'Konteks teks Dokumen Hukum' yang "
            "diberikan. Jangan mengarang nama peraturan, nomor pasal, atau ayat jika tidak "
            "tertulis eksplisit di dalam konteks.\n\n"

            "2. PASAL VALIDATION\n"
            "   a) Verifikasi apakah nomor pasal yang disebut user ada di dalam konteks.\n"
            "   b) Jika pasal yang disebut user TIDAK ADA di dalam konteks: DILARANG KERAS mencantumkan pasal salah tersebut di dalam list 'dasar_hukum'. Tetap tampilkan pasal yang PALING RELEVAN dari konteks yang ada, dan tulis penjelasan koreksinya di 'catatan_validasi' (misalnya: 'User menyebut Pasal 6, tetapi pasal tersebut tidak ada di konteks. Pasal 5 berikut adalah pasal yang relevan').\n"
            "   c) Jika pasal ada tetapi ayat/huruf keliru, koreksi dengan penjelasan di 'catatan_validasi'.\n"
            "   d) Jika user tidak menyebut pasal sama sekali, cukup identifikasi pasal paling "
            "relevan tanpa perlu catatan koreksi.\n\n"

            "3. CLAUSE RELEVANCE GATE\n"
            "   Setiap contoh di Analisa Risiko WAJIB berupa penyimpangan/ketidaksesuaian "
            "terhadap ketentuan LITERAL pasal yang teridentifikasi (kondisi di mana yang "
            "disyaratkan pasal itu TIDAK terpenuhi) — bukan sekadar kemiripan kata kunci, dan "
            "DILARANG mengarang kewajiban/konsep yang tidak disebut di teks pasal. Skenario "
            "WAJIB menyebutkan secara eksplisit ISI/ANGKA/UNSUR/PROSEDUR yang disyaratkan "
            "ayat tersebut — DILARANG hanya menulis 'tidak sesuai ayat (X)' tanpa menjelaskan "
            "apa isinya. Pihak yang menyimpang menyesuaikan dengan siapa yang sebenarnya "
            "diatur pasal tersebut: bisa lembaga/institusi itu sendiri (jika pasal mengatur "
            "susunan, komposisi, pembiayaan, atau tata kerja internal), pejabat yang disebut "
            "eksplisit, atau warga sipil/pihak luar (jika pasal memang mengatur kewajiban/"
            "larangan bagi mereka).\n\n"

            "4. OUTPUT HONESTY\n"
            "   Kejujuran lebih penting daripada kelengkapan artifisial. Jika dasar hukum tidak "
            "cukup relevan untuk suatu field, kembalikan '-' atau [] — jangan memaksakan "
            "korelasi yang tidak sah secara hukum.\n\n"

            "Gunakan gaya bahasa formal, tegas, lugas, dan patuhi PUEBI. "
            "Output HARUS valid JSON tanpa markdown, tanpa penjelasan tambahan, dan wajib "
            "mengikuti schema yang diberikan."
        )

        human_prompt = (
            f"Konteks teks Dokumen Hukum (Referensi):\n{data.context_text}\n\n"
            f"Pertanyaan/Skenario Pengguna:\n{data.user_scenario}\n\n"
            + build_output_instructions()
            + f"\n{self.json_parser.get_format_instructions()}"
        )

        max_attempts = 2
        last_error = None

        for attempt in range(1, max_attempts + 1):
            try:
                chain = self.engine | self.json_parser
                response = await chain.ainvoke([
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=human_prompt),
                ])

                if response is None:
                    raise ValueError("LLM mengembalikan respons kosong/tidak valid.")

                return MaterialResponse.model_validate(response)

            except Exception as e:
                last_error = e
                logger.warning(
                    f"MaterialGeneratorService: Attempt {attempt}/{max_attempts} gagal. "
                    f"Error: {str(e)}"
                )

        logger.error(
            f"MaterialGeneratorService: Semua {max_attempts} attempt gagal. "
            f"Error terakhir: {str(last_error)}"
        )

        is_thin_context = _is_insufficient_context(data.context_text)

        if is_thin_context:
            return MaterialResponse(
                dasar_hukum=[],
                ringkasan=[{"poin": "Konteks dokumen hukum yang tersedia terlalu sedikit untuk dianalisis."}],
                konteks_tambahan="-",
                analisa_risiko=[],
                qa=[],
            )

        return MaterialResponse(
            dasar_hukum=[],
            ringkasan=[{"poin": SYSTEM_ERROR_FALLBACK_MESSAGE}],
            konteks_tambahan="-",
            analisa_risiko=[],
            qa=[],
        )


material_service = MaterialGeneratorService()