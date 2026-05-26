#pdf_extractor.py

import fitz # PyMuPDF
from io import BytesIO
import re

class PDFExtractor:

    @staticmethod
    def extract_text(content: bytes) -> str:
        pdf = fitz.open(stream=content, filetype="pdf")

        pages = []

        for page in pdf:
            #ekstrak teks
            text = page.get_text("text")

            # =========================
            # CLEANING DASAR
            # =========================

            #normalize windows newlines (\r\n) ke \n
            text = text.replace('\r\n', '\n')
            
            #remove null byte
            text = text.replace('\x00', '')

            #normalize whitespace
            text = re.sub(r'[ \t]+', ' ', text)

            #remove excessive newlines
            text = re.sub(r'\n{3,}', '\n\n', text)

            #remove page number patterns
            text = re.sub(r'^\s*-\s*\d+\s*-\s*$', '', text, flags=re.MULTILINE)

            #remove "halaman x"
            text = re.sub(r'Halaman\s+\d+', '', text, flags=re.IGNORECASE)
           
           #remove repeated footer/header sederhana
            text = re.sub(r'www\..*?\.go\.id', '', text, flags=re.IGNORECASE)

            #normalize pasal spacing
            text = re.sub(r'Pasal\s+\n\s*(\d+)', r'Pasal \1', text)

            #normalize bab spacing
            text = re.sub(r'BAB\s+\n\s*([IVXLCDM]+)', r'BAB \1', text)

            #trim
            text = text.strip()

            pages.append(text.strip())

        # =========================
        # GABUNG SELURUH HALAMAN
        # =========================

        final_text = "\n\n".join(pages)

        #final normalize
        final_text = re.sub(r'\n{3,}', '\n\n', final_text)

        return final_text.strip()
