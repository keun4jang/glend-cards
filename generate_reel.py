import os
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
    HOOK = '질문형 또는 충격 사실 제시형'
    QEX = '"car accident night", "police line tape", "ambulance lights night"'
else:
    PERSONA = "너는 'GLEND'라는 경제·재테크 실전 꿀팁 인스타그램 릴스 채널의 전문 작가야. 이득/손해 정보를 조건·금액·절차까지 꽉 채워 전한다."
    TOPIC_DESC = "오늘의 최신 경제/재테크 관련 뉴스 제목 목록"
    HOOK = '"~안 하면 손해" 류의 손실 회피형'
    QEX = '"korean won bills", "korean won calculator desk", "seoul apartment buildings"'

# 3) 릴스 대본 — 길이 A/B.
#    "90초는 작은 계정에 부담"이라는 통설과 "90초 이상으로" 요청 중 어느 쪽이 맞는지
#    근거 없이 정하지 않고, 같은 주제·시간대 조건에서 번갈아 발행해 실측으로 판정한다.
#    변형은 REEL_LENGTH 환경변수로 강제할 수 있고(long/short), 없으면 날짜 기반 자동 배정.
from rotation import reel_length_variant

_slot = os.getenv("REEL_SLOT", "").strip()
LENGTH_VARIANT = (os.getenv("REEL_LENGTH", "").strip().lower()
                  or reel_length_variant(int(_slot) if _slot.isdigit() else 1))
if LENGTH_VARIANT == "short":   # 구 변형명 호환
    LENGTH_VARIANT = "mid"
if LENGTH_VARIANT not in ("long", "mid"):
    LENGTH_VARIANT = "long"

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

AVOID = avoid_line()

