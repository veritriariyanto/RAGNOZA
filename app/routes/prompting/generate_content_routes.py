"""
generate_content_routes.py  (updated)

Perubahan dari versi lama:
- Tambah endpoint /generate-with-eval yang menjalankan RAGAS otomatis
- Endpoint /generate lama tetap tidak berubah (backward compatible)
- Evaluasi berjalan di BackgroundTask — tidak memperlambat response
- FIXED: Import RAGHistoryService dari app.services.history (versi benar, bukan evaluation/history)
"""

from datetime import datetime
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.postgres import get_db
from app.schemas.prompting.generate_content import MaterialRequest, MaterialResponse
from app.services.evaluation.evaluation_hook import trigger_auto_evaluation
from app.services.evaluation.formatter import material_to_text
from app.services.prompting.prompt.generate_content_service import material_service
from app.services.history.rag_history_service import RAGHistoryService

router = APIRouter()

# ── Endpoint: Generate Content (Simpan ke Database) ───────────────────────────

@router.post("/generate", response_model=MaterialResponse)
async def create_material(payload: MaterialRequest, db: Session = Depends(get_db)):
    """
    Generate legal material dari context tanpa audio processing.
    Hasil otomatis disimpan ke database RAG history.
    """
    result = await material_service.generate_legal_material(payload)
    
    # Buat session_title otomatis
    session_title = f"Generate {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    
    # Simpan ke history dengan signature yang benar
    history_id = RAGHistoryService.save_history(
        db=db,
        session_title=session_title,
        knowledge_base="default_kb",
        provider="direct_generation",
        raw_transcribe=payload.user_scenario,
        repaired_text=payload.user_scenario,
        search_query=payload.user_scenario,
        retrieved_context=payload.context_text,
        final_material=result
    )
    
    if history_id:
        print(f"✓ Data generate berhasil disimpan dengan history_id: {history_id}")
    else:
        print(f"✗ GAGAL menyimpan data generate ke database!")
    
    return result


# ── Endpoint: Generate + Evaluasi Otomatis ───────────────────────────────────

@router.post(
    "/generate-with-eval",
    response_model=MaterialResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate Legal Material (dengan evaluasi otomatis di background)",
    description="""
    Generate material hukum dengan evaluasi RAGAS otomatis berjalan di background.
    
    **Metrik yang dievaluasi:**
    - Faithfulness
    - Answer Relevancy
    - Context Precision *(jika ground truth tersedia)*
    - Context Recall *(jika ground truth tersedia)*
    """,
)
async def create_material_with_evaluation(
    payload: MaterialRequest,
    db: Session = Depends(get_db),
    background_tasks: BackgroundTasks = None,
):
    """
    Args:
        payload.context_text  : Teks konteks hukum yang di-retrieve
        payload.user_scenario : Skenario / pertanyaan user
        background_tasks      : Untuk menjalankan evaluasi di background

    Returns:
        MaterialResponse — hasil generate material.
        Evaluasi RAGAS berjalan otomatis di background setelah response dikirim.
    """
    try:
        # Generate material
        result = await material_service.generate_legal_material(payload)
        
        # Buat session_title otomatis
        session_title = f"Generate+Eval {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        # Simpan ke history
        history_id = RAGHistoryService.save_history(
            db=db,
            session_title=session_title,
            knowledge_base="default_kb",
            provider="direct_generation",
            raw_transcribe=payload.user_scenario,
            repaired_text=payload.user_scenario,
            search_query=payload.user_scenario,
            retrieved_context=payload.context_text,
            final_material=result
        )
        
        # Trigger evaluasi di background (jika history_id berhasil dibuat)
        if history_id and background_tasks:
            background_tasks.add_task(
                trigger_auto_evaluation,
                question=payload.user_scenario,
                context=payload.context_text,
                material=result,
                ground_truth=None,
                source_label="direct_generation",
                history_id=history_id
            )
            print(f"✓ Evaluasi RAGAS dijadwalkan di background untuk history_id: {history_id}")
        
        return result
        
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Gagal generate material: {str(exc)}",
        )