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
from recent_topics import avoid_line

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY", "").strip())
PEXELS_KEY = os.getenv("PEXELS_API_KEY", "").strip()
# 모델명 (신규 계정에서 gemini-2.5-flash가 막혀서 최신 별칭 사용). 필요시 GEMINI_MODEL로 교체.
GEMINI_MODEL = (os.getenv("GEMINI_MODEL") or "models/gemini-flash-latest").strip()

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
    PICK_DESC = '독자가 "이거 나도 해봐야겠다", "몰랐던 건강 정보네"라고 느낄 만한, 실생활에 바로 적용 가능한 핵심 주제 하나를 직접 골라서, 5장짜리 카드뉴스 내용을 만들어줘. 단순 연구 결과 나열은 피하고, 방법·수치·습관처럼 구체적이고 실용적인 정보를 우선해.'
    HOOK_STYLE = '"~하면 몸 망친다", "~안 하면 큰일 난다" 류의 경각심 자극형 후킹을 우선 고려.'
    SAVE_LINE = '"💾 나중에 실천할 수 있게 저장해두세요!" 또는 "📤 건강 챙기는 친구에게 공유해주세요!" 중 하나'
    SAVE_GOOD = "따라 할 수 있는 방법·수치·기준이 명확한 것 (자가진단 기준, 권장 섭취량, 운동 방법, 검진 주기, 증상 체크리스트)"
    SAVE_BAD = "읽고 나면 할 일이 없는 것 (연구 결과 소개, 일반론, 남의 사례 소개)"
    FOLLOW_LINE = '"📌 매일 놓치기 쉬운 건강 정보 받고 싶다면 @glend_kr 팔로우!"'
    QUERY_EXAMPLE = '건강/운동은 "healthy meal bowl", "running shoes closeup"; 수면은 "sleeping bedroom night"; 정신건강은 "calm candle interior"'
    LAST_LINE_EXAMPLE = '"<b>하루 20분</b>부터 시작하세요", "<b>3개월</b> 뒤 다시 확인하세요"'
elif CATEGORY == "incident":
    PERSONA = "너는 'GLEND'라는 트렌드 인스타그램 채널의 전문 카드뉴스 작가야. 단순 사건 요약이 아니라, 독자가 \"이거 진짜야?\", \"나도 이런 경험 있어\" 하고 반응할 만큼 자극적이거나 공감을 유발하는 사건·사고·논란 소재를 다룬다."
    TOPIC_DESC = "오늘의 최신 사건·사고·논란 관련 뉴스 제목 목록"
    PICK_DESC = '일반 대중이 가장 관심 가질 만하고, 자극적이거나 충격적이거나 공감을 유발하는 핵심 주제 하나를 직접 골라서, 5장짜리 카드뉴스 내용을 만들어줘. 단순 사실 나열보다 배경/맥락/파장을 구체적으로 담아.'
    HOOK_STYLE = '질문형 또는 충격적 사실 제시형 후킹을 우선 고려.'
    SAVE_LINE = '"💾 나중에 다시 볼 수 있게 저장해두세요!" 또는 "📤 같이 얘기하고 싶은 친구에게 공유해주세요!" 중 하나'
    SAVE_GOOD = "나에게도 닥칠 수 있어 대비법이 필요한 것 (피해 예방법, 신고·구제 절차, 보상 기준, 법 개정으로 바뀐 내 권리)"
    SAVE_BAD = "읽고 나면 할 일이 없는 것 (단순 사건 요약, 남 얘기, 연예·정치 가십)"
    FOLLOW_LINE = '"📌 매일 화제의 이슈 카드 받고 싶다면 @glend_kr 팔로우!"'
    QUERY_EXAMPLE = '사건·사고류는 "car accident night", "police line tape", "ambulance lights night"'
    LAST_LINE_EXAMPLE = '"<b>피해 신고</b>는 국번없이 1332", "<b>계약 전</b> 반드시 확인하세요"'
