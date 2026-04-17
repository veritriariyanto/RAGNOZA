from sqlalchemy import Column, Integer, String, Text
from app.database.postgres import Base

class UUDArticle(Base):
    __tablename__ = "uud_articles"

    id = Column(Integer, primary_key=True, index=True)
    bab = Column(String(50))
    judul_bab = Column(String(255))
    pasal = Column(String(50))
    ayat = Column(String(50), nullable=True)
    isi_teks = Column(Text)