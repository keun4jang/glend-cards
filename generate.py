import os
import json
import re
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
# 모델 후보 목록 (앞에서부터 시도).
# 한 모델이 503("high demand")으로 포화되면 같은 모델을 더 두드려도 소용없어서,
# 다른 무료 모델로 넘어간다. 전부 AI Studio 무료 티어라 비용은 발생하지 않는다.
# GEMINI_MODEL(단일) 또는 GEMINI_MODELS(쉼표구분)로 덮어쓸 수 있다.
_models_env = (os.getenv("GEMINI_MODELS") or "").strip()
if _models_env:
    MODEL_CHAIN = [m.strip() for m in _models_env.split(",") if m.strip()]
else:
    MODEL_CHAIN = [
        (os.getenv("GEMINI_MODEL") or "models/gemini-flash-latest").strip(),
        "models/gemini-flash-lite-latest",
        "models/gemini-2.0-flash",
    ]
GEMINI_MODEL = MODEL_CHAIN[0]

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
    SAVE_LINE = '마지막 장에 무엇이 정리돼 있는지 밝히는 한 줄(예: "💾 실천 기준·권장량은 마지막 장에 정리해뒀어요") 또는 "📤 건강 챙기는 친구에게 공유해주세요!" 중 하나. 그냥 "저장해두세요"라고 시키지 말 것 — 무엇이 저장되는지 알아야 저장한다.'
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
    SAVE_LINE = '마지막 장에 무엇이 정리돼 있는지 밝히는 한 줄(예: "💾 신고 절차·보상 기준은 마지막 장에 정리해뒀어요") 또는 "📤 같이 얘기하고 싶은 친구에게 공유해주세요!" 중 하나. 그냥 "저장해두세요"라고 시키지 말 것 — 무엇이 저장되는지 알아야 저장한다.'
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
    SAVE_LINE = '마지막 장에 무엇이 정리돼 있는지 밝히는 한 줄(예: "💾 신청처·조건·기한은 마지막 장에 정리해뒀어요") 또는 "📤 대상자인 친구에게 공유해주세요!" 중 하나. 그냥 "저장해두세요"라고 시키지 말 것 — 무엇이 저장되는지 알아야 저장한다.'
    SAVE_GOOD = "신청 절차·자격 조건·기한·금액이 명확한 것 (지원금, 환급, 청약, 공제, 신고 방법, 제도 변경)"
    SAVE_BAD = "읽고 나면 할 일이 없는 것 (시황 분석, 전망, 금리 해설, 남 얘기)"
    FOLLOW_LINE = '"📌 매일 놓치기 쉬운 재테크 정보 받고 싶다면 @glend_kr 팔로우!"'
    QUERY_EXAMPLE = '정부지원금은 "korean won bills", "korean won calculator desk"; 부동산은 "apartment korea", "real estate contract"; 금융상품은 "bankbook desk", "korean won cash"'
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
  - 제목·부제에 "꿀팁", "총정리", "비밀", "필독", "주목" 같은 광고성 명사형 표현을 쓰지 마라.
    (실측 2026-09-13, archive/instagram_posts.csv 카드뉴스 338건: 이 표현이 있는 10건은 도달 13.6 vs 없는 328건 23.6, p=0.049로 유의미하게 낮았고, 저장은 0건 vs 0.02건/게시물로 p=0.014.)
- 카드2(분석): 소제목(2줄, 한 줄 6자 이내) + 본문 3줄. 조건/대상/수치/근거 등 구체적 정보를 충실하게. 각 줄 반드시 13~16자 (공백 포함). 절대 17자 초과 금지.
- 카드3(실행): 소제목(2줄, 한 줄 6자 이내) + 본문 3줄. 각 줄 반드시 13~16자 (공백 포함). 절대 17자 초과 금지.
  - 이 카드는 **나중에 다시 꺼내 보려고 저장하는 카드**다. 감상이나 총평이 아니라, 저장해두지 않으면 기억 못 할 정보만 담아.
  - 3줄을 이 순서로: (1) 어디서 신청·확인하는지 정확한 창구·사이트명 (2) 필요한 조건 또는 준비물 (3) 기한·금액 등 놓치면 손해인 숫자.
  - "잘 챙기세요", "관심을 가져야 합니다" 같은 알맹이 없는 문장은 절대 금지. 저장할 이유가 없어진다.
  - 마지막 줄은 숫자·기한을 담으면서 행동을 촉구하는 형태로 (예: {LAST_LINE_EXAMPLE}).
