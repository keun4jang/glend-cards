"""
릴스 자동 발행 오케스트레이터 (GitHub Actions용).
  generate_reel -> render_reel -> build_reel -> git push(mp4) -> upload_reel go
기본은 하루 1개 릴스. POST_INDEX(1=경제 2=사건사고 3=건강)를 인자로 받음(기본 1).
"""
import subprocess
import sys
import datetime

IDX = sys.argv[1] if len(sys.argv) > 1 else "1"


def run(name, args):
    print(f"\n{'='*44}\n[{name}] 실행 중...\n{'='*44}", flush=True)
    r = subprocess.run([sys.executable] + args)
    if r.returncode != 0:
        print(f"[중단] {name} 실패.", flush=True)
        sys.exit(1)


print(f"\n릴스 자동 발행 시작: {datetime.datetime.now()} (릴스 {IDX})", flush=True)

subprocess.run(["git", "config", "user.name", "github-actions"])
subprocess.run(["git", "config", "user.email", "actions@github.com"])

# 1) 대본 + 사진
run("릴스 대본 생성", ["generate_reel.py", IDX])
# 2) 장면 이미지
run("장면 렌더링", ["render_reel.py", IDX])
# 3) 나레이션 + 영상 조립
run("영상 조립", ["build_reel.py", IDX])

# 4) reel.mp4 + json만 커밋 (중간 산출물 제외)
print(f"\n{'='*44}\n[깃허브에 영상 저장]\n{'='*44}", flush=True)
subprocess.run(["git", "add", f"output/reel{IDX}/reel.mp4", f"reel_content_{IDX}.json"])
subprocess.run(["git", "commit", "-m", f"auto reel: {datetime.date.today()} #{IDX}"])
push = subprocess.run(["git", "push"])
if push.returncode != 0:
    print("[중단] 깃허브 저장 실패.", flush=True)
    sys.exit(1)

# GitHub raw 반영 대기
print("깃허브 반영 대기 중... (40초)", flush=True)
import time
time.sleep(40)

# 5) 발행
run("릴스 발행", ["upload_reel.py", "go", IDX])

print(f"\n릴스 자동 발행 완료! {datetime.datetime.now()}", flush=True)
