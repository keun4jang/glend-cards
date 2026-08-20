# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project does

**glend-cards** is a fully automated Instagram card news pipeline for the Korean economic news channel "GLEND". Every day it:
1. Fetches Korean economic headlines from Google News RSS
2. Asks Gemini to pick a topic and write 3-card content (JSON)
3. Fetches matching background photos from Pexels
4. Renders 4 PNG cards (1080×1350 px) via Playwright/Chromium
5. Commits the PNGs to GitHub (so Instagram can fetch them via raw URL)
6. Posts a carousel to Instagram via the Graph API

## Commands

```bash
# Set up (first time)
pip install -r requirements.txt
python -m playwright install chromium

# Full pipeline (local, with random delay)
python daily.py

# Individual steps
python generate.py   # fetch news → Gemini → Pexels → content.json
python render.py     # content.json → output/card{1-4}.png
python upload.py     # dry-run preview (no actual post)
python upload.py go  # actually post to Instagram

# Test individual APIs
python test_gemini.py
python test_pexels.py
python test_news.py
python test_insta.py
```

## Required environment variables (`.env`)

```
GEMINI_API_KEY=...
PEXELS_API_KEY=...
IG_TOKEN=...        # Instagram Graph API long-lived token
IG_USER_ID=...      # Instagram business account numeric ID
```

## Architecture

### Data flow
`generate.py` → `content.json` → `render.py` → `output/card*.png` → git push → `upload.py`

### Card structure (`content.json`)
- **card1** (hook): `title` (2 lines, ≤6 chars/line), `sub` (≤15 chars), `bg` (Pexels URL)
- **card2** (analysis): `subtitle` (2 lines), `lines` (3 lines, 13–16 chars each), `bg`
- **card3** (insight): `subtitle` (2 lines), `lines` (3 lines, 13–16 chars each), `bg`
- **caption**: Instagram caption text with hashtags (HTML `<b>` tags are stripped before posting)

### Rendering (`render.py` + `templates/card.html`)
Playwright opens `templates/card.html` as a local file in a 1080×1350 viewport (device_scale_factor=2 → 2160×2700 actual pixels). Card content is injected via `page.evaluate()`. Card 4 is always the brand card (shows `assets/logo.png` full-bleed). Font size is scaled once, proportionally to character count (not a measure-and-retry loop), so `render.py` also logs any element that still overflows after rendering.

### Upload flow (`upload.py`)
Images are served via `https://raw.githubusercontent.com/keun4jang/glend-cards/main/output/card{N}.png`. Each card is registered as a carousel item via the Instagram Graph API, then published as a single carousel post. A retry loop handles Instagram's async image processing (up to 10 × 8s waits). `upload_log.txt` tracks the last post date to enforce one-post-per-day.

### CI vs local orchestrator
- `daily_ci.py` — used by GitHub Actions; sets git identity (`github-actions`) before committing
- `daily.py` — used locally; assumes git identity already configured
- Both add a random delay (0–4/5 h) so posts don't always land at the same time

### GitHub Actions
`.github/workflows/daily.yml` triggers at UTC 02:00 (KST 11:00). Secrets required: `GEMINI_API_KEY`, `PEXELS_API_KEY`, `IG_TOKEN`, `IG_USER_ID`.

## Key constraints
- Gemini prompt enforces strict character limits: card titles ≤6 chars/line, body lines 13–16 chars. Violating these causes visual overflow.
- Instagram requires images to be publicly accessible URLs before the carousel can be published — hence the GitHub raw CDN approach.
- The `<b>` tags in `lines` and `caption` are intentional: `render.py` passes them raw to HTML (styled yellow in CSS), while `upload.py` strips them for the plain-text caption.

## 비용 정책 (절대 조건: 전액 무료 유지)

이 채널은 요금이 발생하면 안 된다. 아래를 어기면 즉시 과금된다.

- **Gemini**: 결제 계정이 연결되지 않은 AI Studio 키(개인 Gmail 계정)의 **무료 티어**만 사용한다.
  - 과거 `trussvideo1@truss.co.kr` 조직 계정에 결제가 붙어 있어 실제로 ₩543이 청구된 적이 있다.
    그래서 결제 없는 개인 계정 키로 교체했다. 옛 계정 앞으로 오는 안내 메일은 이 프로젝트와 무관하다.
  - 2026-10-12부터 AI Studio가 후불 → **선불(크레딧 구매)** 로 전환된다.
    **전환하거나 크레딧을 구매하면 안 된다.** 무료 티어만 쓰는 한 조치가 필요 없다(구글 공지 명시).
  - 503 "high demand"는 무료 티어의 정상적인 혼잡 신호다. 결제를 붙여 해결하려 하지 말고
    `MODEL_CHAIN`의 다른 무료 모델로 폴백한다(generate.py / generate_reel.py).
- **GitHub Actions**: 퍼블릭 저장소라 실행 시간이 무료다. 비공개로 전환하면 과금되므로 유지할 것.
- **그 외**: Pexels(무료 API), edge-tts(무료), Pretendard(OFL) — 모두 무료 범위 안에서만 사용한다.

## 발행량에 대한 실측 결론 (2026-08-20, 게시물 378개 6개월치 기준)

**발행량은 성과에 영향을 주지 않는다. 줄이거나 늘릴 근거가 없다.**

- 같은 달 안에서 "그날 발행 수 ↔ 그날 게시물당 도달"의 스피어만 상관:
  2월 +0.21 / 3월 +0.08 / 4월 -0.11 / 5월 +0.08 / 6월 +0.64 / 7월 +0.39 / 8월 -0.16
  → 일관된 음의 관계 없음. 많이 올린다고 게시물당 도달이 줄지 않는다.
- 릴스: 하루 1개 발행일 도달 중앙값 114 vs 하루 2개 156.
  같은 날 1번째 153 vs 2번째 166 — **2번째가 더 높다. 자기잠식 없음.**
- 카드뉴스: 하루 1개든 15개든 도달 중앙값 14~18로 평평하다.
  카드 도달은 팔로워 수에 갇혀 있어 발행량과 무관하다.
- 2월(하루 2.9개, 도달 49.5) → 3월(하루 5.0개, 도달 15.6) 하락은 **발행량 탓이 아니다.**
  3월 내부 상관이 +0.08로 무관계다. 신규 계정 부스트 종료 같은 월 단위 효과로 봐야 한다.
  (이전에 "3월의 교훈: 많이 올리는 게 답이 아니다"라고 기록했던 것은 근거 없는 해석이었다.)

현재 주 17개(릴스 14 + 카드 주3회)를 유지한다. 카드뉴스는 도달이 낮지만
**릴스가 profile_visits/follows를 API로 측정조차 못 하므로, 전환을 측정할 수 있는
유일한 포맷**이라 계측 목적으로 유지한다(6개월 누적 팔로우 5명이 전부 카드에서 나왔다).

병목은 발행량이 아니라 **첫 3초**다. 도달 1인당 평균 시청 3.25초, 재생 1회당 2.95초.
