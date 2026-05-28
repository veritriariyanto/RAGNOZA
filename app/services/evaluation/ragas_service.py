from datasets import Dataset

from ragas import evaluate
from ragas.metrics import (
    faithfulness,
    answer_relevancy,
    context_precision,   # butuh ground_truth
    context_recall,      # butuh ground_truth
)

from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper

from app.core.llm_provider import llm
from app.core.embeddings import embeddings


class RagasService:
    def __init__(self):
        self.evaluator_llm = LangchainLLMWrapper(llm)
        self.evaluator_embeddings = LangchainEmbeddingsWrapper(embeddings)

    async def evaluate_rag(
        self,
        question: str,
        context: str,
        answer: str,
        ground_truth: str | None = None,
    ):
        """
        Jalankan evaluasi RAGAS.

        - Jika ground_truth disediakan → jalankan semua 4 metrik
          (faithfulness, answer_relevancy, context_precision, context_recall)
        - Jika ground_truth None → hanya faithfulness & answer_relevancy
        """
        data = {
            "question": [question],
            "retrieved_contexts": [[context]],
            "answer": [answer],
        }

        if ground_truth:
            data["reference"] = [ground_truth]
            metrics = [
                faithfulness,
                answer_relevancy,
                context_precision,
                context_recall,
            ]
        else:
            metrics = [
                faithfulness,
                answer_relevancy,
            ]

        dataset = Dataset.from_dict(data)

        result = evaluate(
            dataset=dataset,
            metrics=metrics,
            llm=self.evaluator_llm,
            embeddings=self.evaluator_embeddings,
        )

        return result