else:
    PERSONA = "너는 'GLEND'라는 경제·재테크 실전 꿀팁 인스타그램 채널의 전문 카드뉴스 작가야. 뉴스 요약이 아니라, 독자가 \"지금 당장 나한테 이득/손해가 되는\" 실전 정보를 얻어가게 만드는 게 목표다."
    TOPIC_DESC = "오늘의 최신 경제/재테크 관련 뉴스 제목 목록"
    PICK_DESC = '독자가 "이거 나도 신청해야겠다", "몰랐으면 손해볼 뻔했다"고 느낄 만한, 실생활에 바로 적용 가능한 핵심 주제 하나를 직접 골라서, 5장짜리 카드뉴스 내용을 만들어줘. 단순 시황 요약이나 추상적 경제 분석은 피하고, 신청 방법·조건·기한·금액처럼 구체적이고 실용적인 정보를 우선해.'
    HOOK_STYLE = '"~하면 손해", "~안 하면 못 받는다" 류의 손실 회피형 후킹을 우선 고려.'
    SAVE_LINE = '"💾 기한 놓치기 전에 저장해두세요!" 또는 "📤 대상자인 친구에게 공유해주세요!" 중 하나'
    SAVE_GOOD = "신청 절차·자격 조건·기한·금액이 명확한 것 (지원금, 환급, 청약, 공제, 신고 방법, 제도 변경)"
    SAVE_BAD = "읽고 나면 할 일이 없는 것 (시황 분석, 전망, 금리 해설, 남 얘기)"
    FOLLOW_LINE = '"📌 매일 놓치기 쉬운 재테크 정보 받고 싶다면 @glend_kr 팔로우!"'
    QUERY_EXAMPLE = '정부지원금은 "korean won bills", "calculator money desk"; 부동산은 "apartment korea", "real estate contract"; 금융상품은 "savings account", "korean won cash"'
    LAST_LINE_EXAMPLE = '"<b>12월 31일</b>까지 신청하세요", "<b>정부24</b>에서 바로 확인하세요"'

AVOID = avoid_line()

