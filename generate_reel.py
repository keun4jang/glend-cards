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
# 모델명 (신규 계정에서 gemini-2.5-flash가 막혀서 최신 별칭 사용). 필요시 GEMINI_MODEL로 교체.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "models/gemini-flash-latest").strip()

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
    QEX = '"healthy meal bowl", "running shoes closeup", "dark bedroom night"'
elif CATEGORY == "incident":
    PERSONA = "너는 'GLEND'라는 트렌드 인스타그램 릴스 채널의 전문 작가야. 자극적·공감형 사건·사고·논란을 15~22초 안에 빠르게 전한다."
    TOPIC_DESC = "오늘의 최신 사건·사고·논란 관련 뉴스 제목 목록"
    HOOK = '질문형 또는 충격 사실 제시형'
    QEX = '"car accident night", "police line tape", "ambulance lights night"'
else:
    PERSONA = "너는 'GLEND'라는 경제·재테크 실전 꿀팁 인스타그램 릴스 채널의 전문 작가야. 15~22초 안에 이득/손해 정보를 빠르게 전한다."
    TOPIC_DESC = "오늘의 최신 경제/재테크 관련 뉴스 제목 목록"
    HOOK = '"~안 하면 손해" 류의 손실 회피형'
    QEX = '"korean won bills", "calculator money desk", "seoul apartment buildings"'

# 3) 릴스 대본 — 5개 장면(후킹+핵심4). 짧고 완주 가능한 15~18초 목표.
PROMPT = f"""
{PERSONA}

아래는 {TOPIC_DESC}이야:
{news_text}

이 중에서 대중이 가장 반응할 핵심 주제 하나를 직접 골라서, 짧고 밀도 높은 세로 릴스 대본을 만들어줘. 목표는 시청자가 끝까지 보는 것 — 전체 15~18초 안에 끝나야 해.
릴스는 5개 장면(scene)으로 구성돼. 각 장면은 성우가 말하는 동시에 화면 중앙에 그대로 뜨는 자막 문장(narration)과 배경 사진 검색어(query)로 이뤄져.

규칙:
- scene 1 = 후킹. narration은 시선을 확 잡는 짧고 강한 한 문장. {HOOK}
- 후킹 형식 다양화: "~알고 계셨나요?", "~하셨나요?" 같은 질문형은 매번 반복되면 식상해. 질문형 말고 이런 형식을 우선 써 — 숫자 제시형("300만원, 신청 안 하면 사라집니다"), 명령형("월급 들어오면 이것부터 확인하세요"), 반전형("다들 아는 그 방법, 사실 손해입니다"), 대상 지목형("만 34세 이하라면 지금 멈추세요").
- scene 2~5 = 본문. 핵심만 4개: 무슨 일인지 → 핵심 수치/내용 → 대상/방법 → 꼭 기억할 것. 곁가지는 버리고 알맹이만.
- narration은 성우가 소리 내어 읽는 문장이니, 실제 사람이 말하듯 자연스러운 구어체로 써. 친근한 '해요체'를 기본으로 하고(예: "~있어요", "~된대요", "~챙기세요"), 딱딱한 문어체나 어색한 번역투(예: "~을 통해", "~에 의해", "~라 할 수 있다")는 쓰지 마. 각 narration은 반드시 짧게 — 한 문장, 공백 포함 15~35자. 길면 영상이 늘어져서 이탈해. 수치·날짜 같은 구체성은 살리되 문장은 압축해.
- 각 narration에서 가장 중요한 핵심 단어 1개만 <b>단어</b>로 감싸 강조(노란색). 장면당 1개만. (성우는 태그를 읽지 않음)
- 자막에 글자수 메모("(16자)" 등)를 절대 쓰지 마. 최종 문장만.
- query는 각 장면 분위기에 맞는 영어 사진 검색어 2~3단어 (예: {QEX}).
- query 중요 규칙: 한국에서 벌어진 일을 다루므로 배경 사진에 외국인 얼굴이 나오면 어색해. 반드시 **사람 얼굴이 안 나오는 사진**으로 검색해 — 사물(돈, 계산기, 서류, 도구), 풍경(도시, 거리, 건물, 자연), 손·뒷모습 클로즈업 위주. "person", "man", "woman", "people" 같은 단어는 쓰지 마. 꼭 사람이 필요하면 "hands closeup"이나 "silhouette"처럼 얼굴 없는 형태로.
- scene 4나 5 중 하나의 narration 끝에 "저장해두고 다시 보세요" 같은 저장 유도를 자연스럽게 한 번 넣어. (저장 유도는 전체에서 딱 한 번만)
- 화면 상단에 영상 내내 고정으로 뜰 짧은 제목(title)도 만들어줘. 주제를 한눈에 보여주는 8자 이내의 간결한 키워드 (예: "운전면허 지원금", "청년 청약통장", "전기요금 절약"). 이모지 1개 붙여도 좋음.
- 인스타 캡션: 첫 줄 후킹 + 핵심 3~4줄 + 저장/팔로우 유도 + 마지막에 주제와 관련된 댓글 유도 질문 한 줄(예: "여러분이라면 신청하실 건가요? 댓글로 알려주세요 👇") + 해시태그 5개(대형 1 + 중형 2 + 니치 2로 믹스).
- 캡션과 자막 모두에 마크다운 문법(**별표**, ##, - 목록 등)을 절대 쓰지 마. 인스타는 마크다운을 표시하지 못해서 별표가 그대로 노출돼. 강조는 이모지나 줄바꿈으로만.

반드시 아래 JSON 형식으로만 답해. 다른 설명 금지.
{{
  "topic": "네가 고른 주제",
  "title": "화면 상단 고정 제목(8자 이내 + 이모지)",
  "scenes": [
    {{ "narration": "후킹 자막 문장", "query": "영어 사진 검색어" }},
    {{ "narration": "본문 자막 문장", "query": "영어 사진 검색어" }},
    {{ "narration": "본문 자막 문장", "query": "영어 사진 검색어" }},
    {{ "narration": "본문 자막 문장", "query": "영어 사진 검색어" }},
    {{ "narration": "본문 자막 문장", "query": "영어 사진 검색어" }}
  ],
  "caption": "인스타 캡션 전체 텍스트"
}}
"""

print("Gemini가 릴스 대본을 만드는 중...\n")


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
    """구조 검증 — 깨진 응답이 렌더/조립 단계로 흘러가지 않게"""
    assert isinstance(d.get("caption"), str) and d["caption"].strip(), "caption 누락"
    assert isinstance(d.get("title"), str) and d["title"].strip(), "title 누락"
    scenes = d.get("scenes")
    assert isinstance(scenes, list) and len(scenes) == 5, f"scenes 개수 오류({len(scenes) if isinstance(scenes, list) else '없음'})"
    for i, s in enumerate(scenes, 1):
        assert isinstance(s.get("narration"), str) and s["narration"].strip(), f"scene{i} narration 누락"
        assert isinstance(s.get("query"), str) and s["query"].strip(), f"scene{i} query 누락"


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
OUTRO_NARRATION = "나중에 또 보려면 지금 저장하고, 매일 돈 되는 정보 받으려면 팔로우해 주세요!"

if True:
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

    # 배경음악 크레딧(CC BY 4.0) — 캡션에 자동 표기
    data["caption"] = data.get("caption", "").rstrip() + \
        "\n\n🎵 Music: Inspired – Kevin MacLeod (incompetech.com), CC BY 4.0"

    print("\n[캡션]\n" + data["caption"])

    out_file = f"reel_content_{POST_INDEX}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n저장 완료! {out_file} 생성됨 🎬")
