import os
import json
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

# 1) 다양한 카테고리 뉴스 수집 (경제 + 사회 자극적 소재)
QUERIES = [
    "경제 OR 금리 OR 증시 OR 부동산 when:1d",
    "사건 OR 사고 OR 논란 OR 충격 when:1d",
    "트렌드 OR 라이프스타일 OR 소비 OR 직장 when:1d",
    "AI OR 기술 OR 스타트업 OR 미래 when:1d",
]
QUERY = random.choice(QUERIES)
url = "https://news.google.com/rss/search?q=" + urllib.parse.quote(QUERY) + "&hl=ko&gl=KR&ceid=KR:ko"
print(f"뉴스 수집 중... (카테고리: {QUERY[:20]})")
feed = feedparser.parse(url)
headlines = [e.title for e in feed.entries[:25]]
print(f"  뉴스 {len(headlines)}개 확보\n")

news_text = "\n".join(f"- {h}" for h in headlines)

# 2) Gemini에게 주제 선정 + 카드 내용 + 사진 검색어 생성
PROMPT = f"""
너는 'GLEND'라는 트렌드 인스타그램 채널의 전문 카드뉴스 작가야. 경제, 사회, 라이프스타일, 기술 등 다양한 주제를 다룬다.

아래는 오늘의 최신 경제 뉴스 제목 목록이야:
{news_text}

이 중에서 일반 대중이 가장 관심 가질 만하고, 자극적이거나 충격적이거나 공감을 유발하는 핵심 주제 하나를 직접 골라서, 4장짜리 카드뉴스 내용을 만들어줘. 단순 경제 수치보다는 사람들이 "이거 진짜야?" "나도 이런 경험 있어" 하고 반응할 소재를 우선해.

규칙:
- 카드1(후킹): 강렬한 2줄 제목(한 줄 6자 이내) + 호기심 자극 부제(15자 이내)
- 카드2(분석): 소제목(2줄, 한 줄 6자 이내) + 본문 3줄. 구체적 사실/배경/숫자를 충실하게. 각 줄 반드시 13~16자 (공백 포함). 절대 17자 초과 금지.
- 카드3(통찰): 소제목(2줄, 한 줄 6자 이내) + 본문 3줄. 시사점/전망/행동제안을 충실하게. 각 줄 반드시 13~16자 (공백 포함). 절대 17자 초과 금지. 마지막 줄은 반드시 독자에게 행동을 촉구하는 문장 (예: "<b>지금</b> 포트폴리오 점검하세요", "<b>저장</b>하고 다시 보세요").
- 본문에서 핵심 키워드는 <b>키워드</b>로 감싸 강조 (각 카드당 2~3개). <b>태그는 글자수에서 제외해서 셈 것.
- 중요: 줄을 생성한 뒤 반드시 직접 글자 수를 세어서 17자 초과면 짧게 다시 써라.
- 인스타 캐션: 아래 구조를 반드시 지켜:
  1) 첫 줄: 오늘 주제를 한 문장으로 강하게 후킹 (질문형 또는 충격 사실)
  2) 본문: 핵심 인사이트 3~4줄, 문장마다 줄바꿈
  3) 저장/공유 유도: "💾 나중에 꾼내볼 수 있게 저장해두세요!" 또는 "📤 경제 공부하는 친구에게 공유해주세요!" 중 하나
  4) 팔로우 유도: "📌 매일 경제 뉴스 카드 받고 싶다면 @glend_economy 팔로우!"
  5) 해시태그: 관련 키워드 5개
- 본문 각 줄은 13~16자로! 너무 짧지 않게, 내용을 충실히. (16자 넘으면 잘림)
- 카드1,2,3 각각에 어울리는 영어 사진 검색어를 만들어줘. 2~3단어, 추상적이지 않고 사진으로 잘 나오는 단어. 주제의 감정/분위기와 반드시 일치시키대 것 (예: 사건·사고류는 "car accident night", "police tape scene", "hospital emergency"; 경제는 "stock market chart", "korean money"; 일상/트렌드는 "business meeting", "seoul street night")

반드시 아래 JSON 형식으로만 답해. 다른 설명 금지.
{{
  "topic": "네가 고른 주제",
  "card1": {{ "title": "1줄\\n2줄", "sub": "부제", "query": "영어 사진 검색어" }},
  "card2": {{ "subtitle": "1줄\\n2줄", "lines": ["줄1","줄2","줄3"], "query": "영어 사진 검색어" }},
  "card3": {{ "subtitle": "1줄\\n2줄", "lines": ["줄1","줄2","줄3"], "query": "영어 사진 검색어" }},
  "caption": "인스타 캐션 전체 텍스트"
}}
"""

print("Gemini가 주제를 고르고 카드 내용을 만드는 중...\n")
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

# 3) Pexels에서 검색어로 사진 가져오는 함수
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
    print(" ->", data.get("topic", "(주제 표시 없음)"))
    print()

    # 각 카드에 Pexels 사진 자동 연결
    print("Pexels에서 배경 사진 가져오는 중...")
    for cardkey in ["card1", "card2", "card3"]:
        q = data[cardkey].get("query", "finance")
        photo = get_photo(q)
        if photo:
            data[cardkey]["bg"] = photo
            print(f"  {cardkey}: '{q}' -> 사진 OK")
        else:
            data[cardkey]["bg"] = "https://images.pexels.com/photos/210607/pexels-photo-210607.jpeg"
            print(f"  {cardkey}: '{q}' -> 실패, 기본 사진 사용")
    print()

    print("[카드1]", data["card1"]["title"].replace("\\n"," / "), "|", data["card1"]["sub"])
    print("[카드2]", data["card2"]["subtitle"].replace("\\n"," / "))
    for l in data["card2"]["lines"]: print("   -", l)
    print("[카드3]", data["card3"]["subtitle"].replace("\\n"," / "))
    for l in data["card3"]["lines"]: print("   -", l)
    print("\n[캐션]\n" + data["caption"])

    with open("content.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("\n저장 완료! content.json 생성됨 (배경 사진 포함) 🎉")
except Exception as e:
    print("[JSON 변환 실패]", e)
    print("받은 원본:")
    print(raw)