PROMPT = f"""
{PERSONA}

아래는 {TOPIC_DESC}이야:
{news_text}

이 중에서 {PICK_DESC}
{AVOID}

주제 선정의 최우선 기준 — **저장 가치**:
카드뉴스는 팔로워에게만 노출되기 때문에, 널리 퍼지려면 '저장'이 일어나야 한다.
사람은 "지금 당장은 못 하지만 나중에 꼭 해야 하는 일"을 저장한다.
- 우선 골라야 할 주제: {SAVE_GOOD}
- 피해야 할 주제: {SAVE_BAD}
읽고 나서 독자가 저장할 이유가 없는 주제라면, 그 주제는 고르지 말고 다른 걸 골라.

규칙:
- 카드1(후킹): 강렬한 2줄 제목(한 줄 6자 이내) + 부제 2줄. {HOOK_STYLE}
  - sub1 = 핵심을 설명하는 한 줄 (공백 포함 12~16자)
  - sub2 = 짧고 강한 마무리 한 줄 (공백 포함 6~10자, 예: "연금 체계 바뀐다", "지금 신청하세요")
  - sub1과 sub2 각각에서 핵심 명사 1개만 <b>단어</b>로 감싸 강조. 반드시 대상·금액·제도명 같은 정보를 담은 명사만 강조하고, 동사·부사·수식어("바뀐다", "두텁게", "지금" 등)는 절대 강조하지 마.
- 카드2(분석): 소제목(2줄, 한 줄 6자 이내) + 본문 3줄. 조건/대상/수치/근거 등 구체적 정보를 충실하게. 각 줄 반드시 13~16자 (공백 포함). 절대 17자 초과 금지.
- 카드3(실행): 소제목(2줄, 한 줄 6자 이내) + 본문 3줄. 각 줄 반드시 13~16자 (공백 포함). 절대 17자 초과 금지.
  - 이 카드는 **나중에 다시 꺼내 보려고 저장하는 카드**다. 감상이나 총평이 아니라, 저장해두지 않으면 기억 못 할 정보만 담아.
  - 3줄을 이 순서로: (1) 어디서 신청·확인하는지 정확한 창구·사이트명 (2) 필요한 조건 또는 준비물 (3) 기한·금액 등 놓치면 손해인 숫자.
  - "잘 챙기세요", "관심을 가져야 합니다" 같은 알맹이 없는 문장은 절대 금지. 저장할 이유가 없어진다.
  - 마지막 줄은 숫자·기한을 담으면서 행동을 촉구하는 형태로 (예: {LAST_LINE_EXAMPLE}).
- 본문에서 핵심 키워드는 <b>키워드</b>로 감싸 강조 (각 카드당 1~2개, 한 줄에 최대 1개). 강조는 반드시 정보를 담은 명사(대상·금액·기한·제도명)만 — 동사·부사·수식어는 강조 금지. <b>태그는 글자수에서 제외해서 셈 것.
- 중요: 줄을 생성한 뒤 머릿속으로 글자 수를 세어서 17자 초과면 짧게 다시 써라. 단, "(16자)"처럼 글자 수를 세었다는 표시나 괄호 메모를 절대 실제 텍스트에 포함하지 마라 — 최종 문장만 순수하게 출력할 것.
- 카드4(저장용 요약): 이 카드는 캐러셀을 다 넘긴 사람이 "저장" 버튼을 누르게 만드는 마지막 관문이다.
  - headline = "이것만 기억하세요" 같은 짧은 한 줄 (8자 이내). 매번 똑같이 쓰지 말고 주제에 맞게 변주.
  - items = 핵심 3개. 각 항목은 공백 포함 12~18자. 앞 카드에 이미 나온 내용을 그대로 반복하지 말고,
    "저장해두고 나중에 이것만 다시 보면 되는" 형태로 압축해라 (창구·조건·기한/금액 순).
  - 각 항목에서 핵심 명사 1개만 <b>단어</b>로 감싸 강조.
  - closing = 저장을 촉구하는 한 줄 (공백 포함 14~22자). "팔로우"는 여기 쓰지 마 — 카드4는 저장 전용이다.
    예: "저장해두고 신청 전에 다시 확인하세요"
- 인스타 캡션: 아래 구조를 반드시 지켜:
  1) 첫 줄: 오늘 주제를 강한 한 문장으로 후킹. "~알고 계셨나요?" 류 질문형 반복 금지 — 숫자 제시형("300만원, 신청 안 하면 사라집니다"), 명령형("이것부터 확인하세요"), 반전형("다들 아는 그 방법, 사실 손해입니다")을 번갈아 사용.
  2) 본문: 실전 정보 3~4줄, 문장마다 줄바꿈
  3) 저장/공유 유도: {SAVE_LINE}
  4) 팔로우 유도: {FOLLOW_LINE}
  5) 주제와 관련된 댓글 유도 질문 한 줄 (예: "여러분이라면 신청하실 건가요? 댓글로 알려주세요 👇")
  6) 해시태그 5개: 대형 1개(#재테크급 광범위) + 중형 2개(주제 카테고리) + 니치 2개(오늘 주제 구체 키워드)로 섞어서
- 캡션에 마크다운 문법(**별표**, ## 등)을 절대 쓰지 마 — 인스타는 마크다운을 표시하지 못해 별표가 그대로 노출됨. 강조는 이모지나 줄바꿈으로만.
- 본문 각 줄은 13~16자로! 너무 짧지 않게, 내용을 충실히. (16자 넘으면 잘림)
- 카드1,2,3 각각에 어울리는 영어 사진 검색어를 만들어줘. 2~3단어, 추상적이지 않고 사진으로 잘 나오는 단어. 주제의 감정/분위기와 반드시 일치시킬 것 (예: {QUERY_EXAMPLE})
- query 중요 규칙: 한국 소식이라 배경에 외국 요소가 보이면 어색해. 돈이 나오는 장면은 반드시 "korean won"을 넣어 검색할 것 (그냥 "money", "cash"로 하면 달러·유로 지폐가 나옴). 그리고 반드시 사람 얼굴이 안 나오는 사진으로 — 사물(돈, 계산기, 서류), 풍경(도시, 건물, 자연), 손 클로즈업 위주. "person", "man", "woman", "people" 단어 금지.

반드시 아래 JSON 형식으로만 답해. 다른 설명 금지.
{{
  "topic": "네가 고른 주제",
  "card1": {{ "title": "1줄\\n2줄", "sub1": "설명 한 줄(<b>포인트</b> 포함)", "sub2": "짧은 마무리(<b>포인트</b> 포함)", "query": "영어 사진 검색어" }},
  "card2": {{ "subtitle": "1줄\\n2줄", "lines": ["줄1","줄2","줄3"], "query": "영어 사진 검색어" }},
  "card3": {{ "subtitle": "1줄\\n2줄", "lines": ["줄1","줄2","줄3"], "query": "영어 사진 검색어" }},
  "card4": {{ "headline": "이것만 기억하세요", "items": ["핵심1","핵심2","핵심3"], "closing": "저장 촉구 한 줄" }},
  "caption": "인스타 캡션 전체 텍스트"
}}
"""

