# shellcheck shell=bash
# 공통 헬퍼: container CLI 자동감지 등

step() { printf "\n\033[1;36m==> %s\033[0m\n" "$*"; }
ok()   { printf "\033[1;32m  ✓ %s\033[0m\n" "$*"; }
warn() { printf "\033[1;33m  ! %s\033[0m\n" "$*"; }
fail() { printf "\033[1;31m  ✗ %s\033[0m\n" "$*"; exit 1; }

# 호스트 셸 alias 가 docker=podman 인 경우를 처리.
# bash 서브쉘에는 alias 가 상속되지 않으므로 실제 바이너리를 찾아 동작 가능한 것을 선택.
detect_container_cli() {
  if command -v docker >/dev/null 2>&1 \
     && docker info >/dev/null 2>&1; then
    echo "docker"
    return 0
  fi
  if command -v podman >/dev/null 2>&1 \
     && podman info >/dev/null 2>&1; then
    echo "podman"
    return 0
  fi
  return 1
}

require_container_cli() {
  CONTAINER_CLI="$(detect_container_cli)" || \
    fail "docker 또는 podman 이 필요합니다. (Docker Desktop 또는 Podman machine 기동 후 재시도)"
  ok "Container CLI: $CONTAINER_CLI"
  export CONTAINER_CLI

  # Podman 사용 시 docker-compose 외부 provider 가 사용할 DOCKER_HOST 보정.
  # 사용자 셸의 DOCKER_HOST 가 잘못된 경로(/tmp/podman.sock 등)를 가리키는 경우가 흔함.
  if [[ "$CONTAINER_CLI" == "podman" ]]; then
    local sock
    sock="$(podman machine inspect --format '{{.ConnectionInfo.PodmanSocket.Path}}' 2>/dev/null | head -1)"
    if [[ -n "$sock" && -S "$sock" ]]; then
      export DOCKER_HOST="unix://$sock"
      ok "DOCKER_HOST=$DOCKER_HOST"
    else
      warn "podman 머신 socket 을 찾지 못했습니다. (podman machine start 확인)"
    fi
  fi
}

# Qdrant 가 응답할 때까지 대기 (최대 30s)
wait_qdrant() {
  printf "  Qdrant 헬스체크"
  for _ in $(seq 1 30); do
    if curl -sf http://localhost:6333/collections >/dev/null 2>&1; then
      printf " OK\n"
      return 0
    fi
    printf "."
    sleep 1
  done
  printf "\n"
  return 1
}

ensure_qdrant() {
  if curl -sf http://localhost:6333/collections >/dev/null 2>&1; then
    ok "Qdrant 이미 응답 중 (http://localhost:6333)"
    return 0
  fi
  step "Qdrant 컨테이너 기동"
  "$CONTAINER_CLI" compose up -d qdrant
  wait_qdrant || fail "Qdrant 응답 없음 (로그: $CONTAINER_CLI compose logs qdrant)"
  ok "Qdrant 준비 완료"
}
