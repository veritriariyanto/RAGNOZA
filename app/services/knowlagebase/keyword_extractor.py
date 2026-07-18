import re
from typing import List

class KeywordExtractor:
    @staticmethod
    def extract(text: str, pasal_type: str) -> List[str]:
        keywords, t = [], text.lower()
        
        if pasal_type == "sanksi":
            for k in ["pidana", "denda", "penjara", "kurungan"]:
                if k in t: keywords.append(k)
        elif pasal_type == "definisi":
            keywords.append("definisi")
            keywords.extend([m.strip().lower() for m in re.findall(r'([A-Z][a-zA-Z\s]+)\s+adalah', text)[:3]])
        elif pasal_type == "kewajiban_larangan":
            if "wajib" in t: keywords.append("kewajiban")
            if "dilarang" in t or "tidak boleh" in t: keywords.append("larangan")
            if "izin" in t: keywords.append("perizinan")
            
        for kw in ["prosedur", "tata cara", "persyaratan", "hak", "kewenangan"]:
            if kw in t: keywords.append(kw)
            
        return list(set(keywords))