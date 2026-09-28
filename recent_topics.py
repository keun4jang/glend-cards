"""
최근 발행한 주제 목록 조회 — 카드/릴스가 같은(비슷한) 주제를 반복 발행하는 것 방지.

주 출처는 main의 archive/ (최근 WINDOW_DAYS일, 카드·릴스 전부).
예전엔 media 브랜치의 content_*.json만 읽었는데, media는 매 실행 덮어써서
카테고리당 "직전 1개"만 남는다. 그래서 창이 사실상 하루였고, 실제로
KB쓰담적금(3일 만에), 건강보험 환급금(9일 새 3번), 퇴직연금 국채(카드→릴스)가 반복 발행됐다.
media는 archive가 비어 있을 때(로컬 첫 실행 등)의 보조 출처로만 남긴다.
실패해도 빈 목록 반환 (파이프라인을 막지 않음).
"""
import datetime
import json
import re
from pathlib import Path

import requests

RAW = "https://raw.githubusercontent.com/keun4jang/glend-cards/media"
FILES = ["content_1.json", "reel_content_1.json", "reel_content_2.json", "reel_content_3.json"]
ARCHIVE_DIR = Path(__file__).parent / "archive"
WINDOW_DAYS = 14
MAX_TOPICS = 40
# 글자 2-gram 겹침 비율(짧은 쪽 기준). 8~9월 아카이브에서 실제 반복 발행 쌍은 0.67~0.86,
# 다른 사건인데 분야만 같은 쌍(티빙 vs 카카오게임즈 개인정보 유출)은 0.54 이하였다.
DUP_THRESHOLD = 0.6


def _archive_topics(days=WINDOW_DAYS):
    today = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)).date()
    cutoff = (today - datetime.timedelta(days=days)).isoformat()
    topics = []
    # 파일명이 YYYY-MM-DD-... 라 이름 역순 = 최신순
    for f in sorted(ARCHIVE_DIR.glob("*/*.json"), key=lambda p: p.name, reverse=True):
        if f.name[:10] < cutoff:
            break
        try:
            t = (json.loads(f.read_text(encoding="utf-8")).get("topic") or "").strip()
        except Exception:
            continue
        if t:
            topics.append(t)
    return topics


def _media_topics():
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


def get_recent_topics():
    try:
        topics = _archive_topics()
    except Exception:
        topics = []
    if not topics:
        topics = _media_topics()
    return list(dict.fromkeys(topics))[:MAX_TOPICS]


def _bigrams(s):
    s = re.sub(r"[^가-힣A-Za-z0-9]", "", s or "")
    return {s[i:i + 2] for i in range(len(s) - 1)}


def find_duplicate(topic, recent):
    """topic과 사실상 같은 최근 주제를 돌려준다(없으면 빈 문자열).

    프롬프트에 "겹치지 마"라고만 적었을 땐 모델이 무시하고 같은 뉴스를 또 골랐다.
    카드4 저장 검증과 같은 이유로, 적는 대신 실제로 센다.
    """
    a = _bigrams(topic)
    if not a:
        return ""
    for r in recent:
        b = _bigrams(r)
        if b and len(a & b) / min(len(a), len(b)) >= DUP_THRESHOLD:
            return r
    return ""


def dup_correction(topic, dup):
    return (f"\n\n[매우 중요] 직전 응답이 거절됐다: 고른 주제 '{topic}'가 최근에 이미 발행한 "
            f"'{dup}'와 사실상 같다. 뉴스 목록에서 **다른 사안**을 골라 처음부터 다시 써라. "
            "같은 제도·같은 사건을 표현만 바꾼 것도 안 된다.")


def avoid_line(topics=None):
    """프롬프트에 넣을 회피 지시문 (최근 주제가 없으면 빈 문자열)"""
    if topics is None:
        topics = get_recent_topics()
    if not topics:
        return ""
    joined = " / ".join(topics)
    return f"\n- 중요: 최근 {WINDOW_DAYS}일 안에 이미 다룬 주제 목록이야 — {joined}. 이것들과 같거나 사실상 겹치는 주제는 절대 고르지 마. 다른 새로운 주제를 골라."
