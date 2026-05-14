from pydantic import BaseModel, Field
from typing import List

class MaterialRequest(BaseModel):
    context_text: str = Field(..., description="Teks sumber atau transkripsi yang akan diolah")
    style: str = Field("formal", description="Gaya bahasa: formal, edukatif, atau ringkasan")

class MaterialResponse(BaseModel):
    title: str = Field(..., description="Judul materi hukum yang menarik dan relevan")
    content: str = Field(..., description="Isi materi lengkap dalam format Markdown (gunakan heading, bold, dan list)")
    key_points: List[str] = Field(..., description="Daftar poin-poin penting yang harus diingat")
    legal_basis: List[str] = Field(..., description="Daftar pasal atau peraturan perundang-undangan yang dirujuk")