"""
사실 확인 — AI가 쓴 릴스·카드 원고의 숫자·법·판결·건강 주장을 검색으로 확인하고 틀린 부분만 고친다.

왜 필요한가:
  대본 생성기는 뉴스 '제목'만 보고 55초 분량을 쓴다. 제목에 없는 금액·기한·처벌·판결·통계는
  모델이 채워 넣는데, 확인하는 단계가 없었다. 예) 2026-10-16 카드 "기한 · 사고 후 7일이내 청구",
  10-17 릴스 "노란불 통과하면 과실 100%". 생활정보 채널에서 틀린 정보는 저장·공유될수록
  계정 신뢰를 깎는다.

어떻게:
  1) 원고를 [위치 id] 단위로 Gemini에 다시 보내 Google 검색 근거(grounding)로 확인시킨다.
     검색을 못 쓰면(무료 한도·모델 미지원) 검색 없이 모델 지식으로만 확인한다 — 이 경우에도
     "예외 없이·100%" 같은 근거 없는 단정은 잡힌다.
  2) 틀린 부분만 원문 부분 문자열 단위로 바꾼다(문장 전체를 다시 쓰지 않는다 → 길이·말투·강조 유지).
     카드 문구는 글자 수 제한이 있어 늘어나는 수정은 버린다.
  3) 주제의 핵심 전제 자체가 사실이 아니면 verdict="reject" — 호출한 쪽이 다른 주제로 재생성한다.

비용: 무료 티어 Gemini 호출 1회(검색 근거 포함)가 늘어난다. 결제 없는 키라 한도를 넘으면 오류가 날 뿐
과금되지 않고, 그 경우 검색 없는 확인으로 넘어간다. 어떤 오류도 발행을 막지 않는다.

단독 실행(확인만, 파일은 안 바꿈):  python factcheck.py archive/2026-10/....json
"""
import datetime as dt
import json
import os
import re
import sys
import time

from dotenv import load_dotenv

load_dotenv()

_models_env = (os.getenv("GEMINI_MODELS") or "").strip()
MODEL_CHAIN = ([m.strip() for m in _models_env.split(",") if m.strip()] if _models_env else [
    (os.getenv("GEMINI_MODEL") or "models/gemini-flash-latest").strip(),
    "models/gemini-flash-lite-latest",
])
TRANSIENT = ("503", "unavailable", "high demand", "overloaded", "deadline",
             "timeout", "timed out", "internal")
MAX_FIXES = 8
KST = dt.timezone(dt.timedelta(hours=9))

_client = None


def _gemini():
    global _client
    if _client is None:
        from google import genai
        _client = genai.Client(api_key=os.getenv("GEMINI_API_KEY", "").strip(),
                               http_options=genai.types.HttpOptions(timeout=180_000))
    return _client


def strip_tags(t):
    return re.sub(r"<[^>]+>", "", t or "")


# ── 원고 ↔ [id] 매핑 ──────────────────────────────────────────────
# 값: (id, 원문, 최대 증가 글자수). 카드 문구는 글자 수 제한(줄당 13~16자 등) 때문에 늘리지 않는다.
def fields_of(content, kind):
    out = []
    if kind == "reel":
        for i, sc in enumerate(content.get("scenes", []), 1):
            t = sc.get("narration", "")
            if t and "@glend" not in t and "팔로우" not in t:
                out.append((f"s{i}", t, 20))
    else:
        c1 = content.get("card1") or {}
        for k in ("sub1", "sub2"):
            if c1.get(k):
                out.append((f"c1.{k}", c1[k], 1))
        for n in (2, 3):
            for j, line in enumerate((content.get(f"card{n}") or {}).get("lines", []) or [], 1):
                out.append((f"c{n}.l{j}", line, 1))
        c4 = content.get("card4") or {}
        for j, item in enumerate(c4.get("items", []) or [], 1):
            out.append((f"c4.i{j}", item, 1))
        if c4.get("closing"):
            out.append(("c4.closing", c4["closing"], 1))
    if content.get("caption"):
        out.append(("caption", content["caption"], 150))
    return out


