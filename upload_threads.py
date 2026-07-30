import os
import json
import sys
import time
import requests
from dotenv import load_dotenv
from content_io import load_content, cache_bust

load_dotenv()
# Threads는 인스타 토큰과 호환되지 않음(검증됨) — 전용 토큰이 없으면 깔끔하게 건너뜀
TOKEN = os.getenv("THREADS_TOKEN", "").strip()
USER_ID = os.getenv("THREADS_USER_ID", "").strip()

if not TOKEN or not USER_ID:
    print("[Threads] THREADS_TOKEN/THREADS_USER_ID 미설정 → 건너뜀 (설정하면 자동 발행됨)")
    raise SystemExit(0)

POST_INDEX = sys.argv[2] if len(sys.argv) > 2 else "1"

GITHUB_USER = "keun4jang"
GITHUB_REPO = "glend-cards"
BRANCH = "media"
IMAGE_BASE = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/{BRANCH}/output/post{POST_INDEX}"
CARD_FILES = ["card1.png", "card2.png", "card3.png", "card4.png"]
GRAPH = "https://graph.threads.net/v1.0"

DRY_RUN = not (len(sys.argv) > 1 and sys.argv[1] == "go")

print("=" * 40)
print(f"[Threads] 모드: {'실제 업로드' if not DRY_RUN else '드라이런'} | 게시물: {POST_INDEX}")
print("=" * 40)

content = load_content(f"content_{POST_INDEX}.json")
caption = content.get("caption", "").replace("<b>", "").replace("</b>", "").replace("**", "").replace("__", "")[:500]

print("\n[캡션 미리보기]")
print(caption[:200], "...\n")
print("[올릴 이미지 4장]")
for fn in CARD_FILES:
    print(f"  {IMAGE_BASE}/{fn}")
print()

if DRY_RUN:
    print("드라이런이라 여기서 멈춰요. 실제 업로드는 'python upload_threads.py go'")
    raise SystemExit

print("Threads 업로드 시작...\n")

# 1) 각 이미지를 캐러셀 아이템으로 등록
item_ids = []
for fn in CARD_FILES:
    img_url = cache_bust(f"{IMAGE_BASE}/{fn}")
    res = requests.post(f"{GRAPH}/{USER_ID}/threads", data={
        "media_type": "IMAGE",
        "image_url": img_url,
        "is_carousel_item": "true",
        "access_token": TOKEN,
    }, timeout=60)
    j = res.json()
    if "id" not in j:
        print(f"[실패] {fn} 등록 오류:", j)
        raise SystemExit
    item_ids.append(j["id"])
    print(f"  {fn} 등록 OK (id: {j['id']})")

# 2) 캐러셀 컨테이너 생성
res = requests.post(f"{GRAPH}/{USER_ID}/threads", data={
    "media_type": "CAROUSEL",
    "children": ",".join(item_ids),
    "text": caption,
    "access_token": TOKEN,
}, timeout=60)
j = res.json()
if "id" not in j:
    print("[실패] 캐러셀 생성 오류:", j)
    sys.exit(1)
container_id = j["id"]
print(f"\n캐러셀 컨테이너 생성 OK (id: {container_id})")

# 3) 발행 (최대 10회 재시도)
print("\nThreads가 이미지를 처리하는 중...")
published = False
for attempt in range(1, 11):
    time.sleep(8)
    res = requests.post(f"{GRAPH}/{USER_ID}/threads_publish", data={
        "creation_id": container_id,
        "access_token": TOKEN,
    }, timeout=60)
    j = res.json()
    if "id" in j:
        print(f"\n🎉 Threads 발행 성공! 게시물 ID: {j['id']}")
        published = True
        break
    else:
        err = j.get("error", {})
        if err.get("is_transient"):
            print(f"  ({attempt}/10) 아직 처리 중... 8초 대기")
            continue
        else:
            print("[실패] Threads 발행 오류:", j)
            sys.exit(1)

if not published:
    print("[실패] Threads 발행 최종 실패. 나중에 수동으로 시도해보세요.")
    sys.exit(1)
