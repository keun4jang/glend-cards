import subprocess
import sys
import os
import random
import time
import datetime

from rotation import describe

# 하루 1개 게시물 — 주제는 매일 로테이션(슬롯 0 = 아침 카드뉴스)
POSTS_PER_DAY = 1
INITIAL_MAX_DELAY_HOURS = 0.5   # KST 07:30~08:00 사이 발행 (출근 시간대), 릴스 잡과 완전 분리
GAP_MIN_HOURS = 1                # 게시물 사이 최소 간격
GAP_MAX_HOURS = 1.5              # 게시물 사이 최대 간격 (GitHub Actions 6시간 제한 여유 확보)

def run(name, args):
    print(f"\n{'='*40}\n[{name}] 실행 중...\n{'='*40}", flush=True)
    result = subprocess.run([sys.executable] + args)
    if result.returncode != 0:
        print(f"[중단] {name} 에서 문제가 생겼어요.", flush=True)
        sys.exit(1)

print(f"\n자동 발행 시작: {datetime.datetime.now()}", flush=True)

subprocess.run(["git", "config", "user.name", "github-actions"])
subprocess.run(["git", "config", "user.email", "actions@github.com"])

# REUSE_CONTENT=true → 콘텐츠 새로 만들지 않고 media 브랜치의 기존 content로 재렌더+재발행
REUSE = os.getenv("REUSE_CONTENT", "false").strip().lower() == "true"
FORCED_IDX = os.getenv("CARD_INDEX", "").strip()

for i in range(1, POSTS_PER_DAY + 1):
    if FORCED_IDX:
        idx, cat_name = FORCED_IDX, f"수동지정({FORCED_IDX})"
    else:
        idx, cat_name = describe(0)   # 슬롯 0 = 아침 카드뉴스 (매일 주제 로테이션)

    # 스케줄 실행일 때만 랜덤 대기 (수동/재발행은 즉시)
    if os.getenv("GITHUB_EVENT_NAME") == "schedule":
        delay_sec = random.randint(0, int(INITIAL_MAX_DELAY_HOURS * 3600))
        print(f"\n[오늘의 카드뉴스 주제: {cat_name}] {delay_sec//60}분 뒤에 진행할게요...", flush=True)
        time.sleep(delay_sec)
    else:
        print(f"\n[카드뉴스 주제: {cat_name}] 바로 진행합니다.", flush=True)

    # 콘텐츠 생성 (뉴스 + 글 + 배경) — 재발행 모드면 건너뜀
    if REUSE:
        print("[재발행 모드] 기존 콘텐츠로 렌더링부터 진행", flush=True)
    else:
        run(f"콘텐츠 생성 ({idx}번째)", ["generate.py", idx])

    # 카드 렌더링
    run(f"카드 렌더링 ({idx}번째)", ["render.py", idx])

    # 만든 카드를 media 브랜치에 저장 (인스타가 가져갈 수 있게, main 히스토리 비대화 방지)
    print(f"\n{'='*40}\n[media 브랜치에 카드 저장 ({idx}번째)]\n{'='*40}", flush=True)
    import media_push
    media_push.push_media()

    # 깃허브 raw에 반영될 시간 확보
    print("깃허브 반영 대기 중... (30초)", flush=True)
    time.sleep(30)

    # 인스타 발행
    run(f"인스타 발행 ({idx}번째)", ["upload.py", "go", idx])

    # 스레드 발행
    run(f"Threads 발행 ({idx}번째)", ["upload_threads.py", "go", idx])

    # 발행한 텍스트를 main에 영구 보관 (media 브랜치는 매일 덮어써져 사라진다)
    try:
        import archive, json as _json
        _c = _json.loads(open(f"content_{idx}.json", encoding="utf-8").read())
        archive.save("card", idx, _c)
    except Exception as _e:
        print(f"[archive] 건너뜀: {_e}", flush=True)

# 아카이브는 마지막에 한 번만 커밋·푸시 (게시물마다 푸시하면 충돌만 늘어난다)
try:
    import archive
    archive.commit_push(f"archive: 카드뉴스 {datetime.date.today().isoformat()}")
except Exception as e:
    print(f"[archive] 푸시 건너뜀: {e}", flush=True)

print(f"\n오늘 자동 발행 완료! {datetime.datetime.now()}", flush=True)
