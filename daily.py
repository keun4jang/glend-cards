import subprocess
import sys
import random
import time
import datetime

# 하루 3개 게시물, 각기 다른 시간에 올리기 위한 랜덤 대기
POSTS_PER_DAY = 3
INITIAL_MAX_DELAY_HOURS = 1     # 첫 게시물까지 대기
GAP_MIN_HOURS = 1                 # 게시물 사이 최소 간격
GAP_MAX_HOURS = 1.5               # 게시물 사이 최대 간격

def run(name, args):
    print(f"\n{'='*40}\n[{name}] 실행 중...\n{'='*40}")
    result = subprocess.run([sys.executable] + args)
    if result.returncode != 0:
        print(f"[중단] {name} 에서 문제가 생겼어요. 오늘은 여기서 멈춥니다.")
        sys.exit(1)

print(f"\n자동 발행 시작: {datetime.datetime.now():%Y-%m-%d %H:%M}")

for i in range(1, POSTS_PER_DAY + 1):
    idx = str(i)

    delay_sec = random.randint(0, int(INITIAL_MAX_DELAY_HOURS * 3600)) if i == 1 \
        else random.randint(int(GAP_MIN_HOURS * 3600), int(GAP_MAX_HOURS * 3600))
    wake_at = datetime.datetime.now() + datetime.timedelta(seconds=delay_sec)
    print(f"\n[{idx}번째 게시물] {delay_sec//60}분 뒤({wake_at:%H:%M})에 진행할게요...")
    time.sleep(delay_sec)

    # 뉴스 수집 + 글 작성 + 배경 사진
    run(f"콘텐츠 생성 ({idx}번째)", ["generate.py", idx])

    # 카드 이미지 렌더링
    run(f"카드 렌더링 ({idx}번째)", ["render.py", idx])

    # 깃허브에 이미지 올리기 (인스타가 가져갈 수 있게)
    print(f"\n{'='*40}\n[깃허브 업로드 ({idx}번째)] 실행 중...\n{'='*40}")
    subprocess.run(["git", "add", "output", f"content_{idx}.json"])
    subprocess.run(["git", "commit", "-m", f"auto: {datetime.date.today()} #{idx}"])
    push = subprocess.run(["git", "push"])
    if push.returncode != 0:
        print("[중단] 깃허브 업로드 실패. 인스타 발행을 멈춥니다.")
        sys.exit(1)

    # 깃허브에 반영될 시간을 잠깐 줌
    print("깃허브 반영 대기 중... (20초)")
    time.sleep(20)

    # 인스타 발행
    run(f"인스타 발행 ({idx}번째)", ["upload.py", "go", idx])

    # 스레드 발행
    run(f"Threads 발행 ({idx}번째)", ["upload_threads.py", "go", idx])

print(f"\n오늘 자동 발행 완료! {datetime.datetime.now():%Y-%m-%d %H:%M}")
