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

        try:
            from ragas.llms import LangchainLLMWrapper
            from ragas.embeddings import LangchainEmbeddingsWrapper
            from app.core.llm_provider import llm          # ← sudah ThrottledChatGroq
            from app.core.embeddings import embeddings

            if llm is None or embeddings is None:
                raise RuntimeError("LLM atau embeddings gagal diinisialisasi")

            # Tidak perlu wrapper tambahan — throttle sudah di dalam llm
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
        import asyncio
        import nest_asyncio
        from ragas import evaluate
        from datasets import Dataset

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
                run_config=RunConfig(
                    max_workers=1,
                    max_retries=5,
                    timeout=500,
                ),
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

        try:
            from ragas.metrics import (
                Faithfulness, AnswerRelevancy,
                ContextPrecision, ContextRecall,
            )
            faithfulness_metric      = Faithfulness()
            answer_relevancy_metric  = AnswerRelevancy()
            context_precision_metric = ContextPrecision()
            context_recall_metric    = ContextRecall()
            logger.info("RAGAS: menggunakan API 0.2+ (class-based metrics)")
        except ImportError:
            from ragas.metrics import (
                faithfulness, answer_relevancy,
                context_precision, context_recall,
            )
            faithfulness_metric      = faithfulness
            answer_relevancy_metric  = answer_relevancy
            context_precision_metric = context_precision
            context_recall_metric    = context_recall
            logger.info("RAGAS: menggunakan API 0.1.x (singleton metrics)")

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
                faithfulness_metric, answer_relevancy_metric,
                context_precision_metric, context_recall_metric,
            ]
        else:
            metrics = [faithfulness_metric, answer_relevancy_metric]

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            _ragas_executor,
            self._run_evaluate_sync,
            data,
            metrics,
        )
        return result


ragas_service = RagasService()