def _set(content, fid, text):
    if fid == "caption":
        content["caption"] = text
    elif fid.startswith("s"):
        content["scenes"][int(fid[1:]) - 1]["narration"] = text
    else:
        card, key = fid.split(".")
        c = content["card" + card[1:]]
        if key.startswith("l"):
            c["lines"][int(key[1:]) - 1] = text
        elif key.startswith("i"):
            c["items"][int(key[1:]) - 1] = text
        else:
            c[key] = text


def _caption_body(cap):
    # 해시태그·고정 CTA·음악 표기는 사실 주장이 아니므로 보내지 않는다(바꿔치기는 전체 캡션에서 한다).
    keep = [ln for ln in cap.split("\n")
            if not ln.lstrip().startswith(("#", "📌", "📤", "🎵", "💾"))]
    return "\n".join(keep).strip()


def build_prompt(content, kind, news, grounded):
    today = dt.datetime.now(KST)
    lines = []
    for fid, text, _ in fields_of(content, kind):
        t = _caption_body(text) if fid == "caption" else text
        t = re.sub(r"\s*\n\s*", " / ", strip_tags(t).strip())
        lines.append(f"[{fid}] {t}")
    what = "인스타그램 릴스 대본" if kind == "reel" else "인스타그램 카드뉴스 문구"
    how = ("Google 검색으로 공식 기관·언론 보도를 찾아 확인하라."
           if grounded else "네가 아는 사실과 상식으로 확인하라. 확신이 없으면 단정만 완화하라.")
    news_block = "\n".join(f"- {h}" for h in (news or [])[:25]) or "(없음)"
    card_rule = ("\n- 카드 문구([c…])는 글자 수 제한이 있다. fix는 wrong보다 길면 안 된다."
                 if kind == "card" else "")
    return f"""너는 한국 생활정보 채널의 팩트체커다. 아래 {what}는 AI가 뉴스 '제목'만 보고 쓴 글이라,
제목에 없는 금액·기한·대상 조건·처벌 수위·판결·통계·건강 효과를 지어냈을 수 있다.
오늘: {today:%Y년 %m월 %d일}(한국 시간)

작가가 본 뉴스 제목:
{news_block}

원고 (각 줄 앞 [id]는 위치):
{chr(10).join(lines)}

할 일:
1. 원고 속 확인 가능한 사실 주장(금액, 비율, 날짜·기한, 대상·자격 조건, 신청처, 법 조항·처벌, 판결, 통계, 건강 효과·수치)을 {how}
2. 틀렸거나 근거를 찾을 수 없는 주장만 고친다. 맞는 문장은 건드리지 마라. 문체·후킹·재미는 평가하지 마라.
3. 사실이 아닌 단정("무조건", "예외 없이", "100%", "절대", "누구나", "전부")은 사실에 맞게 완화한다.
   글자가 빠지거나 틀린 명백한 오타도 고친다(예: "즉시 병부터 가고" → "즉시 병원부터 가고"). 문체는 바꾸지 마라.
4. 고칠 때는 해당 부분만, 비슷한 길이와 같은 말투(~해요/~합니다)로 바꾼다. 확인된 정확한 수치가 있으면 그 수치로.
   바꾼 말 뒤 조사가 어색해지지 않게 wrong에 조사까지 넣어라(예: wrong "과실 100%가" → fix "큰 과실이").{card_rule}

출력: 설명 없이 JSON 하나만.
{{"verdict": "ok" | "fixed" | "reject",
 "reason": "reject일 때만 — 핵심 전제가 사실이 아닌 이유 한 줄",
 "fixes": [{{"id": "s3", "wrong": "원고에 글자 그대로 있는 부분 문자열", "fix": "바꿀 내용", "why": "근거 한 줄(출처 기관·매체)"}}]}}
- ok: 고칠 것 없음. fixed: fixes에 고칠 것. reject: 주제의 핵심 사건·제도 자체가 사실이 아니거나 이미 끝난 일일 때만.
- wrong은 원고 텍스트(태그 제외)에 글자 그대로 있어야 한다. 한 항목에 한 군데만.
- fixes는 중요한 것부터 최대 {MAX_FIXES}개."""


