# qdrant_storage.py

import uuid
import re
import asyncio

from typing import List, Dict, Optional
from datetime import datetime

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models

from app.services.knowledgebase.keyword_extractor import KeywordExtractor


class QdrantStorage:

    def __init__(
        self,
        db: AsyncQdrantClient,
        embeddings,
        vector_size: int = 384
    ):
        self.db = db
        self.embeddings = embeddings
        self.vector_size = vector_size

    # =========================================================
    # INIT COLLECTION
    # =========================================================

    async def init_collections(self, names: List[str]):

        response = await self.db.get_collections()

        existing = {
            c.name
            for c in response.collections
        }

        for name in names:

            if name not in existing:

                await self.db.create_collection(
                    collection_name=name,
                    vectors_config=models.VectorParams(
                        size=self.vector_size,
                        distance=models.Distance.COSINE
                    )
                )

                print(f"✅ Collection '{name}' created.")

    # =========================================================
    # STORE PEMBUKAAN / GENERAL SECTION
    # =========================================================

    async def store_parent_section(
        self,
        parent_col: str,
        child_col: str,
        content: str,
        doc_id: str,
        metadata: Dict,
        section_type: str,
        level: str,
        reference_label: str,
        keyword_tags: List[str] = None
    ):

        if not content.strip():
            return

        parent_id = str(uuid.uuid4())

        vector = await asyncio.to_thread(
            self.embeddings.embed_query,
            content
        )

        payload = {
            "content": content,
            "document_id": doc_id,
            "section_type": section_type,
            "level": level,
            "reference_label": reference_label,
            "uu_number": metadata.get("uu_number", ""),
            "tahun": metadata.get("tahun", ""),
            "judul_uu": metadata.get("judul", ""),
            "created_at": datetime.now().isoformat()
        }

        await self.db.upsert(
            collection_name=parent_col,
            points=[
                models.PointStruct(
                    id=parent_id,
                    vector=vector,
                    payload=payload
                )
            ]
        )

        # =========================================
        # CHILD CHUNKS
        # =========================================

        chunks = [
            p.strip()
            for p in content.split("\n\n")
            if len(p.strip()) > 30
        ]

        if chunks:

            await self._store_child_chunks(
                child_col=child_col,
                chunks=chunks,
                parent_id=parent_id,
                doc_id=doc_id,
                metadata=metadata,
                section_type=section_type,
                reference_label=reference_label,
                keyword_tags=keyword_tags or []
            )

    # =========================================================
    # STORE BATANG TUBUH
    # =========================================================

    async def store_batang_tubuh(
        self,
        parent_col: str,
        child_col: str,
        pasal_list: List[Dict],
        doc_id: str,
        metadata: Dict
    ):

        prefix = (
            f"[UU No {metadata.get('uu_number', 'N/A')} "
            f"Tahun {metadata.get('tahun', 'N/A')}]"
        )

        seen_pasal = set()

        for pos, pasal in enumerate(pasal_list):

            pasal_nomor = pasal["pasal_nomor"]

            # =========================================
            # DUPLICATE PREVENTION
            # =========================================

            if pasal_nomor in seen_pasal:
                continue

            seen_pasal.add(pasal_nomor)

            reference_label = f"Pasal {pasal_nomor}"

            parent_id = str(uuid.uuid4())

            parent_content = (
                f"{prefix}\n"
                f"{reference_label}\n"
                f"{pasal['full_text']}"
            )

            parent_vector = await asyncio.to_thread(
                self.embeddings.embed_query,
                parent_content
            )

            # =========================================
            # STORE PARENT PASAL
            # =========================================

            parent_payload = {
                "content": pasal["full_text"],
                "document_id": doc_id,
                "section_type": "batang_tubuh",
                "level": "pasal",
                "reference_label": reference_label,

                "uu_number": metadata.get("uu_number", ""),
                "tahun": metadata.get("tahun", ""),
                "judul_uu": metadata.get("judul", ""),

                "pasal_nomor": pasal["pasal_nomor"],
                "bab_nomor": pasal["bab_nomor"],
                "bab_judul": pasal["bab_judul"],
                "pasal_type": pasal["type"],

                "total_ayat": len(pasal["ayat_list"]),
                "position": pos,

                "created_at": datetime.now().isoformat()
            }

            await self.db.upsert(
                collection_name=parent_col,
                points=[
                    models.PointStruct(
                        id=parent_id,
                        vector=parent_vector,
                        payload=parent_payload
                    )
                ]
            )

            # =========================================
            # CHILD AYAT + POIN
            # =========================================

            child_points = []

            for ayat in pasal["ayat_list"]:

                ayat_nomor = ayat["ayat_nomor"]

                ayat_text = ayat["text"]

                keyword_tags = KeywordExtractor.extract(
                    ayat_text,
                    pasal["type"]
                )

                ayat_content = (
                    f"{prefix}\n"
                    f"{pasal['bab_judul']}\n"
                    f"{reference_label}\n"
                    f"Ayat ({ayat_nomor})\n"
                    f"{ayat_text}"
                )

                ayat_vector = await asyncio.to_thread(
                    self.embeddings.embed_query,
                    ayat_content
                )

                ayat_payload = {
                    "content": ayat_content,
                    "raw_text": ayat_text,

                    "parent_id": parent_id,
                    "document_id": doc_id,

                    "section_type": "batang_tubuh",
                    "level": "ayat",
                    "type": "ayat",

                    "reference_label": reference_label,

                    "uu_number": metadata.get("uu_number", ""),
                    "tahun": metadata.get("tahun", ""),

                    "pasal_nomor": pasal_nomor,
                    "ayat_nomor": ayat_nomor,

                    "bab_nomor": pasal["bab_nomor"],
                    "bab_judul": pasal["bab_judul"],

                    "pasal_type": pasal["type"],

                    "keyword_tags": keyword_tags,

                    "position_in_doc": pos
                }

                child_points.append(
                    models.PointStruct(
                        id=str(uuid.uuid4()),
                        vector=ayat_vector,
                        payload=ayat_payload
                    )
                )

                # =====================================
                # STORE POIN
                # =====================================

                for poin in ayat["poin_list"]:

                    poin_huruf = poin["huruf"]

                    poin_text = poin["text"]

                    poin_content = (
                        f"{prefix}\n"
                        f"{pasal['bab_judul']}\n"
                        f"{reference_label}\n"
                        f"Ayat ({ayat_nomor}) Huruf ({poin_huruf})\n"
                        f"{poin_text}"
                    )

                    poin_vector = await asyncio.to_thread(
                        self.embeddings.embed_query,
                        poin_content
                    )

                    poin_payload = {
                        "content": poin_content,
                        "raw_text": poin_text,

                        "parent_id": parent_id,
                        "document_id": doc_id,

                        "section_type": "batang_tubuh",
                        "level": "poin",
                        "type": "poin",

                        "reference_label": reference_label,

                        "uu_number": metadata.get("uu_number", ""),
                        "tahun": metadata.get("tahun", ""),

                        "pasal_nomor": pasal_nomor,
                        "ayat_nomor": ayat_nomor,
                        "huruf": poin_huruf,

                        "bab_nomor": pasal["bab_nomor"],
                        "bab_judul": pasal["bab_judul"],

                        "pasal_type": pasal["type"],

                        "keyword_tags": KeywordExtractor.extract(
                            poin_text,
                            pasal["type"]
                        ),

                        "position_in_doc": pos
                    }

                    child_points.append(
                        models.PointStruct(
                            id=str(uuid.uuid4()),
                            vector=poin_vector,
                            payload=poin_payload
                        )
                    )

            if child_points:

                await self.db.upsert(
                    collection_name=child_col,
                    points=child_points
                )

    # =========================================================
    # STORE PENJELASAN
    # =========================================================

    async def store_penjelasan(
        self,
        parent_col: str,
        child_col: str,
        text: str,
        doc_id: str,
        metadata: Dict
    ):

        prefix = (
            f"[UU No {metadata.get('uu_number', 'N/A')} "
            f"Tahun {metadata.get('tahun', 'N/A')}]"
        )

        pattern = (
            r'(?ms)^Pasal\s+(\d+[A-Za-z]?)\s*(.*?)'
            r'(?=^Pasal\s+\d+[A-Za-z]?|\Z)'
        )

        for match in re.finditer(pattern, text):

            pasal_nomor = match.group(1).strip()

            content = match.group(2).strip()

            if len(content) < 20:
                continue

            parent_id = str(uuid.uuid4())

            reference_label = f"Penjelasan Pasal {pasal_nomor}"

            parent_content = (
                f"{prefix}\n"
                f"{reference_label}\n"
                f"{content}"
            )

            parent_vector = await asyncio.to_thread(
                self.embeddings.embed_query,
                parent_content
            )

            parent_payload = {
                "content": content,

                "document_id": doc_id,

                "section_type": "penjelasan",
                "level": "pasal",

                "reference_label": reference_label,

                "uu_number": metadata.get("uu_number", ""),
                "tahun": metadata.get("tahun", ""),
                "judul_uu": metadata.get("judul", ""),

                "pasal_nomor": pasal_nomor,

                "created_at": datetime.now().isoformat()
            }

            await self.db.upsert(
                collection_name=parent_col,
                points=[
                    models.PointStruct(
                        id=parent_id,
                        vector=parent_vector,
                        payload=parent_payload
                    )
                ]
            )

            paragraphs = [
                p.strip()
                for p in content.split("\n\n")
                if len(p.strip()) > 30
            ]

            child_points = []

            for i, paragraph in enumerate(paragraphs):

                child_content = (
                    f"{prefix}\n"
                    f"{reference_label}\n"
                    f"Paragraf {i+1}\n"
                    f"{paragraph}"
                )

                child_vector = await asyncio.to_thread(
                    self.embeddings.embed_query,
                    child_content
                )

                child_payload = {
                    "content": child_content,
                    "raw_text": paragraph,

                    "parent_id": parent_id,
                    "document_id": doc_id,

                    "section_type": "penjelasan",
                    "level": "paragraph",
                    "type": "penjelasan_detail",

                    "reference_label": reference_label,

                    "uu_number": metadata.get("uu_number", ""),
                    "tahun": metadata.get("tahun", ""),

                    "pasal_nomor": pasal_nomor,

                    "position": i
                }

                child_points.append(
                    models.PointStruct(
                        id=str(uuid.uuid4()),
                        vector=child_vector,
                        payload=child_payload
                    )
                )

            if child_points:

                await self.db.upsert(
                    collection_name=child_col,
                    points=child_points
                )

    # =========================================================
    # GENERIC CHILD STORAGE
    # =========================================================

    async def _store_child_chunks(
        self,
        child_col: str,
        chunks: List[str],
        parent_id: str,
        doc_id: str,
        metadata: Dict,
        section_type: str,
        reference_label: str,
        keyword_tags: List[str]
    ):

        vectors = await asyncio.to_thread(
            self.embeddings.embed_documents,
            chunks
        )

        points = []

        for i, chunk in enumerate(chunks):

            payload = {
                "content": chunk,
                "raw_text": chunk,

                "parent_id": parent_id,
                "document_id": doc_id,

                "section_type": section_type,

                "reference_label": reference_label,

                "uu_number": metadata.get("uu_number", ""),
                "tahun": metadata.get("tahun", ""),

                "keyword_tags": keyword_tags,

                "position": i
            }

            points.append(
                models.PointStruct(
                    id=str(uuid.uuid4()),
                    vector=vectors[i],
                    payload=payload
                )
            )

        await self.db.upsert(
            collection_name=child_col,
            points=points
        )

    # =========================================================
    # LIST COLLECTION
    # =========================================================

    async def list_collections(self) -> List[str]:

        response = await self.db.get_collections()

        return sorted({
            c.name.replace("_parent", "")
            for c in response.collections
            if "_parent" in c.name
        })

    # =========================================================
    # DELETE KB
    # =========================================================

    async def delete_knowledgebase(
        self,
        base_name: str
    ) -> bool:

        for suffix in ["_parent", "_child"]:

            try:

                await self.db.delete_collection(
                    f"{base_name}{suffix}"
                )

                print(f"✅ Deleted: {base_name}{suffix}")

            except Exception as e:

                print(f"⚠️ Failed delete {base_name}{suffix}: {e}")

        return True

    # =========================================================
    # STATS
    # =========================================================

    async def get_stats(
        self,
        base_name: str
    ) -> Dict:

        try:

            parent = await self.db.get_collection(
                f"{base_name}_parent"
            )

            child = await self.db.get_collection(
                f"{base_name}_child"
            )

            return {
                "parent_count": parent.points_count,
                "child_count": child.points_count,
                "status": "active"
            }

        except Exception as e:

            return {
                "error": str(e),
                "status": "error"
            }

    # =========================================================
    # KB INFO
    # =========================================================

    async def get_kb_info(
        self,
        base_name: str
    ) -> Dict:

        formatted_name = (
            base_name.lower()
            .strip()
            .replace(" ", "_")
        )

        parent_col = f"{formatted_name}_parent"

        scroll_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="section_type",
                    match=models.MatchValue(
                        value="pembukaan"
                    )
                )
            ]
        )

        points, _ = await self.db.scroll(
            collection_name=parent_col,
            limit=1,
            with_payload=True,
            with_vectors=False,
            scroll_filter=scroll_filter
        )

        if not points:
            raise ValueError(
                f"Knowledge base '{base_name}' not found."
            )

        payload = points[0].payload

        return {
            "name": formatted_name,
            "document_id": payload.get("document_id"),
            "uu_number": payload.get("uu_number"),
            "tahun": payload.get("tahun"),
            "judul_uu": payload.get("judul_uu"),
            "created_at": payload.get("created_at")
        }

    # =========================================================
    # SEARCH
    # =========================================================

    async def search_knowledgebase(
        self,
        base_name: str,
        query: str,
        section_type: Optional[str] = None,
        pasal_type: Optional[str] = None,
        limit: int = 5
    ) -> Dict:

        formatted_name = (
            base_name.lower()
            .strip()
            .replace(" ", "_")
        )

        child_col = f"{formatted_name}_child"
        parent_col = f"{formatted_name}_parent"

        filter_conditions = []

        if section_type:

            filter_conditions.append(
                models.FieldCondition(
                    key="section_type",
                    match=models.MatchValue(
                        value=section_type
                    )
                )
            )

        if pasal_type:

            filter_conditions.append(
                models.FieldCondition(
                    key="pasal_type",
                    match=models.MatchValue(
                        value=pasal_type
                    )
                )
            )

        query_filter = (
            models.Filter(must=filter_conditions)
            if filter_conditions
            else None
        )

        query_vector = await asyncio.to_thread(
            self.embeddings.embed_query,
            query
        )

        response = await self.db.query_points(
            collection_name=child_col,
            query=query_vector,
            limit=limit,
            query_filter=query_filter,
            with_payload=True,
            score_threshold=0.60
        )

        if not response.points:

            return {
                "query": query,
                "total_results": 0,
                "results": []
            }

        parent_ids = list({
            hit.payload.get("parent_id")
            for hit in response.points
            if hit.payload.get("parent_id")
        })

        parents = await self.db.retrieve(
            collection_name=parent_col,
            ids=parent_ids,
            with_payload=True,
            with_vectors=False
        )

        parent_map = {
            str(p.id): p.payload
            for p in parents
        }

        results = []

        for hit in response.points:

            parent_id = hit.payload.get("parent_id")

            parent_payload = parent_map.get(
                str(parent_id),
                {}
            )

            results.append({
                "score": hit.score,

                "child": {
                    "content": hit.payload.get("content"),
                    "raw_text": hit.payload.get("raw_text"),

                    "type": hit.payload.get("type"),
                    "level": hit.payload.get("level"),

                    "reference_label": hit.payload.get("reference_label"),

                    "keyword_tags": hit.payload.get(
                        "keyword_tags",
                        []
                    ),

                    "pasal_nomor": hit.payload.get("pasal_nomor"),
                    "ayat_nomor": hit.payload.get("ayat_nomor"),
                    "huruf": hit.payload.get("huruf")
                },

                "parent": {
                    "content": parent_payload.get("content"),

                    "reference_label": parent_payload.get(
                        "reference_label"
                    ),

                    "pasal_nomor": parent_payload.get(
                        "pasal_nomor"
                    ),

                    "bab_nomor": parent_payload.get(
                        "bab_nomor"
                    ),

                    "bab_judul": parent_payload.get(
                        "bab_judul"
                    ),

                    "pasal_type": parent_payload.get(
                        "pasal_type"
                    )
                }
            })

        return {
            "query": query,
            "total_results": len(results),
            "results": results
        }