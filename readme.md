### Versi Markdown untuk `README.md`

````markdown
# AI RAG UUD Decision Support System 🏛️

Sistem Penunjang Keputusan berbasis AI yang menggunakan metode **Retrieval-Augmented Generation (RAG)** untuk memberikan analisis hukum berdasarkan UUD 1945. Sistem ini menggunakan **FastAPI**, **Qdrant** sebagai Vector Database, **PostgreSQL** untuk data relasional, dan **Groq (Llama 3 70B)** sebagai mesin penalaran utama.

## 🛠️ Tech Stack

- **Backend:** FastAPI
- **AI Engine:** Groq API (Llama3-70b-8192)
- **Vector DB:** Qdrant
- **RDBMS:** PostgreSQL (via Laragon/Docker)
- **Framework:** LangChain

## 🚀 Persiapan Awal

### 1. Clone Repository

```bash
git clone <repository-url>
cd rag-uud
```
````

### 2\. Setup Virtual Environment

Disarankan menggunakan Python 3.10 ke atas.

**Windows:**

```bash
python -m venv venv
venv\Scripts\activate
```

**Linux/Mac:**

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3\. Instalasi Dependensi

```bash
pip install -r requirements.txt
```

## ⚙️ Konfigurasi Environment

Buat file `.env` di root folder dan sesuaikan dengan pengaturan lokal Anda (khususnya untuk database Laragon):

```env
PROJECT_NAME="RAG UUD Decision Support"

# Database PostgreSQL (Docker Default)
PGHOST=localhost
PGPORT=5432
PGDATABASE=aitta_db
PGUSER=postgres
PGPASSWORD=
PGSSLMODE=disable

# Vector Database
QDRANT_HOST=localhost
QDRANT_PORT=6333

# AI & Groq
GROQ_API_KEY=gsk_your_api_key_here

# AI service keys
ELEVENLABS_API_KEY=api_key_here
OPENROUTER_API_KEY=

# Service URLs
EVALUATOR_URL=http://evaluator:8001
EVALUATOR_TIMEOUT_SECONDS=900

# Evaluator models
EVALUATOR_LLM_MODEL=llama-3.1-8b-instant
EVALUATOR_LLM_TEMPERATURE=0.0
RAGAS_LLM_MODEL=llama-3.3-70b-versatile
RAGAS_LLM_TEMPERATURE=0.0
EVALUATOR_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
EVALUATOR_EMBEDDING_DEVICE=cpu
LOG_LEVEL=INFO

# Evaluator throttling
GROQ_TPM_LIMIT=4500
GROQ_MIN_GAP_SEC=1.2
GROQ_TPD_LIMIT=90000
GROQ_RPD_LIMIT=1000
```

## 🗄️ Persiapan Database

1.  **PostgreSQL:**
    - Buka Laragon.
    - Pastikan PostgreSQL sudah aktif.
    - Buat database baru dengan nama `aitta_db` melalui Terminal Laragon (`psql -U postgres -c "CREATE DATABASE aitta_db;"`).

2.  **Qdrant:**
    - Pastikan Qdrant sudah berjalan (biasanya via Docker: `docker run -p 6333:6333 qdrant/qdrant`).

## 🏃 Menjalankan Aplikasi

Jalankan server FastAPI menggunakan Uvicorn:

```bash
uvicorn app.main:app --reload
```

Aplikasi akan berjalan di: [http://127.0.0.1:8000](https://www.google.com/search?q=http://127.0.0.1:8000)
Dokumentasi API (Swagger UI): [http://127.0.0.1:8000/docs](https://www.google.com/search?q=http://127.0.0.1:8000/docs)

## 📁 Struktur Folder

- `app/core/`: Pengaturan sistem dan environment.
- `app/database/`: Modul koneksi PostgreSQL & Qdrant.
- `app/services/`: Logika utama RAG, integrasi Groq, dan pemrosesan dokumen.
- `data/`: Tempat menyimpan dokumen UUD (PDF/TXT) untuk proses indexing.

## 📝 Catatan Git Flow

Proyek ini mengikuti standar **Git Flow**:

- `production` (main): Branch stabil untuk live environment.
- `staging`: Branch untuk QA & testing final.
- `development`: Branch integrasi fitur.
- `feature/*`: Pengembangan fitur baru (misal: `feature/rag-engine`).
