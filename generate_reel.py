import os
import datetime
import re
import json
import sys
import time
import random
import urllib.parse
import requests
import feedparser
from dotenv import load_dotenv
from google import genai
from recent_topics import avoid_line, get_recent_topics, find_duplicate, dup_correction

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
    PERSONA = "너는 'GLEND'라는 건강 실전 꿀팁 인스타그램 릴스 채널의 전문 작가야. 뉴스 한 편을 본 것 같은 밀도로 핵심을 꽉 채워 전달한다."
    TOPIC_DESC = "오늘의 최신 건강 관련 뉴스 제목 목록"
    HOOK = '"~하면 몸 망친다" 류의 경각심 자극형'
    QEX = '"healthy meal bowl", "running shoes closeup", "dark bedroom night"'
elif CATEGORY == "incident":
    PERSONA = "너는 'GLEND'라는 트렌드 인스타그램 릴스 채널의 전문 작가야. 자극적·공감형 사건·사고·논란을 배경부터 대처법까지 꽉 채워 전한다."
    TOPIC_DESC = "오늘의 최신 사건·사고·논란 관련 뉴스 제목 목록"
    HOOK = '충격 사실 제시형 (질문형 아님 — 물음표로 끝내지 마라)'
    QEX = '"car accident night", "police line tape", "ambulance lights night"'
else:
    PERSONA = "너는 'GLEND'라는 경제·재테크 실전 꿀팁 인스타그램 릴스 채널의 전문 작가야. 이득/손해 정보를 조건·금액·절차까지 꽉 채워 전한다."
    TOPIC_DESC = "오늘의 최신 경제/재테크 관련 뉴스 제목 목록"
    HOOK = '"~안 하면 손해" 류의 손실 회피형'
    QEX = '"korean won bills", "korean won calculator desk", "seoul apartment buildings"'

# 3) 릴스 대본 — 길이는 mid(60초) 고정.
# 길이 A/B는 폐기했다. 두 가지 이유:
#  (1) 배정값이 한 번도 저장된 적이 없다 — reel_content_*.json과 로그가 .gitignore에 있고
#      Actions 러너는 매 실행마다 폐기된다. 검증이 원리적으로 불가능한 실험이었다.
#  (2) 길이 규칙이 후킹 길이까지 결정하므로 첫 3초와 교락돼 해석이 안 된다.
# mid(60초)로 고정한다. 러닝타임 검증과 trim_to_budget 방어선이 mid에만 있고,
# 도달 1인당 평균 시청이 3.25초인 채널에서 90초를 만드는 건 87초를 버리는 것이다.
LENGTH_VARIANT = (os.getenv("REEL_LENGTH", "").strip().lower() or "mid")
if LENGTH_VARIANT == "short":   # 구 변형명 호환
    LENGTH_VARIANT = "mid"
if LENGTH_VARIANT not in ("long", "mid"):
    LENGTH_VARIANT = "mid"

if LENGTH_VARIANT == "mid":
    # 60초 안에 밀도 있게 설명하고 마지막을 '결론'으로 닫는 구성.
    BODY_COUNT = 9            # 후킹 1 + 본문 9 = 10장면
    DURATION_DESC = "55~60초 (60초를 절대 넘기면 안 됨)"
    CHAR_RANGE = "32~38자"
    FLOW = ("  (2) 무슨 일인지 배경·맥락  (3) 핵심 내용과 정확한 수치\n"
            "  (4) 누가 대상인지 조건  (5) 얼마를 받거나 아끼는지 구체적 금액\n"
            "  (6) 신청·실행 방법과 절차  (7) 기한과 놓치기 쉬운 주의점\n"
            "  (8) 사람들이 흔히 하는 실수  (9) 함께 챙기면 좋은 추가 꿀팁\n"
            "  (10) **결론** — 오늘 내용을 한 문장으로 압축한 결론과 행동 지시")
    SCENE_STUBS = ["본문2 배경·맥락", "본문3 핵심 수치", "본문4 대상 조건",
                   "본문5 구체적 금액", "본문6 신청 방법", "본문7 기한·주의점",
                   "본문8 흔한 실수", "본문9 추가 꿀팁", "본문10 결론"]
    SAVE_SCENE = "9나 10"
