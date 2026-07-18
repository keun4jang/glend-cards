import os
import json
import sys
import time
import datetime
import requests
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("IG_TOKEN", "").strip()
USER_ID = os.getenv("IG_USER_ID", "").strip()

POST_INDEX = sys.argv[2] if len(sys.argv) > 2 else "1"

GITHUB_USER = "keun4jang"
GITHUB_REPO = "glend-cards"
BRANCH = "main"
IMAGE_BASE = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/{BRANCH}/output/post{POST_INDEX}"
CARD_FILES = ["card1.png", "card2.png", "card3.png", "card4.png"]
LOG_FILE = "upload_log.txt"
GRAPH = "https://graph.instagram.com"

DRY_RUN = not (len(sys.argv) > 1 and sys.argv[1] == "go")

def slot_key():
    return f"{datetime.date.today().isoformat()} post{POST_INDEX}"

def already_posted_slot():
    if not os.path.exists(LOG_FILE):
        return False
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        return slot_key() in f.read()

def mark_posted_slot():
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{slot_key()} posted\n")

print("=" * 40)
print(f"모드: {'실제 업로드' if not DRY_RUN else '드라이런(연습, 실제 업로드 안 함)'} | 게시물: {POST_INDEX}")
print("=" * 40)

if already_posted_slot():
    print(f"오늘 {POST_INDEX}번째 게시물은 이미 업로드했어요. 중복 방지로 멈춥니다.")
    raise SystemExit

with open(f"content_{POST_INDEX}.json", "r", encoding="utf-8") as f:
    content = json.load(f)
caption = content.get("caption", "").replace("<b>", "").replace("</b>", "")
print("\n[캡션 미리보기]")
print(caption[:200], "...\n")

print("[올릴 이미지 4장]")
for fn in CARD_FILES:
    print(f"  {IMAGE_BASE}/{fn}")
print()

if DRY_RUN:
    print("드라이런이라 여기서 멈춰요. 실제 업로드는 안 했어요.")
    print("   문제 없어 보이면, 'python upload.py go' 로 진짜 업로드하세요.")
    raise SystemExit

print("실제 업로드 시작...\n")

item_ids = []
for fn in CARD_FILES:
    img_url = f"{IMAGE_BASE}/{fn}"
    res = requests.post(f"{GRAPH}/{USER_ID}/media", data={
        "image_url": img_url,
        "is_carousel_item": "true",
        "access_token": TOKEN,
    }, timeout=60)
    j = res.json()
    if "id" not in j:
        print(f"[실패] {fn} 등록 중 오류:", j)
        raise SystemExit
    item_ids.append(j["id"])
    print(f"  {fn} 등록 OK (id: {j['id']})")

res = requests.post(f"{GRAPH}/{USER_ID}/media", data={
    "media_type": "CAROUSEL",
    "children": ",".join(item_ids),
    "caption": caption,
    "access_token": TOKEN,
}, timeout=60)
j = res.json()
if "id" not in j:
    print("[실패] 캐러셀 만들기 오류:", j)
    raise SystemExit
container_id = j["id"]
print(f"\n캐러셀 묶음 생성 OK (id: {container_id})")

# 발행 전, 인스타가 이미지 처리할 시간을 주고 + 자동 재시도
print("\n인스타가 이미지를 처리하는 중... 잠시 기다려요.")
published = False
for attempt in range(1, 11):
    time.sleep(8)
    res = requests.post(f"{GRAPH}/{USER_ID}/media_publish", data={
        "creation_id": container_id,
        "access_token": TOKEN,
    }, timeout=60)
    j = res.json()
    if "id" in j:
        print(f"\n🎉🎉 발행 성공! 게시물 ID: {j['id']}")
        published = True
        break
    else:
        err = j.get("error", {})
        if err.get("error_subcode") == 2207027 or err.get("is_transient"):
            print(f"  ({attempt}/10) 아직 준비 중... 8초 더 기다릴게요.")
            continue
        else:
            print("[실패] 발행 오류:", j)
            raise SystemExit

if published:
    mark_posted_slot()
    print(f"{POST_INDEX}번째 게시물 업로드 기록 저장 완료")
else:
    print("\n[실패] 여러 번 시도했지만 인스타가 아직 준비가 안 됐어요.")
    print(f"   1~2분 뒤에 'python upload.py go {POST_INDEX}' 다시 시도해보세요.")

