# app/core/reranker.py

from sentence_transformers import CrossEncoder

# Cross-encoder multilingual (dilatih di mMARCO, termasuk Bahasa Indonesia).
# Beda dari embeddings bi-encoder: query & dokumen diproses BERSAMA dalam satu
# forward pass, jadi jauh lebih akurat menilai relevansi topikal — dipakai
# untuk re-rank kandidat hasil pencarian Qdrant, bukan pengganti pencarian awal.
reranker = CrossEncoder("cross-encoder/mmarco-mMiniLMv2-L12-H384-v1")
