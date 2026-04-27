#!/usr/bin/env bash
# Telegram 봇 기동 (포그라운드)
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

# shellcheck disable=SC1091
source "$PROJECT_DIR/scripts/_lib.sh"

[[ -d .venv ]] || fail ".venv 없음. ./scripts/setup.sh 먼저 실행"
[[ -f .env ]]  || fail ".env 없음."
command -v codex >/dev/null 2>&1 || fail "codex CLI 미설치"

# shellcheck disable=SC1091
source .venv/bin/activate

require_container_cli
ensure_qdrant

# 컬렉션 존재 확인
if ! curl -sf http://localhost:6333/collections | grep -q "company_docs"; then
  warn "company_docs 컬렉션이 비어있을 수 있습니다. ./scripts/ingest.sh 실행 권장."
fi

step "Telegram 봇 시작 (Ctrl+C 로 종료)"
exec python app/main.py
