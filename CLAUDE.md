# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project does

**glend-cards** is a fully automated content pipeline for the Korean life-info/economy
Instagram channel "GLEND"(@glend_kr). 사람이 손대지 않고 GitHub Actions로만 돌아가며,
발행 트랙이 **세 개**다 (이 저장소를 "카드뉴스 전용"으로 오해하기 쉬운데, 발행량은
릴스가 주 14개로 훨씬 많다).

**1. 카드뉴스 — 주 3회, KST 월·수·금 아침** (`daily.yml` → `daily_ci.py`)
1. Google News RSS에서 한국 뉴스 수집 (경제/사건사고/건강 로테이션)
2. Gemini가 주제 선정 + 카드 4장 내용과 캡션을 JSON으로 작성 (`generate.py`)
3. Pexels에서 장면에 맞는 배경 사진 수집
4. Playwright/Chromium으로 PNG **5장** 렌더 (1080×1350, device_scale_factor=2)
5. PNG를 `media` 브랜치에 푸시 (인스타가 공개 URL로 가져가야 하므로)
6. Graph API로 캐러셀 게시 (`upload.py`)

**2. 릴스 — 매일 2회, KST 12:00 / 18:00** (`reel.yml` → `daily_reel_ci.py`)
`generate_reel.py`(대본) → edge-tts(내레이션) → `render_reel.py`·`build_reel.py`(영상 합성)
→ `upload_reel.py`. `REEL_POST_THREADS=true`면 Threads에도 함께 올린다.

**3. 검색 자산(정적 사이트) — 매일 KST 05:40** (`site.yml`)
`article.py`가 쓴 글을 `build_site.py`가 `docs/`(GitHub Pages)로 빌드하고
`indexnow.py`로 색인을 요청한다.

**계측**: `insights.yml`(주간 리포트 → `reports/`), `harvest.yml`(전량 성과 회수 →
`archive/instagram_posts.csv`). 발행 원문은 `archive.py`가 `archive/YYYY-MM/`에 영구 보관한다
(`media` 브랜치는 매번 덮어써서 대본이 남지 않기 때문).

## Commands

```bash
# Set up (first time)
pip install -r requirements.txt
python -m playwright install chromium

# Full pipeline (local, with random delay)
python daily.py

# 카드뉴스 — 개별 단계 (N = 1:경제 / 2:사건사고 / 3:건강)
# 주의: upload 계열만 인자 순서가 반대다 — (go, 인덱스). 나머지는 (인덱스).
python generate.py 1   # 뉴스 → Gemini → Pexels → content_1.json
python render.py 1     # content_1.json → output/post1/card{1-5}.png
python upload.py       # 드라이런 미리보기 (실제 게시 안 함)
python upload.py go 1  # 실제 게시

# 릴스
python generate_reel.py 1   # 대본 → reel_content_1.json
python build_reel.py 1      # 내레이션 + 영상 합성
python upload_reel.py go 1  # 실제 게시

# 성과 계측 / 검색 자산
python insights.py     # 주간 리포트 (reports/ 에 저장)
python harvest.py      # 전량 성과 회수 → archive/instagram_posts.csv
python build_site.py   # docs/ 정적 사이트 빌드

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
`generate.py` → `content_{N}.json` → `render.py N` → `output/post{N}/card{1-5}.png`
→ `media` 브랜치 push → `upload.py N go`

### Card structure (`content_{N}.json`)
- **card1** (hook): `title` (2줄, 줄당 ≤6자), `sub1` (12~16자), `sub2` (6~10자), `query`, `bg`
- **card2** (analysis): `subtitle` (2줄), `lines` (3줄, 각 13~16자), `query`, `bg`
- **card3** (insight): `subtitle` (2줄), `lines` (3줄, 각 13~16자), `query`, `bg`
- **card4** (저장용 요약): `headline` (≤8자), `items` (4개, "라벨 · 값" 12~20자),
  `closing` (14~22자). 사진 없이 연두(#CFFF04) 바탕 — 저장을 유발하는 유일한 카드다.
  `save_value_issues()`가 숫자·라벨 구조를 기계 검증한다 (아래 "진행 중인 실험 B" 참고)
- **caption**: 해시태그 포함 인스타 캡션 (`<b>` 태그는 게시 전 제거됨)

카드5는 JSON에 없다 — 렌더러가 항상 브랜드 카드(`assets/logo.png`)로 붙인다.

### Rendering (`render.py` + `templates/card.html`)
Playwright opens `templates/card.html` as a local file in a 1080×1350 viewport (device_scale_factor=2 → 2160×2700 actual pixels). Card content is injected via `page.evaluate()`. **카드5가 브랜드 카드**다(`assets/logo.png` full-bleed) — 카드4는 저장용 요약 카드다. Font size is scaled once, proportionally to character count (not a measure-and-retry loop), so `render.py` also logs any element that still overflows after rendering (`⚠️ 넘침` 으로 찍힌다 — 프롬프트의 글자수 규칙을 바꿀 땐 이 로그를 반드시 확인할 것).

### Upload flow (`upload.py`)
Images are served via `https://raw.githubusercontent.com/keun4jang/glend-cards/media/output/post{N}/card{M}.png` — **`main`이 아니라 `media` 브랜치다.** (media는 부모 없는 단일 커밋으로 강제 푸시해 저장소 비대화를 막는다 — 47일 만에 446MB가 쌓인 적이 있다. 그 대가로 대본이 매일 사라지므로 텍스트는 `archive.py`가 main에 따로 쌓는다.) Each card is registered as a carousel item via the Instagram Graph API, then published as a single carousel post. A retry loop handles Instagram's async image processing (up to 10 × 8s waits). `upload_log.txt` tracks the last post date to enforce one-post-per-day.

