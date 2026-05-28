from app.services.evaluation.ragas_service import RagasService

ragas_service = RagasService()


class EvaluationService:
    """
    Service layer untuk evaluasi RAG menggunakan RAGAS.
    Bertanggung jawab untuk:
    - Mengorkestrasi pemanggilan RagasService
    - Memformat hasil evaluasi agar konsisten
    - Menangani error dan edge case
    """

    async def run_evaluation(
        self,
        question: str,
        context: str,
        answer: str,
        ground_truth: str | None = None,
    ) -> dict:
        """
        Jalankan evaluasi RAGAS dan kembalikan hasil yang sudah diformat.

        Args:
            question: Pertanyaan yang diajukan user
            context: Konteks yang di-retrieve dari knowledge base
            answer: Jawaban yang dihasilkan oleh LLM

        Returns:
            dict berisi metrik evaluasi dan status
        """
        try:
            result = await ragas_service.evaluate_rag(
                question=question,
                context=context,
                answer=answer,
                ground_truth=ground_truth,
            )

            # Konversi result RAGAS ke dict yang bersih
            scores = result.to_pandas().to_dict(orient="records")[0]

            faithfulness_score = scores.get("faithfulness", None)
            answer_relevancy_score = scores.get("answer_relevancy", None)
            context_precision_score = scores.get("context_precision", None)
            context_recall_score = scores.get("context_recall", None)

            # Hitung rata-rata overall score (hanya dari metrik yang tersedia)
            available_scores = [
                s for s in [
                    faithfulness_score, 
                    answer_relevancy_score,
                    context_precision_score,
                    context_recall_score
                ]
                if s is not None
            ]
            overall_score = (
                round(sum(available_scores) / len(available_scores), 4)
                if available_scores
                else None
            )

            return {
                "status": "success",
                "metrics": {
                    "faithfulness": (
                        round(float(faithfulness_score), 4)
                        if faithfulness_score is not None
                        else None
                    ),
                    "answer_relevancy": (
                        round(float(answer_relevancy_score), 4)
                        if answer_relevancy_score is not None
                        else None
                    ),
                    "context_precision": (
                        round(float(context_precision_score), 4)
                        if context_precision_score is not None
                        else None
                    ),
                    "context_recall": (
                        round(float(context_recall_score), 4)
                        if context_recall_score is not None
                        else None
                    ),
                    "overall_score": overall_score,
                },
                "input": {
                    "question": question,
                    "context": context,
                    "answer": answer,
                    "ground_truth": ground_truth,
                },
            }

        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "metrics": None,
                "input": {
                    "question": question,
                    "context": context,
                    "answer": answer,
                    "ground_truth": ground_truth,
                },
            }