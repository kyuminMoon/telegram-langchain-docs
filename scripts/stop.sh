#!/usr/bin/env bash
# 백그라운드로 띄운 봇 종료
set -euo pipefail

pids=$(pgrep -f "python.*app/main\.py" || true)
if [[ -z "$pids" ]]; then
  echo "실행 중인 봇이 없습니다."
  exit 0
fi
echo "종료할 봇 PID: $pids"
kill $pids
sleep 1
if pgrep -f "python.*app/main\.py" >/dev/null 2>&1; then
  echo "강제 종료 (-9)"
  pkill -9 -f "python.*app/main\.py" || true
fi
echo "✓ 봇 종료 완료"
