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
            # ─────────────────────────────────────────────────────────────────
            # OPTIMASI: Paksa Metrik Adaptasi ke Bahasa Indonesia & Ikat ke LLM Groq
            # ─────────────────────────────────────────────────────────────────
            for metric in metrics:
                if hasattr(metric, "llm"):
                    metric.llm = self.evaluator_llm
                if hasattr(metric, "embeddings") and self.evaluator_embeddings:
                    metric.embeddings = self.evaluator_embeddings

                metric_name = metric.__class__.__name__
                if metric_name not in self._adapted_metrics:
                    if not hasattr(metric, "adapt_prompts"):
                        logger.debug("Metrik %s tidak mendukung adapt_prompts — skip.", metric_name)
                        self._adapted_metrics[metric_name] = False
                    else:
                        try:
                            logger.info("Menerjemahkan prompt metrik %s ke Bahasa Indonesia...", metric_name)
                            metric.adapt_prompts(language="indonesian", llm=self.evaluator_llm)
                            self._adapted_metrics[metric_name] = True
                            logger.info("✅ Cache adaptasi %s tersimpan.", metric_name)
                        except Exception as adapt_err:
                            logger.warning("Gagal adaptasi %s: %s.", metric_name, adapt_err)
                            self._adapted_metrics[metric_name] = False
                else:
                    logger.debug("Cache hit — skip adapt_prompts untuk %s.", metric_name)

            # Di _run_evaluate_sync, sebelum baris Dataset.from_dict(data)
            logger.info(
                "[RagasService] Dataset keys=%s | gt=%s | answer_len=%d",
                list(data.keys()),
                data.get("reference", [None])[0] is not None,
                len(data.get("answer", [""])[0]),
            )
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
    
    async def evaluate_rag_custom(
            self,
            question: str,
            context: str,
            answer: str,
            metric_types: list[str],
            ground_truth: Optional[str] = None,
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

            data = {
                "question": [question],
                "answer": [answer],
                "contexts": [[context]],      # list of list — WAJIB
            }
            if ground_truth:
                data["ground_truths"] = [[ground_truth]]   # list of list — WAJIB untuk ContextRecall 0.1.x
                data["ground_truth"]  = [ground_truth]     # list biasa — untuk ContextPrecision 0.1.x

            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                _ragas_executor,
                self._run_evaluate_sync,
                data,
                metrics,
            )


ragas_service = RagasService()