"""문서 인덱싱 스크립트 (LangChain + 로컬 임베딩)

실행: python app/ingest.py  (또는 cd app && python ingest.py)
"""
import glob
import os

from langchain_community.document_loaders import TextLoader
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_qdrant import QdrantVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

from config import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    COLLECTION_NAME,
    DOCS_DIR,
    EMBEDDING_DIM,
    EMBEDDING_MODEL,
    QDRANT_URL,
)


def load_documents(docs_dir: str) -> list[Document]:
    files = sorted(glob.glob(f"{docs_dir}/*.md"))
    print(f"발견된 문서 {len(files)}개 (경로: {docs_dir})")
    documents: list[Document] = []
    for path in files:
        filename = os.path.basename(path)
        loader = TextLoader(path, encoding="utf-8")
        for doc in loader.load():
            doc.metadata["source"] = filename
            documents.append(doc)
    return documents


def split_documents(documents: list[Document]) -> list[Document]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", "。", ". ", " ", ""],
        length_function=len,
    )
    chunks = splitter.split_documents(documents)
    print(f"생성된 청크 {len(chunks)}개")
    return chunks


def main():
    qdrant = QdrantClient(url=QDRANT_URL)
    if qdrant.collection_exists(COLLECTION_NAME):
        qdrant.delete_collection(COLLECTION_NAME)
    qdrant.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
    )

    documents = load_documents(DOCS_DIR)
    if not documents:
        print(f"[경고] {DOCS_DIR} 안에 .md 파일이 없습니다.")
        return
    chunks = split_documents(documents)

    print(f"임베딩 모델 로드 중: {EMBEDDING_MODEL} (최초 1회 다운로드, 수백 MB)")
    embeddings = HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )
    vectorstore = QdrantVectorStore(
        client=qdrant,
        collection_name=COLLECTION_NAME,
        embedding=embeddings,
    )
    vectorstore.add_documents(chunks)
    print(f"\n총 {len(chunks)}개 청크 적재 완료 (collection={COLLECTION_NAME})")


if __name__ == "__main__":
    main()
