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
from content_io import load_content, threads_text

load_dotenv()
IG_TOKEN = os.getenv("IG_TOKEN", "").strip()
IG_USER = os.getenv("IG_USER_ID", "").strip()
# Threads는 인스타 토큰과 호환되지 않는다(upload_threads.py 참고) — 전용 토큰이 있을 때만 쓴다.
TH_TOKEN = os.getenv("THREADS_TOKEN", "").strip()
TH_USER = os.getenv("THREADS_USER_ID", "").strip()

POST_INDEX = sys.argv[2] if len(sys.argv) > 2 else "1"
DRY_RUN = not (len(sys.argv) > 1 and sys.argv[1] == "go")

GITHUB_USER, GITHUB_REPO, BRANCH = "keun4jang", "glend-cards", "media"
from content_io import cache_bust
VIDEO_URL = cache_bust(f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/{BRANCH}/output/reel{POST_INDEX}/reel.mp4")
IG_GRAPH = (os.getenv("IG_GRAPH_BASE") or "https://graph.instagram.com").rstrip("/")
TH_GRAPH = "https://graph.threads.net/v1.0"
LOG_FILE = "reel_upload_log.txt"

content = load_content(f"reel_content_{POST_INDEX}.json")
caption = content.get("caption", "").replace("<b>", "").replace("</b>", "").replace("**", "").replace("__", "")[:2200]

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


COVER_URL = cache_bust(f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/{BRANCH}/output/reel{POST_INDEX}/cover.png")


def post_instagram_reel():
    print("\n[Instagram] 릴스 컨테이너 생성...")
    payload = {
        "media_type": "REELS", "video_url": VIDEO_URL,
        "caption": caption, "access_token": IG_TOKEN,
    }
    # 커버 썸네일이 media 브랜치에 있으면 지정
    try:
        if requests.head(COVER_URL, timeout=20).status_code == 200:
            payload["cover_url"] = COVER_URL
            print("  커버 썸네일 지정:", COVER_URL.split("?")[0])
    except Exception:
        pass
    res = requests.post(f"{IG_GRAPH}/{IG_USER}/media", data=payload, timeout=60)
    j = res.json()
    if "id" not in j and "cover_url" in payload:
        # 커버 관련 오류일 수 있으니 커버 없이 1회 재시도
        print("  (커버 포함 생성 실패 → 커버 없이 재시도)", j.get("error", {}).get("message", "")[:80])
        payload.pop("cover_url")
        res = requests.post(f"{IG_GRAPH}/{IG_USER}/media", data=payload, timeout=60)
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
        print(f"🎉 인스타 릴스 발행 성공! id: {pub['id']}")
        # media id를 남겨야 archive/instagram_posts.csv(id 컬럼)와 정확히 조인된다.
        # 지금까지는 날짜+인덱스 추정 매칭에 의존했다.
        try:
            import json as _json
            p = os.path.join("output", f"reel{POST_INDEX}", "meta.json")
            m = _json.loads(open(p, encoding="utf-8").read()) if os.path.exists(p) else {}
            m["ig_media_id"] = pub["id"]
            open(p, "w", encoding="utf-8").write(_json.dumps(m, ensure_ascii=False, indent=2))
        except Exception as e:
            print(f"  (meta 기록 실패, 발행에는 영향 없음: {e})")
        return True
    print("[실패] 발행:", pub); return False


def _media_sha():
    """media 브랜치의 현재 커밋 — jsDelivr 주소를 브랜치가 아닌 커밋으로 고정(캐시가 옛 영상을 주지 않게)."""
    try:
        r = requests.get(f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/commits/{BRANCH}", timeout=20)
        if r.status_code == 200:
            return r.json().get("sha") or BRANCH
    except Exception:
        pass
    return BRANCH


def _th_wait(cid, max_wait=300):
    """Threads 컨테이너 처리 상태를 기다린다 → (status, error_message)."""
    status, err = "", ""
    for _ in range(max_wait // 10):
        time.sleep(10)
        j = requests.get(f"{TH_GRAPH}/{cid}", params={"fields": "status,error_message", "access_token": TH_TOKEN},
                         timeout=30).json()
        status, err = j.get("status", ""), j.get("error_message", "") or json.dumps(j.get("error", ""), ensure_ascii=False)
        if status in ("FINISHED", "ERROR", "EXPIRED", "PUBLISHED"):
            break
        print(f"  상태={status or '?'} …")
    return status, err


def post_threads_video():
    """11/3 첫 시도: 30초만 기다리고 발행해 'Media Not Found'(처리 실패로 컨테이너가 사라짐).
    raw.githubusercontent는 mp4를 application/octet-stream으로 준다 — 인스타는 받지만 Threads는 거절할 수 있어
    처리 상태를 확인하고, 실패하면 video/mp4로 주는 jsDelivr 주소로 한 번 더 시도한다."""
    urls = [("raw", VIDEO_URL),
            ("jsdelivr", f"https://cdn.jsdelivr.net/gh/{GITHUB_USER}/{GITHUB_REPO}@{_media_sha()}/output/reel{POST_INDEX}/reel.mp4")]
    for name, url in urls:
        print(f"\n[Threads] 영상 컨테이너 생성({name})...")
        j = requests.post(f"{TH_GRAPH}/{TH_USER}/threads", data={
            "media_type": "VIDEO", "video_url": url,
            "text": threads_text(caption), "access_token": TH_TOKEN,
        }, timeout=60).json()
        if "id" not in j:
            print("[실패] Threads 컨테이너:", j)
            continue
        cid = j["id"]
        status, err = _th_wait(cid)
        print(f"  컨테이너 {cid} 상태={status} {err}")
        if status != "FINISHED":
            continue
        for attempt in range(1, 6):
            pub = requests.post(f"{TH_GRAPH}/{TH_USER}/threads_publish",
                                data={"creation_id": cid, "access_token": TH_TOKEN}, timeout=60).json()
            if "id" in pub:
                print(f"🎉 Threads 영상 발행 성공({name})! id: {pub['id']}")
                return True
            if pub.get("error", {}).get("is_transient"):
                time.sleep(8)
                continue
            print("[실패] Threads 발행:", pub)
            break
    return False


ig_ok = post_instagram_reel()

# Threads: 전용 토큰(THREADS_TOKEN·THREADS_USER_ID)이 있으면 자동으로 함께 올린다(2026-11-03 유입 확대).
# 끄려면 REEL_POST_THREADS=false. 인스타가 성공했으면 Threads 실패로 전체를 실패시키지 않는다.
th_ok = False
if TH_TOKEN and TH_USER and os.getenv("REEL_POST_THREADS", "true").strip().lower() != "false":
    try:
        th_ok = post_threads_video()
    except Exception as e:
        print(f"[Threads] 예외 — 인스타 발행에는 영향 없음: {e}")
else:
    print("[Threads] THREADS_TOKEN/THREADS_USER_ID 미설정 → 건너뜀")

if ig_ok or th_ok:
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        variant = content.get("length_variant", "?")
        f.write(f"{slot_key()} posted (ig={ig_ok}, threads={th_ok}, length={variant})\n")
    print("\n기록 저장 완료.")
else:
    print("\n[실패] 발행이 하나도 성공하지 못했습니다.")
    sys.exit(1)