else:
    BODY_COUNT = 12           # 후킹 1 + 본문 12 = 13장면
    DURATION_DESC = "90~100초"
    CHAR_RANGE = "60~80자"
    FLOW = ("  (2) 무슨 일인지 배경·맥락  (3) 핵심 내용과 정확한 수치  (4) 왜 이렇게 됐는지 이유\n"
            "  (5) 누가 대상인지 조건  (6) 얼마를 받거나 아끼는지 구체적 금액  (7) 신청·실행 방법과 절차\n"
            "  (8) 기한과 놓치기 쉬운 주의점  (9) 사람들이 흔히 하는 실수  (10) 실수를 피하는 구체적 요령\n"
            "  (11) 함께 챙기면 좋은 관련 제도나 추가 꿀팁\n"
            "  (12) **결론** — 오늘 내용을 한 문장으로 압축한 결론과 행동 지시")
    SCENE_STUBS = ["본문2 배경·맥락", "본문3 핵심 수치", "본문4 이유", "본문5 대상 조건",
                   "본문6 구체적 금액", "본문7 신청 방법", "본문8 기한·주의점",
                   "본문9 흔한 실수", "본문10 실수 피하는 요령",
                   "본문11 관련 제도·추가 꿀팁", "본문12 결론"]
    SAVE_SCENE = "11이나 12"

TOTAL_SCENES = BODY_COUNT + 1   # 후킹 포함
SCENE_JSON = ",\n".join(
    ['    { "narration": "후킹 자막 문장", "query": "영어 사진 검색어" }'] +
    ['    { "narration": "%s", "query": "영어 사진 검색어" }' % st for st in SCENE_STUBS])

print(f"[길이 변형] {LENGTH_VARIANT} — 목표 {DURATION_DESC}, 장면 {TOTAL_SCENES}개\n")

RECENT_TOPICS = get_recent_topics()
AVOID = avoid_line(RECENT_TOPICS)

# 오늘 날짜(KST)와 계절 — 프롬프트에 날짜가 없어서 모델이 계절을 짐작으로 썼다.
# 2026-09-26 릴스가 9월에 "봄철 영농기"라고 쓴 게 실제로 나갔다(수확기가 맞다).
_KST = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)
_SEASON = {12: "겨울", 1: "겨울", 2: "겨울", 3: "봄", 4: "봄", 5: "봄",
           6: "여름", 7: "여름", 8: "여름"}.get(_KST.month, "가을")
TODAY_LINE = (f"오늘은 {_KST.year}년 {_KST.month}월 {_KST.day}일, {_SEASON}이야. "
              "계절·시기 표현(봄철, 연말 등)은 반드시 오늘 날짜에 맞게 써.")

