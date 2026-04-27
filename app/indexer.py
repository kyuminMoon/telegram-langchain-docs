"""증분 인덱싱: 단일 source 단위 delete + add (전체 재생성 X)"""
import logging
import os
import re
import threading
from pathlib import Path

from langchain_core.documents import Document
from langchain_qdrant import QdrantVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    VectorParams,
)

from config import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    COLLECTION_NAME,
    EMBEDDING_DIM,
    QDRANT_URL,
)
from embeddings import get_embeddings

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_vs: QdrantVectorStore | None = None

_splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    separators=["\n\n", "\n", "。", ". ", " ", ""],
    length_function=len,
)

_FILENAME_RE = re.compile(r"[^\w\-. ]")


def safe_filename(raw: str) -> str:
    """경로 traversal / 특수문자 제거. .md 가 아니면 빈 문자열 반환."""
    name = os.path.basename(raw or "")
    name = _FILENAME_RE.sub("", name).replace(" ", "_")
    if not name.endswith(".md"):
        return ""
    return name


def _qdrant() -> QdrantClient:
    return QdrantClient(url=QDRANT_URL)


def _ensure_collection(client: QdrantClient) -> None:
    if not client.collection_exists(COLLECTION_NAME):
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
        )


def _vectorstore() -> QdrantVectorStore:
    global _vs
    if _vs is None:
        client = _qdrant()
        _ensure_collection(client)
        _vs = QdrantVectorStore(
            client=client,
            collection_name=COLLECTION_NAME,
            embedding=get_embeddings(),
        )
    return _vs


def delete_source(source: str) -> int:
    """metadata.source == source 인 청크 모두 제거. 삭제 추정 개수 반환."""
    if not source:
        return 0
    with _lock:
        client = _qdrant()
        if not client.collection_exists(COLLECTION_NAME):
            return 0
        flt = Filter(
            must=[FieldCondition(
                key="metadata.source",
                match=MatchValue(value=source),
            )],
        )
        try:
            count_before = client.count(
                COLLECTION_NAME, count_filter=flt, exact=True,
            ).count
        except Exception:
            count_before = -1
        client.delete(collection_name=COLLECTION_NAME, points_selector=flt)
        logger.info("delete_source: %s (≈%d 청크 제거)", source, count_before)
        return count_before


def reindex_source_text(source: str, text: str) -> int:
    """source(파일명) + 본문 → 기존 청크 delete + 새 청크 add. 추가된 청크 수 반환."""
    safe = safe_filename(source)
    if not safe:
        raise ValueError(f"잘못된 파일명: {source!r}")

    delete_source(safe)

    if not text.strip():
        logger.info("reindex_source_text: %s 본문 비어있음, 추가 없음", safe)
        return 0

    docs = [Document(page_content=text, metadata={"source": safe})]
    chunks = _splitter.split_documents(docs)
    if not chunks:
        return 0

    with _lock:
        _vectorstore().add_documents(chunks)
    logger.info("reindex_source_text: %s (%d 청크 적재)", safe, len(chunks))
    return len(chunks)


def reindex_path(path: str) -> int:
    """파일 한 개를 (재)인덱싱."""
    p = Path(path)
    if not p.exists() or not p.is_file():
        raise FileNotFoundError(path)
    text = p.read_text(encoding="utf-8")
    return reindex_source_text(p.name, text)
