#!/bin/bash
# 대화 자동 저장 Stop 훅 — 껍데기(shim).
#
# 실제 로직은 아카이브 저장소 한 곳에 모여 있다:
#   claude-chat-archive/tools/stop-hook.sh
# 여기서는 "이 프로젝트가 누구인지"만 알려 주고 넘긴다. 훅을 고칠 일이 생기면
# 아카이브 저장소 한 곳만 고치면 모든 프로젝트에 반영된다 — 예전엔 같은
# 스크립트가 프로젝트 6곳에 복사돼 있어서, 2026-09-13 push 버그 때 고칠 곳도
# 6곳이었다.
#
# 이 훅은 절대 turn 을 막지 않는다(항상 exit 0).

ARCHIVE_DIR="${CHAT_ARCHIVE_DIR:-/home/user/claude-chat-archive}"
export CHAT_ARCHIVE_DIR="$ARCHIVE_DIR"
export CHAT_ARCHIVE_PROJECT="glend-cards"
export CHAT_ARCHIVE_SOURCE_REPO="keun4jang/glend-cards"

BODY="$ARCHIVE_DIR/tools/stop-hook.sh"
if [[ ! -f "$BODY" ]]; then
  echo "[chat-archive] 아카이브 저장소가 이 세션에 연결되어 있지 않아 자동 저장을 건너뜁니다. '대화 저장해줘'라고 요청하면 수동으로 저장할 수 있습니다." >&2
  exit 0
fi

exec bash "$BODY"
