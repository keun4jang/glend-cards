import subprocess
import sys
import os
import random
import time
import datetime

# 하루 1개 게시물(경제·재테크) — 도달 데이터 기반으로 3→1 축소 (인사이트 2026-07-30)
POSTS_PER_DAY = 1
INITIAL_MAX_DELAY_HOURS = 0.75  # 릴스 잡(UTC 03:00)과 media 푸시가 겹치지 않게 45분 이내로
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

for i in range(1, POSTS_PER_DAY + 1):
    idx = str(i)

    # 첫 게시물은 짧게, 이후 게시물은 간격을 두고 대기
    delay_sec = random.randint(0, int(INITIAL_MAX_DELAY_HOURS * 3600)) if i == 1 \
        else random.randint(int(GAP_MIN_HOURS * 3600), int(GAP_MAX_HOURS * 3600))
    print(f"\n[{idx}번째 게시물] {delay_sec//60}분 뒤에 진행할게요...", flush=True)
    time.sleep(delay_sec)

    # 콘텐츠 생성 (뉴스 + 글 + 배경)
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

print(f"\n오늘 자동 발행 완료! {datetime.datetime.now()}", flush=True)
