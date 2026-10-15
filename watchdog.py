"""
발행 감시 에이전트 — 문제가 생기면 텔레그램으로 알린다(읽기 전용, 아무것도 발행하지 않음).

왜 필요한가:
  2026-10-12~13에 릴스 3편이 연속으로 발행되지 못했는데(edge-tts 403 2건, 5시간 멈춤 1건)
  알림이 없어 이틀 뒤 수동 점검에서야 알았다. 무인 운영이라 "조용한 실패"가 가장 위험하다.

두 겹으로 지킨다:
  1) 각 워크플로 마지막 단계가 실패·취소 즉시 텔레그램을 보낸다(워크플로 파일에 있음).
  2) 이 스크립트가 주기적으로 인스타에 실제로 글이 올라갔는지 본다 — 워크플로가 아예 안 돌았거나
     (예약 비활성화·러너 장애) 성공으로 끝났는데 게시가 안 된 경우까지 잡는다.

모드(WATCH_MODE):
  check   : 이상할 때만 알린다(기본, 6시간마다)
  summary : 매일 아침 지난 24시간 요약을 보낸다(감시가 살아 있다는 신호 겸)
  test    : 연결 테스트 메시지 한 통

필요한 시크릿: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (없으면 콘솔에만 찍고 넘어간다)
"""
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

GRAPH = (os.getenv("IG_GRAPH_BASE") or "https://graph.instagram.com").rstrip("/")
IG_TOKEN = os.getenv("IG_TOKEN", "").strip()
IG_USER_ID = os.getenv("IG_USER_ID", "").strip()
REPO = os.getenv("GITHUB_REPOSITORY", "keun4jang/glend-cards")
GH_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
KST = dt.timezone(dt.timedelta(hours=9))

# 기준: 정상 간격보다 넉넉하게 — 한 편 실패는 워크플로 실패 알림이 즉시 잡고,
# 여기서는 "하루 넘게 아무것도 안 올라감" 같은 전면 중단을 잡는다.
# 릴스는 하루 2편(실제 발행 약 17~19시·24~01시 KST)이라 정상 최대 간격이 18~20시간,
# 카드는 월·수·금이라 금→월 72시간이 정상 최대다.
REEL_MAX_H = float(os.getenv("REEL_MAX_H", "26"))
CARD_MAX_H = float(os.getenv("CARD_MAX_H", "80"))


def send(text):
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    print(text)
    if not token or not chat:
        print("[watchdog] TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID 미설정 — 콘솔 출력만 함")
        return False
    data = urllib.parse.urlencode({"chat_id": chat, "text": text,
                                   "disable_web_page_preview": "true"}).encode()
    try:
        urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage",
                               data=data, timeout=20)
        return True
    except urllib.error.HTTPError as e:
        # 텔레그램이 돌려준 사유만 남긴다(URL에 토큰이 있어 예외 전체를 찍지 않는다).
        try:
            desc = json.loads(e.read().decode("utf-8")).get("description", "")
        except Exception:
            desc = ""
        hint = {401: "토큰이 틀림 — @BotFather가 준 값 그대로(앞에 'bot' 붙이지 않기)",
                404: "토큰 형식이 틀림 — 공백·줄바꿈·'bot' 접두어 확인",
                400: "채팅 ID가 틀렸거나, 봇에게 먼저 아무 메시지를 보내 대화를 시작하지 않음",
                403: "봇이 차단됐거나 그룹에서 내보내짐"}.get(e.code, "")
        print(f"[watchdog] 텔레그램 전송 실패: HTTP {e.code} {desc} {('— ' + hint) if hint else ''}")
        return False
    except Exception as e:                       # 토큰이 메시지에 섞이지 않게 종류만 남긴다
        print(f"[watchdog] 텔레그램 전송 실패: {e.__class__.__name__}")
        return False


