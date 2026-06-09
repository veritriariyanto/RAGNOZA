# app/schemas/history/update_title_request.py

from pydantic import BaseModel, Field


class UpdateHistoryTitleRequest(BaseModel):
    """
    Skema data (Request Body) khusus untuk mendefinisikan aturan dan memvalidasi
    data ketika Frontend (Streamlit) ingin mengubah/memperbarui judul sesi riwayat.
    
    Skema ini memastikan data teks yang dikirim oleh user aman sebelum masuk ke database.
    """
    session_title: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Judul session baru"
    )