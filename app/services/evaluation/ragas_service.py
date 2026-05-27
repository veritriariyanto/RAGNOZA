# ragas_service.py

import logging

from datasets import Dataset

from app.core.embeddings import embeddings
from app.core.llm_provider import llm


logger = logging.getLogger(__name__)

class RagasService:
    def __init__(self):
        self._available = False
        self._availability_error = None
        self.evaluator_llm = None
        self.evaluator_embeddings = None

        try:
            from ragas.embeddings import LangchainEmbeddingsWrapper
            from ragas.llms import LangchainLLMWrapper

            self.evaluator_llm = LangchainLLMWrapper(llm)
            self.evaluator_embeddings = LangchainEmbeddingsWrapper(embeddings)
            self._available = True
        except ImportError as exc:
            self._availability_error = exc
            logger.warning("RAGAS evaluation is unavailable: %s", exc)

    async def evaluate_rag(
        self,
        question: str,
        context : str,
        answer: str 
    ):
        if not self._available:
            logger.warning("Skipping RAGAS evaluation because the dependency stack is unavailable.")
            return None

        from ragas import evaluate
        from ragas.metrics import answer_relevancy, faithfulness
        
        dataset = Dataset.from_dict({
            "question": [question],
            "retrieved_contexts": [[context]],
            "answer": [answer]
        })

        result = evaluate(
            dataset=dataset,
            metrics=[
                faithfulness,
                answer_relevancy
            ],
            llm=self.evaluator_llm,
            embeddings=self.evaluator_embeddings
        )

        return result
