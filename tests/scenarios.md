# 테스트 시나리오

각 항목을 Telegram 채팅창에서 직접 입력해 결과를 확인.
호출은 `/ask <질문>` 또는 일반 메시지(텍스트)로 가능.

> **사전 조건**: 봇이 켜져 있어야 합니다.
>
> ```bash
> # 상태 확인
> pgrep -af "python.*main\.py" && tail -5 bot.log
>
> # 안 켜져 있으면
> cd ~/telegram-langchain-docs
> nohup ./scripts/run.sh > bot.log 2>&1 & disown
> ```
>
> 처음 구축한다면 `README.md §빠른시작` 의 4단계(`.env` → `setup.sh` → `ingest.sh` → `run.sh`) 부터 진행.

---

## 6.1 기본 검색 정확도 (단일 문서)

| # | 질문 | 기대 동작 |
|---|---|---|
| 1 | 신입사원 연차 며칠이야? | **11일**, 출처 `01_hr_vacation.md` |
| 2 | VPN 인증서 며칠마다 갱신해? | **90일**, 출처 `02_it_vpn.md` |
| 3 | 비밀번호 몇 자리 이상이어야 해? | **12자리**, 출처 `03_it_account.md` |
| 4 | 회의실 예약 최대 몇 시간? | **4시간**, 출처 `04_office_facility.md` |
| 5 | 운영 배포는 언제만 가능해? | **평일 10~16시**, 출처 `05_dev_deployment.md` |

## 6.2 다중 문서 통합

| # | 질문 | 기대 동작 |
|---|---|---|
| 6 | 신입사원이 입사 후 처음 해야 할 IT 세팅은? | VPN + 계정/비밀번호 종합, 출처 2개 이상 |
| 7 | 휴가 가기 전에 IT 관련해서 챙겨야 할 게 뭐야? | VPN 만료, 계정 잠금 등 종합 |

## 6.3 답변 거부 (할루시네이션 방지)

| # | 질문 | 기대 동작 |
|---|---|---|
| 8 | 우리 회사 식대 지원금 얼마야? | "관련 문서를 찾지 못했습니다" |
| 9 | CEO 이름 뭐야? | "관련 문서를 찾지 못했습니다" |
| 10 | 출장비 정산 절차 알려줘 | "관련 문서를 찾지 못했습니다" |

## 6.4 엣지 케이스

| # | 질문/입력 | 기대 동작 |
|---|---|---|
| 11 | `/ask` (인자 없음) | "질문을 입력해주세요" 안내 |
| 12 | `안녕` | 일반 인사도 문서 기반 시도 → 관련 없으면 거부 |
| 13 | 5000자 이상 긴 질문 | 정상 처리, 답변 4000자 자동 절단 |

---

## 6.5 자동 인덱싱 — 옵션 C: Telegram 첨부 (NEW)

봇 채팅창에서 `.md` 파일을 끌어다 놓거나 첨부 버튼으로 전송.

| # | 입력 | 기대 동작 |
|---|---|---|
| 14 | 📎 `06_test_doc.md` 첨부 (예: "# 회식 정보\n매주 금요일 7시 본관 1층 식당가") | 봇 응답: `✓ 06_test_doc.md 인덱싱 완료 (N 청크)` (3~10s) |
| 15 | 첨부 직후 `/ask 회식 어디서 해?` | 새 문서 기반 답변, 출처 `06_test_doc.md` |
| 16 | 📎 `evil.exe` 또는 `06_test_doc.txt` 첨부 | "마크다운(.md) 파일만 받습니다" 거부 |
| 17 | 📎 `../etc/passwd.md` (경로 traversal) | `safe_filename()` 으로 sanitize → `passwd.md` 로만 저장 |

