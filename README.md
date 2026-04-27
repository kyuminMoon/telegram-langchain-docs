# Telegram RAG Bot

> Public repo note: commit `.env.example`, sample docs, and source code only. Do not commit `.env`, logs, virtualenvs, generated Qdrant storage, or real internal documents. See `PUBLICATION_CHECKLIST.md`.


API 키 없이 동작하는 사내 문서 RAG 챗봇.
**로그인된 `codex` CLI** 와 **로컬 임베딩 + 리랭커** 로 LLM·임베딩 비용 0, 외부 API 의존 0 (Telegram 토큰 외).

## 구성

| 영역 | 기술 | 비고 |
|---|---|---|
| 메신저 | Telegram (`python-telegram-bot` 21.7, long polling) | 슬래시 커맨드 + 일반 텍스트 + .md 파일 첨부 |
| 오케스트레이션 | LangChain LCEL (`ContextualCompressionRetriever`) | LangGraph 미사용 |
| 임베딩 | 로컬 `BAAI/bge-m3` (sentence-transformers, 1024 dim) | 한국어 품질 우수 |
| **리랭커** | 로컬 `BAAI/bge-reranker-v2-m3` (cross-encoder) | retrieve 20 → rerank top-5 |
| 벡터 DB | Qdrant 1.12.1 (Podman 컨테이너) | Cosine distance |
| **자동 인덱싱** | watchdog + Telegram document handler | 폴더 변경 / 채팅 첨부 시 즉시 반영 |
| LLM | `codex exec --skip-git-repo-check` (subprocess) | ChatGPT 인증, API 키 X |
| 런타임 | macOS Apple Silicon + Python 3.14 venv | 봇은 호스트 네이티브, Qdrant만 컨테이너 |

## 디렉터리

```
telegram-langchain-docs/
├── docker-compose.yml          # Qdrant 1개 서비스 (podman compose 호환)
├── .env                        # 토큰·LLM_CLI·리랭커 설정 (gitignore)
├── .env.example
├── .gitignore
├── README.md
├── docs/
│   └── ARCHITECTURE.md         # 다이어그램 포함 상세 설계 문서
├── scripts/
│   ├── _lib.sh                 # docker/podman 자동감지 + DOCKER_HOST 보정
│   ├── setup.sh                # 1회성 부트스트랩
│   ├── ingest.sh               # 수동 인덱싱 (전체 재생성)
│   ├── run.sh                  # 봇 기동
│   └── stop.sh                 # 봇 종료
├── app/
│   ├── main.py                 # 진입점 (Python 3.14 asyncio fix)
│   ├── bot.py                  # 텔레그램 핸들러 + 첨부파일 + watcher 라이프사이클
│   ├── rag.py                  # LCEL + 리랭커 + codex subprocess
│   ├── embeddings.py           # BGE-M3 싱글톤
│   ├── indexer.py              # 증분 인덱싱 (source 단위 delete + add)
│   ├── watcher.py              # watchdog Observer
│   ├── ingest.py               # 전체 재생성 (수동 1회용)
│   ├── config.py               # .env 로딩
│   └── requirements.txt
├── data/
│   ├── docs/                   # 사내 마크다운 (자동 인덱싱 대상)
│   └── qdrant_storage/         # Qdrant 볼륨
└── tests/
    └── scenarios.md            # 테스트 시나리오
```

## 사전 준비

### 1. codex CLI 설치 & 로그인

```bash
npm install -g @openai/codex      # 또는 brew install codex
codex login                       # 브라우저로 ChatGPT 인증
codex exec "ping"                 # 동작 확인 (응답 받으면 OK)
```

> codex 대신 `claude -p` / `gemini -p` 도 사용 가능. `.env` 의 `LLM_CLI` / `LLM_CLI_ARGS` 만 변경.

### 2. Telegram 봇 등록

1. Telegram 에서 **@BotFather** → `/newbot` → 이름 + username 입력
2. 발급된 **HTTP API token** 을 `.env` 의 `TELEGRAM_BOT_TOKEN` 에 입력
3. (선택) 본인 user id 는 **@userinfobot** 에 메시지 보내면 확인 → `TELEGRAM_ALLOWED_USER_IDS` 에 등록

### 3. Docker 또는 Podman 머신 동작

```bash
# Docker Desktop 사용 시 그냥 켜두면 됨
# Podman 사용 시
podman machine start
```

