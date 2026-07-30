"""
계정 성장 진단용 인사이트 수집 스크립트 (읽기 전용 — 아무것도 발행하지 않음).
GitHub Actions에서 IG_TOKEN/IG_USER_ID로 실행해 로그로 결과 출력.
"""
import os
import requests
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("IG_TOKEN", "").strip()
USER_ID = os.getenv("IG_USER_ID", "").strip()
GRAPH = "https://graph.instagram.com"


def get(path, **params):
    params["access_token"] = TOKEN
    r = requests.get(f"{GRAPH}/{path}", params=params, timeout=60)
    return r.json()


print("=" * 60)
print("[1] 계정 기본 정보")
print("=" * 60)
acc = get(USER_ID, fields="username,followers_count,follows_count,media_count")
print(f"  @{acc.get('username')} | 팔로워 {acc.get('followers_count')} | 팔로잉 {acc.get('follows_count')} | 게시물 {acc.get('media_count')}")

print()
print("=" * 60)
print("[2] 계정 인사이트 (최근 30일)")
print("=" * 60)
for metric, period in [("reach", "day"), ("profile_views", "day"), ("accounts_engaged", "day"), ("views", "day")]:
    j = get(f"{USER_ID}/insights", metric=metric, period=period,
            metric_type="total_value", timeframe="last_30_days" if metric == "views" else None)
    if "data" in j and j["data"]:
        for d in j["data"]:
            tv = d.get("total_value", {}).get("value")
            print(f"  {d.get('name')}: {tv}")
    else:
        print(f"  {metric}: (조회 실패) {j.get('error', {}).get('message', '')[:100]}")

print()
print("=" * 60)
print("[3] 최근 게시물 25개 성과")
print("=" * 60)
media = get(f"{USER_ID}/media",
            fields="id,caption,media_type,media_product_type,timestamp,like_count,comments_count",
            limit=25)
rows = media.get("data", [])
print(f"  (총 {len(rows)}개 조회)")
print()

for m in rows:
    mid = m["id"]
    cap = (m.get("caption") or "").split("\n")[0][:40]
    mtype = m.get("media_product_type") or m.get("media_type")
    ts = (m.get("timestamp") or "")[:10]
    likes = m.get("like_count", 0)
    comments = m.get("comments_count", 0)

    # 게시물별 인사이트
    if mtype == "REELS":
        metrics = "reach,saved,shares,likes,comments,views,total_interactions"
    else:
        metrics = "reach,saved,shares,views,total_interactions,profile_visits,follows"
    ins = get(f"{mid}/insights", metric=metrics)
    vals = {}
    if "data" in ins:
        for d in ins["data"]:
            v = d.get("values", [{}])[0].get("value")
            vals[d.get("name")] = v
    else:
        # 일부 메트릭 미지원 시 최소셋 재시도
        ins2 = get(f"{mid}/insights", metric="reach,saved,shares")
        for d in ins2.get("data", []):
            v = d.get("values", [{}])[0].get("value")
            vals[d.get("name")] = v
        if "error" in ins2:
            vals["error"] = ins2["error"].get("message", "")[:80]

    reach = vals.get("reach", "?")
    saved = vals.get("saved", "?")
    shares = vals.get("shares", "?")
    views = vals.get("views", vals.get("plays", ""))
    pv = vals.get("profile_visits", "")
    fol = vals.get("follows", "")
    print(f"  [{ts}] {mtype:<8} 도달={reach} 저장={saved} 공유={shares} 조회={views} 좋아요={likes} 댓글={comments} 프로필방문={pv} 팔로우={fol}")
    print(f"          └ {cap}")

print()
print("완료 — 발행/변경 없음 (읽기 전용)")
