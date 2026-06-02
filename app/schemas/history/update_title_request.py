# app/schemas/history/update_title_request.py

from pydantic import BaseModel, Field


class UpdateHistoryTitleRequest(BaseModel):
    session_title: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Judul session baru"
    )