"""
app/services/knowlagebase/qdrant_service.py
==========================================
QdrantService — menyimpan dan mencari parent-child chunks
sesuai format output baru ChunkingService.

Struktur koleksi (per knowledge base):
  {base_name}_parent  → satu titik per chunk `type=parent`
  {base_name}_child   → satu titik per chunk `type=child`, berisi parent_id

Payload standar tiap titik:
  chunk_id, type, section, title(parent)/parent_id(child),
  text, source, pasal, ayat, poin, pasal_rujukan, bagian,
  document_id, created_at
"""

from __future__ import annotations

import uuid
import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Dict, Optional, Any

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qmodels

from app.core.config import settings

logger = logging.getLogger(__name__)

# Ukuran vektor default (all-MiniLM-L6-v2 → 384; multilingual-MiniLM → 384)
_DEFAULT_VECTOR_SIZE = 384


# ─────────────────────────────────────────────────────────
# SERVICE
# ─────────────────────────────────────────────────────────

class QdrantService:
    """
    Mengelola koleksi Qdrant dan menyimpan/mencari parent-child chunks.
    Menggunakan AsyncQdrantClient agar kompatibel dengan event loop FastAPI.
    """

    def __init__(self, vector_size: int = _DEFAULT_VECTOR_SIZE):
        self._host = settings.QDRANT_HOST
        self._port = settings.QDRANT_PORT
        self._vector_size = vector_size
        self._client: Optional[AsyncQdrantClient] = None

    # ── Client ────────────────────────────────────────────

    def _get_client(self) -> AsyncQdrantClient:
        if self._client is None:
            self._client = AsyncQdrantClient(
                host=self._host,
                port=self._port,
                timeout=30,
            )
        return self._client

    # ── Health ────────────────────────────────────────────

    async def health_check(self) -> dict:
        try:
            client = self._get_client()
            cols = await client.get_collections()
            return {
                "status": "ok",
                "host": self._host,
                "port": self._port,
                "total_collections": len(cols.collections),
                "collection_names": [c.name for c in cols.collections],
            }
        except Exception as e:
            logger.warning(f"[QDRANT] Health check gagal: {e}")
            return {"status": "error", "detail": str(e)}

    # ── Collection Management ─────────────────────────────

    async def ensure_collection(self, name: str) -> None:
        """Buat koleksi jika belum ada."""
        client = self._get_client()
        existing = {c.name for c in (await client.get_collections()).collections}
        if name not in existing:
            await client.create_collection(
                collection_name=name,
                vectors_config=qmodels.VectorParams(
                    size=self._vector_size,
                    distance=qmodels.Distance.COSINE,
                ),
                optimizers_config=qmodels.OptimizersConfigDiff(
                    indexing_threshold=1000,
                ),
            )
            logger.info(f"[QDRANT] Koleksi '{name}' dibuat (size={self._vector_size})")
        else:
            logger.debug(f"[QDRANT] Koleksi '{name}' sudah ada")

    async def list_collections(self) -> List[str]:
        """Kembalikan semua nama base KB (tanpa suffix _parent/_child)."""
        client = self._get_client()
        cols = await client.get_collections()
        return sorted({
            c.name.replace("_parent", "").replace("_child", "")
            for c in cols.collections
            if c.name.endswith("_parent") or c.name.endswith("_child")
        })

    async def _resolve_collection_name(self, base_name: str) -> str:
        """
        Menerjemahkan nama base KB case-insensitive menjadi nama asli (case-sensitive)
        yang tersimpan di Qdrant. Contoh: 'uuno2002' -> 'UUNO2002'.
        """
        client = self._get_client()
        clean_base = base_name.replace("_parent", "").replace("_child", "").strip()
        try:
            cols = await client.get_collections()
            all_names = {c.name for c in cols.collections}
            
            # 1. Coba exact match dulu
            for suffix in ["_parent", "_child", ""]:
                if f"{clean_base}{suffix}" in all_names:
                    return clean_base
            
            # 2. Coba case-insensitive match
            base_lower = clean_base.lower()
            for col_name in all_names:
                col_lower = col_name.lower()
                for suffix in ["_parent", "_child"]:
                    if col_lower == f"{base_lower}{suffix}":
                        resolved = col_name[:-len(suffix)]
                        logger.info(f"[QDRANT] Mengatasi case mismatch: '{clean_base}' -> '{resolved}'")
                        return resolved
                if col_lower == base_lower:
                    return col_name
        except Exception as e:
            logger.warning(f"[QDRANT] Gagal resolusi nama koleksi: {e}")
        
        return clean_base

    async def delete_knowledgebase(self, base_name: str) -> bool:
        client = self._get_client()
        clean_base = await self._resolve_collection_name(base_name)
        for suffix in ["_parent", "_child"]:
            try:
                await client.delete_collection(f"{clean_base}{suffix}")
                logger.info(f"[QDRANT] Koleksi '{clean_base}{suffix}' dihapus")
            except Exception as e:
                logger.warning(f"[QDRANT] Gagal hapus '{clean_base}{suffix}': {e}")
        return True

    async def get_stats(self, base_name: str) -> Dict:
        client = self._get_client()
        clean_base = await self._resolve_collection_name(base_name)
        try:
            p = await client.get_collection(f"{clean_base}_parent")
            c = await client.get_collection(f"{clean_base}_child")
            return {
                "parent_count": p.points_count,
                "child_count": c.points_count,
                "status": "active",
            }
        except Exception as e:
            return {"error": str(e), "status": "error"}

    async def get_monitor_data(self, base_name: str, preview_limit: int = 5) -> Dict:
        """
        Endpoint khusus monitoring — mengembalikan dalam satu call:
          - Nama kedua collection Qdrant
          - Point count parent & child
          - Cuplikan (preview) dokumen dari masing-masing collection
        """
        client = self._get_client()
        clean_base = await self._resolve_collection_name(base_name)
        parent_col = f"{clean_base}_parent"
        child_col  = f"{clean_base}_child"

        result: Dict = {
            "base_name": clean_base,
            "parent_collection": parent_col,
            "child_collection":  child_col,
            "status": "active",
            "parent_count": 0,
            "child_count": 0,
            "parent_preview": [],
            "child_preview": [],
            "errors": [],
        }

        # ── Parent ────────────────────────────────────────────────────────────
        try:
            p_info = await client.get_collection(parent_col)
            result["parent_count"] = p_info.points_count or 0
            p_points, _ = await client.scroll(
                collection_name=parent_col,
                limit=preview_limit,
                with_payload=True,
                with_vectors=False,
            )
            result["parent_preview"] = [pt.payload for pt in p_points]
        except Exception as e:
            err_str = str(e)
            if "not found" in err_str.lower() or "404" in err_str:
                result["errors"].append(f"Parent collection `{parent_col}` tidak ditemukan di Qdrant. Pastikan dokumen telah di-embed dan diindeks.")
            else:
                result["errors"].append(f"parent: {err_str}")
            result["status"] = "partial_error"

        # ── Child ─────────────────────────────────────────────────────────────
        try:
            c_info = await client.get_collection(child_col)
            result["child_count"] = c_info.points_count or 0
            c_points, _ = await client.scroll(
                collection_name=child_col,
                limit=preview_limit,
                with_payload=True,
                with_vectors=False,
            )
            result["child_preview"] = [pt.payload for pt in c_points]
        except Exception as e:
            err_str = str(e)
            if "not found" in err_str.lower() or "404" in err_str:
                result["errors"].append(f"Child collection `{child_col}` tidak ditemukan di Qdrant. Pastikan dokumen telah di-embed dan diindeks.")
            else:
                result["errors"].append(f"child: {err_str}")
            result["status"] = "partial_error"

        # Tandai sebagai "not_found" jika keduanya tidak ada
        if result["parent_count"] == 0 and result["child_count"] == 0 and result["errors"]:
            result["status"] = "not_found"

        return result

    # ── Store (dari raw_chunks baru) ──────────────────────

    async def store_chunks(
        self,
        raw_chunks: List[dict],
        base_name: str,
        document_id: str,
        embed_fn,                   # callable: list[str] → list[list[float]]
        batch_size: int = 32,
    ) -> dict:
        """
        Simpan seluruh raw_chunks (format baru ChunkingService) ke Qdrant.

        Args:
            raw_chunks : list dict dari chunking_result.__dict__['raw_chunks']
            base_name  : nama KB (koleksi = {base_name}_parent / _child)
            document_id: ID dokumen
            embed_fn   : fungsi embed sinkron (list[str] → list[list[float]])
            batch_size : jumlah chunk per batch embedding

        Return:
            dict dengan statistik penyimpanan
        """
        clean_base = base_name.replace("_parent", "").replace("_child", "")
        parent_col = f"{clean_base}_parent"
        child_col  = f"{clean_base}_child"

        await self.ensure_collection(parent_col)
        await self.ensure_collection(child_col)

        parents = [c for c in raw_chunks if c.get("type") == "parent"]
        children = [c for c in raw_chunks if c.get("type") == "child"]

        created_at = datetime.now(timezone.utc).isoformat()

        # ── Embed & store parents ─────────────────────────
        parent_stored = await self._embed_and_upsert(
            client=self._get_client(),
            collection=parent_col,
            chunks=parents,
            embed_fn=embed_fn,
            batch_size=batch_size,
            extra_payload={"document_id": document_id, "created_at": created_at},
        )

        # ── Embed & store children ────────────────────────
        child_stored = await self._embed_and_upsert(
            client=self._get_client(),
            collection=child_col,
            chunks=children,
            embed_fn=embed_fn,
            batch_size=batch_size,
            extra_payload={"document_id": document_id, "created_at": created_at},
        )

        logger.info(
            f"[QDRANT] Store selesai: {parent_stored} parent, {child_stored} child "
            f"→ '{clean_base}'"
        )
        return {
            "status": "success",
            "base_name": clean_base,
            "parent_stored": parent_stored,
            "child_stored": child_stored,
            "total_stored": parent_stored + child_stored,
        }

    async def _embed_and_upsert(
        self,
        client: AsyncQdrantClient,
        collection: str,
        chunks: List[dict],
        embed_fn,
        batch_size: int,
        extra_payload: dict,
    ) -> int:
        """Batch embed lalu upsert ke satu koleksi. Return jumlah yang berhasil."""
        if not chunks:
            return 0

        stored = 0
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]
            texts = [c.get("text", "") for c in batch]

            # Jalankan embedding di thread agar tidak blokir event loop
            vectors: List[List[float]] = await asyncio.to_thread(embed_fn, texts)

            points = []
            for chunk, vector in zip(batch, vectors):
                payload = self._build_payload(chunk, extra_payload)
                points.append(
                    qmodels.PointStruct(
                        id=str(uuid.uuid4()),
                        vector=vector,
                        payload=payload,
                    )
                )

            await client.upsert(collection_name=collection, points=points)
            stored += len(points)
            logger.debug(f"[QDRANT] Upsert {len(points)} poin ke '{collection}' (batch {i//batch_size + 1})")

        return stored

    @staticmethod
    def _build_payload(chunk: dict, extra: dict) -> dict:
        """
        Bangun payload Qdrant dari satu raw chunk dict.
        Payload disimpan secara flat untuk memudahkan filtering.
        """
        meta = chunk.get("metadata", {})
        payload = {
            # Identitas chunk
            "chunk_id":   chunk.get("chunk_id", ""),
            "type":       chunk.get("type", ""),
            "section":    chunk.get("section", ""),
            "title":      chunk.get("title", ""),       # hanya parent
            "parent_id":  chunk.get("parent_id", ""),  # hanya child
            # Teks
            "content":    chunk.get("text", ""),
            # Metadata dokumen
            "source":     meta.get("source", ""),
            "bagian":     meta.get("bagian", ""),
            "pasal":      meta.get("pasal"),            # int atau None
            "ayat":       meta.get("ayat"),             # int atau None
            "poin":       meta.get("poin", ""),
            "huruf":      meta.get("huruf", ""),
            "pasal_rujukan": meta.get("pasal_rujukan"), # int atau None (penjelasan)
            # Tambahan
            **extra,
        }
        # Hapus key None agar Qdrant tidak complain
        return {k: v for k, v in payload.items() if v is not None and v != ""}

    # ── Search ────────────────────────────────────────────

    @staticmethod
    def _hybrid_rerank(
        results: list,
        pasal_user: Optional[int] = None,
        ayat_user: Optional[int] = None,
    ) -> list:
        """
        Hybrid reranking: boost hasil yang exact match dengan pasal/ayat yang disebut user.
        Jika user menyebut pasal yang salah, semantic score akan tetap rendah → tidak di-boost.
        """
        if pasal_user is None and ayat_user is None:
            return results  # tidak ada reranking jika tidak ada filter

        for r in results:
            child = r.get("child", {})
            # Chunk Penjelasan menyimpan nomor pasal di 'pasal_rujukan', bukan 'pasal'
            child_pasal = child.get("pasal")
            if child_pasal is None:
                child_pasal = child.get("pasal_rujukan")
            child_ayat = child.get("ayat")
            
            # Boost jika pasal match dengan yang disebut user
            if pasal_user is not None and child_pasal == pasal_user:
                r["score"] = round(r["score"] + 0.5, 4)
                r["is_exact_pasal_match"] = True
                logger.debug(
                    "[HYBRID] Boost pasal=%d → score=%.4f",
                    child_pasal, r["score"],
                )
            
            # Boost jika ayat match dengan yang disebut user (dan pasal juga match)
            if ayat_user is not None and child_ayat == ayat_user and child_pasal == pasal_user:
                r["score"] = round(r["score"] + 0.3, 4)
                r["is_exact_ayat_match"] = True
                logger.debug(
                    "[HYBRID] Boost ayat=%d pasal=%d → score=%.4f",
                    child_ayat, child_pasal, r["score"],
                )

        # Sort ulang berdasarkan score yang sudah di-boost
        results.sort(key=lambda x: x["score"], reverse=True)
        return results

    async def search(
        self,
        base_name: str,
        query_vector: List[float],
        section: Optional[str] = None,
        pasal: Optional[int] = None,
        ayat: Optional[int] = None,
        huruf: Optional[str] = None,
        limit: int = 5,
        score_threshold: float = 0.15,
        relative_threshold: float = 0.7,
    ) -> Dict:
        """
        Cari child chunks yang relevan, lalu fetch parent-nya untuk konteks.

        Args:
            base_name     : nama KB
            query_vector  : vektor hasil embed query
            section       : filter section ("Konsiderans"/"Batang Tubuh"/"Penjelasan")
            pasal         : filter nomor pasal
            ayat          : filter nomor ayat
            huruf         : filter huruf (a/b/c/dll)
            limit         : jumlah hasil akhir
            score_threshold   : batas minimal similarity score (absolut, difilter di Qdrant)
            relative_threshold: hasil dengan skor < relative_threshold * skor tertinggi
                                 pada batch pencarian dibuang (kecuali exact match pasal/ayat
                                 user), agar hasil yang jauh lebih lemah dari kandidat terbaik
                                 tidak ikut lolos hanya karena skor absolutnya masih di atas
                                 score_threshold.

        Return:
            {total_results, results: [{score, child, parent}]}
        """
        client = self._get_client()
        clean_base = await self._resolve_collection_name(base_name)
        child_col  = f"{clean_base}_child"
        parent_col = f"{clean_base}_parent"

        # Bangun filter
        conditions = []
        if section:
            conditions.append(
                qmodels.FieldCondition(
                    key="section",
                    match=qmodels.MatchValue(value=section),
                )
            )
        if pasal is not None:
            # Skema baru pakai key "pasal", skema lama (legacy upsert_chunks) pakai
            # "pasal_number" — cek keduanya (OR) supaya filter tetap kena di data lama.
            conditions.append(
                qmodels.Filter(should=[
                    qmodels.FieldCondition(key="pasal", match=qmodels.MatchValue(value=pasal)),
                    qmodels.FieldCondition(key="pasal_number", match=qmodels.MatchValue(value=pasal)),
                ])
            )
        if ayat is not None:
            conditions.append(
                qmodels.Filter(should=[
                    qmodels.FieldCondition(key="ayat", match=qmodels.MatchValue(value=ayat)),
                    qmodels.FieldCondition(key="ayat_number", match=qmodels.MatchValue(value=ayat)),
                ])
            )
        q_filter = qmodels.Filter(must=conditions) if conditions else None

        # Ambil kandidat lebih banyak dari `limit` akhir agar relative threshold
        # punya cukup kandidat untuk dibandingkan sebelum dipotong ke `limit`.
        fetch_limit = max(limit * 3, 10)

        # Search di koleksi child
        search_resp = await client.query_points(
            collection_name=child_col,
            query=query_vector,
            limit=fetch_limit,
            query_filter=q_filter,
            with_payload=True,
            score_threshold=score_threshold,
        )

        pasal_not_found = False

        # ── Retry conditions ─────────────────────────────────────────────────
        # Retry tanpa filter jika:
        #   A) Hasil kosong (pasal/ayat disebut user tidak ada di DB)
        #   B) Hasil ada TAPI skor semantic rendah (< 0.3) — pasal/ayat ditemukan
        #      secara eksak tapi kontennya tidak relevan secara topik.
        #   C) Tidak ada filter pasal/ayat → skip (semantic search murni)
        should_retry = False
        retry_reason = None

        if search_resp.points and (pasal is not None or ayat is not None):
            # Hitung skor semantic tertinggi dari hasil filter
            max_semantic_score = max(hit.score for hit in search_resp.points)
            if max_semantic_score < 0.3:
                should_retry = True
                retry_reason = (
                    f"skor semantic rendah (max={max_semantic_score:.4f}) "
                    f"dengan filter pasal={pasal} ayat={ayat}. "
                    "Pasal ditemukan secara eksak tapi konten tidak relevan secara topik."
                )
        elif not search_resp.points and (pasal is not None or ayat is not None):
            should_retry = True
            retry_reason = (
                f"hasil kosong dengan filter pasal={pasal} ayat={ayat}. "
                "Pasal yang disebut user tidak ditemukan di DB."
            )

        if should_retry:
            logger.info(
                "[QDRANT] %s Retry tanpa filter untuk fallback semantik.",
                retry_reason,
            )
            search_resp = await client.query_points(
                collection_name=child_col,
                query=query_vector,
                limit=fetch_limit,
                query_filter=None,  # tanpa filter apapun
                with_payload=True,
                score_threshold=score_threshold,
            )
            pasal_not_found = True

        if not search_resp.points:
            return {"total_results": 0, "results": [], "pasal_not_found": pasal_not_found}

        # ── Relative threshold: buang kandidat yang jauh lebih lemah dari skor
        #    tertinggi di batch ini, kecuali exact match dengan pasal/ayat user ──
        def _hit_pasal(payload: dict) -> Optional[int]:
            """
            Nomor pasal chunk ini — fallback ke pasal_rujukan (chunk Penjelasan)
            lalu ke pasal_number (skema lama legacy upsert_chunks).
            """
            for key in ("pasal", "pasal_rujukan", "pasal_number"):
                if payload.get(key) is not None:
                    return payload.get(key)
            return None

        def _hit_ayat(payload: dict) -> Optional[int]:
            """Nomor ayat chunk ini — fallback ke ayat_number (skema lama)."""
            return payload.get("ayat") if payload.get("ayat") is not None else payload.get("ayat_number")

        def _is_exact_match(hit) -> bool:
            if pasal is None:
                return False
            hit_pasal = _hit_pasal(hit.payload)
            if hit_pasal != pasal:
                return False
            return ayat is None or _hit_ayat(hit.payload) == ayat

        max_score = max(hit.score for hit in search_resp.points)
        score_cutoff = max_score * relative_threshold
        points = [
            hit for hit in search_resp.points
            if hit.score >= score_cutoff or _is_exact_match(hit)
        ][:limit]

        if not points:
            return {"total_results": 0, "results": [], "pasal_not_found": pasal_not_found}

        # ── Fetch parent chunks ────────────────────────────────────────────
        def _get_parent_id(payload: dict) -> str:
            """Ambil parent_id dari payload, support field lama & baru."""
            return (
                payload.get("parent_id")
                or payload.get("parent_chunk_id")
                or ""
            )

        parent_chunk_ids = list({
            _get_parent_id(hit.payload)
            for hit in points
            if _get_parent_id(hit.payload)
        })

        parent_map: Dict[str, Any] = {}
        if parent_chunk_ids:
            for pid in parent_chunk_ids:
                scroll_resp, _ = await client.scroll(
                    collection_name=parent_col,
                    scroll_filter=qmodels.Filter(
                        must=[qmodels.FieldCondition(
                            key="chunk_id",
                            match=qmodels.MatchValue(value=pid),
                        )]
                    ),
                    limit=1,
                    with_payload=True,
                    with_vectors=False,
                )
                if scroll_resp:
                    parent_map[pid] = scroll_resp[0].payload

        results = []
        for hit in points:
            parent_id = _get_parent_id(hit.payload)
            parent_payload = parent_map.get(parent_id, {})
            # Support field "content" dan "text" (format lama)
            child_content = hit.payload.get("content") or hit.payload.get("text", "")
            parent_content = parent_payload.get("content") or parent_payload.get("text", "")
            results.append({
                "score": round(hit.score, 4),
                "child": {
                    "chunk_id":  hit.payload.get("chunk_id"),
                    "section":   hit.payload.get("section"),
                    "content":   child_content,
                    "pasal":     _hit_pasal(hit.payload),
                    "ayat":      _hit_ayat(hit.payload),
                    "poin":      hit.payload.get("poin"),
                    "parent_id": parent_id,
                    "pasal_rujukan": hit.payload.get("pasal_rujukan"),
                },
                "parent": {
                    "chunk_id": parent_payload.get("chunk_id"),
                    "title":    parent_payload.get("title"),
                    "content":  parent_content,
                    "section":  parent_payload.get("section"),
                    "pasal":    _hit_pasal(parent_payload),
                    "pasal_rujukan": parent_payload.get("pasal_rujukan"),
                },
            })

        # ── Hybrid rerank: boost hasil yang exact match dengan pasal/ayat user ──
        results = self._hybrid_rerank(results, pasal, ayat)

        return {"total_results": len(results), "results": results, "pasal_not_found": pasal_not_found}

    @staticmethod
    def _rerank_with_cross_encoder(query: str, results: list) -> list:
        """
        Re-rank kandidat hasil retrieval pakai cross-encoder lokal (query &
        dokumen diproses bersama), jauh lebih akurat menilai relevansi topikal
        dibanding cosine similarity bi-encoder murni (yang bisa tertipu
        kemiripan kata kunci). Dipanggil lewat asyncio.to_thread karena
        inference model ini CPU-bound/blocking.
        """
        from app.core.reranker import reranker

        pairs = []
        for r in results:
            parent_content = r.get("parent", {}).get("content", "") or ""
            child_content = r.get("child", {}).get("content", "") or ""
            doc_text = parent_content.strip() if len(parent_content.strip()) > 30 else child_content.strip()
            pairs.append((query, doc_text))

        scores = reranker.predict(pairs)
        for r, score in zip(results, scores):
            r["rerank_score"] = round(float(score), 4)

        results.sort(key=lambda x: x["rerank_score"], reverse=True)
        return results

    async def search_knowledgebase(
        self,
        base_name: str,
        query: str,
        section_type: Optional[str] = None,
        pasal_type: Optional[str] = None,
        ayat_type: Optional[str] = None,
        limit: int = 5,
        score_threshold: float = 0.15,
        use_reranker: bool = True,
    ) -> Dict:
        """
        Backward-compatible wrapper untuk pencarian RAG.
        Meng-embed query secara otomatis, memanggil search(), lalu (opsional)
        me-rerank kandidat hasilnya pakai cross-encoder lokal sebelum dipotong
        ke `limit` akhir.
        """
        import re
        from app.core.embeddings import embeddings
        query_vector = await asyncio.to_thread(embeddings.embed_query, query)

        # Abaikan filter "Semua" agar tidak ikut di-filter ke Qdrant
        section = section_type if section_type and section_type.strip().lower() not in ("semua", "all", "") else None

        # Parse nomor pasal jika berupa teks
        pasal_filter = None
        if pasal_type:
            try:
                m = re.search(r"\d+", pasal_type)
                if m:
                    pasal_filter = int(m.group(0))
            except Exception:
                pass

        # Parse nomor ayat jika berupa teks
        ayat_filter = None
        if ayat_type:
            try:
                m = re.search(r"\d+", ayat_type)
                if m:
                    ayat_filter = int(m.group(0))
            except Exception:
                pass

        # Jika reranker aktif, ambil kandidat lebih banyak dari `limit` akhir
        # supaya cross-encoder punya cukup pilihan untuk dinilai ulang.
        candidate_pool = max(limit * 4, 8) if use_reranker else limit

        results_dict = await self.search(
            base_name=base_name,
            query_vector=query_vector,
            section=section,
            pasal=pasal_filter,
            ayat=ayat_filter,
            limit=candidate_pool,
            score_threshold=score_threshold,
        )

        if use_reranker and results_dict.get("results"):
            reranked = await asyncio.to_thread(
                self._rerank_with_cross_encoder, query, results_dict["results"]
            )
            results_dict["results"] = reranked[:limit]
            results_dict["total_results"] = len(results_dict["results"])

        results_dict["query"] = query
        # Sertakan pasal/ayat yang di-parse untuk downstream (integration service)
        results_dict["pasal_filter_used"] = pasal_filter
        results_dict["ayat_filter_used"] = ayat_filter
        return results_dict

    async def get_kb_info(self, base_name: str) -> Dict:
        """Ambil metadata dasar dari collection parent."""
        client = self._get_client()
        clean_base = await self._resolve_collection_name(base_name)
        parent_col = f"{clean_base}_parent"
        points, _ = await client.scroll(
            collection_name=parent_col,
            limit=1,
            with_payload=True,
            with_vectors=False,
        )
        if not points:
            raise ValueError(f"Knowledge base '{clean_base}' tidak ditemukan.")
        payload = points[0].payload
        return {
            "name": clean_base,
            "document_id": payload.get("document_id"),
            "source": payload.get("source"),
            "created_at": payload.get("created_at"),
        }

    async def get_chunks_preview(self, base_name: str, limit: int = 10) -> Dict:
        """Ambil cuplikan parent dan child chunks dari Qdrant."""
        client = self._get_client()
        clean_base = await self._resolve_collection_name(base_name)
        parent_col = f"{clean_base}_parent"
        child_col  = f"{clean_base}_child"

        try:
            # Scroll parent points
            parent_resp, _ = await client.scroll(
                collection_name=parent_col,
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )
            # Scroll child points
            child_resp, _ = await client.scroll(
                collection_name=child_col,
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )

            parents = [p.payload for p in parent_resp]
            children = [c.payload for c in child_resp]

            return {
                "status": "success",
                "parents": parents,
                "children": children
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # ── Legacy compat (upsert_chunks dari DocumentChunk list) ─────────────────

    def upsert_chunks(
        self,
        chunks,   # list[DocumentChunk]
        collection_name: Optional[str] = None,
    ) -> dict:
        """
        Backward-compat: simpan DocumentChunk yang sudah ber-embedding.
        Dipanggil dari endpoint /process saat embed=true.
        Akan membagi parent chunk ke parent collection dan child chunk ke child collection.
        """
        import asyncio as _asyncio
        from qdrant_client import QdrantClient
        from qdrant_client.http import models as _m

        if collection_name:
            clean_base = collection_name.replace("_parent", "").replace("_child", "")
            parent_col = f"{clean_base}_parent"
            child_col = f"{clean_base}_child"
        else:
            parent_col = settings.embedding_collection_parent
            child_col = settings.embedding_collection_child

        client = QdrantClient(host=self._host, port=self._port, timeout=30)

        # Pastikan kedua koleksi ada
        for col in [parent_col, child_col]:
            try:
                existing = {c.name for c in client.get_collections().collections}
                if col not in existing:
                    client.create_collection(
                        collection_name=col,
                        vectors_config=_m.VectorParams(
                            size=self._vector_size,
                            distance=_m.Distance.COSINE,
                        ),
                    )
                    logger.info(f"[QDRANT] Koleksi '{col}' dibuat")
            except Exception as e:
                logger.warning(f"[QDRANT] Gagal cek/buat koleksi '{col}': {e}")

        parent_points = []
        child_points = []

        for c in chunks:
            if c.embedding is None:
                continue
            
            payload = {
                "chunk_id": c.chunk_id,
                "content": c.content,
                "is_parent": c.metadata.is_parent,
                "level_number": c.metadata.level_number,
                "document_id": c.metadata.document_id,
                "source_filename": c.metadata.source_filename,
                "pasal_number": c.metadata.pasal_number,
            }
            if not c.metadata.is_parent:
                payload["ayat_number"] = c.metadata.ayat_number
                payload["parent_chunk_id"] = c.metadata.parent_chunk_id

            point = _m.PointStruct(
                id=str(uuid.uuid4()),
                vector=c.embedding,
                payload=payload,
            )
            # Jika c.metadata.is_parent True, masukkan ke parent collection
            if c.metadata.is_parent:
                parent_points.append(point)
            else:
                child_points.append(point)

        if not parent_points and not child_points:
            return {
                "status": "skipped",
                "reason": "no embedded chunks",
                "parent_collection": parent_col,
                "child_collection": child_col,
            }

        upserted_parent = 0
        upserted_child = 0
        errors = []

        if parent_points:
            try:
                client.upsert(collection_name=parent_col, points=parent_points)
                logger.info(f"[QDRANT] Upsert {len(parent_points)} parent poin ke '{parent_col}'")
                upserted_parent = len(parent_points)
            except Exception as e:
                logger.error(f"[QDRANT] Upsert parent gagal ke '{parent_col}': {e}")
                errors.append(f"Parent upsert error: {str(e)}")

        if child_points:
            try:
                client.upsert(collection_name=child_col, points=child_points)
                logger.info(f"[QDRANT] Upsert {len(child_points)} child poin ke '{child_col}'")
                upserted_child = len(child_points)
            except Exception as e:
                logger.error(f"[QDRANT] Upsert child gagal ke '{child_col}': {e}")
                errors.append(f"Child upsert error: {str(e)}")

        if errors:
            return {
                "status": "partial_error" if (upserted_parent or upserted_child) else "error",
                "detail": "; ".join(errors),
                "parent_collection": parent_col,
                "child_collection": child_col,
                "parent_upserted": upserted_parent,
                "child_upserted": upserted_child,
            }

        return {
            "status": "success",
            "parent_collection": parent_col,
            "child_collection": child_col,
            "parent_upserted": upserted_parent,
            "child_upserted": upserted_child,
            "total_upserted": upserted_parent + upserted_child,
        }

    def get_collections_detailed(self) -> list:
        """Sinkron — untuk endpoint /collections (non-async route)."""
        from qdrant_client import QdrantClient
        client = QdrantClient(host=self._host, port=self._port, timeout=10)
        try:
            cols = client.get_collections().collections
            return [{"name": c.name} for c in cols]
        except Exception as e:
            return [{"error": str(e)}]
