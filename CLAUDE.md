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