PROMPT = f"""
{PERSONA}

{TODAY_LINE}

아래는 {TOPIC_DESC}이야:
{news_text}

이 중에서 대중이 가장 반응할 핵심 주제 하나를 직접 골라서, 정보가 꽉 찬 세로 릴스 대본을 만들어줘. 시청자가 이 영상 하나만 보면 그 주제를 완전히 이해하고 바로 행동할 수 있어야 해. 전체 길이는 약 {DURATION_DESC}.
릴스는 {TOTAL_SCENES}개 장면(scene)으로 구성돼. 각 장면은 성우가 말하는 동시에 화면 중앙에 그대로 뜨는 자막 문장(narration)과 배경 사진 검색어(query)로 이뤄져.
{AVOID}

주제 고르는 기준(공유 설계): 인스타는 '보내기(DM으로 친구에게 공유)'가 비팔로워에게 퍼지는 가장 강한 신호다.
시청자가 "이거 OO한테 보내야겠다" 하고 **특정한 한 사람**을 떠올릴 주제를 우선 골라라
(예: 전세 계약 앞둔 친구, 시골 계신 부모님, 가게 하는 친구, 운전하는 부모님).
시청자 본인이 대상이 아니어도 된다 — 보내줄 사람이 떠오르면 된다. 누구에게도 보낼 이유가 없는 단순 시사 뉴스는 피해라.

규칙:
- scene 1 = 후킹. **공백 포함 12~18자.** 아래 본문 글자수 규칙은 scene 1에 적용하지 마라.
  이건 제목이지 문장이 아니다. 숨 한 번에 읽히는 길이여야 한다. {HOOK}
  좋은 예: "치료비 한 푼도 못 받습니다" / "경차면 연 30만원 환급" / "37번 일부러 박았다"
  나쁜 예: "교통사고 나고 8주 넘게 누워있다간 치료비를 한 푼도 못 받는 상황이 생깁니다" (너무 김)
- 후킹에 "꿀팁", "총정리", "비밀", "필독", "주목", "~하는 법" 같은 광고성 명사형 표현을 쓰지 마라.
  (실측: 해당 표현이 있는 7건의 평균 시청 1.97초 vs 나머지 32건 3.30초. 다만 p=0.086으로
   통계적 유의수준에는 못 미치는 약한 근거다.)
- 후킹은 물음표로 끝내지 마라(질문형 금지). "~알고 계셨나요?", "~하셨나요?"류가 식상해서가 아니라 실제로 덜 본다.
  (실측 2026-09-13, archive/instagram_posts.csv 78건: 질문형 훅 8건 평균시청 3.08초 vs 비질문형 70건 5.44초, p=0.014로 유의미.
   실제 온스크린 훅 34건으로 교차검증해도 같은 방향(3.27초 vs 4.85초).)
- 후킹을 "~하세요", "~보세요" 같은 명령형으로 끝내지도 마라.
  (실측: 명령형 훅 5건 평균시청 2.52초 vs 나머지 73건 5.38초, p=0.002로 가장 강하게 유의미했다.
   표본이 작아 계속 지켜봐야 하지만, 지금까지 측정된 형식 중 가장 나쁘다. 실제 온스크린 훅에서도 같은 방향.)
- 대신 이런 형식을 우선 써 — 숫자 제시형("300만원, 신청 안 하면 사라집니다"), 반전형("다들 아는 그 방법, 사실 손해입니다"),
  대상 지목형(단, 명령형으로 끝내지 말 것 — "만 34세 이하라면 손해" O, "만 34세 이하라면 지금 확인하세요" X).
  대상 지목형은 시청자 대신 **보내줄 사람**을 지목해도 좋다 — "시골 부모님 농기계, 보험 없으면 손해"처럼.
- scene 2~{TOTAL_SCENES} = 본문 {BODY_COUNT}개. 아래 흐름을 따라 각 장면이 서로 다른 알맹이를 담아:
{FLOW}
- 마지막 본문 장면(scene {TOTAL_SCENES})은 반드시 **결론**이다. 앞 내용을 요약 나열하지 말고,
  "그래서 결국 뭘 해야 하는가"를 한 문장으로 딱 못 박아라 (예: "조건만 맞으면 5분 신청으로 40만원, 오늘 안에 확인하세요").
- 절대 같은 말을 다르게 반복하지 마. 각 장면은 앞에서 안 나온 새로운 정보를 하나씩 추가해야 해. 내용이 부족하면 그 주제를 고르지 말고 정보가 풍부한 다른 주제를 골라.
- narration은 성우가 소리 내어 읽는 문장이니, 실제 사람이 말하듯 자연스러운 구어체로 써. 친근한 '해요체'를 기본으로 하고(예: "~있어요", "~된대요", "~챙기세요"), 딱딱한 문어체나 어색한 번역투(예: "~을 통해", "~에 의해", "~라 할 수 있다")는 쓰지 마. **scene 2부터의** 각 narration은 공백 포함 {CHAR_RANGE}로 써 — **최소 글자수를 반드시 지켜라.** (scene 1 후킹은 위 규칙대로 12~18자) 짧게 쓰면 영상이 비어 보인다. 한 문장 또는 짧은 두 문장. 실제 수치·기관명·날짜·조건을 구체적으로 넣어 알맹이를 채워.
- 각 narration에서 가장 중요한 핵심 단어 1개만 <b>단어</b>로 감싸 강조(노란색). 장면당 1개만. (성우는 태그를 읽지 않음)
  강조는 반드시 **정보를 담은 명사**만 — 금액·기한·대상·제도명·기관명 (예: <b>40만원</b>, <b>12월 31일</b>, <b>서울청년포털</b>).
  동사·부사·서술어는 절대 강조하지 마 (나쁜 예: <b>저장해두고</b>, <b>지금</b>, <b>꼭</b>, <b>바로</b>).
- 자막에 글자수 메모("(16자)" 등)를 절대 쓰지 마. 최종 문장만.
- query는 각 장면 분위기에 맞는 영어 사진 검색어 2~3단어 (예: {QEX}).
- query 중요 규칙: 한국에서 벌어진 일을 다루므로 배경에 외국 요소가 보이면 어색해. 두 가지를 반드시 지켜:
  (가) 돈이 나오는 장면은 반드시 "korean won"을 넣어 검색해 (예: "korean won bills", "korean won cash desk").
      단 "korean won"은 그 장면 자막이 **금액·지원금·이자처럼 돈 자체를 말할 때만** 써라. 신청 절차·대상 조건·주의점·건강 정보처럼
      돈 이야기가 없는 장면은 그 내용에 맞는 사물·장소로 검색해 (예: 서류 → "application form desk", 병원 → "hospital corridor",
      음식 → "grilled fish plate"). 돈 사진이 장면마다 반복되면 영상이 단조로워진다(9월 실측: 돈 사진 103장 중 33장이 돈 얘기 없는 장면). 그냥 "money", "cash", "banknotes"로 검색하면 달러·유로·외국 지폐가 나와서 한국 소식에 안 맞아. 외국 지폐·동전·신용카드 로고가 보이면 안 돼. 검색어에 "money"라는 단어 자체를 쓰지 마 — 반드시 "korean won"으로 대체할 것.
  (나) 반드시 **사람 얼굴이 안 나오는 사진**으로 검색해 — 사물(돈, 계산기, 서류, 도구), 풍경(도시, 거리, 건물, 자연), 손·뒷모습 클로즈업 위주. "person", "man", "woman", "people" 같은 단어는 쓰지 마. 꼭 사람이 필요하면 "hands closeup"이나 "silhouette"처럼 얼굴 없는 형태로.
- scene {SAVE_SCENE} 중 하나의 narration 끝에 "저장해두고 다시 보세요" 같은 저장 유도를 자연스럽게 한 번 넣어. (저장 유도는 전체에서 딱 한 번만)
- 화면 상단에 영상 내내 고정으로 뜰 짧은 제목(title)도 만들어줘. 주제를 한눈에 보여주는 8자 이내의 간결한 키워드 (예: "운전면허 지원금", "청년 청약통장", "전기요금 절약"). 이모지 1개 붙여도 좋음.
- 썸네일 커버(cover)도 만들어줘 — 피드에서 클릭을 부르는 카드뉴스식 후킹:
  - cover.title = 강렬한 2줄 제목, 한 줄 6자 이내 (예: "살짝 쿵 했는데\n3천만원 탄다"). 이 두 줄만으로 궁금해서 누르게 만들어.
  - cover.title 안에서 가장 중요한 핵심 명사 1개(금액·대상·제도명)만 <b>단어</b>로 감싸 강조. 동사·부사는 강조 금지 (예: "살짝 쿵 했는데\n<b>3천만원</b> 탄다").
- 팔로우 유도 문장(follow_cta)도 만들어줘 — 마지막 로고 화면 위에 성우 목소리로만 나온다(자막 없음):
  - "이런 정보 매일 받아보세요" 같은 어느 계정에나 붙는 말은 절대 금지. 시청자가 팔로우할 이유가 안 된다.
  - 반드시 이 구조: (1) 방금 본 주제가 속한 **구체적인 분야**를 말하고 (2) 이 계정이 **앞으로 무엇을 계속 주는지** 약속하고 (3) "@glend_kr 팔로우"로 끝낸다.
  - 좋은 예: "놓치면 사라지는 <b>정부지원금</b>, 매일 하나씩 찾아드려요. @glend_kr 팔로우하세요!"
  - 좋은 예: "이런 <b>전세사기</b> 예방법, 매일 올려요. 당하기 전에 @glend_kr 팔로우하세요!"
  - 나쁜 예: "이런 정보 매일 받아보고 싶다면 팔로우 눌러주세요" (분야도 약속도 없음)
  - 공백 포함 40~60자. 핵심 명사 1개만 <b>단어</b>로 감싸 강조.
- 공유 대상(share_target)도 만들어줘 — 이 영상을 보고 떠올릴, 보내줄 **한 사람**. 결론 장면 자막 아래에 "→ OO에게 공유"로 뜬다.
  - 관계 + 상황, 공백 포함 4~16자 (좋은 예: "전세 사는 친구", "시골 계신 부모님", "이번에 결혼하는 친구", "가게 하는 친구", "운전하는 부모님").
  - 나쁜 예: "주변 사람", "필요한 지인", "여러분" — 막연하면 아무도 떠오르지 않아 아무도 안 보낸다.
- 인스타 캡션: 첫 줄 후킹 + 핵심 5~6줄(영상 내용을 글로도 충실히) + 저장/팔로우 유도 + 공유 대상을 지목하는 한 줄(예: "📤 전세 사는 친구에게 보내주세요") + 해시태그 5개(대형 1 + 중형 2 + 니치 2로 믹스).
  "주변에 ~한 분이 있다면 공유해 주세요"처럼 막연하게 쓰지 마라 — share_target과 같은 사람을 그대로 지목해라.
- 캡션의 팔로우 유도도 마찬가지로 "무엇을 계속 주는 계정인지"를 구체적으로 밝혀야 해 (예: "📌 매일 놓치기 쉬운 정부지원금·정책만 골라 올립니다 → @glend_kr").
- 캡션과 자막 모두에 마크다운 문법(**별표**, ##, - 목록 등)을 절대 쓰지 마. 인스타는 마크다운을 표시하지 못해서 별표가 그대로 노출돼. 강조는 이모지나 줄바꿈으로만.

반드시 아래 JSON 형식으로만 답해. 다른 설명 금지.
{{
  "topic": "네가 고른 주제",
  "title": "화면 상단 고정 제목(8자 이내 + 이모지)",
  "cover": {{ "title": "1줄\\n2줄(한 줄 6자 이내, <b>포인트</b> 포함)" }},
  "scenes": [
{SCENE_JSON}
  ],
  "follow_cta": "분야 + 앞으로 줄 것 + @glend_kr 팔로우 (<b>포인트</b> 1개 포함)",
  "share_target": "보내줄 한 사람(관계 + 상황, 4~16자)",
  "caption": "인스타 캡션 전체 텍스트"
}}
"""

