"""
발행한 콘텐츠를 '검색용 글'로 다시 쓴다.

왜 필요한가:
  릴스 대본은 나레이션 408자 + 캡션 460자 = 약 870자다. 말로 듣는 글이라
  문장이 짧고 맥락이 생략돼 있어, 그대로 웹에 올리면 검색엔진이 '얇은 콘텐츠'로
  거른다. 검색은 인스타와 실패 지점이 다르다 —
  인스타는 "팔로우할 이유"가 없어서 실패했지만, 검색은 "구체적 질문에 대한
  구체적 답"이면 팔로워 0명이어도 트래픽이 붙는다. 그래서 얇음만 해결하면 된다.

  대본에 이미 들어 있는 사실(대상 조건·금액·신청처·기한·주의점)을 그대로 살리고,
  검색자가 실제로 치는 질문에 답하는 구조로 재구성한다.

비용: Gemini 무료 티어 호출 1회 추가. 발행당 1회라 하루 3~4회 늘어날 뿐이다.
"""
import json
import os
import re
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY", "").strip())

_models_env = (os.getenv("GEMINI_MODELS") or "").strip()
MODEL_CHAIN = ([m.strip() for m in _models_env.split(",") if m.strip()] if _models_env else [
    (os.getenv("GEMINI_MODEL") or "models/gemini-flash-latest").strip(),
    "models/gemini-flash-lite-latest",
    "models/gemini-2.0-flash",
])

TRANSIENT = ("503", "unavailable", "429", "resource_exhausted",
             "high demand", "overloaded", "deadline", "timeout", "internal")
UNAVAILABLE = ("not found", "404", "not supported", "does not exist",
               "permission", "not available")


def strip_tags(t):
    return re.sub(r"<[^>]+>", "", t or "").replace("**", "").strip()


def source_text(content):
    """대본에서 사실 정보만 뽑아 한 덩어리로"""
    parts = []
    for sc in content.get("scenes", []):
        n = strip_tags(sc.get("narration", ""))
        if n and "@glend" not in n and "팔로우" not in n:
            parts.append(n)
    for key in ("card1", "card2", "card3"):
        c = content.get(key) or {}
        for v in (c.get("sub1"), c.get("sub2"), c.get("title"), c.get("subtitle")):
            if v:
                parts.append(strip_tags(v).replace("\n", " "))
        for l in c.get("lines", []) or []:
            parts.append(strip_tags(l))
    c4 = content.get("card4") or {}
    parts += [strip_tags(x) for x in (c4.get("items") or [])]
    cap = strip_tags(content.get("caption", ""))
    cap = re.sub(r"#\S+", "", cap)
    cap = re.sub(r"🎵.*", "", cap, flags=re.S)
    if cap:
        parts.append(cap)
    return "\n".join(p for p in parts if p)


PROMPT_TMPL = """너는 한국의 생활정보 전문 에디터야. 아래는 같은 주제로 만든 짧은 영상 대본과 캡션이다.
이걸 **검색해서 들어온 사람이 끝까지 읽고 실제로 문제를 해결하는 웹 문서**로 다시 써라.

주제: {topic}

원본 자료:
{source}

작성 규칙:
- 분량 1500~2500자. 원본이 짧으니 배경·절차·판단 기준을 보충해서 채워라.
  단, **원본에 없는 수치·기한·기관명을 지어내지 마라.** 모르면 "공식 안내를 확인해야 한다"고 써라.
- 검색자가 실제로 치는 질문에 답하는 구조로:
  1) 첫 문단: 결론부터 (누가 얼마를 받는지 / 무엇을 해야 하는지) 3~4문장
  2) H2 소제목 4~6개로 구획. 소제목은 질문형 또는 명사형으로
     (예: "누가 받을 수 있나요", "얼마나 받나요", "신청 방법", "놓치기 쉬운 점")
  3) 목록이 필요한 곳은 불릿으로. 표가 더 명확하면 마크다운 표로.
  4) 마지막에 "자주 묻는 질문" 2~3개 (질문/답 형식)
- 문체는 정중한 '합니다체'. 영상 대본의 '해요체'를 그대로 옮기지 마라.
- 과장·낚시 금지. "충격", "경악", "대박" 같은 표현 쓰지 마라.
- 홍보 문구, 팔로우 유도, 해시태그, 이모지를 넣지 마라.
- 검색 제목(title)은 사람이 실제로 검색할 법한 표현으로 30자 내외
  (예: "경차 유류세 환급 신청 방법과 조건").
- 요약(description)은 검색결과에 뜰 한 문장, 80자 내외.

반드시 아래 JSON만 출력해라. 다른 설명 금지.
{{
  "title": "검색 제목",
  "description": "한 문장 요약",
  "keywords": ["검색어1", "검색어2", "검색어3", "검색어4"],
  "body_markdown": "본문 전체 (마크다운, H2는 ## 로)"
}}"""


def _call(prompt):
    usable, last = list(MODEL_CHAIN), None
    for rnd in range(4):
        for model in list(usable):
            try:
                return client.models.generate_content(model=model, contents=prompt)
            except Exception as e:
                last, msg = e, str(e).lower()
                if any(t in msg for t in UNAVAILABLE):
                    usable.remove(model)
                    continue
                if not any(t in msg for t in TRANSIENT):
                    raise
        if not usable:
            break
        if rnd < 3:
            time.sleep(min(120, 30 * (2 ** rnd)))
    raise last if last else RuntimeError("Gemini 호출 실패")


def parse_json(raw):
    raw = raw.strip()
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


def write(content, topic=None):
    """콘텐츠 dict -> 기사 dict. 실패하면 None(발행을 막지 않는다)."""
    try:
        topic = topic or content.get("topic", "")
        src = source_text(content)
        if len(src) < 150:
            print("[article] 원본이 너무 짧아 건너뜀", flush=True)
            return None
        res = _call(PROMPT_TMPL.format(topic=topic, source=src))
        art = parse_json(res.text or "")
        body = art.get("body_markdown", "")
        if not art.get("title") or len(body) < 600:
            print(f"[article] 결과가 부실해 건너뜀 (본문 {len(body)}자)", flush=True)
            return None
        art["chars"] = len(body)
        print(f"[article] 생성: {art['title']} ({len(body)}자)", flush=True)
        return art
    except Exception as e:
        print(f"[article] 생성 실패(무시하고 계속): {e}", flush=True)
        return None


if __name__ == "__main__":
    fn = sys.argv[1] if len(sys.argv) > 1 else "reel_content_1.json"
    data = json.loads(Path(fn).read_text(encoding="utf-8"))
    a = write(data)
    print(json.dumps(a, ensure_ascii=False, indent=2)[:2000] if a else "실패")
