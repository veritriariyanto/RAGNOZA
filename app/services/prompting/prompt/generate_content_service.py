# app/services/prompting/prompt/generate_content_service.py

import logging
from app.core.llm_provider import llm
from app.schemas.prompting.generate_content import MaterialRequest, MaterialResponse
# pyrefly: ignore [missing-import]
from langchain_core.messages import SystemMessage, HumanMessage
# pyrefly: ignore [missing-import]
from langchain_core.output_parsers import JsonOutputParser

logger = logging.getLogger(__name__)

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
        "   - VALIDASI PASAL:\n"
        "     a) Jika user menyebut nomor pasal tertentu, verifikasi keberadaannya di konteks.\n"
        "     b) Jika TIDAK ADA di konteks: tetap tampilkan pasal yang PALING RELEVAN dari "
        "konteks (bukan pasal yang disebut user), dan jelaskan koreksinya secara singkat di "
        "field 'catatan_validasi' (mis. 'Pasal yang Anda sebutkan tidak ditemukan dalam "
        "konteks; pasal berikut yang relevan dengan skenario Anda').\n"
        "     c) Jika pasal ADA namun ayat/huruf yang disebut user keliru, koreksi juga di "
        "'catatan_validasi'.\n"
        "     d) Jika user TIDAK menyebut pasal sama sekali, biarkan 'catatan_validasi' = '-'.\n"
        "     e) DILARANG mengarang nama peraturan/pasal/ayat yang tidak ada di konteks.\n"
        "   - Boleh mengisi lebih dari satu entri 'dasar_hukum' jika ada beberapa pasal yang "
        "sama-sama relevan (misal pasal utama + pasal pendukung).\n\n"

        "2. INTI SARI RINGKASAN (ringkasan)\n"
        "   - Pecah isi pasal/ayat yang kaku menjadi beberapa poin (bullet points) yang mudah "
        "dipahami orang awam.\n"
        "   - WAJIB tetap mempertahankan istilah/kata kunci hukum ASLI dari teks (jangan "
        "diterjemahkan bebas sampai kehilangan makna teknis-nya).\n"
        "   - Setiap poin harus benar-benar didukung oleh konteks, bukan interpretasi bebas.\n\n"

        "3. KONTEKS TAMBAHAN (konteks_tambahan)\n"
        "   - Jika di dalam konteks ada pasal/ayat LAIN (bukan pasal utama) yang berfungsi "
        "sebagai penghubung atau memperjelas pertanyaan user, sebutkan secara singkat di sini.\n"
        "   - Jika tidak ada pasal penghubung yang relevan, isi dengan '-'.\n\n"

        "4. ANALISA RISIKO — CONTOH PELANGGARAN (analisa_risiko)\n"
        "   - Berikan beberapa contoh SKENARIO NARATIF konkret tentang bentuk pelanggaran "
        "terhadap pasal/ayat yang teridentifikasi di atas (bukan menilai tindakan spesifik "
        "user, melainkan ilustrasi edukatif umum).\n"
        "   - Untuk tiap contoh, jelaskan secara singkat MENGAPA skenario tersebut melanggar, "
        "dikaitkan langsung ke ayat/huruf spesifik.\n"
        "   - TIDAK PERLU skor risiko numerik atau status kepatuhan — cukup naratif.\n"
        "   - CLAUSE RELEVANCE GATE: sebelum membuat contoh pelanggaran, pastikan pasal yang "
        "dipakai memang secara LANGSUNG mengatur kewajiban/larangan terkait tindakan tersebut — "
        "jangan paksakan hanya karena ada kemiripan kata kunci (mis. sama-sama soal 'izin' atau "
        "'keamanan').\n"
        "   - Pasal yang HANYA mengatur tugas/wewenang internal lembaga TIDAK BOLEH dijadikan "
        "dasar contoh pelanggaran bagi warga sipil, kecuali pasal tersebut eksplisit menyebut "
        "kewajiban/larangan bagi pihak luar lembaga tersebut.\n"
        "   - Jika tidak ada dasar yang cukup relevan untuk membuat contoh yang valid, "
        "kembalikan list kosong ([]) — JANGAN memaksakan contoh yang tidak berdasar.\n\n"

        "5. Q&A (qa)\n"
        "   - Buat pasangan tanya-jawab seputar pasal/ayat yang teridentifikasi, sebanyak yang "
        "relevan berdasarkan konteks (tidak dibatasi jumlahnya, tapi jangan mengada-ada).\n"
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
            "   a) Jika user menyebut nomor pasal tertentu, verifikasi keberadaannya di konteks.\n"
            "   b) Jika tidak ditemukan, tetap tampilkan pasal PALING RELEVAN dari konteks dan "
            "jelaskan koreksinya di 'catatan_validasi'.\n"
            "   c) Jika pasal ada tapi ayat/huruf keliru, koreksi dengan penjelasan.\n"
            "   d) Jika user tidak menyebut pasal sama sekali, cukup identifikasi pasal paling "
            "relevan tanpa perlu catatan koreksi.\n\n"

            "3. CLAUSE RELEVANCE GATE\n"
            "   Sebelum mengaitkan pasal manapun dengan Analisa Risiko, pastikan pasal tersebut "
            "secara LANGSUNG mengatur kewajiban/larangan yang relevan — bukan sekadar kemiripan "
            "kata kunci. Pasal yang hanya mengatur wewenang internal lembaga tidak boleh "
            "dijadikan dasar contoh pelanggaran bagi warga sipil, kecuali disebutkan eksplisit.\n\n"

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
            ringkasan=[{"poin": f"Terjadi kegagalan sistem: {str(last_error)}"}],
            konteks_tambahan="-",
            analisa_risiko=[],
            qa=[],
        )


material_service = MaterialGeneratorService()