print("Gemini가 릴스 대본을 만드는 중...\n")


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


def _plain_len(s):
    return len(re.sub(r'<[^>]+>', '', s.get("narration", "")))


def est_seconds(scenes):
    """최종 영상 길이 추정 — 대본 장면만 넣으면 아웃트로(팔로우 멘트)까지 포함한 값.

    2026-09-28 재적합: 8/20~9/27 mid 릴스 69편의 실제 total_sec을 대본 글자수로 회귀하면
    실제 ≈ 0.0937 x 글자수 + 21.06초 (10장면 기준, 잔차 표준편차 1.5초).
    예전 식(0.124 x 글자수 + 장면당 0.5 + 6)은 긴 대본을 2초가량 과대추정해서,
    실제로는 57초짜리를 "60초 초과"로 거절하고 재생성시키고 있었다.
    """
    return sum(_plain_len(sc) * 0.0937 + 0.5 for sc in scenes) + 16.06


# mid 목표 구간. 상한은 60초 제한에 잔차 여유를 둔 값, 하한은 그 밑이면 "비어 보이는" 길이.
# 하한이 없던 때는 최근 30편 중 12편이 45초 미만(최저 33초)으로 나갔다 — 길이 초과로
# 재생성할 때 "32자 이내→26자 이내"로 조이던 되먹임이 반대쪽으로 튄 결과였다.
MID_MAX_SEC = 58.0
MID_MIN_SEC = 48.0
_BODY_LO, _BODY_HI = (int(x) for x in CHAR_RANGE.rstrip("자").split("~"))