스크립트가 자동으로 docker/podman 감지하고 DOCKER_HOST 까지 맞춰줍니다.

## 빠른 시작

```bash
cd ~/telegram-langchain-docs

# 1) .env 작성
cp .env.example .env
# 에디터로 열어 TELEGRAM_BOT_TOKEN 만 입력 (나머지는 기본값 OK)

# 2) 부트스트랩 (venv·pip·Qdrant 일괄)
./scripts/setup.sh                       # 5~10분 (sentence-transformers/torch ~1.5GB 다운로드)

# 3) 초기 문서 인덱싱
./scripts/ingest.sh                      # BGE-M3 ~600MB 최초 다운로드

# 4) 봇 기동
./scripts/run.sh                         # 포그라운드 (Ctrl+C 종료)
nohup ./scripts/run.sh > bot.log 2>&1 & disown   # 백그라운드

# 봇 정지
./scripts/stop.sh
```

기동 시 콘솔 또는 `bot.log` 에 `봇 준비 완료: @봇이름 (id=...)` + `watcher 시작: .../data/docs 감시 중` 메시지가 보이면 OK.

## 일상 사용법

### 질문하기

[t.me/yourbot](https://t.me/) 봇과의 채팅창에서:

```
/ask 신입사원 연차 며칠이야?
또는 그냥
신입사원 연차 며칠이야?
```

### 문서 추가/수정/삭제 (자동 인덱싱)

#### 방법 A — 폴더에 `.md` 파일 떨어뜨리기

```bash
cp ~/새문서.md ~/telegram-langchain-docs/data/docs/06_xxx.md
# → 2초 debounce 후 watcher 가 자동 인덱싱
# bot.log 에 "watcher: 06_xxx.md 재인덱싱 (N 청크)" 출력
```

수정·삭제도 동일하게 자동 반영.

#### 방법 B — Telegram 채팅에 `.md` 첨부

```
[사용자]   📎 06_security_policy.md  업로드
[봇]      ✓ 06_security_policy.md 인덱싱 완료 (3 청크)
```

`safe_filename()` 로 sanitize (한글 OK, 공백 → `_`, 경로 traversal 차단).

#### 수동 일괄 재생성 (선택)

대량 변경 후 컬렉션을 통째로 다시 만들고 싶을 때:

```bash
./scripts/ingest.sh
```

이건 **delete + recreate** 방식이라 모든 청크가 다시 임베딩됩니다.

## 환경변수

| 키 | 필수 | 기본값 | 용도 |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | ✓ | — | BotFather 발급 토큰 |
| `TELEGRAM_ALLOWED_USER_IDS` | 선택 | (전체 허용) | 콤마 구분 user id 화이트리스트 |
| `QDRANT_URL` | 선택 | `http://localhost:6333` | Qdrant 엔드포인트 |
| `COLLECTION_NAME` | 선택 | `company_docs` | Qdrant 컬렉션명 |
| `LLM_CLI` | 선택 | `codex` | LLM CLI 실행파일 (codex / claude / gemini) |
| `LLM_CLI_ARGS` | 선택 | `exec --skip-git-repo-check` | 공백 구분 인자 |
| `LLM_CLI_TIMEOUT` | 선택 | `180` | CLI 호출 타임아웃(s) |
| `EMBEDDING_MODEL` | 선택 | `BAAI/bge-m3` | HuggingFace 임베딩 모델 |
| `EMBEDDING_DIM` | 선택 | `1024` | 모델 차원 (변경 시 컬렉션 재생성 필요) |
| `RERANKER_ENABLED` | 선택 | `true` | `false` → 단일 검색으로 fallback |
| `RERANKER_MODEL` | 선택 | `BAAI/bge-reranker-v2-m3` | HuggingFace cross-encoder |
| `RETRIEVE_K` | 선택 | `20` | 1차 검색 후보 수 (rerank 입력) |
| `TOP_K` | 선택 | `5` | 최종 LLM 입력 청크 수 |
| `WATCHER_ENABLED` | 선택 | `true` | `false` → 폴더 자동 감시 끔 |

## 검증 명령

```bash
# 컨테이너 상태
docker compose ps               # Docker
podman ps                       # Podman

# Qdrant 응답 + 적재된 청크 개수
curl -s http://localhost:6333/collections/company_docs | python3 -m json.tool | grep points_count

# source 별 청크 개수
curl -s -X POST http://localhost:6333/collections/company_docs/points/scroll \
  -H 'Content-Type: application/json' \
  -d '{"limit":50,"with_payload":true,"with_vector":false}' \
  | python3 -c "
import sys,json
from collections import Counter
ps = json.load(sys.stdin)['result']['points']
for s,n in sorted(Counter(p['payload']['metadata']['source'] for p in ps).items()):
    print(f'  {s}: {n}')"

# 봇 로그 (리랭커/watcher 활성 메시지)
grep -E "리랭커|watcher|reindex" bot.log | tail

# codex CLI 동작
codex exec "ping" 2>&1 | head
```

## 디버깅

| 증상 | 확인 |
|---|---|
| `codex CLI를 PATH에서 찾을 수 없습니다` | `which codex` / `npm i -g @openai/codex` |
| `codex 실행 실패 (rc=...)` | `codex login` 재실행, 직접 `codex exec "test"` 동작 검증 |
| `Not inside a trusted directory` | `.env` 의 `LLM_CLI_ARGS` 에 `--skip-git-repo-check` 포함됐는지 확인 |
| `RuntimeError: There is no current event loop` | Python 3.14 이슈. `app/main.py` 에 `asyncio.set_event_loop(asyncio.new_event_loop())` 적용 확인 |
| `docker info` 가 서브쉘에서 실패 | `docker` 가 zsh alias `=podman` 인 환경. `_lib.sh` 가 자동 감지 → 안 되면 `podman machine start` |
| `unable to get image ... podman.sock` | `_lib.sh` 가 `DOCKER_HOST` 보정. 안 될 시 `podman machine inspect --format '{{.ConnectionInfo.PodmanSocket.Path}}'` 결과를 `DOCKER_HOST=unix://<path>` 로 export |
| 봇이 메시지에 무응답 (그룹) | BotFather `/setprivacy` Disable 또는 1:1 채팅 사용 |
| 검색 결과가 이상함 | `http://localhost:6333/dashboard` 직접 확인 |
| 응답이 너무 느림 | `RERANKER_ENABLED=false` 로 단순화 / `TOP_K` 축소 / `LLM_CLI=claude` 로 교체 |
| watcher 가 동작 안 함 | `WATCHER_ENABLED=true` 확인, `bot.log` 에 `watcher 시작: ...` 메시지 있는지 |

## 다른 CLI 로 LLM 교체

`.env` 두 줄만 수정 후 봇 재시작:

```bash
# Claude Code CLI
LLM_CLI=claude
LLM_CLI_ARGS=-p

# Gemini CLI
LLM_CLI=gemini
LLM_CLI_ARGS=-p

# Ollama 로컬
LLM_CLI=ollama
LLM_CLI_ARGS=run qwen2.5:7b
```

CLI 마다 사전 인증 (`<cli> login`) 또는 모델 다운로드가 끝나 있어야 합니다.

## 확장 (이번 빌드 이후)

| 신호 | 작업 |
|---|---|
| ✅ 검색 결과 관련성 부족 | **이번에 BGE-Reranker 추가됨** |
| ✅ 자동 인덱싱 필요 | **이번에 watchdog + Telegram 첨부 추가됨** |
| 대화 이력 필요 | `chat_id` 기준 SQLite 저장 → 프롬프트에 전 메시지 포함 |
| 분기 흐름 (검색→판단→재검색→도구) | LangGraph `StateGraph` 로 `rag.py` 재작성 |
| PDF / Word / Confluence 등 | `app/ingest.py` 와 `app/indexer.py` 의 로더만 교체 |
| 대량 문서 수천 개+ | 청크 ID stable hashing → 증분 upsert, Qdrant payload index |

## 더 자세한 문서

- **`docs/CONCEPTS.md`** — 초심자용. RAG / LangChain / LangGraph / 임베딩 / 리랭커 / 오케스트레이션 개념을 비유와 함께 설명, Spring AI 와의 비교 포함
- **`docs/ARCHITECTURE.md`** — 컴포넌트/시퀀스/핸들러 mermaid 다이어그램, 데이터 모델, 환경 의존성 우회 사례, 자동 인덱싱 상세
- **`tests/scenarios.md`** — Telegram 채팅에서 직접 돌려볼 테스트 시나리오
