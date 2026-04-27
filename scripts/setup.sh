#!/usr/bin/env bash
# 1회성 부트스트랩 (idempotent)
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

# shellcheck disable=SC1091
source "$PROJECT_DIR/scripts/_lib.sh"

step "프로젝트 디렉토리: $PROJECT_DIR"

# 1) .env
[[ -f .env ]] || fail ".env 파일이 없습니다. cp .env.example .env 후 토큰 작성 필요"
ok ".env 존재"

# 2) codex CLI
command -v codex >/dev/null 2>&1 || fail "codex CLI 가 PATH 에 없습니다."
ok "codex: $(codex --version 2>/dev/null | head -1)"

# 3) Container CLI (docker / podman 자동감지)
require_container_cli

# 4) Python venv
step "Python 가상환경 준비"
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
  ok "venv 생성"
else
  ok "venv 이미 존재"
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip --quiet
ok "pip 최신화"

step "패키지 설치 (sentence-transformers/torch 포함, 5~10분 소요)"
pip install -r app/requirements.txt
ok "패키지 설치 완료"

# 5) Qdrant
ensure_qdrant

cat <<'EOF'

────────────────────────────────────────────
 다음 단계
────────────────────────────────────────────
 1) codex login              # 아직 안 했으면 (브라우저 열려 ChatGPT 인증)
 2) ./scripts/ingest.sh      # 사내 문서 인덱싱 (BGE-M3 최초 다운로드 ~600MB)
 3) ./scripts/run.sh         # 봇 기동
EOF