def validate(d):
    """구조 검증 — 깨진 응답이 렌더/조립 단계로 흘러가지 않게. 길이·주제·공유는 따로 본다."""
    assert isinstance(d.get("caption"), str) and d["caption"].strip(), "caption 누락"
    assert isinstance(d.get("title"), str) and d["title"].strip(), "title 누락"
    scenes = d.get("scenes")
    assert isinstance(scenes, list) and len(scenes) == TOTAL_SCENES, f"scenes 개수 오류({len(scenes) if isinstance(scenes, list) else '없음'} != {TOTAL_SCENES})"
    for i, s in enumerate(scenes, 1):
        assert isinstance(s.get("narration"), str) and s["narration"].strip(), f"scene{i} narration 누락"
        assert isinstance(s.get("query"), str) and s["query"].strip(), f"scene{i} query 누락"


def trim_to_budget(scenes, limit=MID_MAX_SEC, max_drop=None, quiet=False):
    """긴 대본은 재생성 대신 중간 장면을 덜어 60초에 맞춘다.

    후킹(첫 장면)과 결론(마지막 장면)은 구조의 핵심이라 절대 건드리지 않고,
    결론 바로 앞(추가 꿀팁·흔한 실수)부터 덜어낸다.
    2026-09-29: flash-lite가 62~66초 대본을 반복해서 써서 재생성을 다 태우고,
    결국 47초짜리가 나갔다. 한두 장면만 빼면 57초가 되는 대본을 버린 셈이라,
    이제 초과는 먼저 잘라 보고 구간에 들어오면 그대로 쓴다.
    """
    scenes = list(scenes)
    dropped = 0
    while len(scenes) > 4 and est_seconds(scenes) > limit and (max_drop is None or dropped < max_drop):
        drop = len(scenes) - 2          # 결론 바로 앞 장면
        removed = scenes.pop(drop)
        dropped += 1
        if not quiet:
            print(f"  [길이 조정] 장면 {drop + 1} 제거: {removed.get('narration','')[:24]}...",
                  flush=True)
    return scenes


def length_issue(d):
    """길이 사유(없으면 빈 문자열). 초과는 2장면 이내로 잘라서 구간에 들어오면 문제로 보지 않는다."""
    if LENGTH_VARIANT != "mid":
        return ""
    est = est_seconds(d["scenes"])
    if est > MID_MAX_SEC:
        if MID_MIN_SEC <= est_seconds(trim_to_budget(d["scenes"], max_drop=2, quiet=True)) <= MID_MAX_SEC:
            return ""
        return f"예상 러닝타임 {est:.1f}초 — {MID_MAX_SEC:.0f}초 초과"
    if est < MID_MIN_SEC:
        return f"예상 러닝타임 {est:.1f}초 — {MID_MIN_SEC:.0f}초 미만"
    return ""


