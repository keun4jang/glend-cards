import subprocess
import sys
import random
import time
import datetime

# 매일 다른 시간에 올리기 위한 랜덤 대기 (0 ~ 5시간 사이)
MAX_DELAY_HOURS = 5

def run(name, args):
    print(f"\n{'='*40}\n[{name}] 실행 중...\n{'='*40}")
    result = subprocess.run([sys.executable] + args)
    if result.returncode != 0:
        print(f"[중단] {name} 에서 문제가 생겼어요. 오늘은 여기서 멈춥니다.")
        sys.exit(1)

print(f"\n자동 발행 시작: {datetime.datetime.now():%Y-%m-%d %H:%M}")

# 1) 랜덤 대기
delay_sec = random.randint(0, MAX_DELAY_HOURS * 3600)
wake_at = datetime.datetime.now() + datetime.timedelta(seconds=delay_sec)
print(f"오늘은 랜덤하게 {delay_sec//60}분 뒤({wake_at:%H:%M})에 올릴게요...")
time.sleep(delay_sec)

# 2) 뉴스 수집 + 글 작성 + 배경 사진
run("콘텐츠 생성", ["generate.py"])

# 3) 카드 이미지 렌더링
run("카드 렌더링", ["render.py"])

# 4) 깃허브에 이미지 올리기 (인스타가 가져갈 수 있게)
print(f"\n{'='*40}\n[깃허브 업로드] 실행 중...\n{'='*40}")
subprocess.run(["git", "add", "output", "content.json"])
subprocess.run(["git", "commit", "-m", f"auto: {datetime.date.today()}"])
push = subprocess.run(["git", "push"])
if push.returncode != 0:
    print("[중단] 깃허브 업로드 실패. 인스타 발행을 멈춥니다.")
    sys.exit(1)

# 깃허브에 반영될 시간을 잠깐 줌
print("깃허브 반영 대기 중... (20초)")
time.sleep(20)

# 5) 인스타 발행
run("인스타 발행", ["upload.py", "go"])

print(f"\n오늘 자동 발행 완료! {datetime.datetime.now():%Y-%m-%d %H:%M}")
