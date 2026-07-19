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

# 1) 카테고리 결정 — 1번=경제, 2번=사건사고, 3번=건강 고정
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
print(f"[{POST_INDEX}번째 게시물/{CATEGORY}] 뉴스 수집 중... (카테고리: {QUERY[:20]})")
feed = feedparser.parse(url)
headlines = [e.title for e in feed.entries[:25]]
print(f"  뉴스 {len(headlines)}개 확보\n")

news_text = "\n".join(f"- {h}" for h in headlines)

# 2) Gemini에게 주제 선정 + 카드 내용 + 사진 검색어 생성
if CATEGORY == "health":
    PERSONA = "너는 'GLEND'라는 건강 실전 꿀팁 인스타그램 채널의 전문 카드뉴스 작가야. 뉴스 요약이 아니라, 독자가 \"지금 당장 내 몸에 도움되는\" 실전 건강 정보(다이어트, 영양, 수면, 정신건강 등)를 얻어가게 만드는 게 목표다."
    TOPIC_DESC = "오늘의 최신 건강 관련 뉴스 제목 목록"
    PICK_DESC = '독자가 "이거 나도 해봐야겠다", "몰랐던 건강 정보네"라고 느낄 만한, 실생활에 바로 적용 가능한 핵심 주제 하나를 직접 골라서, 4장짜리 카드뉴스 내용을 만들어줘. 단순 연구 결과 나열은 피하고, 방법·수치·습관처럼 구체적이고 실용적인 정보를 우선해.'
    HOOK_STYLE = '"~하면 몸 망친다", "~안 하면 큰일 난다" 류의 경각심 자극형 후킹을 우선 고려.'
    SAVE_LINE = '"💾 나중에 실천할 수 있게 저장해두세요!" 또는 "📤 건강 챙기는 친구에게 공유해주세요!" 중 하나'
    FOLLOW_LINE = '"📌 매일 놓치기 쉬운 건강 정보 받고 싶다면 @glend_economy 팔로우!"'
    QUERY_EXAMPLE = '건강/운동은 "morning stretching", "healthy meal prep"; 수면은 "sleeping bedroom night"; 정신건강은 "meditation calm person"'
    LAST_LINE_EXAMPLE = '"<b>지금</b> 실천 여부 확인하세요", "<b>저장</b>하고 오늘부터 시작하세요"'
elif CATEGORY == "incident":
    PERSONA = "너는 'GLEND'라는 트렌드 인스타그램 채널의 전문 카드뉴스 작가야. 단순 사건 요약이 아니라, 독자가 \"이거 진짜야?\", \"나도 이런 경험 있어\" 하고 반응할 만큼 자극적이거나 공감을 유발하는 사건·사고·논란 소재를 다룬다."
    TOPIC_DESC = "오늘의 최신 사건·사고·논란 관련 뉴스 제목 목록"
    PICK_DESC = '일반 대중이 가장 관심 가질 만하고, 자극적이거나 충격적이거나 공감을 유발하는 핵심 주제 하나를 직접 골라서, 4장짜리 카드뉴스 내용을 만들어줘. 단순 사실 나열보다 배경/맥락/파장을 구체적으로 담아.'
    HOOK_STYLE = '질문형 또는 충격적 사실 제시형 후킹을 우선 고려.'
    SAVE_LINE = '"💾 나중에 다시 볼 수 있게 저장해두세요!" 또는 "📤 같이 얘기하고 싶은 친구에게 공유해주세요!" 중 하나'
    FOLLOW_LINE = '"📌 매일 화제의 이슈 카드 받고 싶다면 @glend_economy 팔로우!"'
    QUERY_EXAMPLE = '사건·사고류는 "car accident night", "police tape scene", "hospital emergency"'
    LAST_LINE_EXAMPLE = '"<b>지금</b> 어떻게 생각하는지 댓글로", "<b>저장</b>하고 다시 보세요"'
