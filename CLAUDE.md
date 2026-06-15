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
Playwright opens `templates/card.html` as a local file in a 1080×1350 viewport (device_scale_factor=2 → 2160×2700 actual pixels). Card content is injected via `page.evaluate()`. Card 4 is always the brand card (shows `assets/logo.png` full-bleed). A font-size auto-shrink loop prevents lines from overflowing 920 px wide.

### Upload flow (`upload.py`)
Images are served via `https://raw.githubusercontent.com/trussvideo1/glend-cards/main/output/card{N}.png`. Each card is registered as a carousel item via the Instagram Graph API, then published as a single carousel post. A retry loop handles Instagram's async image processing (up to 10 × 8s waits). `upload_log.txt` tracks the last post date to enforce one-post-per-day.

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
