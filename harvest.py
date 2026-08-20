"""
인스타그램에 이미 올라간 게시물 전량을 회수해 CSV로 보관 (1회성 + 반복 실행 가능).

왜 필요한가:
  게시물 374개를 올렸지만 대본·캡션이 저장소에 하나도 남지 않았다(media 브랜치가
  매일 덮어써짐). 영상 원본은 못 살리지만, **캡션 본문과 성과 수치**는 인스타 API로
  지금 회수할 수 있다. 이게 "어떤 주제·각도가 먹혔는가"를 배울 유일한 재료이고,
  검색 자산(정적 사이트) 발행의 원료다.

  insights.py는 limit=25로 최근 것만 본다. 여기서는 페이징으로 전량을 긁는다.

출력: archive/instagram_posts.csv  (중복은 id 기준으로 갱신)
"""
import csv
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("IG_TOKEN", "").strip()
USER_ID = os.getenv("IG_USER_ID", "").strip()
GRAPH = (os.getenv("IG_GRAPH_BASE") or "https://graph.instagram.com").rstrip("/")

BASE = Path(__file__).parent
OUT = BASE / "archive" / "instagram_posts.csv"

FIELDS = ["id", "timestamp", "media_product_type", "media_type", "permalink",
          "like_count", "comments_count", "caption"]
METRIC_FIELDS = ["reach", "saved", "shares", "views", "total_interactions",
                 "profile_visits", "follows",
                 "ig_reels_avg_watch_time", "ig_reels_video_view_total_time"]


def get(path, **params):
    params["access_token"] = TOKEN
    for attempt in range(1, 4):
        try:
            r = requests.get(f"{GRAPH}/{path}", params=params, timeout=60)
            j = r.json()
            if "error" in j and j["error"].get("is_transient"):
                raise RuntimeError(j["error"].get("message", "transient"))
            return j
        except Exception as e:
            if attempt == 3:
                return {"error": {"message": str(e)}}
            time.sleep(3 * attempt)


def fetch_all_media(max_pages=60):
    """페이징으로 전량 수집. insights.py의 limit=25와 달리 끝까지 간다."""
    rows, url_params = [], {"fields": ",".join(FIELDS), "limit": 50}
    path = f"{USER_ID}/media"
    for page in range(1, max_pages + 1):
        j = get(path, **url_params)
        data = j.get("data", [])
        rows.extend(data)
        print(f"  {page}페이지: {len(data)}개 (누적 {len(rows)})", flush=True)
        nxt = (j.get("paging") or {}).get("cursors", {}).get("after")
        if not data or not nxt:
            break
        url_params["after"] = nxt
        time.sleep(0.4)          # 무료 티어 레이트리밋 여유
    return rows


# 탐침(harvest.py --probe) 결과 확인된 지원 지표:
#   REELS: reach saved shares likes comments views total_interactions
#          ig_reels_avg_watch_time ig_reels_video_view_total_time
#          (profile_visits/follows는 릴스에서 API가 지원하지 않음)
#   FEED : reach saved shares views total_interactions profile_visits follows profile_activity
# 지원 안 되는 지표를 하나라도 섞으면 요청 전체가 실패해 최소셋으로 폴백된다.
def fetch_metrics(media_id, product_type):
    if product_type == "REELS":
        metrics = ("reach,saved,shares,likes,comments,views,total_interactions,"
                   "ig_reels_avg_watch_time,ig_reels_video_view_total_time")
    else:
        metrics = ("reach,saved,shares,views,total_interactions,"
                   "profile_visits,follows,profile_activity")
    j = get(f"{media_id}/insights", metric=metrics)
    vals = {}
    for d in j.get("data", []):
        v = d.get("values", [{}])[0].get("value")
        vals[d.get("name")] = v
    if "data" not in j:           # 일부 메트릭 미지원 계정 대비 최소셋 재시도
        j2 = get(f"{media_id}/insights", metric="reach,saved,shares")
        for d in j2.get("data", []):
            vals[d.get("name")] = d.get("values", [{}])[0].get("value")
    return vals


def load_existing():
    if not OUT.exists():
        return {}
    with OUT.open(encoding="utf-8") as f:
        return {r["id"]: r for r in csv.DictReader(f)}


def main():
    if not TOKEN or not USER_ID:
        print("[중단] IG_TOKEN / IG_USER_ID 없음")
        sys.exit(1)
    with_metrics = "--no-metrics" not in sys.argv

    print("게시물 목록 수집 중 (페이징)...", flush=True)
    media = fetch_all_media()
    print(f"총 {len(media)}개 확보\n", flush=True)

    existing = load_existing()
    print(f"기존 CSV: {len(existing)}개", flush=True)

    out_rows = dict(existing)
    for i, m in enumerate(media, 1):
        row = {k: m.get(k, "") for k in FIELDS}
        row["caption"] = (row.get("caption") or "").replace("\r", " ")
        if with_metrics:
            vals = fetch_metrics(m["id"], m.get("media_product_type"))
            for k in METRIC_FIELDS:
                row[k] = vals.get(k, "")
            if i % 20 == 0:
                print(f"  성과 수집 {i}/{len(media)}", flush=True)
            time.sleep(0.3)
        else:
            for k in METRIC_FIELDS:
                row.setdefault(k, existing.get(m["id"], {}).get(k, ""))
        out_rows[m["id"]] = row

    OUT.parent.mkdir(parents=True, exist_ok=True)
    cols = FIELDS + METRIC_FIELDS
    with OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in sorted(out_rows.values(), key=lambda x: x.get("timestamp", ""), reverse=True):
            w.writerow(r)
    print(f"\n저장 완료: {OUT} ({len(out_rows)}개)", flush=True)


def probe():
    """어떤 지표가 실제로 되는지 API에 하나씩 물어본다.

    릴스의 profile_visits/follows/ig_reels_avg_watch_time이 전부 빈값으로 와서,
    '전환 0'인지 '측정 불가'인지 구분이 안 됐다. 지표를 하나씩 단독 요청해
    성공/실패와 오류 메시지를 그대로 찍는다.
    """
    candidates = [
        "reach", "saved", "shares", "likes", "comments", "views", "plays",
        "total_interactions", "profile_visits", "follows", "profile_activity",
        "ig_reels_avg_watch_time", "ig_reels_video_view_total_time",
        "avg_watch_time", "video_views", "clips_replays_count",
        "ig_reels_aggregated_all_plays_count", "navigation", "impressions",
    ]
    media = fetch_all_media(max_pages=2)
    samples = {}
    for m in media:
        t = "REELS" if m.get("media_product_type") == "REELS" else "FEED"
        if t not in samples:
            samples[t] = m
        if len(samples) == 2:
            break
    for t, m in samples.items():
        print(f"\n=== {t} (id {m['id']}, {m.get('timestamp','')[:10]}) ===", flush=True)
        for c in candidates:
            j = get(f"{m['id']}/insights", metric=c)
            if "data" in j and j["data"]:
                v = j["data"][0].get("values", [{}])[0].get("value")
                tv = j["data"][0].get("total_value", {}).get("value")
                print(f"  ✅ {c:36} = {v if v is not None else tv}", flush=True)
            else:
                err = (j.get("error") or {}).get("message", "")[:88]
                print(f"  ❌ {c:36} {err}", flush=True)
            time.sleep(0.25)


if __name__ == "__main__":
    if "--probe" in sys.argv:
        probe()
    else:
        main()