def _parse(raw):
    raw = (raw or "").strip()
    a, b = raw.find("{"), raw.rfind("}")
    if a < 0 or b <= a:
        raise ValueError("JSON 없음")
    return json.loads(raw[a:b + 1])


def _sources(resp):
    try:
        gm = resp.candidates[0].grounding_metadata
        chunks = getattr(gm, "grounding_chunks", None) or []
        return [c.web.title for c in chunks if getattr(c, "web", None) and c.web.title][:8]
    except Exception:
        return []


def _call(prompt, grounded):
    """(응답 텍스트, 출처 제목들, 모델) 또는 예외."""
    from google.genai import types
    cfg = types.GenerateContentConfig(
        temperature=0,
        tools=[types.Tool(google_search=types.GoogleSearch())] if grounded else None)
    last = None
    for rnd in range(2):
        for model in MODEL_CHAIN:
            try:
                resp = _gemini().models.generate_content(model=model, contents=prompt, config=cfg)
                return resp.text or "", _sources(resp), model
            except Exception as e:
                last = e
                msg = str(e).lower()
                if any(t in msg for t in TRANSIENT):
                    print(f"  [사실확인] {model}: 일시 과부하 — 다음 모델", flush=True)
                    continue
                if grounded:
                    # 무료 한도 초과(429)·검색 도구 미지원(400)은 모델마다 다르다(10/18 시험: flash-latest는
                    # 검색 한도 0으로 429). 다른 무료 모델로 넘어가 보고, 전부 막히면 검색 없이 확인한다.
                    print(f"  [사실확인] {model}: 검색 근거 불가({str(e)[:60]}) — 다음 모델", flush=True)
                    continue
                if "not found" in msg or "404" in msg:
                    continue
                raise
        if grounded and last is not None and not any(t in str(last).lower() for t in TRANSIENT):
            break                       # 과부하가 아니라 한도·미지원이면 기다려도 소용없다
        if rnd == 0:
            time.sleep(30)
    raise last or RuntimeError("Gemini 호출 실패")


def apply_fixes(content, kind, fixes):
    """원문 부분 문자열 단위로 바꾼다. 돌려주는 값: (적용 목록, 건너뛴 목록)"""
    fields = {fid: (text, grow) for fid, text, grow in fields_of(content, kind)}
    applied, skipped = [], []
    for f in (fixes or [])[:MAX_FIXES]:
        fid, wrong, fix = f.get("id", ""), (f.get("wrong") or "").strip(), (f.get("fix") or "").strip()
        if fid not in fields or not wrong or wrong == fix:
            skipped.append({**f, "skip": "위치·내용 없음"})
            continue
        text, grow = fields[fid]
        if len(strip_tags(fix)) > len(wrong) + grow:
            skipped.append({**f, "skip": f"너무 길어짐(+{len(fix) - len(wrong)}자)"})
            continue
        if wrong in text:
            new = text.replace(wrong, fix, 1)
        elif wrong in strip_tags(text):
            # 강조 태그에 걸친 경우 — 태그를 벗기고 바꾼다(릴스는 뒤에서 강조를 다시 칠한다)
            new = strip_tags(text).replace(wrong, fix, 1)
        else:
            skipped.append({**f, "skip": "원문에서 못 찾음"})
            continue
        _set(content, fid, new)
        fields[fid] = (new, grow - max(0, len(fix) - len(wrong)))
        applied.append(f)
    return applied, skipped