def length_correction(d, msg):
    """길이 사유를 되먹인다. 몇 자를 써야 하는지 숫자로, 직전 평균과 함께.

    예전엔 초과할 때마다 상한만 6자씩 깎아("26자 이내") 모델이 반대로 너무 짧게 썼다.
    목표 구간을 양쪽 다 명시하고, 직전 시도가 평균 몇 자였는지 알려 스스로 보정하게 한다.
    """
    body = d["scenes"][1:]
    avg = sum(_plain_len(s) for s in body) / max(1, len(body))
    if "초과" in msg:
        lo, hi, verb = _BODY_LO, _BODY_HI - 2, "줄여라"
    else:
        lo, hi, verb = _BODY_LO + 2, _BODY_HI, "늘려라 — 수치·조건·기관명을 더 넣어 채워"
    return (f"\n\n[매우 중요] 직전 시도가 길이 문제로 거절됐다: {msg}\n"
            f"직전 시도의 scene 2~{TOTAL_SCENES} narration은 평균 {avg:.0f}자였다. "
            f"이번에는 각각 공백 포함 **{lo}~{hi}자**로 {verb}. "
            f"{lo}자 미만도, {hi}자 초과도 안 된다. 장면 수는 그대로 유지해라.")


# 공유 설계 — "이 영상을 누구에게 보낼지"를 콘텐츠가 대신 정해 준다.
# 시청자 본인이 대상이 아니어도 "이거 OO한테 보내야겠다"가 떠오르면 보내기(DM)가 생긴다.
# 인스타는 보내기를 비팔로워 도달의 가장 강한 신호로 쓴다고 밝혀 왔다.
# 2026-09: 릴스 49편 중 공유 1건(1,000도달당 0.27) — 8월 3.29에서 사실상 0이 됐다.
# 기존 캡션의 "주변에 고민하는 분이 있다면 공유해 주세요"는 아무도 떠올리게 하지 못한다.
SHARE_RELATIONS = ("친구", "부모님", "엄마", "아빠", "어머니", "아버지", "동생", "언니", "오빠",
                   "누나", "형", "남편", "아내", "배우자", "동료", "사장님", "자녀", "아들", "딸",
                   "가족", "할머니", "할아버지", "조부모", "선배", "후배", "룸메", "이웃", "애인",
                   "남친", "여친", "신랑", "신부", "시부모", "장인", "장모", "처가", "시댁", "팀장")
SHARE_GENERIC = ("주변", "여러분", "지인", "필요한", "누구나", "모두", "모든", "분들", "사람들")


def share_target(d):
    return re.sub(r"<[^>]+>", "", d.get("share_target") or "").strip()


def share_issues(d):
    t = share_target(d)
    if not t:
        return ["share_target 누락"]
    issues = []
    if not (4 <= len(t) <= 16):
        issues.append(f"share_target '{t}': {len(t)}자 — 4~16자로")
    if any(g in t for g in SHARE_GENERIC):
        issues.append(f"share_target '{t}': 막연하다 — '주변·지인·필요한 분' 대신 떠오르는 한 사람")
    if not any(r in t for r in SHARE_RELATIONS):
        issues.append(f"share_target '{t}': 관계가 없다 — 친구·부모님·동생·동료처럼 관계 + 상황")
    return issues


def share_correction(issues):
    return ("\n\n[매우 중요] 직전 응답의 share_target이 거절됐다:\n- " + "\n- ".join(issues) +
            "\nshare_target은 이 영상을 보고 '이거 OO한테 보내야겠다' 하고 떠올릴 **한 사람**이다. "
            "관계 + 상황으로 써라 (예: \"전세 사는 친구\", \"시골 계신 부모님\", \"운전하는 부모님\", "
            "\"가게 하는 친구\", \"이번에 결혼하는 친구\").")


def add_share_line(d):
    """캡션 해시태그 바로 위에 공유 대상 지목 한 줄을 보장한다(모델이 빠뜨려도)."""
    t = share_target(d)
    cap = d.get("caption", "")
    if not t or t in cap:
        return
    line = f"📤 {t}에게 보내주세요"
    lines = cap.rstrip().split("\n")
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].lstrip().startswith("#"):
            lines[i:i] = [line, ""]
            break
    else:
        lines += ["", line]
    d["caption"] = "\n".join(lines)