- 본문에서 핵심 키워드는 <b>키워드</b>로 감싸 강조 (각 카드당 1~2개, 한 줄에 최대 1개). 강조는 반드시 정보를 담은 명사(대상·금액·기한·제도명)만 — 동사·부사·수식어는 강조 금지. <b>태그는 글자수에서 제외해서 셈 것.
- 중요: 줄을 생성한 뒤 머릿속으로 글자 수를 세어서 17자 초과면 짧게 다시 써라. 단, "(16자)"처럼 글자 수를 세었다는 표시나 괄호 메모를 절대 실제 텍스트에 포함하지 마라 — 최종 문장만 순수하게 출력할 것.
- 카드4(저장용 요약): 이 카드는 "저장" 버튼을 누르게 만드는 유일한 카드다.
  대전제 — 사람은 **나중에 다시 찾기 귀찮은 정보**만 저장한다. 검색 한 번이면 나오는 말은 아무도 저장하지 않는다.
  앞 카드(2·3)에 나온 핵심 사실을 **일부러 다시 적어라.** 이 카드 한 장만 저장하면 끝나야 하므로
  중복을 피하려고 알맹이를 빼면 저장할 이유가 사라진다 — 다만 문장이 아니라 아래 요약 형식으로 압축한다.
  - headline = 짧은 한 줄 (8자 이내). 매번 똑같이 쓰지 말고 주제에 맞게 변주.
  - items = 핵심 4개. 각 항목은 반드시 **"라벨 · 값" 구조**로 쓴다 (공백 포함 12~20자).
    라벨은 2~4자, 값에는 **기관·사이트·제도명 같은 고유명사나 숫자를 반드시 넣어라.**
    라벨은 주제에 맞게 골라라 — 경제/지원금이면 신청처·대상·서류·기한, 건강이면 기준·권장량·주의·시기,
    사건사고면 신고처·대상·증거·기한 식으로.
    좋은 예: "신청처 · <b>정부24</b> 보조금24 메뉴" / "대상 · 건보료 <b>10만원</b> 이하"
            / "서류 · 신분증+<b>통장사본</b>+등본" / "기한 · <b>12월 31일</b> 마감 연장없음"
    나쁜 예: "정부24에서 신청하세요" (라벨도 숫자도 없음) / "조건을 잘 확인하세요" (알맹이 없음)
  - **특히 '서류·준비물' 항목을 빼먹지 마라.** 기억으로 재구성이 불가능해서 저장 동기가 가장 확실하다.
  - 4개 중 최소 2개에는 숫자가 들어가야 한다 (금액·기한·비율·나이·인원 등).
  - "확인하세요", "알아보세요", "챙기세요" 같은 서술어로 끝나는 항목은 금지 — 그건 정보가 아니라 잔소리다.
  - 각 항목에서 핵심 명사 1개만 <b>단어</b>로 감싸 강조.
  - closing = 한 줄 (공백 포함 14~22자). "팔로우"는 여기 쓰지 마 — 카드4는 저장 전용이다.
    "저장하세요"라고 시키지 말고, **저장해두면 언제 쓸모 있는지**를 말해라.
    좋은 예: "신청 전에 이 카드만 다시 보면 됩니다" / "마감 일주일 전에 다시 꺼내보세요"
