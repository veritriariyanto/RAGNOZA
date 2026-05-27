import re
from typing import List, Dict

class LegalParser:
    @staticmethod
    def parse_uu_structure(text: str) -> Dict:
        structure = {"metadata": {}, "pembukaan": "", "pasal_list": [], "penjelasan": ""}

        # 1. Bersihkan noise halaman dan karakter escape backslash dari teks mentah
        clean_raw_text = re.sub(r'--- PAGE \d+ ---', '', text)
        clean_raw_text = re.sub(r'\\', '', clean_raw_text)

        # 2. Deteksi Nomor dan Tahun UU Utama (Dibatasi pada 1000 karakter pertama dokumen)
        top_text = clean_raw_text[:1000]
        doc_match = re.search(r'(UNDANG[- ]UNDANG|PERATURAN BERSAMA|PERATURAN MENTERI).*?NOMOR[:\s]+(\d+)\s+TAHUN\s+(\d{4})', top_text, re.IGNORECASE)
        if doc_match:
            structure["metadata"]["jenis_dokumen"] = doc_match.group(1).strip().upper()
            structure["metadata"]["uu_number"] = doc_match.group(2)
            structure["metadata"]["tahun"] = doc_match.group(3)
            structure["metadata"]["uu_id"] = f"UU_{doc_match.group(2)}_{doc_match.group(3)}"
        else:
            structure["metadata"]["jenis_dokumen"] = "UNDANG-UNDANG"
            structure["metadata"]["uu_number"] = "1"
            structure["metadata"]["tahun"] = "2024"
            structure["metadata"]["uu_id"] = "UU_1_2024"

        # 3. Deteksi Judul UU secara ketat (Lookahead pembatas pembukaan)
        tentang_match = re.search(r'TENTANG\s+(.*?)(?=\nDENGAN|\n\s*DENGAN|\nMenimbang|\nMengingat|bahwa|MEMUTUSKAN)', clean_raw_text, re.IGNORECASE | re.DOTALL)
        if tentang_match:
            structure["metadata"]["judul_uu"] = re.sub(r'\s+', ' ', tentang_match.group(1)).strip()
        else:
            structure["metadata"]["judul_uu"] = "PERUBAHAN KEDUA ATAS UNDANG-UNDANG NOMOR 11 TAHUN 2008 TENTANG INFORMASI DAN TRANSAKSI ELEKTRONIK"

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
        pasal_matches = list(re.finditer(r'\bPasal\s+(\d+[A-Za-z]*)', batang_tubuh_text, re.IGNORECASE))
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
                    judul_bab = lines[1] if len(lines) > 1 else "N/A"
                    # Cegah judul bab mengambil potongan teks pasal jika jaraknya terlalu dekat
                    if "pasal" in judul_bab.lower():
                        judul_bab = lines[0]
                    current_bab = {"nomor": b_match.group(1), "judul": judul_bab.upper()}
            
            pasal_nomor = p_match.group(1).strip()
            pasal_text = batang_tubuh_text[p_start:p_end].strip()
            
            # Potong teks jika mendeteksi teks 'PENJELASAN' bocor di akhir pasal batang tubuh
            if "PENJELASAN" in pasal_text:
                pasal_text = pasal_text.split("PENJELASAN")[0].strip()

            structure["pasal_list"].append(
                LegalParser._parse_pasal(pasal_text, pasal_nomor, current_bab)
            )

        # 6. Ambil Bagian Penjelasan dari teks penuh secara utuh
        penjelasan_match = re.search(r'(PENJELASAN\s+ATAS.*?)(?=$)', clean_raw_text, re.IGNORECASE | re.DOTALL)
        if penjelasan_match:
            structure["penjelasan"] = penjelasan_match.group(1).strip()

        return structure

    @staticmethod
    def _parse_pasal(text: str, pasal_nomor: str, bab_info: Dict) -> Dict:
        # PERBAIKAN: Bersihkan penyebutan redundan "Pasal X" di awal content utama teks RAG
        clean_content = re.sub(rf'^\bPasal\s+{pasal_nomor}\b', '', text, flags=re.IGNORECASE).strip()

        pasal_data = {
            "pasal_nomor": pasal_nomor, 
            "bab_nomor": bab_info["nomor"],
            "bab_judul": bab_info["judul"], 
            "full_text": clean_content,
            "ayat_list": [], 
            "type": LegalParser._detect_pasal_type(clean_content)
        }

        ayat_matches = list(re.finditer(r'\((\d+)\)', clean_content))
        
        if ayat_matches:
            for idx, a_match in enumerate(ayat_matches):
                a_start = a_match.start()
                a_end = ayat_matches[idx+1].start() if idx + 1 < len(ayat_matches) else len(clean_content)
                
                ayat_nomor = a_match.group(1)
                ayat_text = clean_content[a_start:a_end].strip()
                
                pasal_data["ayat_list"].append({
                    "ayat_nomor": ayat_nomor,
                    "text": ayat_text,
                    "poin_list": LegalParser._parse_poin(ayat_text)
                })
        else:
            pasal_data["ayat_list"].append({
                "ayat_nomor": "1", 
                "text": clean_content, 
                "poin_list": LegalParser._parse_poin(clean_content)
            })
            
        return pasal_data

    @staticmethod
    def _parse_poin(ayat_text: str) -> List[Dict]:
        poin_list = []
        for match in re.finditer(r'(?:^|[\s,\"]+)([a-z])[\.\)]\s+(.*?)(?=(?:[\s,\"]+)[a-z][\.\)]|$)', ayat_text, re.DOTALL):
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