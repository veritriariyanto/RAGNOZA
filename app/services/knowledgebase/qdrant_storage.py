import uuid
import re
import asyncio
from typing import List, Dict, Optional
from datetime import datetime
from qdrant_client.http import models
from qdrant_client import AsyncQdrantClient

class QdrantStorage:
    def __init__(self, db: AsyncQdrantClient, embeddings, vector_size: int = 384):
        self.db = db
        self.embeddings = embeddings
        self.vector_size = vector_size

    async def init_collections(self, names: List[str]):
        response = await self.db.get_collections()
        existing = {c.name for c in response.collections}
        for name in names:
            if name not in existing:
                await self.db.create_collection(
                    collection_name=name,
                    vectors_config=models.VectorParams(size=self.vector_size, distance=models.Distance.COSINE)
                )
                print(f"✅ Koleksi '{name}' dibuat.")

    async def store_parent_section(self, parent_col: str, child_col: str, content: str, doc_id: str, metadata: Dict, section_type: str, level: str, reference_label: str, keyword_tags: List[str] = None):
        if not content.strip(): return
        parent_id = str(uuid.uuid4())
        vector = await asyncio.to_thread(self.embeddings.embed_query, content)
        
        await self.db.upsert(collection_name=parent_col, points=[
            models.PointStruct(id=parent_id, vector=vector, payload={
                "content": content, "document_id": doc_id, "section_type": section_type, "level": level,
                "reference_label": reference_label, "uu_number": metadata.get("uu_number", ""),
                "tahun": metadata.get("tahun", ""), "judul_uu": metadata.get("judul_uu", ""),
                "created_at": datetime.now().isoformat()
            })
        ])

        chunks = [p.strip() for p in content.split("\n\n") if len(p.strip()) > 30]
        if chunks:
            await self._store_child_chunks(child_col, chunks, parent_id, doc_id, metadata, section_type, reference_label, keyword_tags or [])

    async def store_batang_tubuh(self, parent_col: str, child_col: str, pasal_list: List[Dict], doc_id: str, metadata: Dict):
        from app.services.knowledgebase.keyword_extractor import KeywordExtractor
        
        for pos, pasal in enumerate(pasal_list):
            parent_id = str(uuid.uuid4())
            ref = f"Pasal {pasal['pasal_nomor']}"
            prefix = f"[UU No {metadata.get('uu_number', 'N/A')} Tahun {metadata.get('tahun', 'N/A')}]"
            
            vector = await asyncio.to_thread(self.embeddings.embed_query, f"{prefix} {pasal['full_text']}")
            await self.db.upsert(collection_name=parent_col, points=[models.PointStruct(
                id=parent_id, vector=vector, payload={
                    "content": pasal['full_text'], "document_id": doc_id, "section_type": "batang_tubuh",
                    "level": "pasal", "reference_label": ref, "uu_number": metadata.get("uu_number", ""),
                    "tahun": metadata.get("tahun", ""), "judul_uu": metadata.get("judul_uu", ""),
                    "pasal_nomor": pasal['pasal_nomor'], "bab_nomor": pasal['bab_nomor'],
                    "bab_judul": pasal['bab_judul'], "pasal_type": pasal['type'],
                    "total_ayat": len(pasal['ayat_list']), "position": pos
                })])

            chunks, meta_list = [], []
            for ayat in pasal['ayat_list']:
                c = f"{prefix} {ref} Ayat ({ayat['ayat_nomor']}): {ayat['text']}"
                tags = KeywordExtractor.extract(ayat['text'], pasal['type'])
                chunks.append(c)
                meta_list.append({"raw_text": ayat['text'], "type": "ayat", "pasal_nomor": pasal['pasal_nomor'],
                    "ayat_nomor": ayat['ayat_nomor'], "pasal_type": pasal['type'], "bab_nomor": pasal['bab_nomor'],
                    "keyword_tags": tags, "position_in_doc": pos})
                
                for poin in ayat['poin_list']:
                    c_p = f"{prefix} {ref} Ayat ({ayat['ayat_nomor']}) huruf {poin['huruf']}: {poin['text']}"
                    chunks.append(c_p)
                    meta_list.append({"raw_text": poin['text'], "type": "poin", "pasal_nomor": pasal['pasal_nomor'],
                        "ayat_nomor": ayat['ayat_nomor'], "huruf": poin['huruf'], "pasal_type": pasal['type'],
                        "bab_nomor": pasal['bab_nomor'], "keyword_tags": KeywordExtractor.extract(poin['text'], pasal['type']),
                        "position_in_doc": pos})

            if chunks:
                vectors = await asyncio.to_thread(self.embeddings.embed_documents, chunks)
                await self.db.upsert(collection_name=child_col, points=[
                    models.PointStruct(id=str(uuid.uuid4()), vector=vectors[i], payload={
                        "content": chunks[i], "parent_id": parent_id, "document_id": doc_id,
                        "section_type": "batang_tubuh", "reference_label": ref,
                        "uu_number": metadata.get("uu_number", ""), "tahun": metadata.get("tahun", ""),
                        **meta_list[i]
                    }) for i in range(len(chunks))
                ])

    async def store_penjelasan(self, parent_col: str, child_col: str, text: str, doc_id: str, metadata: Dict):
        prefix = f"[UU No {metadata.get('uu_number', 'N/A')} Tahun {metadata.get('tahun', 'N/A')}]"
        for m in re.finditer(r'Pasal\s+(\d+[A-Za-z]?)(.*?)(?=Pasal\s+\d+|$)', text, re.DOTALL):
            pn, pc = m.group(1), m.group(2).strip()
            if len(pc) < 30: continue
            
            ref = f"Penjelasan Pasal {pn}"
            vector = await asyncio.to_thread(self.embeddings.embed_query, f"{prefix} {ref}: {pc}")
            await self.db.upsert(collection_name=parent_col, points=[models.PointStruct(
                id=str(uuid.uuid4()), vector=vector, payload={
                    "content": pc, "document_id": doc_id, "section_type": "penjelasan", "level": "pasal",
                    "reference_label": ref, "uu_number": metadata.get("uu_number", ""),
                    "tahun": metadata.get("tahun", ""), "judul_uu": metadata.get("judul_uu", ""),
                    "pasal_nomor": pn
                })])

            paras = [p.strip() for p in pc.split("\n\n") if len(p.strip()) > 30]
            if paras:
                vectors = await asyncio.to_thread(self.embeddings.embed_documents, paras)
                await self.db.upsert(collection_name=child_col, points=[
                    models.PointStruct(id=str(uuid.uuid4()), vector=vectors[i], payload={
                        "content": f"{prefix} {ref} paragraf {i+1}: {paras[i]}", "raw_text": paras[i],
                        "parent_id": str(uuid.uuid4()), "document_id": doc_id, "section_type": "penjelasan",
                        "reference_label": ref, "uu_number": metadata.get("uu_number", ""),
                        "tahun": metadata.get("tahun", ""), "type": "penjelasan_detail",
                        "pasal_nomor": pn, "position": i
                    }) for i in range(len(paras))
                ])

    async def _store_child_chunks(self, child_col: str, chunks: List[str], parent_id: str, doc_id: str, metadata: Dict, section_type: str, reference_label: str, keyword_tags: List[str]):
        vectors = await asyncio.to_thread(self.embeddings.embed_documents, chunks)
        await self.db.upsert(collection_name=child_col, points=[
            models.PointStruct(id=str(uuid.uuid4()), vector=vectors[i], payload={
                "content": chunks[i], "raw_text": chunks[i], "parent_id": parent_id,
                "document_id": doc_id, "section_type": section_type, "reference_label": reference_label,
                "uu_number": metadata.get("uu_number", ""), "tahun": metadata.get("tahun", ""),
                "keyword_tags": keyword_tags, "position": i
            }) for i in range(len(chunks))
        ])

    async def list_collections(self) -> List[str]:
        res = await self.db.get_collections()
        return sorted({c.name.replace("_parent", "") for c in res.collections if "_parent" in c.name})

    async def delete_knowledgebase(self, base_name: str) -> bool:
        for s in ["_parent", "_child"]:
            try:
                await self.db.delete_collection(f"{base_name}{s}")
                print(f"✅ Koleksi '{base_name}{s}' dihapus.")
            except Exception as e:
                print(f"⚠️ Gagal hapus '{base_name}{s}': {e}")
        return True

    async def get_stats(self, base_name: str) -> Dict:
        try:
            p = await self.db.get_collection(f"{base_name}_parent")
            c = await self.db.get_collection(f"{base_name}_child")
            return {"parent_count": p.points_count, "child_count": c.points_count, "status": "active"}
        except Exception as e:
            return {"error": str(e), "status": "error"}
        

    async def get_kb_info(self, base_name: str) -> Dict:
        """Mengambil metadata UU dari collection parent"""
        formatted_name = base_name.lower().strip().replace(" ", "_")
        parent_col = f"{formatted_name}_parent"
        
        from qdrant_client.http import models
        
        # Build filter untuk mencari dokumen "pembukaan"
        scroll_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="section_type",
                    match=models.MatchValue(value="pembukaan")
                )
            ]
        )
        # ✅ AsyncQdrantClient.scroll() mengembalikan TUPLE (points, next_offset)
        points, next_offset = await self.db.scroll(
            collection_name=parent_col,
            limit=1,
            with_payload=True,
            with_vectors=False,
            scroll_filter=scroll_filter
        )
        
        if not points:
            raise ValueError(f"Knowledge base '{base_name}' tidak ditemukan.")
        
        payload = points[0].payload
        
        return {
            "name": formatted_name,
            "document_id": payload.get("document_id"),
            "uu_number": payload.get("uu_number"),
            "tahun": payload.get("tahun"),
            "judul_uu": payload.get("judul_uu"),
            "created_at": payload.get("created_at")
        }
    
    async def search_knowledgebase(
        self,
        base_name: str,
        query: str,
        section_type: Optional[str] = None,
        pasal_type: Optional[str] = None,
        limit: int = 5
    ) -> Dict:
        formatted_name = base_name.lower().strip().replace(" ", "_")
        child_col = f"{formatted_name}_child"
        parent_col = f"{formatted_name}_parent"
        
        filter_conditions = []
        if section_type:
            filter_conditions.append(models.FieldCondition(key="section_type", match=models.MatchValue(value=section_type)))
        if pasal_type:
            filter_conditions.append(models.FieldCondition(key="pasal_type", match=models.MatchValue(value=pasal_type)))
        
        query_filter = models.Filter(must=filter_conditions) if filter_conditions else None
        
        # Embedding (CPU-bound → thread)
        query_vector = await asyncio.to_thread(self.embeddings.embed_query, query)
        
        # ✅ Query pakai .query_points() (bukan .search())
        search_response = await self.db.query_points(
            collection_name=child_col,
            query=query_vector,
            limit=limit,
            query_filter=query_filter,
            with_payload=True
        )
        
        if not search_response.points:
            return {"query": query, "total_results": 0, "results": []}
            
        # Batch retrieve parent (hindari N+1 query)
        parent_ids = [hit.payload.get("parent_id") for hit in search_response.points if hit.payload.get("parent_id")]
        parents = await self.db.retrieve(
            collection_name=parent_col, 
            ids=parent_ids, 
            with_payload=True, 
            with_vectors=False
        )
        parent_map = {p.id: p.payload for p in parents}
        
        results = []
        for hit in search_response.points:
            parent_id = hit.payload.get("parent_id")
            parent_data = parent_map.get(parent_id, {})
            
            results.append({
                "score": hit.score,
                "child": {
                    "content": hit.payload.get("content"),
                    "raw_text": hit.payload.get("raw_text"),
                    "type": hit.payload.get("type"),
                    "reference_label": hit.payload.get("reference_label"),
                    "keyword_tags": hit.payload.get("keyword_tags", [])
                },
                "parent": {
                    "content": parent_data.get("content"),
                    "reference_label": parent_data.get("reference_label"),
                    "pasal_nomor": parent_data.get("pasal_nomor")
                }
            })
            
        return {"query": query, "total_results": len(results), "results": results}