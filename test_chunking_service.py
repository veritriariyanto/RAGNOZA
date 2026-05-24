"""
test_chunking_service.py
========================
Script pengujian untuk ChunkingService.
Menggunakan teks dummy UU untuk memverifikasi pembagian parent-child chunk.
"""

import sys
import io
import asyncio
import json
from pathlib import Path

# Fix encoding Windows terminal
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent))

from app.services.cleaning_service import CleaningService
from app.services.chunking_service import ChunkingService
from app.models.schemas import CleaningResult, CleaningStatus

def print_separator(title: str = "", char: str = "-", width: int = 70):
    if title:
        pad = max(0, width - len(title) - 2)
        print(f"\n{char * (pad // 2)} {title} {char * (pad - pad // 2)}")
    else:
        print(char * width)

async def main():
    sample_text = """
UNDANG-UNDANG REPUBLIK INDONESIA
NOMOR 11 TAHUN 2008
TENTANG INFORMASI DAN TRANSAKSI ELEKTRONIK

BAB I
KETENTUAN UMUM

Pasal 1

(1) Informasi Elektronik adalah satu atau sekumpulan data elektronik, termasuk tetapi tidak terbatas pada tulisan, suara, gambar, peta, rancangan, foto, electronic data interchange (EDI), surat elektronik (electronic mail), telegram, teleks, telecopy atau sejenisnya, huruf, tanda, angka, kode akses, simbol, atau perforasi yang telah diolah yang memiliki arti atau dapat dipahami oleh orang yang mampu memahaminya.
(2) Transaksi Elektronik adalah perbuatan hukum yang dilakukan dengan menggunakan Komputer, jaringan Komputer, dan/atau media elektronik lainnya.
(3) Teknologi Informasi adalah suatu teknik untuk mengumpulkan, menyiapkan, menyimpan, memproses, mengumumkan, menganalisis, dan/atau menyebarkan informasi.

Pasal 2

Undang-Undang ini berlaku untuk setiap Orang yang melakukan perbuatan hukum sebagaimana diatur dalam Undang-Undang ini, baik yang berada di wilayah hukum Indonesia maupun di luar wilayah hukum Indonesia, yang memiliki akibat hukum di wilayah hukum Indonesia dan/atau di luar wilayah hukum Indonesia dan merugikan kepentingan Indonesia.

BAB II
ASAS DAN TUJUAN

Pasal 3

Pemanfaatan Teknologi Informasi dan Transaksi Elektronik dilaksanakan berdasarkan asas kepastian hukum, manfaat, kehati-hatian, iktikad baik, dan kebebasan memilih teknologi atau netral teknologi.
"""

    print_separator("1. TAHAP CLEANING & PARSING STRUKTUR")
    cleaner = CleaningService()
    
    # Jalankan parser struktur UU
    parsed = cleaner._parse_structure(sample_text)
    print(f"Total BAB   : {parsed.total_bab}")
    print(f"Total Pasal : {parsed.total_pasal}")
    print(f"Total Ayat  : {parsed.total_ayat}")
    
    cleaning_result = CleaningResult(
        source_filename="test_uud.pdf",
        total_pages=1,
        full_cleaned_text=sample_text.strip(),
        metadata=cleaner.extract_uu_metadata(sample_text),
        parsed_structure=parsed,
        status=CleaningStatus.SUCCESS
    )

    print_separator("2. TAHAP CHUNKING")
    chunker = ChunkingService()
    chunking_result = await chunker.chunk(cleaning_result)
    
    print(f"Total Chunks Dihasilkan: {chunking_result.total_chunks}")
    
    # Tampilkan breakdown level
    print(f"  Level 0 (Document) : {len(chunking_result.level_0_chunks)} chunk")
    print(f"  Level 1 (BAB)      : {len(chunking_result.level_1_chunks)} chunk")
    print(f"  Level 2 (Pasal)    : {len(chunking_result.level_2_chunks)} chunk")
    print(f"  Level 3 (Ayat)     : {len(chunking_result.level_3_chunks)} chunk")
    
    print_separator("3. DETAIL SETIAP CHUNK (PARENT-CHILD RELATION)")
    all_chunks = chunking_result.all_chunks
    for idx, chunk in enumerate(all_chunks):
        m = chunk.metadata
        print(f"\nChunk #{idx+1} [ID: {chunk.chunk_id[:8]}...]")
        print(f"  Level     : {m.hierarchy_level.value.upper()} (L{m.level_number})")
        print(f"  Is Parent : {m.is_parent}")
        print(f"  Parent ID : {m.parent_chunk_id[:8] if m.parent_chunk_id else 'None'}")
        
        # Konteks Hierarki
        hierarchy = []
        if m.bab_title: hierarchy.append(m.bab_title)
        if m.pasal_title: hierarchy.append(m.pasal_title)
        if m.ayat_number: hierarchy.append(f"Ayat ({m.ayat_number})")
        print(f"  Hierarchy : {' > '.join(hierarchy)}")
        
        print(f"  Tokens    : {m.token_count}")
        print("  Content Preview:")
        # Tampilkan teks asli setelah prefix context
        lines = chunk.content.split("\n")
        content_lines = [l for l in lines if not l.startswith("[")]
        preview = "\n".join(content_lines).strip()
        print(f"    {preview[:180]}...")

if __name__ == "__main__":
    asyncio.run(main())
