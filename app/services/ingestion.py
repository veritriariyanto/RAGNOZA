# ingestion.py
#
# File ini bertanggung jawab untuk:
# 1. Membaca file PDF undang-undang
# 2. Mem-parsing struktur hukumnya (pembukaan, pasal, penjelasan)
# 3. Menyimpan setiap segmen ke database Qdrant sebagai vector embedding
#
# Alur kerja: PDF → ekstrak teks → parse → embed → simpan ke Qdrant + PostgreSQL

import io
import re
from datetime import datetime

from pypdf import PdfReader
from sqlalchemy.orm import Session

from app.core.qdrant import qdrant_db
from app.core.embeddings import embeddings

from app.database.migration.uud import UUDArticle

from app.services.knowledgebase.legal_parser import LegalParser


# =========================================================
# MAIN INGESTION
# =========================================================
# Fungsi utama yang dipanggil ketika user mengupload file PDF.
# Menerima bytes file, session DB, dan nama koleksi Qdrant sebagai target.

def run_ingestion_upload(
    file_contents: bytes,   # Raw bytes dari file PDF yang diupload
    db: Session,            # Session koneksi ke PostgreSQL (via SQLAlchemy)
    collection_name: str    # Nama koleksi Qdrant, misal: "uud_1945"
):

    # =====================================================
    # INIT QDRANT COLLECTION
    # =====================================================
    # Pastikan koleksi Qdrant sudah ada sebelum menyimpan data.
    # Jika belum ada, qdrant_db.init_collection() akan membuatnya.
    # vector_size=384 sesuai dengan model embedding yang digunakan
    # (misal: all-MiniLM-L6-v2 menghasilkan vector 384 dimensi).

    qdrant_db.init_collection(
        collection_name=collection_name,
        vector_size=384
    )

    # =====================================================
    # EXTRACT PDF TEXT
    # =====================================================
    # PdfReader dari pypdf digunakan untuk membaca PDF dari memory (bytes),
    # bukan dari file path. io.BytesIO mengubah bytes menjadi file-like object.
    # Setiap halaman diekstrak teksnya lalu digabung dengan newline.

    stream = io.BytesIO(file_contents)
    reader = PdfReader(stream)

    full_text = ""

    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            full_text += page_text + "\n"

    # =====================================================
    # CLEAN BASIC TEXT
    # =====================================================
    # Hilangkan baris kosong berlebih hasil ekstraksi PDF
    # agar teks lebih rapi sebelum di-parse.

    full_text = re.sub(r'\n\s*\n', '\n', full_text)

    # =====================================================
    # PARSE LEGAL STRUCTURE
    # =====================================================
    # LegalParser.parse_uu_structure() memecah teks menjadi:
    #   - metadata  : nomor UU, tahun, judul
    #   - pembukaan : konsiderans / bagian awal sebelum pasal
    #   - pasal_list: daftar pasal beserta ayat dan poin
    #   - penjelasan: bagian penjelasan resmi di akhir UU

    parsed = LegalParser.parse_uu_structure(full_text)

    # Ambil metadata hasil parsing
    metadata   = parsed.get("metadata", {})
    doc_id     = metadata.get("uu_id", "UU_UNKNOWN")   # Contoh: "UU_29_1945_abc12345"
    uu_number  = metadata.get("uu_number", "")          # Contoh: "29"
    tahun      = metadata.get("tahun", "")              # Contoh: "1945"
    judul_uu   = metadata.get("judul", "")              # Contoh: "UNDANG-UNDANG DASAR..."

    # Prefix standar untuk field "content" agar mudah dibaca saat retrieval
    # Format: "[UUD 1945]" atau "[UU No 29 Tahun 1945]"
    doc_prefix = f"[UU No {uu_number} Tahun {tahun}]"

    total_segments = 0  # Counter untuk laporan hasil ingestion

    # =====================================================
    # SIMPAN PEMBUKAAN
    # =====================================================
    # Pembukaan adalah bagian sebelum "MEMUTUSKAN:" atau "BAB I".
    # Berisi konsiderans: Menimbang, Mengingat, dst.
    # Disimpan sebagai satu segmen tunggal (tidak dipecah per ayat).

    pembukaan = parsed.get("pembukaan", "").strip()

    if pembukaan:

        pembukaan_id = f"{doc_id}_PEMBUKAAN"

        # -----------------------------------------------
        # FORMAT CONTENT PEMBUKAAN
        # -----------------------------------------------
        # Field "content" adalah teks utama yang akan di-embed dan
        # ditampilkan saat hasil retrieval. Format:
        #   [UU No X Tahun Y]
        #   Pembukaan
        #   <isi teks pembukaan>

        pembukaan_content = (
            f"{doc_prefix}\n"
            f"Pembukaan\n"
            f"{pembukaan}"
        )

        pembukaan_payload = {
            # ── CONTENT ──────────────────────────────────────────────────────
            # Teks lengkap yang akan dikonversi menjadi vector embedding.
            # Selalu sertakan konteks (prefix UU + label) agar embedding
            # mengandung informasi identitas dokumen.
            "content": pembukaan_content,

            # ── IDENTITAS DOKUMEN ─────────────────────────────────────────────
            # document_id: ID unik per file UU (satu PDF = satu document_id)
            "document_id": doc_id,

            # ── KLASIFIKASI SEGMEN ────────────────────────────────────────────
            # section_type: kategori besar segmen dalam UU
            #   "pembukaan"   → bagian awal (konsiderans)
            #   "batang_tubuh"→ pasal-pasal inti
            #   "penjelasan"  → penjelasan resmi
            "section_type": "pembukaan",

            # level: kedalaman hierarki dalam section_type
            #   pembukaan → "pembukaan" (flat, tidak ada sub-level)
            #   batang_tubuh → "pasal" | "ayat" | "poin"
            "level": "pembukaan",

            # reference_label: label human-readable untuk ditampilkan di UI
            "reference_label": "Pembukaan",

            # ── METADATA UU ───────────────────────────────────────────────────
            # Digunakan untuk filter pencarian per UU tertentu
            "uu_number": uu_number,   # Nomor UU, misal: "1"
            "tahun":     tahun,       # Tahun UU, misal: "1945"
            "judul_uu":  judul_uu,    # Judul lengkap UU

            # ── TIMESTAMP ────────────────────────────────────────────────────
            # Waktu data dimasukkan ke Qdrant (bukan tanggal UU disahkan)
            "created_at": datetime.now().isoformat()
        }

        save_chunk(
            chunk_id=pembukaan_id,
            payload=pembukaan_payload,
            db=db,
            collection_name=collection_name
        )

        total_segments += 1

    # =====================================================
    # PROSES PASAL (BATANG TUBUH)
    # =====================================================
    # Setiap pasal disimpan dalam dua level:
    #   1. PARENT (level="pasal") → teks lengkap satu pasal
    #   2. CHILD  (level="ayat") → tiap ayat dalam pasal tsb
    #
    # Struktur parent-child ini memungkinkan:
    #   - Retrieval kasar via parent (satu pasal penuh)
    #   - Retrieval presisi via child (per ayat)
    #   - Re-ranking: temukan ayat relevan → ambil konteks pasalnya

    for position, pasal in enumerate(parsed["pasal_list"]):

        # Ambil data pasal dari hasil parser
        pasal_nomor    = str(pasal.get("pasal_nomor", ""))
        bab_nomor      = pasal.get("bab_nomor", "N/A")   # Angka Romawi, misal: "XI"
        bab_judul      = pasal.get("bab_judul", "N/A")   # Misal: "AGAMA"
        pasal_type     = pasal.get("type", "umum")        # "definisi"|"sanksi"|"kewajiban_larangan"|"umum"
        full_text_pasal = pasal.get("full_text", "").strip()

        if not full_text_pasal:
            continue  # Skip pasal kosong hasil parsing gagal

        # =================================================
        # PARENT PASAL
        # =================================================
        # Satu record per pasal. Menyimpan teks pasal secara utuh.
        # Digunakan untuk:
        #   - Menampilkan konteks penuh pasal setelah retrieval
        #   - Fallback jika pencarian ayat spesifik tidak cukup

        parent_id = f"{doc_id}_PASAL_{pasal_nomor}"

        # -----------------------------------------------
        # FORMAT CONTENT PARENT PASAL
        # -----------------------------------------------
        # Format yang ditargetkan:
        #   [UU No X Tahun Y] [BAB XI AGAMA] Pasal 29
        #   (1) Negara berdasar atas Ketuhanan Yang Maha Esa.
        #   (2) Negara menjamin kemerdekaan...

        parent_content = (
            f"{doc_prefix} "                              # "[UU No 1 Tahun 1945]"
            f"[BAB {bab_nomor} {bab_judul}] "             # "[BAB XI AGAMA]"
            f"Pasal {pasal_nomor}\n"                       # "Pasal 29"
            f"{full_text_pasal}"                           # Teks lengkap pasal
        )

        parent_payload = {
            # ── CONTENT ──────────────────────────────────────────────────────
            # Teks yang akan di-embed. Menyertakan identitas BAB dan nomor
            # pasal di awal agar embedding kontekstual dan mudah di-retrieve.
            "content": parent_content,

            # ── IDENTITAS ─────────────────────────────────────────────────────
            "document_id": doc_id,

            # ── KLASIFIKASI ───────────────────────────────────────────────────
            "section_type": "batang_tubuh",  # Ini adalah bagian inti UU
            "level":        "pasal",          # Hierarki tertinggi dalam batang tubuh
            "reference_label": f"Pasal {pasal_nomor}",  # Label untuk UI/citation

            # ── METADATA UU ───────────────────────────────────────────────────
            "uu_number": uu_number,
            "tahun":     tahun,
            "judul_uu":  judul_uu,

            # ── METADATA PASAL ────────────────────────────────────────────────
            # pasal_nomor: nomor pasal (string, karena bisa "29A", "1B", dst.)
            "pasal_nomor": pasal_nomor,

            # bab_nomor: nomor BAB dalam angka Romawi, misal: "XI"
            "bab_nomor": bab_nomor,

            # bab_judul: judul BAB dalam huruf kapital, misal: "AGAMA"
            "bab_judul": bab_judul,

            # pasal_type: hasil deteksi otomatis jenis norma dalam pasal
            #   "definisi"           → pasal yang mendefinisikan istilah
            #   "sanksi"             → pasal berisi pidana/denda
            #   "kewajiban_larangan" → pasal berisi "wajib"/"dilarang"
            #   "peralihan"          → pasal ketentuan peralihan
            #   "umum"               → pasal umum lainnya
            "pasal_type": pasal_type,

            # total_ayat: jumlah ayat dalam pasal ini
            # Berguna untuk menampilkan info ringkas tanpa query ulang
            "total_ayat": len(pasal.get("ayat_list", [])),

            # position: urutan pasal dalam dokumen (0-based index)
            # Berguna untuk sorting hasil retrieval secara kronologis
            "position": position,

            # ── TIMESTAMP ────────────────────────────────────────────────────
            "created_at": datetime.now().isoformat()
        }

        save_chunk(
            chunk_id=parent_id,
            payload=parent_payload,
            db=db,
            collection_name=collection_name
        )

        total_segments += 1

        # =================================================
        # CHILD AYAT
        # =================================================
        # Setiap ayat dalam pasal disimpan sebagai record terpisah.
        # Menggunakan parent_id untuk merujuk ke pasal induknya.
        #
        # Keuntungan penyimpanan per ayat:
        #   - Pencarian lebih presisi (embedding lebih fokus)
        #   - Bisa filter by ayat_nomor
        #   - Bisa reconstruct konteks via parent_id

        for ayat in pasal.get("ayat_list", []):

            ayat_nomor  = str(ayat.get("ayat_nomor", ""))
            ayat_text   = ayat.get("text", "").strip()

            if not ayat_text:
                continue  # Skip ayat kosong

            child_id = f"{doc_id}_PASAL_{pasal_nomor}_AYAT_{ayat_nomor}"

            # -----------------------------------------------
            # FORMAT CONTENT CHILD AYAT
            # -----------------------------------------------
            # Format yang ditargetkan:
            #   [UU No X Tahun Y] [BAB XI AGAMA] Pasal 29 Ayat (1)
            #   (1) Negara berdasar atas Ketuhanan Yang Maha Esa.
            #
            # Menyertakan prefix + BAB + nomor pasal + nomor ayat
            # agar embedding ayat tetap tahu konteks lengkapnya.

            child_content = (
                f"{doc_prefix} "                          # "[UU No 1 Tahun 1945]"
                f"[BAB {bab_nomor} {bab_judul}] "         # "[BAB XI AGAMA]"
                f"Pasal {pasal_nomor} "                    # "Pasal 29"
                f"Ayat ({ayat_nomor})\n"                   # "Ayat (1)"
                f"{ayat_text}"                             # Teks ayat
            )

            child_payload = {
                # ── CONTENT ──────────────────────────────────────────────────
                # Teks yang di-embed. Lebih spesifik dari parent karena
                # hanya berisi satu ayat, tapi tetap menyertakan konteks
                # (prefix UU, BAB, nomor pasal) untuk retrieval yang akurat.
                "content": child_content,

                # ── RELASI HIERARKI ───────────────────────────────────────────
                # parent_id: ID record parent (pasal) yang menaungi ayat ini.
                # Digunakan untuk "parent lookup" setelah retrieval child:
                #   1. Cari ayat relevan (child)
                #   2. Ambil parent_id → query parent → tampilkan pasal penuh
                "parent_id": parent_id,

                # ── IDENTITAS ─────────────────────────────────────────────────
                "document_id": doc_id,

                # ── KLASIFIKASI ───────────────────────────────────────────────
                "section_type": "batang_tubuh",
                "level":        "ayat",    # Lebih dalam dari "pasal"
                "type":         "ayat",    # Tipe spesifik node ini

                # reference_label: label pasal induk (bukan ayat) agar
                # citation di UI menampilkan "Pasal 29" bukan "Ayat 1"
                "reference_label": f"Pasal {pasal_nomor}",

                # ── METADATA UU ───────────────────────────────────────────────
                "uu_number": uu_number,
                "tahun":     tahun,
                "judul_uu":  judul_uu,

                # ── TEKS MENTAH ───────────────────────────────────────────────
                # raw_text: teks ayat tanpa prefix/konteks tambahan.
                # Digunakan untuk menampilkan teks bersih di UI,
                # terpisah dari field "content" yang sudah diperkaya konteks.
                "raw_text": ayat_text,

                # ── METADATA PASAL & AYAT ────────────────────────────────────
                "pasal_nomor": pasal_nomor,  # Nomor pasal induk
                "ayat_nomor":  ayat_nomor,   # Nomor ayat ini (string: "1", "2", dst.)
                "pasal_type":  pasal_type,   # Jenis norma pasal induk

                # ── METADATA BAB ──────────────────────────────────────────────
                "bab_nomor": bab_nomor,
                "bab_judul": bab_judul,

                # ── FILTER TAGS ───────────────────────────────────────────────
                # keyword_tags: list kata kunci untuk filter pencarian
                # (akan diisi oleh KeywordExtractor di pipeline lanjutan)
                "keyword_tags": [],

                # position_in_doc: urutan pasal induk dalam dokumen.
                # Berguna untuk sorting hasil retrieval secara kronologis.
                "position_in_doc": position,

                # ── TIMESTAMP ────────────────────────────────────────────────
                "created_at": datetime.now().isoformat()
            }

            save_chunk(
                chunk_id=child_id,
                payload=child_payload,
                db=db,
                collection_name=collection_name
            )

            total_segments += 1

    # =====================================================
    # PENJELASAN
    # =====================================================
    # Bagian penjelasan resmi UU (biasanya di akhir dokumen).
    # Berisi penjabaran maksud pembuat UU per pasal.
    # Disimpan sebagai satu segmen besar karena penjelasan
    # biasanya tidak memiliki struktur ayat yang formal.

    penjelasan = parsed.get("penjelasan", "").strip()

    if penjelasan:

        penjelasan_id = f"{doc_id}_PENJELASAN"

        # -----------------------------------------------
        # FORMAT CONTENT PENJELASAN
        # -----------------------------------------------

        penjelasan_content = (
            f"{doc_prefix}\n"
            f"Penjelasan\n"
            f"{penjelasan}"
        )

        penjelasan_payload = {
            # ── CONTENT ──────────────────────────────────────────────────────
            # Seluruh teks penjelasan UU dalam satu field.
            # Untuk UU yang panjang, bisa dipertimbangkan untuk dipecah
            # per pasal penjelasan di pipeline yang lebih advanced.
            "content": penjelasan_content,

            # ── IDENTITAS ─────────────────────────────────────────────────────
            "document_id": doc_id,

            # ── KLASIFIKASI ───────────────────────────────────────────────────
            "section_type":   "penjelasan",  # Bukan batang tubuh, ini penjelasan
            "level":          "penjelasan",  # Flat, tidak ada sub-level
            "reference_label": "Penjelasan", # Label untuk UI

            # ── METADATA UU ───────────────────────────────────────────────────
            "uu_number": uu_number,
            "tahun":     tahun,
            "judul_uu":  judul_uu,

            # ── TIMESTAMP ────────────────────────────────────────────────────
            "created_at": datetime.now().isoformat()
        }

        save_chunk(
            chunk_id=penjelasan_id,
            payload=penjelasan_payload,
            db=db,
            collection_name=collection_name
        )

        total_segments += 1

    # =====================================================
    # RETURN
    # =====================================================
    # Kembalikan ringkasan hasil ingestion untuk logging/response API.

    return {
        "status":         "success",
        "collection":     collection_name,
        "document_id":    doc_id,
        "total_segments": total_segments  # Jumlah total record yang disimpan
    }