### CI vs local orchestrator
- `daily_ci.py` — used by GitHub Actions; sets git identity (`github-actions`) before committing
- `daily.py` — used locally; assumes git identity already configured
- 발행 시각이 매번 똑같지 않도록 랜덤 지연을 준다: **카드 0~30분**
  (`daily_ci.py`의 `INITIAL_MAX_DELAY_HOURS = 0.5`), **릴스 0~50분**(`daily_reel_ci.py`)

### GitHub Actions (크론은 전부 UTC — KST는 +9시간)

| 워크플로 | 크론 | 크론상 KST | 하는 일 |
|---|---|---|---|
| `daily.yml` | `30 22 * * 0,2,4` | 월·수·금 07:30 | 카드뉴스 (주 3회) |
| `reel.yml` | `0 3 * * *` / `0 9 * * *` | 매일 12:00 / 18:00 | 릴스 2편 |
| `site.yml` | `40 20 * * *` | 매일 05:40 | 정적 사이트 빌드 |
| `insights.yml` | `0 0 * * 1` | 월 09:00 | 주간 성과 리포트 |
| `harvest.yml` | `0 1 * * 1` | 월 10:00 | 전량 성과 회수(CSV) |
| `refresh-token.yml` | `17 3 * * *` | 매일 12:17 | IG 토큰 자동 갱신 |

Secrets required: `GEMINI_API_KEY`, `PEXELS_API_KEY`, `IG_TOKEN`, `IG_USER_ID`
(토큰 자동 갱신에는 `GH_PAT`도 필요).

#### ⚠️ 크론 시각 ≠ 실제 발행 시각 (2026-09-15 실측)

**GitHub Actions 예약 실행은 크론 시각에 시작하지 않는다.** 무료 러너 혼잡 때문에
매번 밀리고, 이 저장소에서는 그 지연이 일관되게 크다. 최근 실행 기록으로 잰 값:

| 워크플로 | 크론 | 실제 시작 지연 | **실제 발행(KST)** |
|---|---|---|---|
| `daily.yml` (카드) | 22:30 UTC | +1시간 40~50분 (5회 측정) | **약 09:20** (07:30 아님) |
| `reel.yml` #1 | 03:00 UTC | +5시간 20분 | **약 17:35** (12:00 아님) |
| `reel.yml` #2 | 09:00 UTC | +5시간 20분 | **약 24:00** (18:00 아님) |

