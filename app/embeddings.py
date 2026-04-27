"""공유 BGE-M3 임베딩 싱글톤 (rag.py + indexer.py 가 같이 사용)"""
from langchain_huggingface import HuggingFaceEmbeddings

from config import EMBEDDING_MODEL

_emb: HuggingFaceEmbeddings | None = None


def get_embeddings() -> HuggingFaceEmbeddings:
    global _emb
    if _emb is None:
        _emb = HuggingFaceEmbeddings(
            model_name=EMBEDDING_MODEL,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
    return _emb
