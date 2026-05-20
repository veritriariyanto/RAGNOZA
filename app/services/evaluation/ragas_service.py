# ragas_service.py

from datasets import Dataset

from ragas import evaluate 
from ragas.metrics import (
    faithfulness,
    answer_relevancy
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
        context : str,
        answer: str 
    ):
        
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
