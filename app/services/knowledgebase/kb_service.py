import uuid
import re
import asyncio
from typing import List, Dict, Optional
from PyPDF2 import PdfReader
from io import BytesIO
from datetime import datetime

from app.core.qdrant import qdrant_db
from app.core.embeddings import embeddings
from app.services.prompting.prompt.repair_text import text_refiner
from qdrant_client.http import models


class KnowledgeBaseService:
    def __init__(self):
        self.db = qdrant_db.client  # AsyncQdrantClient
        self.embeddings = embeddings
        self.vector_size = 384

    async def create_knowledgebase(self, base_name: str, file_content: bytes) -> Dict:
        """Membuat knowledge base dengan 2 collection: parent & child"""
        parent_col = f"{base_name}_parent"
        child_col = f"{base_name}_child"

        # 1. Inisialisasi Koleksi
        await self._init_kb_collections([parent_col, child_col])

        # 2. Extract & Repair Text
        raw_text = self._extract_pdf_text(file_content)
        clean_text = await text_refiner.repair_legal_text(raw_text)

        # 3. Parse struktur dokumen hukum
        doc_structure = self._parse_uu_structure(clean_text)

        # 4. Generate document_id untuk tracking
        doc_id = doc_structure["metadata"].get("uu_id", f"UU_{base_name}")

        # 5. Store Parent: Identitas UU (Pembukaan)
        await self._store_parent_section(
            parent_col, child_col,
            content=doc_structure["pembukaan"],
            doc_id=doc_id,
            metadata=doc_structure["metadata"],
            section_type="pembukaan",
            level="identitas",
            reference_label=f"UU {doc_structure['metadata'].get('uu_number', 'N/A')}/{doc_structure['metadata'].get('tahun', 'N/A')}"
        )

        # 6. Store Parent & Child: Batang Tubuh
        await self._store_batang_tubuh(
            parent_col, child_col,
            pasal_list=doc_structure["pasal_list"],
            doc_id=doc_id,
            metadata=doc_structure["metadata"]
        )

        # 7. Store Parent & Child: Penjelasan
        if doc_structure.get("penjelasan"):
            await self._store_penjelasan_section(
                parent_col, child_col,
                penjelasan_text=doc_structure["penjelasan"],
                doc_id=doc_id,
                metadata=doc_structure["metadata"]
            )

        return {
            "status": "success",
            "document_id": doc_id,
            "total_pasal": len(doc_structure["pasal_list"]),
            "metadata": doc_structure["metadata"]
        }

    # ========================================================================
    # PARSING LOGIC (Sync - aman karena tidak ada I/O blocking)
    # ========================================================================
    def _parse_uu_structure(self, text: str) -> Dict:
        structure = {"metadata": {}, "pembukaan": "", "pasal_list": [], "penjelasan": ""}

        uu_pattern = r'UNDANG[- ]UNDANG.*?NOMOR\s+(\d+)\s+TAHUN\s+(\d{4})'
        uu_match = re.search(uu_pattern, text, re.IGNORECASE)
        if uu_match:
            structure["metadata"]["uu_number"] = uu_match.group(1)
            structure["metadata"]["tahun"] = uu_match.group(2)
            structure["metadata"]["uu_id"] = f"UU_{uu_match.group(1)}_{uu_match.group(2)}"
        
        tentang_pattern = r'TENTANG\s+(.*?)(?=\n\n|DENGAN|Menimbang)'
        tentang_match = re.search(tentang_pattern, text, re.IGNORECASE | re.DOTALL)
        if tentang_match:
            structure["metadata"]["judul_uu"] = tentang_match.group(1).strip()

        pembukaan_pattern = r'((?:Menimbang|Mengingat|DENGAN).*?)(?=\nBAB\s+[IVXLCDM]+|\nPasal\s+1[^\d])'
        pembukaan_match = re.search(pembukaan_pattern, text, re.IGNORECASE | re.DOTALL)
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
                pasal_data = self._parse_pasal(section, pasal_match.group(1), current_bab)
                structure["pasal_list"].append(pasal_data)

        penjelasan_pattern = r'(PENJELASAN.*?UNDANG[- ]UNDANG.*?)(?=TAMBAHAN|$)'
        penjelasan_match = re.search(penjelasan_pattern, text, re.IGNORECASE | re.DOTALL)
        if penjelasan_match:
            structure["penjelasan"] = penjelasan_match.group(1).strip()

        return structure

    def _parse_pasal(self, text: str, pasal_nomor: str, bab_info: Dict) -> Dict:
        pasal_data = {
            "pasal_nomor": pasal_nomor,
            "bab_nomor": bab_info["nomor"],
            "bab_judul": bab_info["judul"],
            "full_text": text.strip(),
            "ayat_list": [],
            "type": self._detect_pasal_type(text)
        }

        ayat_pattern = r'\((\d+)\)(.*?)(?=\n\([\d]+\)|$)'
        ayat_matches = re.finditer(ayat_pattern, text, re.DOTALL)
        ayat_found = False
        
        for match in ayat_matches:
            ayat_found = True
            ayat_nomor = match.group(1)
            ayat_text = match.group(2).strip()
            poin_list = self._parse_poin(ayat_text)
            pasal_data["ayat_list"].append({"ayat_nomor": ayat_nomor, "text": ayat_text, "poin_list": poin_list})
        
        if not ayat_found:
            pasal_data["ayat_list"].append({"ayat_nomor": "1", "text": text.strip(), "poin_list": []})

        return pasal_data

    def _parse_poin(self, ayat_text: str) -> List[Dict]:
        poin_list = []
        poin_pattern = r'\n([a-z][\.\)])(.*?)(?=\n[a-z][\.\)]|$)'
        for match in re.finditer(poin_pattern, ayat_text, re.DOTALL):
            poin_list.append({"huruf": match.group(1)[0], "text": match.group(2).strip()})
        return poin_list

    def _detect_pasal_type(self, text: str) -> str:
        text_lower = text.lower()
        if any(k in text_lower for k in ["adalah", "dimaksud dengan", "yang dimaksud"]): return "definisi"
        if any(k in text_lower for k in ["pidana", "denda", "penjara", "kurungan"]): return "sanksi"
        if any(k in text_lower for k in ["dilarang", "tidak boleh", "wajib"]): return "kewajiban_larangan"
        if any(k in text_lower for k in ["ketentuan peralihan", "mulai berlaku"]): return "peralihan"
        return "umum"

    # ========================================================================
    # STORAGE LOGIC (Async + Embedding Thread Offloading)
    # ========================================================================
    async def _store_parent_section(self, parent_col: str, child_col: str, content: str, doc_id: str, metadata: Dict, section_type: str, level: str, reference_label: str, keyword_tags: List[str] = None):
        if not content.strip(): return

        parent_id = str(uuid.uuid4())
        # ⚡ Embedding di thread terpisah agar tidak blokir event loop
        parent_vector = await asyncio.to_thread(self.embeddings.embed_query, content)
        
        await self.db.upsert(
            collection_name=parent_col,
            points=[
                models.PointStruct(
                    id=parent_id,
                    vector=parent_vector,
                    payload={
                        "content": content, "document_id": doc_id, "section_type": section_type, "level": level,
                        "reference_label": reference_label, "uu_number": metadata.get("uu_number", ""),
                        "tahun": metadata.get("tahun", ""), "judul_uu": metadata.get("judul_uu", ""),
                        "created_at": datetime.now().isoformat()
                    }
                )
            ]
        )

        chunks = [p.strip() for p in content.split("\n\n") if len(p.strip()) > 30]
        if chunks:
            await self._store_child_chunks(child_col, chunks, parent_id, doc_id, metadata, section_type, reference_label, keyword_tags or [])

    async def _store_batang_tubuh(self, parent_col: str, child_col: str, pasal_list: List[Dict], doc_id: str, metadata: Dict):
        for position, pasal in enumerate(pasal_list):
            parent_id = str(uuid.uuid4())
            reference_label = f"Pasal {pasal['pasal_nomor']}"
            uu_prefix = f"[UU No {metadata.get('uu_number', 'N/A')} Tahun {metadata.get('tahun', 'N/A')}]"
            full_content = f"{uu_prefix} {pasal['full_text']}"
            
            parent_vector = await asyncio.to_thread(self.embeddings.embed_query, full_content)
            await self.db.upsert(collection_name=parent_col, points=[
                models.PointStruct(
                    id=parent_id, vector=parent_vector,
                    payload={
                        "content": pasal['full_text'], "document_id": doc_id, "section_type": "batang_tubuh",
                        "level": "pasal", "reference_label": reference_label,
                        "uu_number": metadata.get("uu_number", ""), "tahun": metadata.get("tahun", ""),
                        "judul_uu": metadata.get("judul_uu", ""), "pasal_nomor": pasal['pasal_nomor'],
                        "bab_nomor": pasal['bab_nomor'], "bab_judul": pasal['bab_judul'],
                        "pasal_type": pasal['type'], "total_ayat": len(pasal['ayat_list']), "position": position
                    }
                )
            ])

            child_chunks, child_metadata_list = [], []
            for ayat in pasal['ayat_list']:
                ayat_content = f"{uu_prefix} {reference_label} Ayat ({ayat['ayat_nomor']}): {ayat['text']}"
                keyword_tags = self._extract_keywords(ayat['text'], pasal['type'])
                child_chunks.append(ayat_content)
                child_metadata_list.append({
                    "raw_text": ayat['text'], "type": "ayat", "pasal_nomor": pasal['pasal_nomor'],
                    "ayat_nomor": ayat['ayat_nomor'], "pasal_type": pasal['type'], "bab_nomor": pasal['bab_nomor'],
                    "keyword_tags": keyword_tags, "position_in_doc": position
                })
                
                for poin in ayat['poin_list']:
                    poin_content = f"{uu_prefix} {reference_label} Ayat ({ayat['ayat_nomor']}) huruf {poin['huruf']}: {poin['text']}"
                    poin_keywords = self._extract_keywords(poin['text'], pasal['type'])
                    child_chunks.append(poin_content)
                    child_metadata_list.append({
                        "raw_text": poin['text'], "type": "poin", "pasal_nomor": pasal['pasal_nomor'],
                        "ayat_nomor": ayat['ayat_nomor'], "huruf": poin['huruf'], "pasal_type": pasal['type'],
                        "bab_nomor": pasal['bab_nomor'], "keyword_tags": poin_keywords, "position_in_doc": position
                    })
            
            if child_chunks:
                # ⚡ Batch embedding di thread terpisah
                child_vectors = await asyncio.to_thread(self.embeddings.embed_documents, child_chunks)
                child_points = [
                    models.PointStruct(
                        id=str(uuid.uuid4()), vector=child_vectors[idx],
                        payload={"content": chunk, "parent_id": parent_id, "document_id": doc_id, "section_type": "batang_tubuh",
                                 "reference_label": reference_label, "uu_number": metadata.get("uu_number", ""),
                                 "tahun": metadata.get("tahun", ""), **child_metadata_list[idx]}
                    ) for idx, chunk in enumerate(child_chunks)
                ]
                await self.db.upsert(collection_name=child_col, points=child_points)

    async def _store_penjelasan_section(self, parent_col: str, child_col: str, penjelasan_text: str, doc_id: str, metadata: Dict):
        penjelasan_pattern = r'Pasal\s+(\d+[A-Za-z]?)(.*?)(?=Pasal\s+\d+|$)'
        for match in re.finditer(penjelasan_pattern, penjelasan_text, re.DOTALL):
            pasal_nomor, penjelasan_content = match.group(1), match.group(2).strip()
            if not penjelasan_content or len(penjelasan_content) < 30: continue
            
            parent_id = str(uuid.uuid4())
            reference_label = f"Penjelasan Pasal {pasal_nomor}"
            uu_prefix = f"[UU No {metadata.get('uu_number', 'N/A')} Tahun {metadata.get('tahun', 'N/A')}]"
            full_content = f"{uu_prefix} {reference_label}: {penjelasan_content}"
            
            parent_vector = await asyncio.to_thread(self.embeddings.embed_query, full_content)
            await self.db.upsert(collection_name=parent_col, points=[
                models.PointStruct(
                    id=parent_id, vector=parent_vector,
                    payload={
                        "content": penjelasan_content, "document_id": doc_id, "section_type": "penjelasan",
                        "level": "pasal", "reference_label": reference_label,
                        "uu_number": metadata.get("uu_number", ""), "tahun": metadata.get("tahun", ""),
                        "judul_uu": metadata.get("judul_uu", ""), "pasal_nomor": pasal_nomor
                    }
                )
            ])
            
            paragraphs = [p.strip() for p in penjelasan_content.split("\n\n") if len(p.strip()) > 30]
            if paragraphs:
                child_vectors = await asyncio.to_thread(self.embeddings.embed_documents, paragraphs)
                child_points = [
                    models.PointStruct(
                        id=str(uuid.uuid4()), vector=child_vectors[idx],
                        payload={
                            "content": f"{uu_prefix} {reference_label} paragraf {idx+1}: {para}",
                            "raw_text": para, "parent_id": parent_id, "document_id": doc_id,
                            "section_type": "penjelasan", "reference_label": reference_label,
                            "uu_number": metadata.get("uu_number", ""), "tahun": metadata.get("tahun", ""),
                            "type": "penjelasan_detail", "pasal_nomor": pasal_nomor, "position": idx
                        }
                    ) for idx, para in enumerate(paragraphs)
                ]
                await self.db.upsert(collection_name=child_col, points=child_points)

    async def _store_child_chunks(self, child_col: str, chunks: List[str], parent_id: str, doc_id: str, metadata: Dict, section_type: str, reference_label: str, keyword_tags: List[str]):
        if not chunks: return
        
        child_vectors = await asyncio.to_thread(self.embeddings.embed_documents, chunks)
        child_points = [
            models.PointStruct(
                id=str(uuid.uuid4()), vector=child_vectors[idx],
                payload={
                    "content": chunk, "raw_text": chunk, "parent_id": parent_id, "document_id": doc_id,
                    "section_type": section_type, "reference_label": reference_label,
                    "uu_number": metadata.get("uu_number", ""), "tahun": metadata.get("tahun", ""),
                    "keyword_tags": keyword_tags, "position": idx
                }
            ) for idx, chunk in enumerate(chunks)
        ]
        await self.db.upsert(collection_name=child_col, points=child_points)

    def _extract_keywords(self, text: str, pasal_type: str) -> List[str]:
        keywords, text_lower = [], text.lower()
        if pasal_type == "sanksi":
            for k in ["pidana", "denda", "penjara", "kurungan"]:
                if k in text_lower: keywords.append(k)
        elif pasal_type == "definisi":
            keywords.append("definisi")
            keywords.extend([m.strip().lower() for m in re.findall(r'([A-Z][a-zA-Z\s]+)\s+adalah', text)[:3]])
        elif pasal_type == "kewajiban_larangan":
            if "wajib" in text_lower: keywords.append("kewajiban")
            if "dilarang" in text_lower or "tidak boleh" in text_lower: keywords.append("larangan")
            if "izin" in text_lower: keywords.append("perizinan")
        
        for kw in ["prosedur", "tata cara", "persyaratan", "hak", "kewenangan"]:
            if kw in text_lower: keywords.append(kw)
        return list(set(keywords))

    # ========================================================================
    # ADMIN / UTILS (Fully Async)
    # ========================================================================
    async def _init_kb_collections(self, collection_names: List[str]):
        collections_response = await self.db.get_collections()
        existing_collections = {c.name for c in collections_response.collections}
        
        for name in collection_names:
            if name not in existing_collections:
                await self.db.create_collection(
                    collection_name=name,
                    vectors_config=models.VectorParams(size=self.vector_size, distance=models.Distance.COSINE)
                )
                print(f"✅ Koleksi '{name}' dibuat.")

    def _extract_pdf_text(self, content: bytes) -> str:
        pdf = PdfReader(BytesIO(content))
        return "".join(page.extract_text() or "" for page in pdf.pages)

    async def list_collections(self) -> List[str]:
        collections_response = await self.db.get_collections()
        kb_names = set()
        for c in collections_response.collections:
            if "_parent" in c.name:
                kb_names.add(c.name.replace("_parent", ""))
        return sorted(list(kb_names))

    async def delete_knowledgebase(self, base_name: str) -> bool:
        for suffix in ["_parent", "_child"]:
            try:
                await self.db.delete_collection(f"{base_name}{suffix}")
                print(f"✅ Koleksi '{base_name}{suffix}' dihapus.")
            except Exception as e:
                print(f"⚠️ Koleksi '{base_name}{suffix}' tidak ditemukan/error: {e}")
        return True

    async def get_collection_stats(self, base_name: str) -> Dict:
        parent_col, child_col = f"{base_name}_parent", f"{base_name}_child"
        try:
            parent_info = await self.db.get_collection(parent_col)
            child_info = await self.db.get_collection(child_col)
            return {"parent_count": parent_info.points_count, "child_count": child_info.points_count, "status": "active"}
        except Exception as e:
            return {"error": str(e), "status": "error"}


# Singleton instance
kb_service = KnowledgeBaseService()