# 재생성할 때 같은 프롬프트를 그대로 보내면 모델은 왜 거절당했는지 모른다.
# 사유별로 되먹이되, 순서는 주제 → 길이 → 공유. 주제가 바뀌면 나머지는 다 새로 쓰이기 때문이다.
# 2026-09-29: 중복 검사가 길이 검사 뒤에 있어서, 길이로 세 번 탈락하는 동안 모델은
# 매번 같은 DMZ 주제를 골랐고 마지막 시도라 중복인 채로 발행됐다.
TRIES = 5
data = None
best = None          # (점수, 후보) — 끝내 전부 통과하지 못하면 가장 나은 후보로 발행
correction = ""
for gen_try in range(1, TRIES + 1):
    response = call_gemini(correction)
    try:
        cand = parse_json(response.text or "")
        validate(cand)
    except AssertionError as e:
        msg = str(e)
        print(f"  검증 실패({msg}) — 재생성 {gen_try}/{TRIES}", flush=True)
        correction = (f"\n\n[매우 중요] 직전 응답이 거절됐다: {msg}\n"
                      "지정한 JSON 형식과 장면 수를 그대로 지켜라.")
        time.sleep(3)
        continue
    except Exception as e:
        print(f"  응답 형식 오류({e}) — 재생성 {gen_try}/{TRIES}", flush=True)
        correction = ("\n\n[매우 중요] 직전 응답이 형식 오류로 거절됐다. "
                      "지정한 JSON 형식만, 다른 설명 없이 출력해라.")
        time.sleep(3)
        continue

    dup = find_duplicate(cand.get("topic", ""), RECENT_TOPICS)
    length = length_issue(cand)
    share = share_issues(cand)
    if not (dup or length or share):
        data = cand
        break

    # 점수: 중복 > 길이 > 공유 순으로 나쁘다. 길이는 잘라 본 뒤 구간에서 벗어난 초 +
    # 3장면 이상 잘라야 하면 한 장면당 3초 감점(내용이 비는 것도 짧은 것만큼 나쁘다).
    trimmed = trim_to_budget(cand["scenes"], quiet=True)
    est = est_seconds(trimmed)
    off = (max(0.0, MID_MIN_SEC - est, est - MID_MAX_SEC)
           + 3.0 * max(0, len(cand["scenes"]) - len(trimmed) - 2)) if LENGTH_VARIANT == "mid" else 0.0
    score = (bool(dup), off, len(share))
    if best is None or score < best[0]:
        best = (score, cand)

    if dup:
        print(f"  주제 중복 — 재생성 {gen_try}/{TRIES}: '{cand.get('topic')}' ≈ 최근 '{dup}'", flush=True)
        correction = dup_correction(cand.get("topic"), dup)
    elif length:
        print(f"  길이 문제({length}) — 재생성 {gen_try}/{TRIES}", flush=True)
        correction = length_correction(cand, length)
    else:
        print(f"  공유 대상 부족 — 재생성 {gen_try}/{TRIES}: {share}", flush=True)
        correction = share_correction(share)
    time.sleep(3)

if data is None and best is not None:
    (was_dup, off, n_share), data = best
    print(f"  [경고] {TRIES}회 안에 모든 조건을 못 채워 가장 나은 후보로 발행합니다 "
          f"(주제 중복={'예' if was_dup else '아니오'}, 길이 이탈 {off:.1f}초, 공유 문제 {n_share}건).",
          flush=True)
if data is None:
    print(f"[중단] Gemini가 {TRIES}회 연속 조건을 만족하지 못했어요.")
    sys.exit(1)

if LENGTH_VARIANT == "mid" and est_seconds(data["scenes"]) > MID_MAX_SEC:
    before = est_seconds(data["scenes"])
    data["scenes"] = trim_to_budget(data["scenes"])
    print(f"  [길이 조정] {before:.1f}초 -> {est_seconds(data['scenes']):.1f}초 "
          f"(장면 {len(data['scenes'])}개)", flush=True)
print(f"  [길이] 예상 {est_seconds(data['scenes']):.1f}초", flush=True)

# 노란 강조(<b>) 보정 — 프롬프트는 "장면당 정보 명사 1개"를 요구하지만,
# 9월 릴스 본문 477장면 중 34%(162장면)에 강조가 아예 없었고 14건은 동사·부사를 칠했다
# ("저장해두고" 8건, "기다려요", "확인" 등). 재생성 없이 코드로 바로잡는다:
#  1) 서술어·부사를 감싼 <b>는 벗긴다
#  2) 강조가 없으면 첫 수치(금액·날짜·비율 등)를, 수치도 없으면 첫 기관·제도 이름을 감싼다.
_BAD_BOLD_END = re.compile(r"(요|다|세요|해|하기|하고|해두고|하자|니다)$")
_BAD_BOLD_WORD = {"지금", "꼭", "바로", "확인", "미리", "반드시", "당장", "절대", "조치", "파악", "금물", "안전"}
_NUM = re.compile(r"\d[\d,.]*\s*(?:만|억|천|백)?\s*(?:원|%|퍼센트|명|개|년|개월|월|일|시|세|살|배|회|건|호|곳|kg|g|kcal|칼로리|분|시간|주|평|mg|잔|번|종|대|차|단계|가지|등급|층|박)?")
# 수치가 없으면 기관·제도·상품 이름(정보 명사)을 칠한다.
_ENTITY = re.compile(r"[가-힣A-Za-z0-9]*(?:공단|공사|센터|포털|보험|지원금|장려금|수당|대출|적금|예금|통장|급여|연금|정부24|홈택스|복지로|국세청|보건소|은행|카드|바우처|공제|감면|환급금|제도|사업|청약|검진|접종)")


