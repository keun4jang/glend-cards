#!/usr/bin/env bash
# Claude Code 대화 자동 저장 훅 (Stop hook)
#
# 매 턴이 끝날 때마다 이 대화 기록을 keun4jang/claude-chat-archive 저장소로
# export → commit → push 한다. 다른 프로젝트(coupang-partners-shop 등)와
# 완전히 동일한 구조를 이 프로젝트용으로 재사용한 것 — PROJECT 값만 다르다.
#
# 무슨 일이 있어도 사용자 turn을 막으면 안 되므로 항상 exit 0로 끝난다.

PROJECT="glend-cards"
ARCHIVE_DIR="/home/user/claude-chat-archive"

INPUT="$(cat)"

# Stop hook이 자기 자신을 재귀적으로 다시 트리거하는 것을 방지
STOP_HOOK_ACTIVE="$(printf '%s' "$INPUT" | jq -r '.stop_hook_active // false' 2>/dev/null)"
if [ "$STOP_HOOK_ACTIVE" = "true" ]; then
  exit 0
fi

# 보관소 저장소가 이 세션에 연결되어 있지 않으면 조용히 건너뜀
if [ ! -d "$ARCHIVE_DIR/.git" ]; then
  exit 0
fi

TRANSCRIPT_PATH="$(printf '%s' "$INPUT" | jq -r '.transcript_path // empty' 2>/dev/null)"
SESSION_ID="$(printf '%s' "$INPUT" | jq -r '.session_id // empty' 2>/dev/null)"
CWD="$(printf '%s' "$INPUT" | jq -r '.cwd // empty' 2>/dev/null)"
[ -z "$CWD" ] && CWD="$(pwd)"

if [ -z "$TRANSCRIPT_PATH" ] || [ -z "$SESSION_ID" ] || [ ! -f "$TRANSCRIPT_PATH" ]; then
  exit 0
fi

SOURCE_REPO=""
SOURCE_BRANCH=""
if git -C "$CWD" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  REMOTE_URL="$(git -C "$CWD" remote get-url origin 2>/dev/null)"
  SOURCE_REPO="$(printf '%s' "$REMOTE_URL" | sed -E 's#^.*github\.com[:/]##; s#\.git$##')"
  SOURCE_BRANCH="$(git -C "$CWD" branch --show-current 2>/dev/null)"
fi

LOG_FILE="/tmp/chat-archive-stop-${SESSION_ID}.log"

node "$ARCHIVE_DIR/tools/export.mjs" \
  --transcript "$TRANSCRIPT_PATH" \
  --project "$PROJECT" \
  --session-id "$SESSION_ID" \
  --archive-dir "$ARCHIVE_DIR" \
  --source-repo "${SOURCE_REPO:-알 수 없음}" \
  --source-branch "${SOURCE_BRANCH:-알 수 없음}" \
  >"$LOG_FILE" 2>&1

(
  cd "$ARCHIVE_DIR" || exit 0

  git add -A >/dev/null 2>&1

  if git diff --cached --quiet 2>/dev/null; then
    exit 0
  fi

  git commit -m "auto(${PROJECT}): 대화 기록 업데이트 (session ${SESSION_ID:0:8})" >>"$LOG_FILE" 2>&1

  BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null)"

  # 다른 프로젝트 세션이 동시에 이 공용 보관소에 push할 수 있어 non-fast-forward로
  # 거절되는 경우가 실제로 있다 (2026-09-12 테스트 중 확인). fetch + rebase 후
  # 한 번 더 시도하고, 그래도 안 되면 포기한다 — 로컬 커밋은 남아있으니 다음
  # 턴에서 다시 시도된다.
  for attempt in 1 2; do
    if git push origin "HEAD:${BRANCH}" >>"$LOG_FILE" 2>&1; then
      break
    fi
    git fetch origin "$BRANCH" >>"$LOG_FILE" 2>&1
    if ! git rebase "origin/${BRANCH}" >>"$LOG_FILE" 2>&1; then
      git rebase --abort >>"$LOG_FILE" 2>&1
      break
    fi
  done
)

exit 0
