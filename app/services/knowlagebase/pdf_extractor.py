from io import BytesIO

import fitz  # PyMuPDF – sudah ada di requirements.txt


class PDFExtractor:
    @staticmethod
    def extract_text(content: bytes) -> str:
        """Membaca semua halaman PDF dan mengembalikan teks mentah menggunakan PyMuPDF."""
        doc = fitz.open(stream=content, filetype="pdf")
        pages = [doc.load_page(i).get_text("text") for i in range(len(doc))]
        doc.close()
        return "\n".join(pages)