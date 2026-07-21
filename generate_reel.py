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

# 1) 카테고리 결정 — 1번=경제, 2번=사건사고, 3번=건강 (카드뉴스와 동일 체계)
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
    PERSONA = "너는 'GLEND'라는 건강 실전 꿀팁 인스타그램 릴스 채널의 전문 작가야. 독자가 \"지금 당장 내 몸에 도움되는\" 정보를 15~25초 안에 빠르게 얻어가게 만든다."
    TOPIC_DESC = "오늘의 최신 건강 관련 뉴스 제목 목록"
    HOOK_STYLE = '"~하면 몸 망친다" 류의 경각심 자극형'
    QUERY_EXAMPLE = '"morning stretching", "healthy meal prep", "sleeping bedroom night", "meditation calm person"'
elif CATEGORY == "incident":
    PERSONA = "너는 'GLEND'라는 트렌드 인스타그램 릴스 채널의 전문 작가야. 자극적이거나 공감을 유발하는 사건·사고·논란 소재를 15~25초 안에 빠르게 전달한다."
    TOPIC_DESC = "오늘의 최신 사건·사고·논란 관련 뉴스 제목 목록"
    HOOK_STYLE = '질문형 또는 충격 사실 제시형'
    QUERY_EXAMPLE = '"car accident night", "police tape scene", "hospital emergency", "crowd protest"'
else:
    PERSONA = "너는 'GLEND'라는 경제·재테크 실전 꿀팁 인스타그램 릴스 채널의 전문 작가야. 독자가 \"지금 당장 나한테 이득/손해가 되는\" 정보를 15~25초 안에 빠르게 얻어가게 만든다."
    TOPIC_DESC = "오늘의 최신 경제/재테크 관련 뉴스 제목 목록"
    HOOK_STYLE = '"~안 하면 손해" 류의 손실 회피형'
    QUERY_EXAMPLE = '"money hand korean", "bank application", "apartment korea", "korean won cash"'

# 3) 릴스 대본 프롬프트 — 5개 장면(후킹→내용3→마무리)
PROMPT = f"""
{PERSONA}

아래는 {TOPIC_DESC}이야:
{news_text}

이 중에서 대중이 가장 반응할 핵심 주제 하나를 직접 골라서, 세로 릴스(15~25초) 대본을 만들어줘.
릴스는 5개 장면(scene)으로 구성돼. 각 장면은 "화면에 크게 뜨는 짧은 텍스트(text)"와 "성우가 읽는 나레이션 문장(narration)", 그리고 "배경으로 쓸 영어 사진 검색어(query)"로 이뤄져.

규칙:
- scene 1 = 후킹. text는 강렬한 2줄(한 줄 6자 이내). {HOOK_STYLE}. narration은 시선을 잡는 첫 문장.
- scene 2,3,4 = 핵심 내용. text는 화면용 짧은 핵심 문구(한 줄 최대 16자, 최대 2줄). 핵심 단어는 <b>단어</b>로 감싸 강조. narration은 그 내용을 자연스럽게 설명하는 1~2문장(구어체, 빠르고 명확하게).
- scene 5 = 마무리/행동유도. text는 저장·팔로우를 부르는 짧은 문구. narration도 행동 촉구 한 문장.
- 각 narration은 너무 길지 않게(장면당 대략 3~5초 분량, 한국어 20~45자). 전체 합쳐 15~25초.
- text에는 절대 글자수 메모("(16자)" 등)를 쓰지 마. 최종 문구만 순수하게.
- query는 각 장면 분위기에 맞는 사진 검색어 2~3단어 (예: {QUERY_EXAMPLE}).
- 인스타 캡션: 첫 줄 후킹 + 핵심 3줄 + 저장/팔로우 유도 + 해시태그 5개.

반드시 아래 JSON 형식으로만 답해. 다른 설명 금지.
{{
  "topic": "네가 고른 주제",
  "scenes": [
    {{ "text": "1줄\\n2줄", "narration": "나레이션", "query": "영어 사진 검색어" }},
    {{ "text": "화면문구", "narration": "나레이션", "query": "영어 사진 검색어" }},
    {{ "text": "화면문구", "narration": "나레이션", "query": "영어 사진 검색어" }},
    {{ "text": "화면문구", "narration": "나레이션", "query": "영어 사진 검색어" }},
    {{ "text": "저장·팔로우 유도 문구", "narration": "나레이션", "query": "영어 사진 검색어" }}
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


try:
    data = json.loads(raw)
    print("=== Gemini가 고른 주제 ===")
    print(" ->", data.get("topic", "(주제 표시 없음)"), "\n")

    print("Pexels에서 장면별 배경 사진 가져오는 중...")
    for i, scene in enumerate(data["scenes"], start=1):
        q = scene.get("query", "background")
        photo = get_photo(q)
        scene["bg"] = photo or "https://images.pexels.com/photos/210607/pexels-photo-210607.jpeg"
        print(f"  scene{i}: '{q}' -> {'OK' if photo else '실패(기본사진)'}")
        print(f"     text: {scene['text'].replace(chr(10),' / ')}")
        print(f"     narration: {scene['narration']}")
    print()
    print("[캡션]\n" + data["caption"])

    out_file = f"reel_content_{POST_INDEX}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n저장 완료! {out_file} 생성됨 🎬")
except Exception as e:
    print("[JSON 변환 실패]", e)
    print("받은 원본:")
    print(raw)
