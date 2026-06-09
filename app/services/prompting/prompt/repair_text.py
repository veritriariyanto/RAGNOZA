import asyncio
import logging
import re
from typing import Dict, Optional

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.output_parsers import JsonOutputParser
from app.core.llm_provider import llm

logger = logging.getLogger(__name__)


class LegalTextPostProcessor:
    """Perbaikan akhir berbasis aturan regex (tanpa pustaka eksternal)."""
    
    # Pola koreksi deterministik: (pola regex, pengganti)
    RULE_BASED_CORRECTIONS = [
        (r'\budang[- ]?udang\b', 'Undang-Undang'),
        (r'\bunang2\b', 'Undang-Undang'),
        (r'\buud\s+(?:tahun\s+)?1949\b', 'UUD 1945'),
        (r'\bkemenangan\s+juara\b', 'keterangan saksi'),
        (r'\bresipu\w*\b', 'residivis'),
        (r'\bresipunya\b', 'residivisnya'),
        (r'\bpihak\s+pidana\b', 'pihak tersangka'),
        (r'\bmemaksakan\s+melaporkan\b', 'memeriksa laporan'),
        (r'\bpasal\s+(\d+)\b', r'Pasal \1'),
        (r'\bayat\s+(\d+)\b', r'Ayat \1'),
        (r'\buu\b(?!\s+[A-Z])', 'UU'),  # hindari false positive
        (r'\buud\b(?!\s+[A-Z])', 'UUD'),
    ]
    
    @classmethod
    def apply(cls, text: str) -> str:
        if not text:
            return text
        
        for pattern, repl in cls.RULE_BASED_CORRECTIONS:
            text = re.sub(pattern, repl, text, flags=re.IGNORECASE)
            
        # Kapitalisasi setiap awal kalimat (menangani multi-kalimat)
        text = '. '.join(s.strip().capitalize() for s in text.split('.'))
        
        # Hapus spasi ganda
        text = re.sub(r'\s+', ' ', text).strip()
        return text


