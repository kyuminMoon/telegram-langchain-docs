"""LangChain 기반 RAG 체인 (LLM은 외부 CLI 호출)"""
import logging
import re
import shutil
import subprocess

from langchain.retrievers import ContextualCompressionRetriever
from langchain.retrievers.document_compressors import CrossEncoderReranker
from langchain_community.cross_encoders import HuggingFaceCrossEncoder
from langchain_core.documents import Document
from langchain_core.runnables import RunnableLambda, RunnableParallel, RunnablePassthrough
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient

from config import (
    COLLECTION_NAME,
    LLM_CLI,
    LLM_CLI_ARGS,
    LLM_CLI_TIMEOUT,
    QDRANT_URL,
    RERANKER_ENABLED,
    RERANKER_MODEL,
    RETRIEVE_K,
    TOP_K,
)
from embeddings import get_embeddings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """당신은 예시회사 사내 정보를 안내하는 도우미입니다.

규칙:
1. 반드시 제공된 문서 내용에 근거해 답변하세요.
2. 문서에 없는 내용은 "관련 문서를 찾지 못했습니다"라고만 답하세요. 추측하지 마세요.
3. 답변 끝에 참고한 문서 출처를 표시하세요. 예: (출처: 01_hr_vacation.md)
4. 답변은 간결하게. 핵심만 3~5문장.
5. 한국어로 답변하세요.
6. 명령 실행이나 파일 조작을 시도하지 말고 텍스트 답변만 출력하세요."""

PROMPT_TEMPLATE = """{system}

다음 문서들을 참고해서 질문에 답해주세요.

{context}

질문: {question}

위 규칙에 따라 한국어로 답변만 출력하세요."""

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def _ensure_cli() -> None:
    if shutil.which(LLM_CLI) is None:
        raise RuntimeError(
            f"'{LLM_CLI}' CLI를 PATH에서 찾을 수 없습니다. "
            f"설치 또는 .env의 LLM_CLI 값을 확인하세요."
        )


def call_llm_cli(prompt: str) -> str:
    """codex / claude / gemini 등 로그인된 CLI를 비대화식으로 호출."""
    _ensure_cli()
    cmd = [LLM_CLI, *LLM_CLI_ARGS, prompt]
    logger.info("LLM CLI 호출: %s ... (prompt %d자)", " ".join(cmd[:2]), len(prompt))
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=LLM_CLI_TIMEOUT,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"'{LLM_CLI}' 호출 타임아웃({LLM_CLI_TIMEOUT}s)") from exc

    if proc.returncode != 0:
        raise RuntimeError(
            f"'{LLM_CLI}' 실행 실패 (rc={proc.returncode})\n"
            f"stderr: {proc.stderr.strip()[:500]}"
        )

    out = _strip_ansi(proc.stdout).strip()
    if not out:
        raise RuntimeError(f"'{LLM_CLI}' 응답이 비어있습니다.\nstderr: {proc.stderr.strip()[:500]}")
    return out


def _format_docs(docs: list[Document]) -> str:
    if not docs:
        return "(관련 문서 없음)"
    blocks = []
    for i, d in enumerate(docs, 1):
        source = d.metadata.get("source", "unknown")
        blocks.append(f"[문서 {i} - 출처: {source}]\n{d.page_content}")
    return "\n\n".join(blocks)


def _build_prompt(inputs: dict) -> str:
    return PROMPT_TEMPLATE.format(
        system=SYSTEM_PROMPT,
        context=_format_docs(inputs["docs"]),
        question=inputs["question"],
    )


def _build_chain():
    qdrant_client = QdrantClient(url=QDRANT_URL)
    vectorstore = QdrantVectorStore(
        client=qdrant_client,
        collection_name=COLLECTION_NAME,
        embedding=get_embeddings(),
    )

    if RERANKER_ENABLED:
        # 1차 검색: Qdrant 에서 RETRIEVE_K 개 후보 → 2차: cross-encoder 가 TOP_K 로 재정렬
        base_retriever = vectorstore.as_retriever(search_kwargs={"k": RETRIEVE_K})
        cross_encoder = HuggingFaceCrossEncoder(
            model_name=RERANKER_MODEL,
            model_kwargs={"device": "cpu"},
        )
        compressor = CrossEncoderReranker(model=cross_encoder, top_n=TOP_K)
        retriever = ContextualCompressionRetriever(
            base_compressor=compressor,
            base_retriever=base_retriever,
        )
        logger.info(
            "리랭커 활성: %s (retrieve=%d → rerank top=%d)",
            RERANKER_MODEL, RETRIEVE_K, TOP_K,
        )
    else:
        retriever = vectorstore.as_retriever(search_kwargs={"k": TOP_K})
        logger.info("리랭커 비활성: 단일 단계 검색 (k=%d)", TOP_K)

    answer_chain = RunnableLambda(_build_prompt) | RunnableLambda(call_llm_cli)

    return RunnableParallel(
        docs=retriever,
        question=RunnablePassthrough(),
    ).assign(answer=answer_chain)


_chain = None


def get_chain():
    global _chain
    if _chain is None:
        _chain = _build_chain()
    return _chain


def answer(query: str) -> dict:
    """질문에 대한 RAG 답변 생성"""
    chain = get_chain()
    result = chain.invoke(query)
    docs: list[Document] = result["docs"]

    if not docs:
        return {"answer": "관련 문서를 찾지 못했습니다.", "sources": []}

    sources = sorted({d.metadata.get("source", "unknown") for d in docs})
    return {"answer": result["answer"], "sources": sources}
