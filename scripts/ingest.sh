#!/usr/bin/env bash
# 문서 인덱싱 재실행
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

# shellcheck disable=SC1091
source "$PROJECT_DIR/scripts/_lib.sh"

[[ -d .venv ]] || fail ".venv 없음. ./scripts/setup.sh 먼저 실행"
# shellcheck disable=SC1091
source .venv/bin/activate

require_container_cli
ensure_qdrant

step "인덱싱 시작 (data/docs/*.md)"
cd app
python ingest.py
