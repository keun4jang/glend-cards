"""
계정 성장 진단용 인사이트 수집 스크립트 (읽기 전용 — 아무것도 발행하지 않음).
GitHub Actions에서 IG_TOKEN/IG_USER_ID로 실행. 로그 출력 + reports/에 마크다운 리포트 저장.
"""
import os
import datetime
import requests
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("IG_TOKEN", "").strip()
USER_ID = os.getenv("IG_USER_ID", "").strip()
GRAPH = (os.getenv("IG_GRAPH_BASE") or "https://graph.instagram.com").rstrip("/")

_report_lines = []


def print(*args, **kwargs):  # noqa: A001 — 로그와 리포트에 동시 기록
    import builtins
    builtins.print(*args, **kwargs)
    _report_lines.append(" ".join(str(a) for a in args))


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
# 주의: timeframe을 빼면 period="day"라서 "하루치"가 온다.
# 예전엔 views에만 붙어 있어서, 리포트 헤더는 30일인데 reach/profile_views/accounts_engaged는
# 하루치가 찍혔다(30일 도달 74인데 그 안에 도달 1097 릴스가 있는 모순의 원인).
for metric in ["reach", "profile_views", "accounts_engaged", "views"]:
    j = get(f"{USER_ID}/insights", metric=metric, period="day",
            metric_type="total_value", timeframe="last_30_days")
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
        # 릴스는 비팔로워에게 닿는 유일한 포맷인데 정작 팔로우 퍼널(profile_visits/follows)을
        # 한 번도 수집하지 않았다. 시청 완주율도 없어서 러닝타임 판단 근거가 없었다.
        metrics = ("reach,saved,shares,likes,comments,views,total_interactions,"
                   "profile_visits,follows,ig_reels_avg_watch_time")
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
# 토큰 만료 임박 경고 (자동 갱신이 실패해도 리포트에서 눈에 띄게)
try:
    dbg = requests.get(f"{GRAPH}/access_token",
                       params={"fields": "expires_at", "access_token": TOKEN}, timeout=30).json()
except Exception:
    dbg = {}
exp = dbg.get("expires_at") or dbg.get("data", {}).get("expires_at")
if exp:
    import datetime as _dt
    left = (_dt.datetime.fromtimestamp(int(exp)) - _dt.datetime.now()).days
    if left < 14:
        print(f"[🚨 경고] IG_TOKEN 만료까지 {left}일 — 자동 갱신 워크플로우(Refresh Instagram Token)를 확인하세요!")
    else:
        print(f"[토큰] 만료까지 약 {left}일 (주 2회 자동 갱신 중)")
else:
    print("[토큰] 만료일 확인 불가 — 자동 갱신 워크플로우 실행 이력을 확인하세요.")
print()
print("완료 — 발행/변경 없음 (읽기 전용)")

# 리포트 파일 저장 (주간 비교용)
os.makedirs("reports", exist_ok=True)
today = datetime.date.today().isoformat()
path = f"reports/insights_{today}.md"
with open(path, "w", encoding="utf-8") as f:
    f.write(f"# GLEND 주간 인사이트 리포트 ({today})\n\n```\n")
    f.write("\n".join(_report_lines))
    f.write("\n```\n")
import builtins
builtins.print(f"리포트 저장: {path}")
