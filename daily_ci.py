import subprocess
import sys
import os
import random
import time
import datetime

# 깨어난 뒤 0~4시간 사이 랜덤 대기 (매일 다른 시간에 올리기)
MAX_DELAY_HOURS = 4

def run(name, args):
    print(f"\n{'='*40}\n[{name}] 실행 중...\n{'='*40}", flush=True)
    result = subprocess.run([sys.executable] + args)
    if result.returncode != 0:
        print(f"[중단] {name} 에서 문제가 생겼어요.", flush=True)
        sys.exit(1)

print(f"\n자동 발행 시작: {datetime.datetime.now()}", flush=True)

# 1) 랜덤 대기
delay_sec = random.randint(0, MAX_DELAY_HOURS * 3600)
print(f"오늘은 랜덤하게 {delay_sec//60}분 뒤에 올릴게요...", flush=True)
time.sleep(delay_sec)

# 2) 콘텐츠 생성 (뉴스 + 글 + 배경)
run("콘텐츠 생성", ["generate.py"])

# 3) 카드 렌더링
run("카드 렌더링", ["render.py"])

# 4) 만든 카드를 깃허브에 커밋 (인스타가 가져갈 수 있게)
print(f"\n{'='*40}\n[깃허브에 카드 저장]\n{'='*40}", flush=True)
subprocess.run(["git", "config", "user.name", "github-actions"])
subprocess.run(["git", "config", "user.email", "actions@github.com"])
subprocess.run(["git", "add", "output", "content.json"])
subprocess.run(["git", "commit", "-m", f"auto cards: {datetime.date.today()}"])
push = subprocess.run(["git", "push"])
if push.returncode != 0:
    print("[중단] 깃허브 저장 실패.", flush=True)
    sys.exit(1)

# 깃허브 raw에 반영될 시간 확보
print("깃허브 반영 대기 중... (30초)", flush=True)
time.sleep(30)

# 5) 인스타 발행
run("인스타 발행", ["upload.py", "go"])

# 6) 스레드 발행
run("Threads 발행", ["upload_threads.py", "go"])

print(f"\n오늘 자동 발행 완료! {datetime.datetime.now()}", flush=True)
