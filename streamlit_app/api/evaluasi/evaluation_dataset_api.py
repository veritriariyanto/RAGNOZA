"""
streamlit_app/api/evaluasi/evaluation_dataset_api.py

Client API untuk fitur Dataset Evaluation (golden dataset, kurasi manual).
Terpisah dari evaluation_api.py (evaluasi per-request) karena:
  - Endpoint backend berbeda (/evaluation-dataset/... vs /evaluation/...)
  - Siklus hidup data berbeda: dataset dibuat/dikelola dulu, baru dijalankan
    sebagai batch job (BackgroundTasks) — bukan submit-langsung-dapat-hasil
    seperti evaluasi per-request.

Pola error-handling mengikuti evaluation_api.py:
  - dict return: {"status": "success"/"error", ...}
  - connection/timeout ditangani eksplisit per fungsi
"""

import logging
import requests
from config.settings import settings

logger = logging.getLogger(__name__)

DATASET_URL = f"{settings.API_BASE_URL}/evaluation-dataset"


def _handle_response(response: requests.Response) -> dict:
    """Helper seragam untuk parse response sukses/gagal dari FastAPI."""
    if response.status_code in (200, 201):
        return {"status": "success", "data": response.json()}
    try:
        err_detail = response.json().get("detail", response.text)
    except Exception:
        err_detail = response.text
    return {
        "status": "error",
        "data": None,
        "error": f"Server error {response.status_code}: {err_detail}",
    }


def _handle_exception(exc: Exception) -> dict:
    if isinstance(exc, requests.exceptions.ConnectionError):
        return {"status": "error", "data": None, "error": "Backend evaluasi dataset tidak dapat dijangkau."}
    if isinstance(exc, requests.exceptions.Timeout):
        return {"status": "error", "data": None, "error": "Request timeout."}
    logger.error("[DatasetEvalAPI] Exception: %s", exc, exc_info=True)
    return {"status": "error", "data": None, "error": str(exc)}


# ── Dataset CRUD ─────────────────────────────────────────────────────────

def list_datasets() -> dict:
    """GET /evaluation-dataset/ — daftar semua dataset."""
    try:
        response = requests.get(f"{DATASET_URL}/", timeout=30)
        return _handle_response(response)
    except Exception as exc:
        return _handle_exception(exc)


def create_dataset(name: str, description: str | None = None) -> dict:
    """POST /evaluation-dataset/ — buat dataset baru."""
    try:
        payload = {"name": name, "description": description}
        response = requests.post(f"{DATASET_URL}/", json=payload, timeout=30)
        return _handle_response(response)
    except Exception as exc:
        return _handle_exception(exc)


# ── Dataset Items ────────────────────────────────────────────────────────

def list_items(dataset_id: int) -> dict:
    """GET /evaluation-dataset/{id}/items — daftar soal dalam dataset."""
    try:
        response = requests.get(f"{DATASET_URL}/{dataset_id}/items", timeout=30)
        return _handle_response(response)
    except Exception as exc:
        return _handle_exception(exc)


def add_items(dataset_id: int, items: list[dict]) -> dict:
    """
    POST /evaluation-dataset/{id}/items — tambah soal manual (tanpa CSV).

    items: list of dict, masing-masing berisi:
        question, ground_truth, reference_context, category (opsional), knowledge_base

    CATATAN: backend saat ini TIDAK menyimpan field knowledge_base pada endpoint ini
    (lihat evaluation_dataset_router.py -> add_items). Field tetap dikirim di sini
    agar konsisten dengan schema, tapi UI wajib menampilkan warning ke user.
    """
    try:
        payload = {"items": items}
        response = requests.post(f"{DATASET_URL}/{dataset_id}/items", json=payload, timeout=30)
        return _handle_response(response)
    except Exception as exc:
        return _handle_exception(exc)


# ── CSV Upload ───────────────────────────────────────────────────────────

def download_csv_template() -> dict:
    """GET /evaluation-dataset/csv-template — unduh template CSV kosong."""
    try:
        response = requests.get(f"{DATASET_URL}/csv-template", timeout=30)
        if response.status_code == 200:
            return {"status": "success", "content": response.content}
        return {"status": "error", "content": None, "error": f"Server error {response.status_code}"}
    except requests.exceptions.ConnectionError:
        return {"status": "error", "content": None, "error": "Backend evaluasi dataset tidak dapat dijangkau."}
    except requests.exceptions.Timeout:
        return {"status": "error", "content": None, "error": "Request timeout."}
    except Exception as exc:
        logger.error("[DatasetEvalAPI] download_csv_template exception: %s", exc, exc_info=True)
        return {"status": "error", "content": None, "error": str(exc)}


def upload_items_csv(dataset_id: int, file_bytes: bytes, filename: str) -> dict:
    """POST /evaluation-dataset/{id}/items/upload-csv — upload CSV bulk."""
    try:
        files = {"file": (filename, file_bytes, "text/csv")}
        response = requests.post(
            f"{DATASET_URL}/{dataset_id}/items/upload-csv",
            files=files,
            timeout=120,
        )
        return _handle_response(response)
    except Exception as exc:
        return _handle_exception(exc)


# ── Run ──────────────────────────────────────────────────────────────────

def trigger_run(dataset_id: int, label: str | None = None) -> dict:
    """POST /evaluation-dataset/{id}/run — mulai evaluasi dataset (async/background)."""
    try:
        payload = {"label": label}
        response = requests.post(f"{DATASET_URL}/{dataset_id}/run", json=payload, timeout=30)
        return _handle_response(response)
    except Exception as exc:
        return _handle_exception(exc)

def list_runs(dataset_id: int) -> dict:
    """GET /evaluation-dataset/{id}/runs — daftar riwayat run untuk suatu dataset."""
    try:
        response = requests.get(f"{DATASET_URL}/{dataset_id}/runs", timeout=30)
        return _handle_response(response)
    except Exception as exc:
        return _handle_exception(exc)

def get_run_report(run_id: int) -> dict:
    """GET /evaluation-dataset/runs/{run_id} — ambil laporan hasil run."""
    try:
        response = requests.get(f"{DATASET_URL}/runs/{run_id}", timeout=30)
        return _handle_response(response)
    except Exception as exc:
        return _handle_exception(exc)