def fix_emphasis(text):
    def unwrap(m):
        inner = m.group(1).strip()
        return m.group(1) if (_BAD_BOLD_END.search(inner) or inner in _BAD_BOLD_WORD) else m.group(0)
    text = re.sub(r"<b>(.*?)</b>", unwrap, text)
    if "<b>" not in text:
        m = _NUM.search(text)
        if not (m and m.group(0).strip()):
            m = _ENTITY.search(text)
        if m and m.group(0).strip():
            tok = m.group(0).rstrip()
            text = text[:m.start()] + f"<b>{tok}</b>" + text[m.start() + len(tok):]
    return text


_fixed = 0
for _sc in data["scenes"][1:]:
    _new = fix_emphasis(_sc.get("narration", ""))
    if _new != _sc.get("narration"):
        _sc["narration"] = _new
        _fixed += 1
_nob = sum(1 for _sc in data["scenes"][1:] if "<b>" not in _sc.get("narration", ""))
print(f"  [강조] 보정 {_fixed}장면 / 강조 없는 장면 {_nob}개", flush=True)

# 결론 장면(마지막 본문) 자막 아래에 "→ OO에게 공유"를 띄우고, 캡션에도 같은 대상을 지목한다.
if share_target(data) and not share_issues(data):
    data["scenes"][-1]["share"] = f"→ {share_target(data)}에게 공유"
    add_share_line(data)
    print(f"  [공유] {share_target(data)}", flush=True)


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


# 로고 직전 팔로우 유도 장면 (배경 사진 + 자막 있음)
#
# 왜 Gemini가 쓰게 하는가:
#   기존의 "이런 정보 매일 받아보고 싶다면 팔로우"는 어느 계정에나 붙는 말이라
#   시청자에게 팔로우할 이유를 주지 못했다(도달 1097짜리 릴스도 전환 2명).
#   전환은 "이 계정을 팔로우하면 앞으로 뭘 받는지"가 구체적일 때 일어나므로,
#   방금 본 주제와 이어지는 약속을 매번 새로 쓰게 한다.
FOLLOW_FALLBACK = {
    "economy": "놓치면 사라지는 <b>지원금</b> 소식, 매일 골라 올려요. @glend_kr 팔로우하세요!",
    "incident": "당하기 전에 알아야 할 <b>대처법</b>, 매일 올려요. @glend_kr 팔로우하세요!",
    "health": "돈 안 드는 <b>건강 관리법</b>, 매일 하나씩 알려드려요. @glend_kr 팔로우하세요!",
}[CATEGORY]


def follow_narration(d):
    cta = (d.get("follow_cta") or "").strip()
    if not cta or "<b>" not in cta:
        return FOLLOW_FALLBACK
    return cta

if True:
    print("=== Gemini가 고른 주제 ===")
    print(" ->", data.get("topic", "(주제 표시 없음)"), "\n")

    print("Pexels에서 장면별 배경 사진 가져오는 중...")
    for i, scene in enumerate(data["scenes"], start=1):
        q = scene.get("query", "background")
        photo = get_photo(q)
        scene["bg"] = photo or "https://images.pexels.com/photos/210607/pexels-photo-210607.jpeg"
        print(f"  scene{i}: '{q}' -> {'OK' if photo else '실패(기본사진)'} | 자막: {scene['narration']}")

    # 마지막은 '결론(본문 마지막 장면) -> 로고' 순서.
    # 팔로우 멘트는 별도 장면을 만들지 않고 로고 화면 위에 음성으로만 얹는다.
    # (아웃트로는 render_reel.py가 로고만 그리고 자막을 렌더하지 않으므로 자막 없이 목소리만 나온다)
    n = len(data["scenes"])
    data["scenes"].append({"outro": True, "narration": follow_narration(data)})
    print(f"  scene{n+1}(아웃트로): 로고 + 팔로우 멘트(자막 없음)")

    # 배경음악 크레딧(CC BY 4.0) — 캡션에 자동 표기
    data["caption"] = data.get("caption", "").rstrip() + \
        "\n\n🎵 Music: Inspired – Kevin MacLeod (incompetech.com), CC BY 4.0"

    print("\n[캡션]\n" + data["caption"])

    data["length_variant"] = LENGTH_VARIANT
    out_file = f"reel_content_{POST_INDEX}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n저장 완료! {out_file} 생성됨 🎬")
