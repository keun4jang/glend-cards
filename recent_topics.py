"""
최근 발행한 주제 목록 조회 — 카드/릴스가 같은(비슷한) 주제를 반복 발행하는 것 방지.
media 브랜치에 올라간 content_*.json / reel_content_*.json 의 topic을 읽어온다.
실패해도 빈 목록 반환 (파이프라인을 막지 않음).
"""
import requests

RAW = "https://raw.githubusercontent.com/keun4jang/glend-cards/media"
FILES = ["content_1.json", "reel_content_1.json", "reel_content_2.json", "reel_content_3.json"]


def get_recent_topics():
    topics = []
    for fn in FILES:
        try:
            r = requests.get(f"{RAW}/{fn}", timeout=15)
            if r.status_code == 200:
                t = (r.json().get("topic") or "").strip()
                if t:
                    topics.append(t)
        except Exception:
            pass
    return topics


def avoid_line():
    """프롬프트에 넣을 회피 지시문 (최근 주제가 없으면 빈 문자열)"""
    topics = get_recent_topics()
    if not topics:
        return ""
    joined = " / ".join(dict.fromkeys(topics))
    return f"\n- 중요: 최근에 이미 다룬 주제 목록이야 — {joined}. 이것들과 같거나 사실상 겹치는 주제는 절대 고르지 마. 다른 새로운 주제를 골라."