- 인스타 캡션: 아래 구조를 반드시 지켜:
  1) 첫 줄: 오늘 주제를 강한 한 문장으로 후킹. "~알고 계셨나요?" 류 질문형 반복 금지 — 숫자 제시형("300만원, 신청 안 하면 사라집니다"), 반전형("다들 아는 그 방법, 사실 손해입니다")을 우선 쓰고, "~하세요"로 끝나는 명령형은 되도록 피해라
     (실측: 표본은 아직 작지만(n=4) 명령형 첫 줄은 저장률이 유의미하게 낮았다(p=0.014) — 릴스 후킹에서도 같은 방향으로 더 크게 나온 패턴이라 같이 주의).
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
  "card4": {{ "headline": "이것만 기억하세요", "items": ["라벨 · 값1","라벨 · 값2","라벨 · 값3","라벨 · 값4"], "closing": "저장해두면 언제 쓸모 있는지 한 줄" }},
  "caption": "인스타 캡션 전체 텍스트"
}}
"""

print("Gemini가 주제를 고르고 카드 내용을 만드는 중...\n")


# 503 UNAVAILABLE("high demand")·429는 몇 분이면 풀리는 일시적 과부하다.
# 기존 30/60/90초(총 3분)로는 못 넘겨서, 잠깐의 수요 급증에 그날 발행이 통째로 날아갔다.
# 무인 운영이므로 사람이 다시 돌려줄 수 없다 → 총 대기 시간을 넉넉히 잡는다.
# (퍼블릭 저장소 GitHub Actions는 실행 시간이 무료라 대기 비용은 0)
TRANSIENT = ("503", "unavailable", "429", "resource_exhausted",
             "high demand", "overloaded", "deadline", "timeout", "internal")


# 계정에서 아예 못 쓰는 모델(404/not found)은 재시도해도 소용없으니 목록에서 뺀다.
UNAVAILABLE_MODEL = ("not found", "404", "not supported", "does not exist",
                     "permission", "not available")


def call_gemini(correction=""):
    """모델 후보를 돌면서 시도하고, 한 바퀴 다 막히면 백오프 후 다시 한 바퀴."""
    prompt = PROMPT + correction
    usable = list(MODEL_CHAIN)
    rounds = 5
    last_err = None
    for rnd in range(rounds):
        for model in list(usable):
            try:
                if model != MODEL_CHAIN[0] or rnd > 0:
                    print(f"  모델 시도: {model}", flush=True)
                return client.models.generate_content(model=model, contents=prompt)
            except Exception as e:
                last_err = e
                msg = str(e).lower()
                if any(t in msg for t in UNAVAILABLE_MODEL):
                    print(f"  {model}: 이 계정에서 사용 불가 — 후보에서 제외", flush=True)
                    usable.remove(model)
                    continue
                if not any(t in msg for t in TRANSIENT):
                    print(f"  일시적 오류가 아니라 재시도하지 않습니다: {e}", flush=True)
                    raise
                print(f"  {model}: 일시 과부하({e.__class__.__name__})", flush=True)
        if not usable:
            break
        if rnd < rounds - 1:
            wait = min(300, 45 * (2 ** rnd))   # 45s, 90s, 180s, 300s → 총 ~10분
            print(f"  후보 모델이 모두 과부하 — {wait}초 후 다시 시도 "
                  f"({rnd + 1}/{rounds - 1})", flush=True)
            time.sleep(wait)
    raise last_err if last_err else RuntimeError("Gemini 호출 실패")


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


# 저장 가치 검증 — 구조는 멀쩡한데 알맹이가 없는 카드4를 걸러 재생성시킨다.
#
# 왜 기계 검사가 필요한가 (2026-09-14 실측): 게시물 338개 중 저장이 일어난 건
# 6개뿐이었다. 프롬프트에 "저장 가치 있게 써라"라고 적는 것만으로는 안 바뀌었다 —
# 실제로 나온 항목이 "정부24에서 신청하세요"처럼 검색 한 번이면 나오는 말이었고,
# 그런 건 아무도 저장하지 않는다. 그래서 "숫자가 들어있는가"를 기계적으로 센다.
# 숫자는 구체성의 지문이라(금액·기한·비율), 뭉뚱그린 문장을 가장 싸게 걸러낸다.
#
# 저장은 알고리즘 신호이기도 하다: 저장·공유가 있는 카드는 평균 도달 191,
# 없는 카드는 15였다(12.4배). 저장이 안 되면 도달 자체가 팔로워 안에 갇힌다.
EMPTY_TAILS = ("확인하세요", "알아보세요", "챙기세요", "준비하세요",
               "주목하세요", "기억하세요", "신청하세요")


def save_value_issues(d):
    """카드4의 저장 가치가 부족한 지점을 목록으로 반환 (빈 목록이면 합격)"""
    issues = []
    items = [re.sub(r"<[^>]+>", "", x).strip() for x in (d.get("card4") or {}).get("items", [])]
    if len(items) < 4:
        issues.append(f"카드4 항목이 {len(items)}개 — 4개를 채워라 (신청처·대상·서류·기한 식)")
    if sum(1 for t in items if re.search(r"\d", t)) < 2:
        issues.append("카드4에 숫자가 든 항목이 2개 미만 — 금액·기한·비율 같은 구체적 수치를 넣어라")
    # 구분자는 모델이 ·/ㆍ/•/: 중 아무거나 쓸 수 있어 넉넉히 인정한다
    # (프롬프트는 "·"를 지시하지만, 구분자 종류로 재생성을 낭비할 이유가 없다)
    labeled = re.compile(r"^[가-힣A-Za-z]{2,5}\s*[·ㆍ•・:：]\s*\S")
    unlabeled = [t for t in items if not labeled.match(t)]
    if unlabeled:
        issues.append(f"카드4 항목에 '라벨 · 값' 구조가 없음({' / '.join(unlabeled)})")
    vague = [t for t in items if t.rstrip(" .!·").endswith(EMPTY_TAILS)]
    if vague:
        issues.append(f"카드4 항목이 잔소리로 끝남({' / '.join(vague)}) — 정보로 바꿔라")
    return issues


# 재생성할 때 같은 프롬프트를 그대로 보내면 모델은 왜 거절당했는지 모른다.
# (generate_reel.py에서 이미 쓰고 있는 방식 — 실패 사유를 되먹인다)
TRIES = 4
data = None
correction = ""
for gen_try in range(1, TRIES + 1):
    response = call_gemini(correction)
    try:
        cand = parse_json(response.text or "")
        validate(cand)
    except Exception as e:
        print(f"  응답 형식 오류({e}) — 재생성 {gen_try}/{TRIES}")
        correction = ("\n\n[매우 중요] 직전 응답이 형식 오류로 거절됐다. "
                      "지정한 JSON 형식만, 다른 설명 없이 출력해라.")
        time.sleep(5)
        continue

    issues = save_value_issues(cand)
    if not issues:
        data = cand
        break
    if gen_try == TRIES:
        # 마지막 시도에서는 저장 가치가 미달이어도 발행을 막지 않는다.
        # 무인 운영이라 사람이 다시 돌려줄 수 없다 — 아쉬운 카드가 빈손보다 낫다.
        print(f"  [경고] 저장 가치 미달이지만 마지막 시도라 그대로 발행: {issues}")
        data = cand
        break

    print(f"  저장 가치 부족 — 재생성 {gen_try}/{TRIES}: {issues}")
    correction = ("\n\n[매우 중요] 직전 응답의 카드4가 거절됐다:\n- "
                  + "\n- ".join(issues)
                  + "\n카드4 items를 반드시 '라벨 · 값' 구조로 다시 써라 "
                    "(예: \"신청처 · <b>정부24</b> 보조금24\", \"기한 · <b>12월 31일</b>까지\"). "
                    "각 항목에 기관·사이트·제도명 같은 고유명사나 금액·기한 같은 숫자를 넣어라.")
    time.sleep(3)

if data is None:
    print(f"[중단] Gemini가 {TRIES}회 연속 올바른 형식을 주지 않았어요.")
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
