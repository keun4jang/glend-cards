"""
릴스 자동 발행 오케스트레이터 (GitHub Actions용).
  generate_reel -> render_reel -> build_reel -> git push(mp4) -> upload_reel go
기본은 하루 1개 릴스. POST_INDEX(1=경제 2=사건사고 3=건강)를 인자로 받음(기본 1).
"""
import os
import random
import subprocess
import sys
import time
import datetime

IDX = sys.argv[1] if len(sys.argv) > 1 else "1"
# "auto" → 하루 3개 슬롯(카드/릴스1/릴스2)에 3개 주제를 하나씩 배정하고 매일 한 칸씩 로테이션
#   슬롯 1 = 릴스#1(KST 12:00), 슬롯 2 = 릴스#2(KST 18:00)
SLOT = 1 if datetime.datetime.now(datetime.timezone.utc).hour < 6 else 2
if IDX == "auto":
    from rotation import describe
    IDX, CAT_NAME = describe(SLOT)
    print(f"[로테이션] 오늘 이 슬롯의 주제: {CAT_NAME}", flush=True)

# 길이 A/B 배정을 generate_reel/build_reel이 같은 값으로 보게 환경변수로 넘긴다.
# (수동 실행에서 REEL_LENGTH를 지정했으면 그 값이 우선)
os.environ["REEL_SLOT"] = str(SLOT)
if not os.getenv("REEL_LENGTH", "").strip():
    from rotation import reel_length_variant
    os.environ["REEL_LENGTH"] = reel_length_variant(SLOT)
print(f"[길이 A/B] 이번 릴스: {os.environ['REEL_LENGTH']}", flush=True)

# PUBLISH=false 면 영상만 만들고(커밋까지) 발행은 건너뜀 — 업로드 전 검토용
PUBLISH = os.getenv("PUBLISH", "true").strip().lower() != "false"
# UPLOAD_ONLY=true 면 새로 만들지 않고, 이미 커밋된 영상만 발행 (검토 통과분 발행용)
UPLOAD_ONLY = os.getenv("UPLOAD_ONLY", "false").strip().lower() == "true"


def run(name, args):
    print(f"\n{'='*44}\n[{name}] 실행 중...\n{'='*44}", flush=True)
    r = subprocess.run([sys.executable] + args)
    if r.returncode != 0:
        print(f"[중단] {name} 실패.", flush=True)
        sys.exit(1)


print(f"\n릴스 자동 발행 시작: {datetime.datetime.now()} (릴스 {IDX})", flush=True)

# 스케줄 실행일 때만 0~50분 랜덤 대기 — 매일 다른 시간에 올라가게 (수동 실행은 즉시)
if os.getenv("GITHUB_EVENT_NAME") == "schedule":
    delay = random.randint(0, 50 * 60)
    print(f"오늘은 랜덤하게 {delay // 60}분 뒤에 올릴게요...", flush=True)
    time.sleep(delay)

subprocess.run(["git", "config", "user.name", "github-actions"])
subprocess.run(["git", "config", "user.email", "actions@github.com"])

# 업로드 전용: 이미 커밋된 영상만 발행하고 종료
if UPLOAD_ONLY:
    print("[업로드 전용] 이미 만들어진 영상을 발행합니다.", flush=True)
    run("릴스 발행", ["upload_reel.py", "go", IDX])
    print(f"\n릴스 발행 완료! {datetime.datetime.now()}", flush=True)
    sys.exit(0)

# 1) 대본 + 사진
run("릴스 대본 생성", ["generate_reel.py", IDX])
# 2) 장면 이미지
run("장면 렌더링", ["render_reel.py", IDX])
# 3) 나레이션 + 영상 조립
run("영상 조립", ["build_reel.py", IDX])

# 4) 영상을 media 브랜치에 저장 (main 히스토리 비대화 방지)
print(f"\n{'='*44}\n[media 브랜치에 영상 저장]\n{'='*44}", flush=True)
import media_push
media_push.push_media()

if not PUBLISH:
    print(f"\n[검토 모드] PUBLISH=false → 발행 생략. 영상은 media 브랜치에 저장됨.", flush=True)
    print(f"영상 URL: https://raw.githubusercontent.com/keun4jang/glend-cards/media/output/reel{IDX}/reel.mp4", flush=True)
    sys.exit(0)

# GitHub raw 반영 대기
print("깃허브 반영 대기 중... (40초)", flush=True)
import time
time.sleep(40)

# 5) 발행
run("릴스 발행", ["upload_reel.py", "go", IDX])

# 6) 발행한 대본·캡션을 main에 영구 보관
try:
    import archive, json as _json
    _c = _json.loads(open(f"reel_content_{IDX}.json", encoding="utf-8").read())
    archive.save("reel", IDX, _c, extra={"length_variant": _c.get("length_variant")})
    archive.commit_push(f"archive: 릴스{IDX} {datetime.date.today().isoformat()}")
except Exception as _e:
    print(f"[archive] 건너뜀: {_e}", flush=True)

print(f"\n릴스 자동 발행 완료! {datetime.datetime.now()}", flush=True)
