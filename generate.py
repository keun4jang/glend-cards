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

# 1) 경제·재테크 실전 꿀팁 중심 뉴스 수집 (게시물 순번마다 다른 카테고리 고정)
QUERIES = [
    "정부지원금 OR 환급 OR 세금 혜택 OR 신청 마감 when:1d",
    "금리 OR 예금 OR 적금 OR 대출 조건 when:1d",
    "부동산 OR 청약 OR 전세 OR 임대 when:1d",
    "카드혜택 OR 재테크 OR 절약 OR 연말정산 when:1d",
]
QUERY = QUERIES[(int(POST_INDEX) - 1) % len(QUERIES)]
url = "https://news.google.com/rss/search?q=" + urllib.parse.quote(QUERY) + "&hl=ko&gl=KR&ceid=KR:ko"
print(f"[{POST_INDEX}번째 게시물] 뉴스 수집 중... (카테고리: {QUERY[:20]})")
feed = feedparser.parse(url)
headlines = [e.title for e in feed.entries[:25]]
print(f"  뉴스 {len(headlines)}개 확보\n")

news_text = "\n".join(f"- {h}" for h in headlines)

# 2) Gemini에게 주제 선정 + 카드 내용 + 사진 검색어 생성
PROMPT = f"""
너는 'GLEND'라는 경제·재테크 실전 꿀팁 인스타그램 채널의 전문 카드뉴스 작가야. 뉴스 요약이 아니라, 독자가 "지금 당장 나한테 이득/손해가 되는" 실전 정보를 얻어가게 만드는 게 목표다.

아래는 오늘의 최신 경제/재테크 관련 뉴스 제목 목록이야:
{news_text}

이 중에서 독자가 "이거 나도 신청해야겠다", "몰랐으면 손해볼 민했다"고 느낌 만한, 실생활에 바로 적용 가능한 핵심 주제 하나를 직접 골라서, 4장짜리 카드뉴스 내용을 만들어줘. 단순 시황 요약이나 추상적 경제 분석은 피하고, 신청 방법·조건·기한·금액처럼 구체적이고 실용적인 정보를 우선해.

규칙:
- 카드1(후킹): 강렬한 2줄 제목(한 줄 6자 이내) + 호기심 자극 부제(15자 이내). "~하면 손해", "~안 하면 못 받는다" 류의 손실 회피형 후킹을 우선 고려.
- 카드2(분석): 소제목(2줄, 한 줄 6자 이내) + 본문 3줄. 조건/대상/금액/기한 등 구체적 정보를 충실하게. 각 줄 반드시 13~16자 (공백 포함). 절대 17자 초과 금지.
- 카드3(통찰): 소제목(2줄, 한 줄 6자 이내) + 본문 3줄. "그래서 어떻게 신청/실행하면 되는지" 행동 방법을 충실하게. 각 줄 반드시 13~16자 (공백 포함). 절대 17자 초과 금지. 마지막 줄은 반드시 독자에게 행동을 촉구하는 문장 (예: "<b>지금</b> 신청 여부 확인하세요", "<b>저장</b>하고 기한 놓치지 마세요").
- 본문에서 핵심 키워드(금액, 기한, 조건)는 <b>키워드</b>로 감싸 강조 (각 카드당 2~3개). <b>태그는 글자수에서 제외해서 셈 것.
- 중요: 줄을 생성한 뒤 반드시 직접 글자 수를 세어서 17자 초과면 짧게 다시 써라.
- 인스타 캐션: 아래 구조를 반드시 지켜:
  1) 첫 줄: 오늘 주제를 손실 회피형 또는 이득 강조형 한 문장으로 강하게 후킹
  2) 본문: 신청 조건/기한/금액 등 실전 정보 3~4줄, 문장마다 줄바꿈
  3) 저장/공유 유도: "💾 기한 놓치기 전에 저장해두세요!" 또는 "📤 대상자인 친구에게 공유해주세요!" 중 하나
  4) 팔로우 유도: "📌 매일 놓치기 쉬운 재테크 정보 받고 싶다면 @glend_economy 팔로우!"
  5) 해시태그: 관련 키워드 5개
- 본문 각 줄은 13~16자로! 너무 짧지 않게, 내용을 충실히. (16자 넘으면 잘림)
- 카드1,2,3 각각에 어울리는 영어 사진 검색어를 만들어줘. 2~3단어, 추상적이지 않고 사진으로 잘 나오는 단어. 주제의 감정/분위기와 반드시 일치시키대 것 (예: 정부지원금은 "money hand korean", "bank application"; 부동산은 "apartment korea", "real estate contract"; 금융상품은 "savings account", "korean won cash")

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

    out_file = f"content_{POST_INDEX}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n저장 완료! {out_file} 생성됨 (배경 사진 포함) 🎉")
except Exception as e:
    print("[JSON 변환 실패]", e)
    print("받은 원본:")
    print(raw)
