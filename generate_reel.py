import os
import json
import sys
import time
import random
import urllib.parse
import requests
import feedparser
from dotenv import load_dotenv
from google import genai

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY", "").strip())
PEXELS_KEY = os.getenv("PEXELS_API_KEY", "").strip()

POST_INDEX = sys.argv[1] if len(sys.argv) > 1 else "1"

# 1) 카테고리 결정 — 1번=경제, 2번=사건사고, 3번=건강
ECONOMY_QUERIES = [
    "정부지원금 OR 환급 OR 세금 혜택 OR 신청 마감 when:1d",
    "금리 OR 예금 OR 적금 OR 대출 조건 when:1d",
    "부동산 OR 청약 OR 전세 OR 임대 when:1d",
    "카드혜택 OR 재테크 OR 절약 OR 연말정산 when:1d",
]
INCIDENT_QUERY = "사건 OR 사고 OR 논란 OR 충격 when:1d"
HEALTH_QUERY = "다이어트 OR 영양 OR 수면 OR 건강관리 when:1d"

CATEGORY = {"1": "economy", "2": "incident", "3": "health"}.get(POST_INDEX, "economy")
if CATEGORY == "incident":
    QUERY = INCIDENT_QUERY
elif CATEGORY == "health":
    QUERY = HEALTH_QUERY
else:
    QUERY = ECONOMY_QUERIES[random.randint(0, len(ECONOMY_QUERIES) - 1)]

url = "https://news.google.com/rss/search?q=" + urllib.parse.quote(QUERY) + "&hl=ko&gl=KR&ceid=KR:ko"
print(f"[릴스 {POST_INDEX}/{CATEGORY}] 뉴스 수집 중... (카테고리: {QUERY[:20]})")
feed = feedparser.parse(url)
headlines = [e.title for e in feed.entries[:25]]
print(f"  뉴스 {len(headlines)}개 확보\n")

news_text = "\n".join(f"- {h}" for h in headlines)

# 2) 카테고리별 페르소나
if CATEGORY == "health":
    PERSONA = "너는 'GLEND'라는 건강 실전 꿀팁 인스타그램 릴스 채널의 전문 작가야. 15~22초 안에 빠르게 핵심을 전달한다."
    TOPIC_DESC = "오늘의 최신 건강 관련 뉴스 제목 목록"
    HOOK = '"~하면 몸 망친다" 류의 경각심 자극형'
    QEX = '"morning stretching", "healthy meal prep", "sleeping bedroom night"'
elif CATEGORY == "incident":
    PERSONA = "너는 'GLEND'라는 트렌드 인스타그램 릴스 채널의 전문 작가야. 자극적·공감형 사건·사고·논란을 15~22초 안에 빠르게 전한다."
    TOPIC_DESC = "오늘의 최신 사건·사고·논란 관련 뉴스 제목 목록"
    HOOK = '질문형 또는 충격 사실 제시형'
    QEX = '"car accident night", "police tape scene", "crowd protest"'
else:
    PERSONA = "너는 'GLEND'라는 경제·재테크 실전 꿀팁 인스타그램 릴스 채널의 전문 작가야. 15~22초 안에 이득/손해 정보를 빠르게 전한다."
    TOPIC_DESC = "오늘의 최신 경제/재테크 관련 뉴스 제목 목록"
    HOOK = '"~안 하면 손해" 류의 손실 회피형'
    QEX = '"money hand korean", "bank application", "apartment korea"'

