#legal_parser.py

from pydoc import text
import re
from typing import List, Dict
import uuid

class LegalParser:
    @staticmethod
    def parse_uu_structure(text: str) -> Dict:
        structure = {"metadata": {}, "pembukaan": "", "pasal_list": [], "penjelasan": ""}

        # 1. Bersihkan noise halaman dan karakter escape backslash dari teks mentah
        clean_raw_text = re.sub(r'--- PAGE \d+ ---', '', text)
        clean_raw_text = re.sub(r'\\', '', clean_raw_text)

        # Hapus watermark / footer JDIH
        clean_raw_text = re.sub(r'jdih\.[^\s]+', '', clean_raw_text, flags=re.IGNORECASE)

        # Hapus marker perubahan
        clean_raw_text = re.sub(r'\*+\)\s*:\s*Perubahan\s+\w+','', clean_raw_text, flags=re.IGNORECASE)

        # Rapikan spasi berlebih
        clean_raw_text = re.sub(r'\n{2,}', '\n', clean_raw_text)

        # Hapus footer / watermark berulang
        clean_raw_text = re.sub(r'jdih\.[^\n]+', '', clean_raw_text, flags=re.IGNORECASE)

        # Hapus marker perubahan
        clean_raw_text = re.sub(r'\*+\)\s*:\s*Perubahan\s+\w+','', clean_raw_text, flags=re.IGNORECASE)

        # Hapus nomor halaman standalone
        clean_raw_text = re.sub(r'\n\s*\d+\s*\n', '\n', clean_raw_text)

        # Rapikan whitespace
        clean_raw_text = re.sub(r'[ \t]+', ' ', clean_raw_text)

        # Rapikan newline berlebih
        clean_raw_text = re.sub(r'\n{2,}', '\n', clean_raw_text)

        # 2. Deteksi Nomor dan Tahun UU Utama (Dibatasi pada 1000 karakter pertama dokumen)
        top_text = clean_raw_text[:1000]
        doc_match = re.search(r'(UNDANG[- ]UNDANG|PERATURAN BERSAMA|PERATURAN MENTERI).*?NOMOR[:\s]+(\d+)\s+TAHUN\s+(\d{4})', top_text, re.IGNORECASE)
        if doc_match:
            structure["metadata"]["jenis_dokumen"] = doc_match.group(1).strip().upper()
            structure["metadata"]["uu_number"] = doc_match.group(2)
            structure["metadata"]["tahun"] = doc_match.group(3)
            structure["metadata"]["uu_id"] = f"UU_{doc_match.group(2)}_{doc_match.group(3)}_" f"{uuid.uuid4().hex[:8]}"
        else:
            structure["metadata"]["jenis_dokumen"] = "UNDANG-UNDANG"
            structure["metadata"]["uu_number"] = "1"
            structure["metadata"]["tahun"] = "2024"
            structure["metadata"]["uu_id"] = "UU_1_2024"

        # 3. Deteksi Judul UU 
        judul_match = re.search(r'(UNDANG[- ]UNDANG DASAR NEGARA REPUBLIK INDONESIA TAHUN 1945)', clean_raw_text, re.IGNORECASE)

        tentang_match = re.search(r'TENTANG\s+(.*?)(?=\nDENGAN|\nMENIMBANG|\nMENGINGAT|\nMEMUTUSKAN)', clean_raw_text, re.IGNORECASE)

        if judul_match: 
            structure["metadata"]["judul"] = judul_match.group(1).strip()

        elif tentang_match:
            structure["metadata"]["judul"] = re.sub (r'\s+',' ',tentang_match.group(1)).strip()

        else:
            structure["metadata"]["judul"] = "DOKUMEN HUKUM"

        # 4. PERBAIKAN SEKAT: Temukan gerbang masuk Batang Tubuh utama
        # Menghindari pengambilan pasal-pasal dasar hukum UUD 1945 di dalam konsiderans 'Mengingat'
        batang_tubuh_start = 0
        start_match = re.search(r'(MEMUTUSKAN\s*:|MENETAPKAN\s*:|\bBAB\s+I\b|\bPasal\s+1\b)', clean_raw_text, re.IGNORECASE)
        
        if start_match:
            batang_tubuh_start = start_match.start()
            structure["pembukaan"] = clean_raw_text[:batang_tubuh_start].strip()
        else:
            structure["pembukaan"] = ""

        # Isolasi teks: Hanya menyisir teks dari gerbang MEMUTUSKAN/BAB I ke bawah
        batang_tubuh_text = clean_raw_text[batang_tubuh_start:]

        # 5. Ekstraksi Pasal Menggunakan Pola Word Boundary (\b) pada teks Batang Tubuh saja
        pasal_pattern = r'(?im)^\s*Pasal\s+(\d+[A-Za-z]*)'
        pasal_matches = list(re.finditer(pasal_pattern, batang_tubuh_text, re.IGNORECASE))
        bab_matches = list(re.finditer(r'\bBAB\s+([IVXLCDM]+)', batang_tubuh_text, re.IGNORECASE))
        
        current_bab = {"nomor": "N/A", "judul": "N/A"}

        for i, p_match in enumerate(pasal_matches):
            p_start = p_match.start()
            p_end = pasal_matches[i+1].start() if i + 1 < len(pasal_matches) else len(batang_tubuh_text)
            
            # Tentukan BAB yang menaungi pasal ini berdasarkan koordinat posisi indeks
            for b_match in bab_matches:
                if b_match.start() < p_start:
                    bab_segment = batang_tubuh_text[b_match.start():p_start]
                    lines = [l.strip() for l in bab_segment.split('\n') if l.strip()]
                    judul_bab = "N/A"
                    for line in lines[1:4]:
                        if(
                            "pasal" not in line.lower()
                            and len(line.strip()) > 3
                        ):
                            judul_bab = line.strip()
                            break

                    # Cegah judul bab mengambil potongan teks pasal jika jaraknya terlalu dekat
                    if "pasal" in judul_bab.lower():
                        judul_bab = lines[0]
                    current_bab = {"nomor": b_match.group(1), "judul": judul_bab.upper()}
            
            pasal_nomor = p_match.group(1).strip()
            pasal_text = batang_tubuh_text[p_start:p_end].strip()
            
            # Potong teks jika mendeteksi teks 'PENJELASAN' bocor di akhir pasal batang tubuh
            if "PENJELASAN" in pasal_text:
                pasal_text = pasal_text.split("PENJELASAN")[0].strip()

            # Stop jika masuk bagian penjelasan
            if re.search(r'\bPENJELASAN\b', pasal_text, re.IGNORECASE):
                pasal_text = re.split(r'\bPENJELASAN\b', pasal_text, flags=re.IGNORECASE)[0]
            parsed_pasal = LegalParser._parse_pasal(
                pasal_text,
                pasal_nomor,
                current_bab
            )

            if parsed_pasal["full_text"].strip():
                structure["pasal_list"].append(parsed_pasal)

        # 6. Ambil Bagian Penjelasan dari teks penuh secara utuh
        penjelasan_match = re.search(r'(PENJELASAN\s+ATAS.*?)(?=$)', clean_raw_text, re.IGNORECASE | re.DOTALL)
        if penjelasan_match:
            structure["penjelasan"] = penjelasan_match.group(1).strip()

        return structure

    @staticmethod
    def _parse_pasal(text: str, pasal_nomor: str, bab_info: Dict) -> Dict:
        # PERBAIKAN: Bersihkan penyebutan redundan "Pasal X" di awal content utama teks RAG
        clean_content = re.sub(rf'^\s*Pasal\s+{pasal_nomor}[A-Za-z]*', '', text, flags=re.IGNORECASE).strip()

        # Hapus footer sisa
        clean_content = re.sub(r'jdih\.[^\n]+', '', clean_content, flags=re.IGNORECASE)

        # =========================
        # NORMALISASI PDF / OCR
        # =========================

        # kurung unicode/fullwidth → normal
        clean_content = clean_content.replace('（', '(')
        clean_content = clean_content.replace('）', ')')

        # normalisasi unicode dash
        clean_content = clean_content.replace('–', '-')
        clean_content = clean_content.replace('—', '-')

        # normalisasi bullet aneh
        clean_content = clean_content.replace('•', '-')

        # normalize multiple spaces
        clean_content = re.sub(r'[ \t]+', ' ', clean_content)

        # hapus zero width char
        clean_content = re.sub(r'[\u200b\u200c\u200d]', '', clean_content)

        # normalisasi newline
        clean_content = clean_content.replace('\r', '\n')

        # rapikan spasi/tab TANPA menghapus newline
        clean_content = re.sub(r'[ \t]+', ' ', clean_content)

        # rapikan newline berlebih
        clean_content = re.sub(r'\n{2,}', '\n', clean_content)

        clean_content = re.sub(
            r'\)\s+\((\d+)\)',
            r')\n(\1)',
            clean_content
        )

        clean_content = re.sub(
            r'Ayat\s+\((\d+)\)',
            r'(\1)',
            clean_content,
            flags=re.IGNORECASE
        )
        
        # FIX FORMAT AYAT:
        clean_content = re.sub(
            rf'^\s*Pasal\s+{re.escape(str(pasal_nomor))}\s*',
            '',
            clean_content,
            flags=re.IGNORECASE
        ).strip()

        # =========================
        # NORMALISASI AYAT INLINE PDF
        # =========================

        # kasus:
        # "... negara.(2) Setiap ..."
        # menjadi:
        # "... negara.\n(2) Setiap ..."

        clean_content = re.sub(
            r'([a-zA-Z0-9\.\;\:])\s*\((\d+)\)',
            r'\1\n(\2)',
            clean_content
        )

        # hapus newline berlebih lagi
        clean_content = re.sub(r'\n{2,}', '\n', clean_content)

        clean_content = clean_content.strip()

        # =========================
        # POTONG JIKA MASUK BAB BARU
        # =========================

        clean_content = re.split(
            r'(?=\nBAB\s+[IVXLCDM]+)',
            clean_content,
            maxsplit=1
        )[0]

        clean_content = re.split(
            r'(?=\nPENJELASAN\b)',
            clean_content,
            maxsplit=1,
            flags=re.IGNORECASE
        )[0]

        pasal_data = {
            "pasal_nomor": pasal_nomor, 
            "bab_nomor": bab_info["nomor"],
            "bab_judul": bab_info["judul"], 
            "full_text": clean_content,
            "ayat_list": [], 
            "type": LegalParser._detect_pasal_type(clean_content)
        }

        # =========================
        # SPLIT AYAT GENERIC
        # =========================

        ayat_pattern = r'(?m)(?=^\(\d+\))'

        ayat_chunks = re.split(
            ayat_pattern,
            clean_content
        )

        filtered_ayat = []

        for chunk in ayat_chunks:

            chunk = chunk.strip()

            nomor_match = re.match(
                r'^\((\d+)\)',
                chunk
            )

            if nomor_match:

                ayat_nomor = nomor_match.group(1)

                filtered_ayat.append({
                    "ayat_nomor": ayat_nomor,
                    "text": chunk,
                    "poin_list": LegalParser._parse_poin(chunk)
                })

        # jika tidak ada ayat
        if filtered_ayat:

            pasal_data["ayat_list"] = filtered_ayat

        else:

            pasal_data["ayat_list"].append({
                "ayat_nomor": "1",
                "text": clean_content,
                "poin_list": LegalParser._parse_poin(clean_content)
            })

        # Validasi minimal isi pasal
        if len(clean_content) < 15:
            return {
                "pasal_nomor": pasal_nomor,
                "bab_nomor": bab_info["nomor"],
                "bab_judul": bab_info["judul"],
                "full_text": "",
                "ayat_list": [],
                "type": "invalid"
            }

        return pasal_data

    @staticmethod
    def _parse_poin(ayat_text: str) -> List[Dict]:
        poin_list = []
        poin_pattern = r'(?m)^\s*([a-z])[\.\)]\s+(.*?)(?=^\s*[a-z][\.\)]|\Z)'
        for match in re.finditer(poin_pattern, ayat_text, re.DOTALL):
            poin_list.append({
                "huruf": match.group(1), 
                "text": re.sub(r'\s+', ' ', match.group(2)).strip()
            })
        return poin_list

    @staticmethod
    def _detect_pasal_type(text: str) -> str:
        t = text.lower()
        if any(k in t for k in ["adalah", "dimaksud dengan", "yang dimaksud"]): return "definisi"
        if any(k in t for k in ["pidana", "denda", "penjara", "kurungan"]): return "sanksi"
        if any(k in t for k in ["dilarang", "tidak boleh", "wajib"]): return "kewajiban_larangan"
        if any(k in t for k in ["ketentuan peralihan", "mulai berlaku"]): return "peralihan"
        return "umum"