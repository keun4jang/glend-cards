import os
import json
import urllib.parse
import requests
import feedparser
from dotenv import load_dotenv
from google import genai

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY", "").strip())
PEXELS_KEY = os.getenv("PEXELS_API_KEY", "").strip()

# 1) 최신 경제 뉴스 수집
QUERY = "경제 OR 금리 OR 증시 OR 부동산 when:1d"
url = "https://news.google.com/rss/search?q=" + urllib.parse.quote(QUERY) + "&hl=ko&gl=KR&ceid=KR:ko"
print("최신 경제 뉴스 수집 중...")
feed = feedparser.parse(url)
headlines = [e.title for e in feed.entries[:25]]
print(f"  뉴스 {len(headlines)}개 확보\n")

news_text = "\n".join(f"- {h}" for h in headlines)

# 2) Gemini에게 주제 선정 + 카드 내용 + 사진 검색어 생성
PROMPT = f"""
너는 'GLEND'라는 경제 인스타그램 채널의 전문 카드뉴스 작가야.

아래는 오늘의 최신 경제 뉴스 제목 목록이야:
{news_text}

이 중에서 일반 대중이 가장 관심 가질 만하고, 카드뉴스로 만들기 좋은 핵심 주제 하나를 직접 골라서, 4장짜리 카드뉴스 내용을 만들어줘.

규칙:
- 카드1(후킹): 강렬한 2줄 제목(한 줄 6자 이내) + 호기심 자극 부제(15자 이내)
- 카드2(분석): 소제목(2줄, 한 줄 6자 이내) + 본문 3줄. 구체적 사실/배경/숫자를 충실하게. 각 줄 13~16자.
- 카드3(통찰): 소제목(2줄, 한 줄 6자 이내) + 본문 3줄. 시사점/전망/행동제안을 충실하게. 각 줄 13~16자.
- 본문에서 핵심 키워드는 <b>키워드</b>로 감싸 강조 (각 카드당 2~3개)
- 인스타 캡션: 친근하고 정보성 있게, 문장마다 줄바꿈, 마지막에 해시태그 5개
- 본문 각 줄은 13~16자로! 너무 짧지 않게, 내용을 충실히. (16자 넘으면 잘림)
- 카드1,2,3 각각에 어울리는 영어 사진 검색어를 만들어줘. 2~3단어, 추상적이지 않고 사진으로 잘 나오는 단어 (예: stock market chart, korean money, business meeting)

반드시 아래 JSON 형식으로만 답해. 다른 설명 금지.
{{
  "topic": "네가 고른 주제",
  "card1": {{ "title": "1줄\\n2줄", "sub": "부제", "query": "영어 사진 검색어" }},
  "card2": {{ "subtitle": "1줄\\n2줄", "lines": ["줄1","줄2","줄3"], "query": "영어 사진 검색어" }},
  "card3": {{ "subtitle": "1줄\\n2줄", "lines": ["줄1","줄2","줄3"], "query": "영어 사진 검색어" }},
  "caption": "인스타 캡션 전체 텍스트"
}}
"""

print("Gemini가 주제를 고르고 카드 내용을 만드는 중...\n")
response = client.models.generate_content(model="models/gemini-2.5-flash", contents=PROMPT)

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
    print("\n[캡션]\n" + data["caption"])

    with open("content.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("\n저장 완료! content.json 생성됨 (배경 사진 포함) 🎉")
except Exception as e:
    print("[JSON 변환 실패]", e)
    print("받은 원본:")
    print(raw)








