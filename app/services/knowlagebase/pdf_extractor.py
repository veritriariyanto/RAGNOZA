from PyPDF2 import PdfReader
from io import BytesIO

class PDFExtractor:
    @staticmethod
    def extract_text(content: bytes) -> str:
        """Membaca semua halaman PDF dan mengembalikan teks mentah"""
        pdf = PdfReader(BytesIO(content))
        return "".join(page.extract_text() or "" for page in pdf.pages)