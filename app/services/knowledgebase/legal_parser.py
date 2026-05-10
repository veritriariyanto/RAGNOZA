import re
from typing import List, Dict

class LegalParser:
    @staticmethod
    def parse_uu_structure(text: str) -> Dict:
        structure = {"metadata": {}, "pembukaan": "", "pasal_list": [], "penjelasan": ""}

        uu_match = re.search(r'UNDANG[- ]UNDANG.*?NOMOR\s+(\d+)\s+TAHUN\s+(\d{4})', text, re.IGNORECASE)
        if uu_match:
            structure["metadata"]["uu_number"] = uu_match.group(1)
            structure["metadata"]["tahun"] = uu_match.group(2)
            structure["metadata"]["uu_id"] = f"UU_{uu_match.group(1)}_{uu_match.group(2)}"
        
        tentang_match = re.search(r'TENTANG\s+(.*?)(?=\n\n|DENGAN|Menimbang)', text, re.IGNORECASE | re.DOTALL)
        if tentang_match:
            structure["metadata"]["judul_uu"] = tentang_match.group(1).strip()

        pembukaan_match = re.search(r'((?:Menimbang|Mengingat|DENGAN).*?)(?=\nBAB\s+[IVXLCDM]+|\nPasal\s+1[^\d])', text, re.IGNORECASE | re.DOTALL)
        if pembukaan_match:
            structure["pembukaan"] = pembukaan_match.group(1).strip()

        pasal_splits = re.split(r'\n(?=Pasal\s+\d+)', text)
        current_bab = {"nomor": "", "judul": ""}
        
        for section in pasal_splits:
            if not section.strip(): continue
            
            bab_match = re.search(r'BAB\s+([IVXLCDM]+)\s+(.*?)(?=\nPasal|\n\n)', section, re.IGNORECASE)
            if bab_match:
                current_bab = {"nomor": bab_match.group(1), "judul": bab_match.group(2).strip()}
                continue
            
            pasal_match = re.search(r'Pasal\s+(\d+[A-Za-z]?)', section, re.IGNORECASE)
            if pasal_match:
                structure["pasal_list"].append(
                    LegalParser._parse_pasal(section, pasal_match.group(1), current_bab)
                )

        penjelasan_match = re.search(r'(PENJELASAN.*?UNDANG[- ]UNDANG.*?)(?=TAMBAHAN|$)', text, re.IGNORECASE | re.DOTALL)
        if penjelasan_match:
            structure["penjelasan"] = penjelasan_match.group(1).strip()

        return structure

    @staticmethod
    def _parse_pasal(text: str, pasal_nomor: str, bab_info: Dict) -> Dict:
        pasal_data = {
            "pasal_nomor": pasal_nomor, "bab_nomor": bab_info["nomor"],
            "bab_judul": bab_info["judul"], "full_text": text.strip(),
            "ayat_list": [], "type": LegalParser._detect_pasal_type(text)
        }

        ayat_found = False
        for match in re.finditer(r'\((\d+)\)(.*?)(?=\n\([\d]+\)|$)', text, re.DOTALL):
            ayat_found = True
            pasal_data["ayat_list"].append({
                "ayat_nomor": match.group(1),
                "text": match.group(2).strip(),
                "poin_list": LegalParser._parse_poin(match.group(2).strip())
            })
        
        if not ayat_found:
            pasal_data["ayat_list"].append({"ayat_nomor": "1", "text": text.strip(), "poin_list": []})
        return pasal_data

    @staticmethod
    def _parse_poin(ayat_text: str) -> List[Dict]:
        poin_list = []
        for match in re.finditer(r'\n([a-z][\.\)])(.*?)(?=\n[a-z][\.\)]|$)', ayat_text, re.DOTALL):
            poin_list.append({"huruf": match.group(1)[0], "text": match.group(2).strip()})
        return poin_list

    @staticmethod
    def _detect_pasal_type(text: str) -> str:
        t = text.lower()
        if any(k in t for k in ["adalah", "dimaksud dengan", "yang dimaksud"]): return "definisi"
        if any(k in t for k in ["pidana", "denda", "penjara", "kurungan"]): return "sanksi"
        if any(k in t for k in ["dilarang", "tidak boleh", "wajib"]): return "kewajiban_larangan"
        if any(k in t for k in ["ketentuan peralihan", "mulai berlaku"]): return "peralihan"
        return "umum"