# 3) 릴스 대본 — 6개 장면(후킹+핵심5). 각 장면 narration = 화면 중앙에 뜰 자막.
PROMPT = f"""
{PERSONA}

아래는 {TOPIC_DESC}이야:
{news_text}

이 중에서 대중이 가장 반응할 핵심 주제 하나를 직접 골라서, 한 편의 짧은 뉴스를 본 것 같은 알찬 세로 릴스 대본을 만들어줘.
릴스는 7개 장면(scene)으로 구성돼. 각 장면은 성우가 말하는 동시에 화면 중앙에 그대로 뜨는 자막 문장(narration)과 배경 사진 검색어(query)로 이뤄져.

규칙:
- scene 1 = 후킹. narration은 시선을 확 잡는 짧고 강한 한 문장. {HOOK}
- scene 2~7 = 본문. 하나의 뉴스처럼 흐름을 갖고 깊이 있게 전달해: 무슨 일인지(배경/맥락) → 핵심 내용/수치 → 대상/조건 → 방법/절차 → 주의점 → 전망이나 의미. 각 장면이 서로 다른 알맹이를 담아 전체를 보면 주제를 제대로 이해하게.
- narration은 자연스러운 뉴스 구어체. 후킹(scene1)은 짧게, 본문(scene2~7)은 한두 문장으로 정보를 구체적으로(공백 포함 대략 30~60자). 실제 수치·기관·날짜 등 구체성을 살려 풍부하게.
- 각 narration에서 가장 중요한 핵심 단어 1개만 <b>단어</b>로 감싸 강조(노란색). 장면당 1개만. (성우는 태그를 읽지 않음)
- 자막에 글자수 메모("(16자)" 등)를 절대 쓰지 마. 최종 문장만.
- query는 각 장면 분위기에 맞는 영어 사진 검색어 2~3단어 (예: {QEX}).
- 화면 상단에 영상 내내 고정으로 뜰 짧은 제목(title)도 만들어줘. 주제를 한눈에 보여주는 8자 이내의 간결한 키워드 (예: "운전면허 지원금", "청년 청약통장", "전기요금 절약"). 이모지 1개 붙여도 좋음.
- 인스타 캡션: 첫 줄 후킹 + 핵심 5~6줄 + 저장/팔로우 유도 + 해시태그 5개.

반드시 아래 JSON 형식으로만 답해. 다른 설명 금지.
{{
  "topic": "네가 고른 주제",
  "title": "화면 상단 고정 제목(8자 이내 + 이모지)",
  "scenes": [
    {{ "narration": "후킹 자막 문장", "query": "영어 사진 검색어" }},
    {{ "narration": "본문 자막 문장", "query": "영어 사진 검색어" }},
    {{ "narration": "본문 자막 문장", "query": "영어 사진 검색어" }},
    {{ "narration": "본문 자막 문장", "query": "영어 사진 검색어" }},
    {{ "narration": "본문 자막 문장", "query": "영어 사진 검색어" }},
    {{ "narration": "본문 자막 문장", "query": "영어 사진 검색어" }},
    {{ "narration": "본문 자막 문장", "query": "영어 사진 검색어" }}
  ],
  "caption": "인스타 캡션 전체 텍스트"
}}
"""

print("Gemini가 릴스 대본을 만드는 중...\n")
for attempt in range(4):
    try:
        response = client.models.generate_content(model="models/gemini-2.5-flash", contents=PROMPT)
        break
    except Exception as e:
        if attempt < 3:
            wait = 30 * (attempt + 1)
            print(f"  Gemini 오류 ({e.__class__.__name__}), {wait}초 후 재시도... ({attempt+1}/3)")
            time.sleep(wait)
        else:
            raise

raw = response.text.strip()
if "```" in raw:
    raw = raw.split("```")[1]
    if raw.startswith("json"):
        raw = raw[4:]
raw = raw.strip()


def get_photo(query):
    try:
        res = requests.get(
            "https://api.pexels.com/v1/search",
            headers={"Authorization": PEXELS_KEY},
            params={"query": query, "per_page": 1, "orientation": "portrait"},
            timeout=30,
        )
        if res.status_code == 200:
            photos = res.json().get("photos", [])
            if photos:
                return photos[0]["src"]["large2x"]
    except Exception as e:
        print("  (사진 검색 실패:", query, "->", e, ")")
    return None


# 마지막(아웃트로) 장면 나레이션 — 좋아요/팔로우 유도 (자막 없음)
OUTRO_NARRATION = "도움이 됐다면 지금 좋아요와 팔로우 눌러주세요!"

try:
    data = json.loads(raw)
    print("=== Gemini가 고른 주제 ===")
    print(" ->", data.get("topic", "(주제 표시 없음)"), "\n")

    print("Pexels에서 장면별 배경 사진 가져오는 중...")
    for i, scene in enumerate(data["scenes"], start=1):
        q = scene.get("query", "background")
        photo = get_photo(q)
        scene["bg"] = photo or "https://images.pexels.com/photos/210607/pexels-photo-210607.jpeg"
        print(f"  scene{i}: '{q}' -> {'OK' if photo else '실패(기본사진)'} | 자막: {scene['narration']}")

    # 아웃트로 장면 추가 (검정 배경 + 로고, 자막 없음)
    data["scenes"].append({"outro": True, "narration": OUTRO_NARRATION})
    print(f"  scene5(아웃트로): 좋아요 유도 나레이션")

    print("\n[캡션]\n" + data["caption"])

    out_file = f"reel_content_{POST_INDEX}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n저장 완료! {out_file} 생성됨 🎬")
except Exception as e:
    print("[JSON 변환 실패]", e)
    print("받은 원본:")
    print(raw)