else:
    PERSONA = "너는 'GLEND'라는 경제·재테크 실전 꿀팁 인스타그램 채널의 전문 카드뉴스 작가야. 뉴스 요약이 아니라, 독자가 \"지금 당장 나한테 이득/손해가 되는\" 실전 정보를 얻어가게 만드는 게 목표다."
    TOPIC_DESC = "오늘의 최신 경제/재테크 관련 뉴스 제목 목록"
    PICK_DESC = '독자가 "이거 나도 신청해야겠다", "몰랐으면 손해볼 뻔했다"고 느낄 만한, 실생활에 바로 적용 가능한 핵심 주제 하나를 직접 골라서, 4장짜리 카드뉴스 내용을 만들어줘. 단순 시황 요약이나 추상적 경제 분석은 피하고, 신청 방법·조건·기한·금액처럼 구체적이고 실용적인 정보를 우선해.'
    HOOK_STYLE = '"~하면 손해", "~안 하면 못 받는다" 류의 손실 회피형 후킹을 우선 고려.'
    SAVE_LINE = '"💾 기한 놓치기 전에 저장해두세요!" 또는 "📤 대상자인 친구에게 공유해주세요!" 중 하나'
    FOLLOW_LINE = '"📌 매일 놓치기 쉬운 재테크 정보 받고 싶다면 @glend_economy 팔로우!"'
    QUERY_EXAMPLE = '정부지원금은 "money hand korean", "bank application"; 부동산은 "apartment korea", "real estate contract"; 금융상품은 "savings account", "korean won cash"'
    LAST_LINE_EXAMPLE = '"<b>지금</b> 신청 여부 확인하세요", "<b>저장</b>하고 기한 놓치지 마세요"'

PROMPT = f"""
{PERSONA}

아래는 {TOPIC_DESC}이야:
{news_text}

이 중에서 {PICK_DESC}

규칙:
- 카드1(후킹): 강렬한 2줄 제목(한 줄 6자 이내) + 호기심 자극 부제(15자 이내). {HOOK_STYLE}
- 카드2(분석): 소제목(2줄, 한 줄 6자 이내) + 본문 3줄. 조건/대상/수치/근거 등 구체적 정보를 충실하게. 각 줄 반드시 13~16자 (공백 포함). 절대 17자 초과 금지.
- 카드3(통찰): 소제목(2줄, 한 줄 6자 이내) + 본문 3줄. "그래서 어떻게 실행하면 되는지" 행동 방법을 충실하게. 각 줄 반드시 13~16자 (공백 포함). 절대 17자 초과 금지. 마지막 줄은 반드시 독자에게 행동을 촉구하는 문장 (예: {LAST_LINE_EXAMPLE}).
- 본문에서 핵심 키워드(수치, 기한, 조건)는 <b>키워드</b>로 감싸 강조 (각 카드당 2~3개). <b>태그는 글자수에서 제외해서 셈 것.
- 중요: 줄을 생성한 뒤 반드시 직접 글자 수를 세어서 17자 초과면 짧게 다시 써라.
- 인스타 캡션: 아래 구조를 반드시 지켜:
  1) 첫 줄: 오늘 주제를 강한 한 문장으로 후킹
  2) 본문: 실전 정보 3~4줄, 문장마다 줄바꿈
  3) 저장/공유 유도: {SAVE_LINE}
  4) 팔로우 유도: {FOLLOW_LINE}
  5) 해시태그: 관련 키워드 5개
- 본문 각 줄은 13~16자로! 너무 짧지 않게, 내용을 충실히. (16자 넘으면 잘림)
- 카드1,2,3 각각에 어울리는 영어 사진 검색어를 만들어줘. 2~3단어, 추상적이지 않고 사진으로 잘 나오는 단어. 주제의 감정/분위기와 반드시 일치시킬 것 (예: {QUERY_EXAMPLE})

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