지연은 UTC 03:00·09:00처럼 혼잡한 시간대에 특히 크고, 22:30처럼 한산한 시간대엔 작다.
여기에 스크립트 자체의 랜덤 지연(카드 0~30분, 릴스 0~50분)과 실행 시간(13~50분)이 더 붙는다.

**주의할 점:**
- `daily_ci.py`의 "KST 07:30~08:00 발행(출근 시간대)" 주석은 **의도일 뿐 실제와 다르다.**
  점심 타깃 릴스는 저녁에, 저녁 타깃 릴스는 자정에 나가고 있다.
- "언제 발행되나"를 계산할 때 크론만 보면 틀린다. 반드시 Actions 실행 기록을 볼 것.
- 발행 시각을 앞당기려면 크론을 그만큼 앞으로 당겨야 하지만, 지연폭이 4~7시간으로
  흔들려서 정밀 조준은 어렵다. 시간대를 바꾸기 전에 지연을 다시 측정할 것.
- 발행 시각이 도달에 영향을 주는지는 **아직 측정한 적 없다.** 바꾸기 전에 근거부터 만들 것.

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

## 진행 중인 실험 (판정 전까지 결론을 바꾸지 말 것)

### A. 프로필 전환율 — 2026-09-14 변경, 3주 뒤 판정

**변경 전 기준선(이 숫자와 비교해야 한다):**
- 누적 프로필방문 **292** → 팔로우 **6** = 전환율 **2.1%** (건강한 계정은 보통 5~15%)
- 팔로워 59 / 팔로잉 263 / 게시물 418
- 게시물 338개 중 저장 6개, 팔로우 4개. 팔로우의 2/3가 도달 1000+ 게시물 2개에서 나왔다.

**무엇을 바꿨나 (2026-09-14, 인스타 앱에서 수동):**
1. 바이오를 "무엇을 주는 계정인지 + 빈도"가 드러나게 교체
2. 고정 게시물 3개 지정 (실제 전환을 만든 게시물 기준)
3. 팔로잉 정리 (263 > 팔로워 59는 방문자에게 품앗이 계정으로 읽힘)

**진단 근거:** 콘텐츠는 사람을 데려오고 있었다(프로필까지 292명). 팔로우가 안 난 건
도달 부족이 아니라 프로필에서 놓친 것이다. 그래서 콘텐츠를 더 만드는 것보다
프로필 한 번 고치는 게 레버리지가 크다고 판단했다.

**판정 방법:** `insights.py`의 `[4] 팔로우 깔때기`가 매 리포트에 전환율을 찍는다.
변경 이후 프로필 방문이 20 이상 쌓인 뒤(대략 2~3주) 2.1%와 비교한다.
주간 리포트는 최근 25개만 봐서 표본이 작으니, 확정 판정은
`archive/instagram_posts.csv`를 2026-09-14 전/후로 갈라서 해야 한다.

### B. 카드4 저장 포맷 — 2026-09-14 변경, 3주 뒤 판정

**기준선:** 게시물 338개 중 저장 6개(1.8%). 저장·공유가 붙은 카드는 평균 도달 191,
없는 카드는 15로 **12.4배** 차이 — 저장이 안 되면 도달이 팔로워 안에 갇힌다.

**변경:** 카드4 항목을 문장("정부24에서 신청하세요")에서 "라벨 · 값" 4개
(신청처·대상·서류·기한)로 바꾸고, `save_value_issues()`로 숫자·라벨 구조를
기계 검증해 미달이면 사유를 되먹여 재생성한다. 프롬프트에 적기만 했던 이전
시도가 실패했기 때문에 이번엔 실제로 센다.

**판정 방법:** 저장 발생 비율(현재 1.8%)과 저장 있는 게시물의 도달을 비교한다.
