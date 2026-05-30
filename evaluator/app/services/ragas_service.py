"""
evaluator/app/services/ragas_service.py

Fix: RAGAS menggunakan nest_asyncio yang tidak kompatibel dengan uvloop.
Solusi: jalankan evaluate() di thread terpisah via run_in_executor,
sehingga ia mendapat event loop asyncio standar (bukan uvloop).
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

logger = logging.getLogger(__name__)

# Thread pool khusus untuk RAGAS — 1 worker cukup karena evaluasi sequential
_ragas_executor = ThreadPoolExecutor(max_workers=1)


class RagasService:
    def __init__(self):
        self._available = False
        self._availability_error = None
        self.evaluator_llm = None
        self.evaluator_embeddings = None

        try:
            from ragas.llms import LangchainLLMWrapper
            from ragas.embeddings import LangchainEmbeddingsWrapper
            from app.core.llm_provider import llm
            from app.core.embeddings import embeddings

            if llm is None or embeddings is None:
                raise RuntimeError("LLM atau embeddings gagal diinisialisasi")

            self.evaluator_llm = LangchainLLMWrapper(llm)
            self.evaluator_embeddings = LangchainEmbeddingsWrapper(embeddings)
            self._available = True
            logger.info("✅ RagasService siap")

        except Exception as exc:
            self._availability_error = str(exc)
            logger.warning("⚠️ RAGAS tidak tersedia: %s", exc)

    @property
    def is_available(self) -> bool:
        return self._available

    def _run_evaluate_sync(self, data: dict, metrics: list):
        """
        Jalankan ragas.evaluate() secara synchronous di thread terpisah.
        Thread ini mendapat event loop asyncio standar (bukan uvloop),
        sehingga nest_asyncio bisa bekerja normal.
        """
        import asyncio
        import nest_asyncio
        from ragas import evaluate
        from datasets import Dataset

        # Buat event loop baru di thread ini (asyncio standar, bukan uvloop)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        nest_asyncio.apply(loop)

        try:
            dataset = Dataset.from_dict(data)
            result = evaluate(
                dataset=dataset,
                metrics=metrics,
                llm=self.evaluator_llm,
                embeddings=self.evaluator_embeddings,
            )
            return result
        finally:
            loop.close()

    async def evaluate_rag(
        self,
        question: str,
        context: str,
        answer: str,
        ground_truth: Optional[str] = None,
    ):
        if not self._available:
            raise RuntimeError(
                f"RagasService tidak tersedia: {self._availability_error}"
            )

        # Import metrik — deteksi versi ragas
        try:
            from ragas.metrics import (
                Faithfulness,
                AnswerRelevancy,
                ContextPrecision,
                ContextRecall,
            )
            faithfulness_metric      = Faithfulness()
            answer_relevancy_metric  = AnswerRelevancy()
            context_precision_metric = ContextPrecision()
            context_recall_metric    = ContextRecall()
            logger.info("RAGAS: menggunakan API 0.2+ (class-based metrics)")
        except ImportError:
            from ragas.metrics import (
                faithfulness,
                answer_relevancy,
                context_precision,
                context_recall,
            )
            faithfulness_metric      = faithfulness
            answer_relevancy_metric  = answer_relevancy
            context_precision_metric = context_precision
            context_recall_metric    = context_recall
            logger.info("RAGAS: menggunakan API 0.1.x (singleton metrics)")

        # Dataset — kirim kedua nama kolom agar kompatibel lintas versi ragas
        data = {
            "question":           [question],
            "answer":             [answer],
            "contexts":           [[context]],
            "retrieved_contexts": [[context]],
        }

        if ground_truth:
            data["reference"]    = [ground_truth]
            data["ground_truth"] = [ground_truth]
            metrics = [
                faithfulness_metric,
                answer_relevancy_metric,
                context_precision_metric,
                context_recall_metric,
            ]
        else:
            metrics = [
                faithfulness_metric,
                answer_relevancy_metric,
            ]

        # Jalankan di thread terpisah agar nest_asyncio tidak bentrok uvloop
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            _ragas_executor,
            self._run_evaluate_sync,
            data,
            metrics,
        )

        return result


# Singleton
ragas_service = RagasService()