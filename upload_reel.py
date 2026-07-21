"""
릴스 발행 — 인스타그램 Reels API + Threads VIDEO.
사용:  python upload_reel.py go [POST_INDEX]
드라이런: python upload_reel.py       (실제 발행 안 함)
전제: reel.mp4가 GitHub raw로 접근 가능해야 함(먼저 git push).
"""
import os
import sys
import json
import time
import datetime
import requests
from dotenv import load_dotenv

load_dotenv()
IG_TOKEN = os.getenv("IG_TOKEN", "").strip()
IG_USER = os.getenv("IG_USER_ID", "").strip()
TH_TOKEN = os.getenv("THREADS_TOKEN", os.getenv("IG_TOKEN", "")).strip()
TH_USER = os.getenv("THREADS_USER_ID", os.getenv("IG_USER_ID", "")).strip()

POST_INDEX = sys.argv[2] if len(sys.argv) > 2 else "1"
DRY_RUN = not (len(sys.argv) > 1 and sys.argv[1] == "go")

GITHUB_USER, GITHUB_REPO, BRANCH = "keun4jang", "glend-cards", "main"
VIDEO_URL = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/{BRANCH}/output/reel{POST_INDEX}/reel.mp4"
IG_GRAPH = "https://graph.instagram.com"
TH_GRAPH = "https://graph.threads.net/v1.0"
LOG_FILE = "reel_upload_log.txt"

with open(f"reel_content_{POST_INDEX}.json", "r", encoding="utf-8") as f:
    content = json.load(f)
caption = content.get("caption", "").replace("<b>", "").replace("</b>", "")

print("=" * 44)
print(f"[릴스 발행] 모드: {'실제' if not DRY_RUN else '드라이런'} | 릴스: {POST_INDEX}")
print("=" * 44)
print("영상 URL:", VIDEO_URL)
print("\n[캡션 미리보기]\n" + caption[:200], "...\n")


def slot_key():
    return f"{datetime.date.today().isoformat()} reel{POST_INDEX}"


def already_done():
    return os.path.exists(LOG_FILE) and slot_key() in open(LOG_FILE, encoding="utf-8").read()


if DRY_RUN:
    print("드라이런이라 여기서 멈춰요. 실제 발행: python upload_reel.py go", POST_INDEX)
    raise SystemExit

if already_done():
    print(f"오늘 릴스 {POST_INDEX}는 이미 발행함. 중복 방지로 멈춤.")
    raise SystemExit


def post_instagram_reel():
    print("\n[Instagram] 릴스 컨테이너 생성...")
    res = requests.post(f"{IG_GRAPH}/{IG_USER}/media", data={
        "media_type": "REELS", "video_url": VIDEO_URL,
        "caption": caption, "access_token": IG_TOKEN,
    }, timeout=60)
    j = res.json()
    if "id" not in j:
        print("[실패] 컨테이너 생성:", j); return False
    cid = j["id"]
    print("  컨테이너 id:", cid)

    # 비동기 처리 대기 (status_code=FINISHED)
    print("  인스타가 영상 처리 중... (최대 ~4분)")
    for attempt in range(1, 31):
        time.sleep(8)
        s = requests.get(f"{IG_GRAPH}/{cid}",
                         params={"fields": "status_code", "access_token": IG_TOKEN},
                         timeout=60).json()
        st = s.get("status_code")
        if st == "FINISHED":
            print("  처리 완료 ✅"); break
        if st == "ERROR":
            print("[실패] 영상 처리 오류:", s); return False
        print(f"  ({attempt}/30) 상태={st}...")
    else:
        print("[실패] 처리 시간 초과."); return False

    pub = requests.post(f"{IG_GRAPH}/{IG_USER}/media_publish",
                        data={"creation_id": cid, "access_token": IG_TOKEN}, timeout=60).json()
    if "id" in pub:
        print(f"🎉 인스타 릴스 발행 성공! id: {pub['id']}"); return True
    print("[실패] 발행:", pub); return False


def post_threads_video():
    print("\n[Threads] 영상 컨테이너 생성...")
    res = requests.post(f"{TH_GRAPH}/{TH_USER}/threads", data={
        "media_type": "VIDEO", "video_url": VIDEO_URL,
        "text": caption, "access_token": TH_TOKEN,
    }, timeout=60)
    j = res.json()
    if "id" not in j:
        print("[실패] Threads 컨테이너:", j); return False
    cid = j["id"]
    print("  컨테이너 id:", cid, "| 처리 대기 30초")
    time.sleep(30)
    for attempt in range(1, 11):
        pub = requests.post(f"{TH_GRAPH}/{TH_USER}/threads_publish",
                            data={"creation_id": cid, "access_token": TH_TOKEN}, timeout=60).json()
        if "id" in pub:
            print(f"🎉 Threads 영상 발행 성공! id: {pub['id']}"); return True
        if pub.get("error", {}).get("is_transient"):
            print(f"  ({attempt}/10) 아직 처리 중... 8초"); time.sleep(8); continue
        print("[실패] Threads 발행:", pub); return False
    return False


ig_ok = post_instagram_reel()

# Threads는 기본 비활성 (REEL_POST_THREADS=true 로 켜기)
th_ok = False
if os.getenv("REEL_POST_THREADS", "false").strip().lower() == "true":
    th_ok = post_threads_video()

if ig_ok or th_ok:
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{slot_key()} posted (ig={ig_ok}, threads={th_ok})\n")
    print("\n기록 저장 완료.")