# =========================================================
# SAVE CHUNK
# =========================================================
# Helper function untuk menyimpan satu segmen ke dua tempat:
#   1. PostgreSQL (via SQLAlchemy ORM) → untuk query relasional
#   2. Qdrant (via client langsung) → untuk pencarian vektor (semantic search)
#
# Mengapa dua database?
#   - PostgreSQL: cocok untuk filter eksak (WHERE pasal = '29')
#   - Qdrant: cocok untuk pencarian semantik ("apa hak kebebasan beragama?")

def save_chunk(
    chunk_id: str,       # ID unik segmen, misal: "UU_1_1945_PASAL_29_AYAT_1"
    payload: dict,       # Semua metadata + content segmen
    db: Session,         # Session PostgreSQL
    collection_name: str # Nama koleksi Qdrant
):

    # =====================================================
    # SAVE POSTGRES
    # =====================================================
    # Simpan ke tabel UUDArticle (PostgreSQL).
    # Berguna untuk browsing terstruktur: "tampilkan semua pasal BAB XI"

    new_entry = UUDArticle(
        bab=payload.get("bab_nomor", ""),         # Nomor BAB (Romawi)
        pasal=payload.get("reference_label", ""), # Label pasal, misal: "Pasal 29"
        isi_teks=payload.get("content", "")       # Teks lengkap (sudah diperkaya konteks)
    )

    db.add(new_entry)
    db.commit()
    db.refresh(new_entry)

    # =====================================================
    # EMBEDDING
    # =====================================================
    # Konversi teks "content" menjadi vector float 384 dimensi.
    # embed_query() digunakan untuk satu teks (vs embed_documents() untuk batch).
    # Vector ini yang akan dipakai Qdrant untuk cosine similarity search.

    vector = embeddings.embed_query(payload["content"])

    # =====================================================
    # SAVE QDRANT
    # =====================================================
    # Simpan ke Qdrant sebagai satu "point" yang terdiri dari:
    #   - id     : identifier unik (string)
    #   - vector : hasil embedding (list of float, 384 elemen)
    #   - payload: semua metadata yang bisa difilter saat search
    #
    # upsert() berarti: insert jika belum ada, update jika sudah ada.
    # Ini aman dipanggil berulang kali dengan ID yang sama.

    qdrant_db.client.upsert(
        collection_name=collection_name,
        points=[{
            "id":      chunk_id,  # Harus string atau integer (UUID juga valid)
            "vector":  vector,    # Vector embedding dari field "content"
            "payload": payload    # Semua field metadata untuk filter & display
        }]
    )