검증:
```bash
grep -E "document|reindex" bot.log | tail
curl -s -X POST http://localhost:6333/collections/company_docs/points/scroll -H 'Content-Type: application/json' -d '{"limit":50,"with_payload":true}' | python3 -c "import sys,json;[print(p['payload']['metadata']['source']) for p in json.load(sys.stdin)['result']['points']]" | sort -u
```

---

## 6.6 자동 인덱싱 — 옵션 A: 폴더 watchdog (NEW)

`data/docs/` 디렉토리에 셸/Finder/에디터로 파일 작업.

| # | 작업 | 기대 동작 |
|---|---|---|
| 18 | `cp 새문서.md data/docs/07_xxx.md` | 2초 debounce 후 `bot.log` 에 `watcher: 07_xxx.md 재인덱싱 (N 청크)` |
| 19 | 18 직후 `/ask <새 문서 내용 관련 질문>` | 새 문서 기반 답변, 출처 `07_xxx.md` |
| 20 | `vim data/docs/07_xxx.md` 로 내용 수정 | `delete_source ≈N` + `reindex_source_text N` 두 라인 |
| 21 | `rm data/docs/07_xxx.md` | `delete_source` + `watcher: 07_xxx.md 삭제 처리` |
| 22 | 21 직후 같은 질문 재질의 | 답변에 `07_xxx.md` 출처가 더이상 안 나옴 |

cleanup:
```bash
rm -f data/docs/07_xxx.md           # 또는 watcher 가 알아서 삭제 처리
```

---

## 6.7 성능 측정

각 질문 응답 시간을 기록한다.

### 목표 (실측 기반)

| 단계 | 콜드 스타트 (첫 호출) | 워밍업 후 |
|---|---|---|
| 단순 질문 (1~5번) | 15~25s | 6~12s |
| 다중 문서 통합 (6~7번) | 20~30s | 10~18s |
| 거부 응답 (8~10번) | 15~22s | 6~10s |
| Telegram 첨부 인덱싱 (14번) | 12~15s | 3~5s |
| 폴더 watcher 인덱싱 (18번) | 12~15s (+ 2s debounce) | 3~5s (+ 2s debounce) |

### 응답이 30초를 넘으면 점검

| 단계 | 정상 시간 | 점검 방법 |
|---|---|---|
| BGE-M3 임베딩 | < 0.5s | `bot.log` 에 임베딩 단계 시간 추적 (필요 시 logger 추가) |
| Qdrant 검색 | < 0.1s | `curl -w "%{time_total}\n"` 으로 측정 |
| BGE-Reranker | 1~3s (워밍업), 10s+ (콜드) | `RERANKER_ENABLED=false` 로 토글해 차이 확인 |
| codex CLI | 5~15s (대부분 시간 여기) | `time codex exec "test"` 직접 비교 |

병목이 codex 인 경우:
- `LLM_CLI=claude`, `LLM_CLI_ARGS=-p` 로 교체
- 또는 `LLM_CLI=ollama`, `LLM_CLI_ARGS=run qwen2.5:7b` 로 로컬 LLM

---

## 6.8 입력 방식 정리

| 방식 | 예시 | 비고 |
|---|---|---|
| 슬래시 커맨드 | `/ask 휴가 며칠?` | 어디서나 동작 |
| 일반 메시지 | `휴가 며칠?` | 1:1 채팅 권장 (그룹은 BotFather privacy 설정 필요) |
| `/start` | `/start` | 봇 사용법 안내 |
| 문서 첨부 | 📎 `.md` 파일 | 자동 인덱싱 |

---

## 6.9 합격 기준

| 그룹 | 합격선 |
|---|---|
| §6.1 단일 정확도 | 5/5 정답 + 정확한 출처 |
| §6.3 거부 응답 | 3/3 모두 거부 |
| §6.5 Telegram 첨부 | 14, 15 통과 + 16 거부 |
| §6.6 폴더 watchdog | 18~22 모두 로그 + 답변 변화 확인 |
| §6.7 성능 | 워밍업 후 단순 질문 평균 < 12s |
