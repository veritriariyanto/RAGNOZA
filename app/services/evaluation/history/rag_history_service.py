# app/services/history/rag_history_service.py

import json  
from sqlalchemy.orm import Session

from app.database.models import RAGHistory

class RAGHistoryService:
    @staticmethod
    def save_history(
        db: Session,
        knowledge_base: str,
        provider: str,
        raw_transcribe: str,
        repaired_text: str,
        search_query: str,
        retrieved_context: str,
        final_material
    ):
        history = RAGHistory(
            knowledge_base=knowledge_base,
            provider=provider,
            raw_transcribe=raw_transcribe,
            repaired_text=repaired_text,
            search_query=search_query,
            retrieved_context=retrieved_context,
            generate_material=json.dumps(
                final_material.model_dump(),
                ensure_ascii=False
            ) if final_material else None,
            compliance_score=final_material.compliance_score if final_material else None,
            decision_status=final_material.decision_status if final_material else None
        )

        db.add(history)
        db.commit()
        db.refresh(history)

        return history
    
    
    