def check(content, kind, news=None):
    """원고를 확인하고 틀린 부분을 제자리에서 고친다. 어떤 경우에도 예외를 던지지 않는다.

    돌려주는 값(content["factcheck"]에도 기록): mode(grounded/ungrounded/skipped), verdict, reason,
    applied, skipped, sources
    """
    report = {"mode": "skipped", "verdict": "ok", "reason": "", "applied": [], "skipped": [], "sources": []}
    if not os.getenv("GEMINI_API_KEY", "").strip():
        report["reason"] = "GEMINI_API_KEY 없음"
        return report
    try:
        try:
            raw, src, model = _call(build_prompt(content, kind, news, True), grounded=True)
            report["mode"] = "grounded"
        except Exception as e:   # 무료 한도·도구 미지원·과부하 — 검색 없이라도 확인한다
            print(f"  [사실확인] 검색 근거 사용 불가 → 검색 없이 확인 ({str(e)[:160]})", flush=True)
            raw, src, model = _call(build_prompt(content, kind, news, False), grounded=False)
            report["mode"] = "ungrounded"
        res = _parse(raw)
        report["sources"] = src
        report["verdict"] = res.get("verdict", "ok")
        report["reason"] = res.get("reason", "")
        if report["verdict"] != "reject":
            report["applied"], report["skipped"] = apply_fixes(content, kind, res.get("fixes"))
            if report["verdict"] == "fixed" and not report["applied"]:
                report["verdict"] = "unfixed"
        else:
            report["skipped"] = res.get("fixes") or []
        tag = {"grounded": "검색 근거", "ungrounded": "검색 없이"}[report["mode"]]
        print(f"  [사실확인] {tag}({model.split('/')[-1]}, 출처 {len(src)}건) → {report['verdict']}"
              + (f": {report['reason']}" if report["reason"] else ""), flush=True)
        for f in report["applied"]:
            print(f"    고침 {f['id']}: '{f['wrong']}' → '{f['fix']}' ({f.get('why', '')})", flush=True)
        for f in report["skipped"]:
            if f.get("skip"):
                print(f"    건너뜀 {f.get('id')}: {f.get('skip')} — '{f.get('wrong', '')}'", flush=True)
    except Exception as e:
        report["mode"] = "skipped"
        report["reason"] = f"{e.__class__.__name__}: {str(e)[:160]}"
        print(f"  [사실확인] 건너뜀 — {report['reason']} (발행은 그대로 진행)", flush=True)
    content["factcheck"] = {k: report[k] for k in ("mode", "verdict", "reason", "sources")} | {
        "applied": [{k: f.get(k) for k in ("id", "wrong", "fix", "why")} for f in report["applied"]]}
    return report


def reject_correction(reason):
    return ("\n\n[매우 중요] 직전 응답이 거절됐다: 사실 확인 결과 주제의 핵심 전제가 사실이 아니다"
            f"({reason}). 뉴스 목록에서 사실 관계가 분명한 다른 사안을 골라 처음부터 다시 써라. "
            "뉴스 제목에 없는 금액·기한·처벌·판결 수치를 지어내지 마라.")


if __name__ == "__main__":
    # 확인만 하고 파일은 바꾸지 않는다 — 고친 결과를 화면에 보여 준다. 여러 파일을 줄 수 있다.
    for path in sys.argv[1:]:
        rec = json.load(open(path, encoding="utf-8"))
        content = rec.get("content", rec)
        kind = "reel" if content.get("scenes") else "card"
        content.pop("factcheck", None)
        before = {fid: t for fid, t, _ in fields_of(content, kind)}
        print(f"\n=== [{kind}] {rec.get('topic') or content.get('topic')}", flush=True)
        r = check(content, kind, news=None)
        for fid, t, _ in fields_of(content, kind):
            if before.get(fid) != t and fid != "caption":
                print(f"  {fid} 전: {strip_tags(before[fid])}\n  {fid} 후: {strip_tags(t)}")
        if r["sources"]:
            print("  출처:", " / ".join(r["sources"]))