def _get_json(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def ig_media(limit=30):
    q = urllib.parse.urlencode({"fields": "timestamp,media_product_type,caption",
                                "limit": limit, "access_token": IG_TOKEN})
    return _get_json(f"{GRAPH}/{IG_USER_ID}/media?{q}").get("data", [])


def ig_followers():
    q = urllib.parse.urlencode({"fields": "followers_count", "access_token": IG_TOKEN})
    return _get_json(f"{GRAPH}/{IG_USER_ID}?{q}").get("followers_count")


def split_failures(runs):
    """실패·취소 실행을 (아직 문제, 이미 해결됨)으로 나눈다.

    같은 워크플로가 그 뒤에 성공했다면 이미 해결된 것으로 본다. 첫 요약(10/15)이
    연결 테스트 실패 2건과 Pages의 자동 취소(10초 뒤 새 배포가 성공) 1건으로 ⚠️를 띄웠다 —
    전부 해결된 것이었다. 겁주는 요약은 진짜 알림을 무시하게 만든다.
    """
    open_, resolved = [], []
    for r in runs:
        if r.get("conclusion") not in ("failure", "cancelled", "timed_out"):
            continue
        later_ok = any(o["name"] == r["name"] and o.get("conclusion") == "success"
                       and o["created_at"] > r["created_at"] for o in runs)
        (resolved if later_ok else open_).append((r["name"], r.get("conclusion"), r["html_url"]))
    return open_, resolved


def gh_runs_since(since):
    """지난 기간 GitHub Actions 실행 목록(없으면 None)."""
    if not GH_TOKEN:
        return None
    q = urllib.parse.urlencode({"per_page": 100, "created": f">={since:%Y-%m-%dT%H:%M:%SZ}"})
    data = _get_json(f"https://api.github.com/repos/{REPO}/actions/runs?{q}",
                     {"Authorization": f"Bearer {GH_TOKEN}", "Accept": "application/vnd.github+json"})
    return data.get("workflow_runs", [])


def _ts(m):
    return dt.datetime.fromisoformat(m["timestamp"].replace("+0000", "+00:00"))


def newest(media, reels):
    ts = [_ts(m) for m in media if (m.get("media_product_type") == "REELS") == reels]
    return max(ts) if ts else None


def check(media, now):
    """이상 징후 목록(정상이면 빈 목록)."""
    problems = []
    for label, reels, limit in (("릴스", True, REEL_MAX_H), ("카드뉴스", False, CARD_MAX_H)):
        last = newest(media, reels)
        if last is None:
            problems.append(f"{label}: 최근 게시물을 찾지 못함")
            continue
        age = (now - last).total_seconds() / 3600
        if age > limit:
            problems.append(f"{label}: 마지막 발행 {age:.0f}시간 전 "
                            f"({last.astimezone(KST):%m/%d %H:%M} KST) — 기준 {limit:.0f}시간 초과")
    return problems


def main():
    mode = (os.getenv("WATCH_MODE") or "check").strip().lower()
    now = dt.datetime.now(dt.timezone.utc)

    if mode == "test":
        ok = send("✅ GLEND 감시 봇 연결 테스트 — 이 메시지가 보이면 알림이 정상 동작합니다.")
        sys.exit(0 if ok else 1)

    try:
        media = ig_media()
    except Exception as e:
        send(f"🚨 GLEND 감시: 인스타 API 호출 실패({e.__class__.__name__}).\n"
             "토큰 만료·권한 문제일 수 있어요. Refresh Instagram Token 워크플로를 확인하세요.")
        return

    problems = check(media, now)

    if mode == "summary":
        since = now - dt.timedelta(hours=24)
        recent = [m for m in media if _ts(m) >= since]
        n_reel = sum(1 for m in recent if m.get("media_product_type") == "REELS")
        n_card = len(recent) - n_reel
        try:
            runs = gh_runs_since(since)
        except Exception as e:
            runs = None
            print(f"[watchdog] GitHub 실행 기록 조회 실패: {e.__class__.__name__}")
        fails, resolved = split_failures(runs) if runs is not None else (None, [])
        try:
            followers = ig_followers()
        except Exception:
            followers = None
        lines = [f"{'⚠️' if (problems or fails) else '☀️'} GLEND 일일 요약 ({now.astimezone(KST):%m/%d})",
                 f"지난 24시간 발행: 릴스 {n_reel} · 카드 {n_card}"
                 + ("" if n_card or now.astimezone(KST).weekday() in (0, 2, 4)
                    else " (카드는 월·수·금 발행)")]
        if followers is not None:
            lines.append(f"팔로워 {followers}")
        if fails is None:
            lines.append("실행 실패: (조회 불가)")
        elif fails:
            lines.append(f"실행 실패·취소 {len(fails)}건:")
            lines += [f"- {name}: {concl}\n  {url}" for name, concl, url in fails[:5]]
        else:
            lines.append("실행 실패: 0건")
        if resolved:
            lines.append(f"(이후 정상화된 실패·취소 {len(resolved)}건은 제외)")
        if problems:
            lines.append("이상 징후:")
            lines += [f"- {p}" for p in problems]
        send("\n".join(lines))
        return

    if problems:
        send("🚨 GLEND 발행 중단 의심\n" + "\n".join(f"- {p}" for p in problems) +
             f"\nhttps://github.com/{REPO}/actions")
    else:
        print("[watchdog] 이상 없음")


if __name__ == "__main__":
    main()
