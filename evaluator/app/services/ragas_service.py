"""
evaluator/app/services/ragas_service.py

Bersihkan semua wrapper throttle lama — throttle sekarang ada di ThrottledChatGroq.
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Optional
from ragas.run_config import RunConfig

logger = logging.getLogger(__name__)

_ragas_executor = ThreadPoolExecutor(max_workers=1)

# ── HAPUS semua kode _TokenBucket, _PerRequestThrottle,
#    _ThrottledLLMWrapper yang ada di sini. Tidak diperlukan lagi. ──


class RagasService:
    def __init__(self):
        self._available = False
        self._availability_error = None
        self.evaluator_llm = None
        self.evaluator_embeddings = None
        self.is_v2 = False
        self._adapted_metrics: dict = {} 

        try:
            from ragas.llms import LangchainLLMWrapper
            from ragas.embeddings import LangchainEmbeddingsWrapper
            from app.core.llm_provider import llm          # ← sudah ThrottledChatGroq
            from app.core.throttled_llm import ThrottledChatGroq
            from app.core.config import settings
            from app.core.embeddings import embeddings

            eval_llm_raw = ThrottledChatGroq(
                temperature=settings.ragas_llm_temperature,
                groq_api_key=settings.GROQ_API_KEY,
                model_name=settings.ragas_llm_model,       # llama-3.1-70b-versatile
            )

            # Tidak perlu wrapper tambahan — throttle sudah di dalam llm
            self.evaluator_llm = LangchainLLMWrapper(eval_llm_raw)
            self.evaluator_embeddings = LangchainEmbeddingsWrapper(embeddings)
            self._available = True
            logger.info(
                "✅ RagasService siap | evaluator_model=%s",
                settings.ragas_llm_model,
            )
        except Exception as exc:
            self._availability_error = str(exc)
            logger.warning("⚠️ RAGAS tidak tersedia: %s", exc)

    @property
    def is_available(self) -> bool:
        return self._available

    def _run_evaluate_sync(self, data: dict, metrics: list):
        import asyncio
        import nest_asyncio
        from ragas import evaluate
        from datasets import Dataset

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        nest_asyncio.apply(loop)

        logger.info(
            "[RagasDebug] contexts n_chunks=%d | first_chunk_len=%d | gt=%s",
            len(data["contexts"][0]),
            len(data["contexts"][0][0]) if data["contexts"][0] else 0,
            data.get("ground_truth", [None])[0][:80] if data.get("ground_truth") else "NONE",
        )
        
        try:
            # Ikat LLM & embeddings ke tiap metrik — TANPA adapt_prompts (tidak ada di v0.1.21)
            for metric in metrics:
                if hasattr(metric, "llm"):
                    metric.llm = self.evaluator_llm
                if hasattr(metric, "embeddings") and self.evaluator_embeddings:
                    metric.embeddings = self.evaluator_embeddings

            # Di _run_evaluate_sync, sebelum baris Dataset.from_dict(data)
            logger.info(
                "[RagasService] Dataset keys=%s | gt=%s | answer_len=%d",
                list(data.keys()),
                data.get("ground_truth", [None])[0] is not None,
                len(data.get("answer", [""])[0]),
            )

            logger.info("========== RAGAS DEBUG ==========")

            logger.info("QUESTION:\n%s", data["question"][0])

            logger.info("ANSWER:\n%s", data["answer"][0][:500])

            if data.get("ground_truth"):
                logger.info(
                    "GROUND TRUTH:\n%s",
                    data["ground_truth"][0][:2000]
                )

            for idx, chunk in enumerate(data["contexts"][0]):
                logger.info(
                    "CHUNK[%d]:\n%s",
                    idx,
                    chunk[:1000]
                )

            logger.info("=================================")

            dataset = Dataset.from_dict(data)
            result = evaluate(
                dataset=dataset,
                metrics=metrics,
                llm=self.evaluator_llm,
                embeddings=self.evaluator_embeddings,
                run_config=RunConfig(
                    max_workers=1,
                    max_retries=5,
                    timeout=500,
                ),
            )
            logger.info(
                "[RAGAS RESULT]\n%s",
                result.to_pandas().to_dict(orient="records")
            )
            
            return result
        finally:
            loop.close()
    
    async def evaluate_rag_custom(
            self,
            question: str,
            context: str, #faithfulness
            answer: str,
            metric_types: list[str],
            ground_truth: Optional[str] = None,
            context_chunks: Optional[list[str]] = None, #yang dipakai untuk precision + recall
        ):
            """Fungsi pembantu baru untuk mengevaluasi jenis metrik tertentu saja."""
            from ragas.metrics import Faithfulness, AnswerRelevancy, ContextPrecision, ContextRecall
            
            # Inisialisasi metrik dinamis berdasarkan request
            metrics = []
            if "faithfulness" in metric_types:
                metrics.append(Faithfulness(llm=self.evaluator_llm))
            if "answer_relevancy" in metric_types:
                metrics.append(AnswerRelevancy(llm=self.evaluator_llm, embeddings=self.evaluator_embeddings))
            if "context_precision" in metric_types:
                metrics.append(ContextPrecision(llm=self.evaluator_llm))
            if "context_recall" in metric_types:
                metrics.append(ContextRecall(llm=self.evaluator_llm))

            if context_chunks and len(context_chunks) > 1:
                chunks_for_eval = context_chunks
            else:
                # Pecah context besar jadi paragraf — minimal ada beberapa item untuk diranking
                chunks_for_eval = [c.strip() for c in context.split("\n\n") if c.strip()]
                if not chunks_for_eval:
                    chunks_for_eval = [context]

            data = {
                "question": [question],
                "answer": [answer],
                "contexts": [chunks_for_eval],  # ✅ list of chunks, bukan [[big_string]]
            }
            if ground_truth:
                data["ground_truth"] = [ground_truth]     # (benar untuk v0.1.21)

            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                _ragas_executor,
                self._run_evaluate_sync,
                data,
                metrics,
            )


ragas_service = RagasService()