class TextRefinerService:
    def __init__(self):
        self.engine = llm
        self.json_parser = JsonOutputParser()
        self.system_prompt = self._build_super_prompt()

    def _build_super_prompt(self) -> str:
        """Prompt super bagus dengan few-shot learning dan aturan eksplisit."""
        return """Anda adalah AI spesialis koreksi teks hasil STT (speech-to-text) untuk DOMAIN HUKUM INDONESIA. Tugas Anda: memperbaiki kesalahan transkripsi audio yang sering terjadi, terutama kesalahan FONETIK (kedengaran mirip).

========================================
ATURAN MUTLAK (WAJIB DIPATUHI)
========================================
1. JANGAN MENGARANG ISI. Jika suatu kata tidak yakin 100%, biarkan asli dan tambahkan tag [STT_UNCLEAR].
2. PERBAIKI hanya berdasarkan KEDENGARAN MIRIP + KONTEKS KALIMAT.
3. GUNAKAN TABEL PADANAN di bawah ini sebagai acuan WAJIB.
4. OUTPUT hanya JSON, tanpa teks lain, tanpa markdown format block.

========================================
TABEL PADANAN WAJIB (STT error -> Koreksi)
========================================
| STT Error (salah dengar) | Koreksi (benar) | Alasan fonetik/konteks |
|---------------------------|----------------|------------------------|
| "udang-udang", "unang2"   | "Undang-Undang" | /udang/ vs /undang/ |
| "1949" dalam konstitusi   | "1945"          | konteks UUD |
| "kemenangan juara"        | "keterangan saksi" | /kemenangan/ ~ /keterangan/, /juara/ ~ /saksi/ |
| "resipu", "resipunya"     | "residivis", "residivisnya" | fonem /pu/ vs /divis/ |
| "memaksakan melaporkan"   | "memeriksa laporan" | konteks penyidikan |
| "pihak pidana"            | "pihak tersangka" | penyebutan resmi |
| "pidana kemenangan"       | "kejaksaan" | /kemenangan/ ~ /kejaksaan/ |
| "BAP"                     | "Berita Acara Pemeriksaan" | jika dalam konteks penyidikan |
| "pasal [angka]"           | "Pasal [angka]" | kapitalisasi resmi |
| "ayat [angka]"            | "Ayat [angka]" | kapitalisasi resmi |

========================================
CONTOH FEW-SHOT (Pelajari ini)
========================================
INPUT STT: "Saya melaporkan pihak pidana kemenangan juara yang baik"
OUTPUT JSON:
{
  "repaired_text": "Saya melaporkan pihak tersangka keterangan saksi yang baik",
  "search_query": "pihak tersangka keterangan saksi",
  "confidence": 0.92
}

INPUT STT: "Mengapa resipunya juga memaksakan melaporkan?"
OUTPUT JSON:
{
  "repaired_text": "Mengapa residivisnya juga memeriksa laporan?",
  "search_query": "residivis memeriksa laporan",
  "confidence": 0.88
}

INPUT STT: "udang udang dasar 1949 mengatur tentang hak asasi"
OUTPUT JSON:
{
  "repaired_text": "Undang-Undang Dasar 1945 mengatur tentang hak asasi",
  "search_query": "UUD 1945 hak asasi",
  "confidence": 0.95
}

INPUT STT (kasus tidak yakin): "Saya melihat kejadian aneh di pasar"
OUTPUT JSON:
{
  "repaired_text": "Saya melihat kejadian aneh di pasar [STT_UNCLEAR]",
  "search_query": "kejadian aneh pasar",
  "confidence": 0.50
}

========================================
PETUNJUK TAMBAHAN
========================================
- Jika input sudah benar, output tetap sama dengan confidence 1.0.
- Jangan mengubah nomor pasal/ayat kecuali jelas salah dengar.
- Gunakan tag [STT_UNCLEAR] jika kata tidak dikenal dan tidak bisa dipetakan.
- Search query: maksimal 5 kata kunci, ambil frasa inti dari repaired_text, hindari kata sambung.

SEKARANG, proses input di bawah ini.
"""

    async def repair_legal_text(self, raw_text: str) -> Dict[str, str]:
        if not raw_text or not raw_text.strip():
            return {"repaired_text": "", "search_query": ""}

        human_prompt = f"""Teks mentah dari STT:
\"{raw_text}\"

Kembalikan JSON dengan skema:
{{
  "repaired_text": "hasil perbaikan sesuai aturan di atas",
  "search_query": "kata kunci singkat (maks 5 kata)",
  "confidence": 0.0-1.0
}}"""

        max_retries = 3
        for attempt in range(max_retries):
            try:
                chain = self.engine | self.json_parser
                response = await chain.ainvoke([
                    SystemMessage(content=self.system_prompt),
                    HumanMessage(content=human_prompt)
                ])

                if not isinstance(response, dict) or "repaired_text" not in response:
                    raise ValueError("Response format is not a valid JSON dict or missing keys")

                repaired = response.get("repaired_text", raw_text)
                # Terapkan rule-based post-processing (tanpa LLM)
                repaired = LegalTextPostProcessor.apply(repaired)
                
                search_query = response.get("search_query", repaired[:100])
                search_query = re.sub(r'\s+', ' ', search_query).strip()
                
                return {
                    "repaired_text": repaired,
                    "search_query": search_query
                }

            except Exception as e:
                logger.warning(f"Attempt {attempt+1}/{max_retries} failed for text repair: {e}")
                if attempt < max_retries - 1:
                    if "429" in str(e).lower():
                        await asyncio.sleep(3)
                    else:
                        await asyncio.sleep(1) # Backoff tipis untuk error non-429 (network glitch/parsing error)
                    continue
                break

        # Fallback aman jika semua retry gagal
        return {
            "repaired_text": LegalTextPostProcessor.apply(raw_text),
            "search_query": raw_text.strip()[:200]
        }


# Singleton
text_refiner = TextRefinerService()