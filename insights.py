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

# 프로필 본문은 별도 요청으로 가져온다 — 계정 종류에 따라 지원 안 되는 필드가
# 섞이면 요청 전체가 실패해서, 위의 기본 정보까지 같이 날아가기 때문이다.
prof = get(USER_ID, fields="biography,website")
if "error" not in prof:
    bio = (prof.get("biography") or "").strip()
    print(f"  바이오: {bio if bio else '(비어 있음)'}")
    print(f"  링크: {prof.get('website') or '(없음)'}")
else:
    print(f"  (프로필 본문 조회 실패: {prof['error'].get('message','')[:60]})")

# 팔로잉이 팔로워보다 많으면 프로필 방문자에게 '팔로우 품앗이 계정'으로 읽혀
# 팔로우 전환을 직접 깎는다. 방문자가 가장 먼저 보는 숫자라 영향이 크다.
_fr = acc.get("followers_count") or 0
_fg = acc.get("follows_count") or 0
if _fg > _fr:
    print(f"  [⚠️ 계정 위생] 팔로잉({_fg}) > 팔로워({_fr}) — 방문자에게 저품질 계정으로 보여 전환을 깎습니다.")

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

# 깔때기 누적 — 게시물별 수치는 원래도 찍혔지만 합산을 안 해서,
# "프로필까지 온 사람 중 몇 %가 팔로우했는가"를 아무도 본 적이 없었다.
# 2026-09-14에 CSV로 직접 세어보니 누적 프로필방문 292 → 팔로우 6 (2.1%)였다.
# 콘텐츠가 아니라 프로필이 병목이라는 신호라, 상시로 보이게 만든다.
funnel = {"reach": 0, "pv": 0, "follows": 0, "n": 0}


def _num(v):
    return v if isinstance(v, (int, float)) else 0

for m in rows:
    mid = m["id"]
    cap = (m.get("caption") or "").split("\n")[0][:40]
    mtype = m.get("media_product_type") or m.get("media_type")
    ts = (m.get("timestamp") or "")[:10]
    likes = m.get("like_count", 0)
    comments = m.get("comments_count", 0)

    # 게시물별 인사이트
    # 릴스는 profile_visits/follows를 API가 지원하지 않는다(탐침으로 확인).
    # 지원 안 되는 지표를 섞으면 요청 전체가 실패해 최소셋으로 폴백되므로 분리한다.
    if mtype == "REELS":
        metrics = ("reach,saved,shares,likes,comments,views,total_interactions,"
                   "ig_reels_avg_watch_time,ig_reels_video_view_total_time")
    else:
        metrics = ("reach,saved,shares,views,total_interactions,"
                   "profile_visits,follows,profile_activity")
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
    # 시청 완주율 — 릴스 길이 A/B(60초 vs 90초)의 유일한 판정 변수.
    # 수집만 하고 출력하지 않아서 지금까지 한 번도 눈에 보인 적이 없었다.
    wt = vals.get("ig_reels_avg_watch_time", "")
    wt_s = f" 평균시청={int(wt)/1000:.1f}초" if isinstance(wt, (int, float)) and wt else ""
    print(f"  [{ts}] {mtype:<8} 도달={reach} 저장={saved} 공유={shares} 조회={views} 좋아요={likes} 댓글={comments} 프로필방문={pv} 팔로우={fol}{wt_s}")
    print(f"          └ {cap}")

    # 릴스는 profile_visits/follows를 API가 아예 안 주므로 깔때기에서 뺀다.
    # (릴스를 섞으면 분모만 커지고 분자는 0이라 전환율이 가짜로 낮아진다)
    if mtype != "REELS":
        funnel["reach"] += _num(reach)
        funnel["pv"] += _num(pv)
        funnel["follows"] += _num(fol)
        funnel["n"] += 1

print()
print("=" * 60)
print("[4] 팔로우 깔때기 (카드뉴스 기준 — 릴스는 API가 전환을 측정 못 함)")
print("=" * 60)
if funnel["n"] == 0:
    print("  (이번 25개에 카드뉴스가 없어 측정 불가)")
else:
    r, p, f = funnel["reach"], funnel["pv"], funnel["follows"]
    pv_rate = f"{p / r * 100:.1f}%" if r else "-"
    fo_rate = f"{f / p * 100:.1f}%" if p else "-"
    print(f"  카드뉴스 {funnel['n']}개: 도달 {r:.0f} → 프로필방문 {p:.0f} ({pv_rate}) → 팔로우 {f:.0f} ({fo_rate})")
    # 판정: 방문은 생기는데 팔로우가 안 나오면 콘텐츠가 아니라 프로필이 병목이다.
    # 건강한 계정은 방문→팔로우가 보통 5~15%.
    if p >= 20 and f / p < 0.05:
        print(f"  [⚠️ 프로필 병목] 프로필까지 {p:.0f}명이 왔는데 팔로우는 {f:.0f}명({fo_rate})입니다.")
        print("     콘텐츠는 사람을 데려오고 있으니, 바이오·고정게시물·하이라이트를 손봐야 합니다.")
    elif p < 20:
        print("  (표본이 적어 판정 보류 — 프로필 방문 20 이상 쌓인 뒤 보세요)")
    else:
        print("  프로필 전환은 정상 범위입니다. 병목은 도달 쪽입니다.")

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