print("Gemini가 주제를 고르고 카드 내용을 만드는 중...\n")


def call_gemini():
    for attempt in range(4):
        try:
            return client.models.generate_content(model=GEMINI_MODEL, contents=PROMPT)
        except Exception as e:
            if attempt < 3:
                wait = 30 * (attempt + 1)
                print(f"  Gemini 오류 ({e.__class__.__name__}), {wait}초 후 재시도... ({attempt+1}/3)")
                time.sleep(wait)
            else:
                raise


def parse_json(raw):
    raw = raw.strip()
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


def validate(d):
    """구조 검증 — 깨진 응답이 렌더 단계로 흘러가지 않게"""
    assert isinstance(d.get("caption"), str) and d["caption"].strip(), "caption 누락"
    c1 = d.get("card1") or {}
    assert c1.get("title") and c1.get("query"), "card1 필드 누락"
    assert (c1.get("sub1") and c1.get("sub2")) or c1.get("sub"), "card1 부제(sub1/sub2) 누락"
    for k in ("card2", "card3"):
        c = d.get(k) or {}
        assert c.get("subtitle") and c.get("query"), f"{k} 필드 누락"
        lines = c.get("lines")
        assert isinstance(lines, list) and len(lines) >= 3 and all(
            isinstance(l, str) and l.strip() for l in lines), f"{k}.lines 형식 오류"
    c4 = d.get("card4") or {}
    assert c4.get("headline") and c4.get("closing"), "card4 필드 누락"
    items = c4.get("items")
    assert isinstance(items, list) and len(items) >= 3 and all(
        isinstance(x, str) and x.strip() for x in items), "card4.items 형식 오류"


data = None
for gen_try in range(1, 4):
    response = call_gemini()
    try:
        cand = parse_json(response.text or "")
        validate(cand)
        data = cand
        break
    except Exception as e:
        print(f"  응답 형식 오류({e}) — 재생성 {gen_try}/3")
        time.sleep(5)
if data is None:
    print("[중단] Gemini가 3회 연속 올바른 형식을 주지 않았어요.")
    sys.exit(1)

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

if True:
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

    print("[카드1]", data["card1"]["title"].replace("\\n", " / "), "|",
          data["card1"].get("sub1", data["card1"].get("sub", "")), "/", data["card1"].get("sub2", ""))
    print("[카드2]", data["card2"]["subtitle"].replace("\\n"," / "))
    for l in data["card2"]["lines"]: print("   -", l)
    print("[카드3]", data["card3"]["subtitle"].replace("\\n"," / "))
    for l in data["card3"]["lines"]: print("   -", l)
    print("\n[캐션]\n" + data["caption"])

    out_file = f"content_{POST_INDEX}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n저장 완료! {out_file} 생성됨 (배경 사진 포함) 🎉")
