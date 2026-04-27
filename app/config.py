"""환경변수 및 설정 로딩"""
import os
import shlex
from pathlib import Path

from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
load_dotenv(PROJECT_DIR / ".env")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

_allowed_raw = os.getenv("TELEGRAM_ALLOWED_USER_IDS", "").strip()
TELEGRAM_ALLOWED_USER_IDS: set[int] = (
    {int(x) for x in _allowed_raw.split(",") if x.strip().isdigit()}
    if _allowed_raw
    else set()
)

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "company_docs")

# 로컬 임베딩 모델 (HuggingFace에서 자동 다운로드, 1회성)
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "1024"))

# 리랭커 (cross-encoder, 로컬, ~570MB 최초 다운로드)
RERANKER_ENABLED = os.getenv("RERANKER_ENABLED", "true").lower() == "true"
RERANKER_MODEL = os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")

# LLM CLI 설정 (API 키 대신 codex / claude / gemini 등 로그인된 CLI 사용)
LLM_CLI = os.getenv("LLM_CLI", "codex")
LLM_CLI_ARGS = shlex.split(os.getenv("LLM_CLI_ARGS", "exec"))
LLM_CLI_TIMEOUT = int(os.getenv("LLM_CLI_TIMEOUT", "180"))

DOCS_DIR = os.getenv("DOCS_DIR", str(PROJECT_DIR / "data" / "docs"))

# 자동 인덱싱: data/docs/ 변경 시 watchdog 으로 증분 재인덱싱
WATCHER_ENABLED = os.getenv("WATCHER_ENABLED", "true").lower() == "true"

# Retrieval & rerank 파라미터
# - RETRIEVE_K: Qdrant 가 1차로 가져오는 후보 수 (리랭커 입력)
# - TOP_K     : 리랭커가 골라 최종적으로 LLM 에 넘기는 청크 수 (리랭커 OFF 시엔 이 값으로 직접 검색)
RETRIEVE_K = int(os.getenv("RETRIEVE_K", "20"))
TOP_K = int(os.getenv("TOP_K", "5"))
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
MAX_TELEGRAM_MESSAGE_LEN = 3900
