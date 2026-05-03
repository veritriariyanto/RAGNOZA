from app.core.qdrant import qdrant_db
from app.services.rag_logic import llm, embeddings

def get_answer_from_rag(prompt: str, collection_name: str):
    # 1. Ubah pertanyaan user menjadi vektor
    query_vector = embeddings.embed_query(prompt)

    # 2. Cari konteks paling relevan di Qdrant
    search_results = qdrant_db.client.query_points(
    collection_name=collection_name,
    query=query_vector,
    limit=3
    ).points

    # 3. Gabungkan konteks untuk LLM
    context = ""
    sources = []
    for res in search_results:
        context += f"\n{res.payload['isi_teks']}\n"
        sources.append({
            "pasal": res.payload.get("pasal"),
            "bab": res.payload.get("bab"),
            "score": res.score # Tingkat kemiripan
        })

    # 4. Susun System Prompt agar LLM patuh pada aturan hukum
    system_prompt = f"""
    Anda adalah Pakar Hukum Konstitusi Indonesia yang ahli dalam UUD 1945.
    Tugas Anda adalah menjawab pertanyaan user berdasarkan KONTEKS yang diberikan.
    
    Aturan:
    - Jawab hanya berdasarkan KONTEKS yang disediakan.
    - Jika jawaban tidak ada dalam konteks, katakan: "Maaf, informasi tersebut tidak ditemukan dalam dokumen UUD ini."
    - Sebutkan Pasal yang menjadi referensi jawaban Anda.

    KONTEKS:
    {context}

    PERTANYAAN:
    {prompt}
    """

    # 5. Dapatkan jawaban dari Groq
    response = llm.invoke(system_prompt)
    
    return {
        "answer": response.content,
        "sources": sources
    }