PROMPT = f"""
{PERSONA}

아래는 {TOPIC_DESC}이야:
{news_text}

이 중에서 대중이 가장 반응할 핵심 주제 하나를 직접 골라서, 정보가 꽉 찬 세로 릴스 대본을 만들어줘. 시청자가 이 영상 하나만 보면 그 주제를 완전히 이해하고 바로 행동할 수 있어야 해. 전체 길이는 약 {DURATION_DESC}.
릴스는 {TOTAL_SCENES}개 장면(scene)으로 구성돼. 각 장면은 성우가 말하는 동시에 화면 중앙에 그대로 뜨는 자막 문장(narration)과 배경 사진 검색어(query)로 이뤄져.
{AVOID}

규칙:
- scene 1 = 후킹. narration은 시선을 확 잡는 짧고 강한 한 문장. {HOOK}
- 후킹 형식 다양화: "~알고 계셨나요?", "~하셨나요?" 같은 질문형은 매번 반복되면 식상해. 질문형 말고 이런 형식을 우선 써 — 숫자 제시형("300만원, 신청 안 하면 사라집니다"), 명령형("월급 들어오면 이것부터 확인하세요"), 반전형("다들 아는 그 방법, 사실 손해입니다"), 대상 지목형("만 34세 이하라면 지금 멈추세요").
- scene 2~{TOTAL_SCENES} = 본문 {BODY_COUNT}개. 아래 흐름을 따라 각 장면이 서로 다른 알맹이를 담아:
{FLOW}
- 마지막 본문 장면(scene {TOTAL_SCENES})은 반드시 **결론**이다. 앞 내용을 요약 나열하지 말고,
  "그래서 결국 뭘 해야 하는가"를 한 문장으로 딱 못 박아라 (예: "조건만 맞으면 5분 신청으로 40만원, 오늘 안에 확인하세요").
- 절대 같은 말을 다르게 반복하지 마. 각 장면은 앞에서 안 나온 새로운 정보를 하나씩 추가해야 해. 내용이 부족하면 그 주제를 고르지 말고 정보가 풍부한 다른 주제를 골라.
- narration은 성우가 소리 내어 읽는 문장이니, 실제 사람이 말하듯 자연스러운 구어체로 써. 친근한 '해요체'를 기본으로 하고(예: "~있어요", "~된대요", "~챙기세요"), 딱딱한 문어체나 어색한 번역투(예: "~을 통해", "~에 의해", "~라 할 수 있다")는 쓰지 마. 각 narration은 공백 포함 {CHAR_RANGE}로 써 — **최소 글자수를 반드시 지켜라.** 짧게 쓰면 영상이 비어 보인다. 한 문장 또는 짧은 두 문장. 실제 수치·기관명·날짜·조건을 구체적으로 넣어 알맹이를 채워.
- 각 narration에서 가장 중요한 핵심 단어 1개만 <b>단어</b>로 감싸 강조(노란색). 장면당 1개만. (성우는 태그를 읽지 않음)
  강조는 반드시 **정보를 담은 명사**만 — 금액·기한·대상·제도명·기관명 (예: <b>40만원</b>, <b>12월 31일</b>, <b>서울청년포털</b>).
  동사·부사·서술어는 절대 강조하지 마 (나쁜 예: <b>저장해두고</b>, <b>지금</b>, <b>꼭</b>, <b>바로</b>).
- 자막에 글자수 메모("(16자)" 등)를 절대 쓰지 마. 최종 문장만.
- query는 각 장면 분위기에 맞는 영어 사진 검색어 2~3단어 (예: {QEX}).
- query 중요 규칙: 한국에서 벌어진 일을 다루므로 배경에 외국 요소가 보이면 어색해. 두 가지를 반드시 지켜:
  (가) 돈이 나오는 장면은 반드시 "korean won"을 넣어 검색해 (예: "korean won bills", "korean won cash desk"). 그냥 "money", "cash", "banknotes"로 검색하면 달러·유로·외국 지폐가 나와서 한국 소식에 안 맞아. 외국 지폐·동전·신용카드 로고가 보이면 안 돼. 검색어에 "money"라는 단어 자체를 쓰지 마 — 반드시 "korean won"으로 대체할 것.
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
- 인스타 캡션: 첫 줄 후킹 + 핵심 5~6줄(영상 내용을 글로도 충실히) + 저장/팔로우 유도 + 마지막에 주제와 관련된 댓글 유도 질문 한 줄(예: "여러분이라면 신청하실 건가요? 댓글로 알려주세요 👇") + 해시태그 5개(대형 1 + 중형 2 + 니치 2로 믹스).
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


def validate(d):
    """구조 검증 — 깨진 응답이 렌더/조립 단계로 흘러가지 않게"""
    assert isinstance(d.get("caption"), str) and d["caption"].strip(), "caption 누락"
    assert isinstance(d.get("title"), str) and d["title"].strip(), "title 누락"
    scenes = d.get("scenes")
    assert isinstance(scenes, list) and len(scenes) == TOTAL_SCENES, f"scenes 개수 오류({len(scenes) if isinstance(scenes, list) else '없음'} != {TOTAL_SCENES})"
    # 러닝타임 추정 — mid는 '60초 안에'가 요구사항이라, 넘칠 대본은 만들기 전에 걸러 재생성한다.
    # 실측 회귀: 장면 길이 ≈ 글자수 x 0.124초 + 0.5초(패딩). 로고 장면(팔로우 멘트)은 약 6초.
    if LENGTH_VARIANT == "mid":
        est = sum(len(re.sub(r'<[^>]+>', '', s.get("narration", ""))) * 0.124 + 0.5
                  for s in scenes) + 6.0
        assert est <= 59.0, f"예상 러닝타임 {est:.0f}초 — 60초 초과. 각 문장을 더 짧게 다시 써야 함"
    for i, s in enumerate(scenes, 1):
        assert isinstance(s.get("narration"), str) and s["narration"].strip(), f"scene{i} narration 누락"
        assert isinstance(s.get("query"), str) and s["query"].strip(), f"scene{i} query 누락"


# 재생성할 때 같은 프롬프트를 그대로 보내면 모델은 왜 거절당했는지 모른다.
# 실제로 러닝타임 초과로 3연속 실패해 발행이 중단된 적이 있어, 실패 사유를 되먹인다.
TRIES = 5
data = None
correction = ""
for gen_try in range(1, TRIES + 1):
    response = call_gemini(correction)
    try:
        cand = parse_json(response.text or "")
        validate(cand)
        data = cand
        break
    except AssertionError as e:
        msg = str(e)
        print(f"  검증 실패({msg}) — 재생성 {gen_try}/{TRIES}", flush=True)
        if "러닝타임" in msg:
            # 모델이 글자수 지시를 반복적으로 무시한다. 몇 자로 줄여야 하는지 숫자로 지시.
            budget = int(CHAR_RANGE.split("~")[1].rstrip("자"))
            budget = max(20, budget - 6 * gen_try)
            correction = (f"\n\n[매우 중요] 직전 시도가 길이 초과로 거절됐다: {msg}\n"
                          f"이번에는 각 narration을 **{budget}자 이내**로 훨씬 짧게 써라. "
                          f"장면 수는 그대로 유지하고 문장만 줄여라.")
        time.sleep(3)
    except Exception as e:
        print(f"  응답 형식 오류({e}) — 재생성 {gen_try}/{TRIES}", flush=True)
        correction = ("\n\n[매우 중요] 직전 응답이 형식 오류로 거절됐다. "
                      "지정한 JSON 형식만, 다른 설명 없이 출력해라.")
        time.sleep(3)
if data is None:
    print(f"[중단] Gemini가 {TRIES}회 연속 조건을 만족하지 못했어요.")
    sys.exit(1)


def est_seconds(scenes):
    """러닝타임 추정 (실측 회귀: 글자수 x 0.124 + 0.5초 패딩) + 로고 장면 6초"""
    return sum(len(re.sub(r'<[^>]+>', '', sc.get("narration", ""))) * 0.124 + 0.5
               for sc in scenes) + 6.0


def trim_to_budget(scenes, limit=59.0):
    """마지막 방어선 — 그래도 길면 중간 장면을 덜어내 60초에 맞춘다.

    후킹(첫 장면)과 결론(마지막 장면)은 구조의 핵심이라 절대 건드리지 않고,
    뒤쪽 중간 장면부터 덜어낸다. 발행이 통째로 무산되는 것보다 낫다.
    """
    scenes = list(scenes)
    while len(scenes) > 4 and est_seconds(scenes) > limit:
        drop = len(scenes) - 2          # 결론 바로 앞 장면
        removed = scenes.pop(drop)
        print(f"  [길이 조정] 장면 {drop + 1} 제거: {removed.get('narration','')[:24]}...",
              flush=True)
    return scenes


if LENGTH_VARIANT == "mid" and est_seconds(data["scenes"]) > 59.0:
    before = est_seconds(data["scenes"])
    data["scenes"] = trim_to_budget(data["scenes"])
    print(f"  [길이 조정] {before:.0f}초 -> {est_seconds(data['scenes']):.0f}초 "
          f"(장면 {len(data['scenes'])}개)", flush=True)


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
