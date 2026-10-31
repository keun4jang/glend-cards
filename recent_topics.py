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
# 2026-10-19: 0.6 → 0.55. 10/6 "수면마취 의원 제세동기 미보유" 릴스 2편이 0.59로 빠져나가 같은 날 두 번 나갔다.
# 아카이브 134개 주제(14일 이내 쌍 3,592개) 백테스트: 0.55~0.6에 새로 걸리는 건 이 쌍과
# "신혼부부 전세자금 대출이자 지원"(도시만 다름, 0.57), "수면 부족·고혈압"(8일 간격, 0.55) — 시청자에겐 사실상 반복이다.
# 티빙/카카오게임즈(0.54)는 여전히 통과한다.
DUP_THRESHOLD = 0.55


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
    return same_subject(topic)


# 같은 소재 반복 — 2-gram 비율로는 각도만 바꾼 같은 소재를 못 잡는다.
# 10/30 하루에 "갤럭시 워치 수면 무호흡 기능"과 "수면무호흡증 방치 시 심근경색" 릴스가 둘 다 나갔다(겹침 비율 낮음).
# 그래서 최근 SAME_SUBJECT_DAYS일 주제와 군더더기 말을 뺀 뒤 5글자 이상 이어서 같으면 같은 소재로 본다.
# 2026-02~10 아카이브 164개 백테스트(3일 창): 걸린 6쌍이 전부 사실상 반복
# (KB쓰담적금·제세동기 미보유·사랑상품권 추가 환급·수면무호흡·영양 불균형·대출이자 지원).
SAME_SUBJECT_DAYS = 3
SAME_SUBJECT_LEN = 5
_FILLER = ["에따른", "따른", "효과와", "올바른", "급증과", "급증", "관리법", "대처법", "방법", "기준", "주의",
           "안내", "증가", "위험", "필수", "실태와", "실태", "및"]


def _core(t):
    t = re.sub(r"[^가-힣A-Za-z0-9]", "", t or "")
    for w in sorted(_FILLER, key=len, reverse=True):
        t = t.replace(w, "|")
    return t


def _common_run(a, b):
    """a와 b에 공통으로 이어서 나오는 가장 긴 글자열('|'는 넘지 않는다)."""
    best = ""
    for i in range(len(a)):
        j = i + len(best) + 1
        while j <= len(a) and "|" not in a[i:j] and a[i:j] in b:
            best = a[i:j]
            j += 1
    return best


def same_subject(topic):
    try:
        recent = _archive_topics(SAME_SUBJECT_DAYS)
    except Exception:
        return ""
    a = _core(topic)
    for r in recent:
        if r != topic and len(_common_run(a, _core(r))) >= SAME_SUBJECT_LEN:
            return r
    return ""


# 당파적 정치 주제 — 생활정보 채널에 정치색이 묻으면 팔로우 이유가 흐려지고 반감을 산다.
# 사건사고 검색어("사건 OR 사고 OR 논란")에 정치 기사가 섞여 들어와 2026-10-14 릴스가
# "국민의힘 선거법 위반 397억 반환 위기"로 나갔다. 정부 정책·지원금 소식은 막지 않는다
# (그래서 "대통령", "정부", "국회" 단독은 목록에 없다 — 아카이브 122편 백테스트에서 오탐 0, 적중 1).
POLITICAL = re.compile(r"국민의힘|더불어민주당|민주당|조국혁신당|개혁신당|정의당|진보당|여당|야당|정당|당대표|"
                       r"원내대표|국회의원|대선|총선|지방선거|선거법|선거|공천|탄핵|특검|윤석열|이재명|김건희|한동훈|이준석")


def political_hit(d):
    """주제·제목·캡션 앞부분에서 당파적 정치 단어를 찾아 돌려준다(없으면 빈 문자열)."""
    text = " ".join([d.get("topic") or "", d.get("title") or "",
                     re.sub(r"<[^>]+>", "", d.get("caption") or "")[:300]])
    m = POLITICAL.search(text)
    return m.group(0) if m else ""


def political_correction(word):
    return (f"\n\n[매우 중요] 직전 응답이 거절됐다: 정치 주제다('{word}'). 이 채널은 정치 중립 생활정보 채널이라 "
            "정당·선거·정치인 관련 뉴스는 다루지 않는다. 뉴스 목록에서 생활에 직접 도움이 되는 다른 사안을 골라라.")


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
