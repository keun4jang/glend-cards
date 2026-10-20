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
사이트 디자인(2026-10-17)은 `.claude/skills/frontend-design`·`redesign-existing-projects` 기준으로 손봤다 —
카드4의 연두(#CFFF04)를 본문 굵은 글씨의 형광펜으로만 쓰고, 글꼴은 카드와 같은 Pretendard(jsDelivr CDN).
목록엔 검색·분야 필터·월별 묶음, 글 끝엔 인스타 팔로우 안내와 같은 분야 글 3개. 디자인은 `build_site.py`의 `CSS`에 있다.

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

#### 감시·알림 (텔레그램) — 2026-10-14 추가

10/12~13에 릴스 3편이 조용히 실패했는데 이틀 뒤 수동 점검에서야 알았다. 그래서 두 겹으로 지킨다.
- **즉시 알림**: 6개 워크플로 마지막 단계 `Notify failure (Telegram)`가 실패·취소(시간 초과 포함) 시 링크와 함께 보낸다.
- **감시 에이전트** `watchdog.yml` → `watchdog.py`(읽기 전용):
  6시간마다 인스타 최근 게시물을 보고 릴스 26시간·카드 80시간 넘게 발행이 없으면 알린다(워크플로가 아예 안 돈 경우까지).
  매일 UTC 00:07 크론으로 지난 24시간 요약(발행 수·실패 수·팔로워)을 보낸다 — 크론 지연 때문에 실제 도착은 KST 13시 전후(10/16·17 실측). 이 요약이 안 오면 감시 자체가 죽은 것.
- 시크릿 `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`가 없으면 알림만 건너뛰고 파이프라인은 그대로 돈다.
  연결 확인: Actions → Watchdog (Telegram) → Run workflow(mode=test).

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

### 사실 확인 (`factcheck.py`) — 2026-10-18 추가

대본·카드는 뉴스 **제목만** 보고 쓰여서, 제목에 없는 금액·기한·처벌·판결·통계를 모델이 지어낼 수 있다
(예: 10/16 카드4 "기한 · 사고 후 7일이내 청구", 10/17 릴스 "노란불 통과 사고 = 과실 100%").
그래서 생성 루프의 다른 검사를 통과한 후보를 한 번 더 Gemini에 보내 **Google 검색 근거**로 확인한다.
- 틀린 부분만 원문 부분 문자열로 바꾼다(릴스 장면 +20자, 캡션 +150자까지, 카드 문구는 글자 수가 늘면 버림).
- 핵심 전제가 거짓이면 `reject` → 다른 주제로 **한 번만** 재생성.
- 검색 근거를 못 쓰면(무료 한도·미지원) 검색 없이 확인, 그것도 실패하면 건너뛴다 — 발행은 절대 막지 않는다.
- **2026-10-18 실측: 무료 티어는 모든 모델에서 검색 근거가 429(한도 0)라 현재는 항상 '검색 없이' 확인이다.**
  그래도 시험에서 징역→금고(교특법), 반환보증 가입 시점(계약 절반 경과 전), '누구나·100%' 단정 등을 잡았다.
  검색 근거를 쓰려면 결제가 필요해 보이는데 비용 정책상 하지 않는다. `gemini-2.0-flash`는 404(서비스 종료)라 2026-10-19에 모델 목록에서 뺐다.
- 결과는 `content["factcheck"]`(mode·verdict·applied·sources)로 아카이브에 남는다. 로그는 `[사실확인]`.
- 시험: Actions → Factcheck test(수동) — 최근 발행분을 다시 확인해 출력만 한다. `factcheck.py`를 바꾸는 PR에서도 자동 실행.
- 아직 남은 빈틈: 검색 근거도 틀릴 수 있고, 모델이 "ok"라고 놓치는 것도 있다. 정기적으로 `applied`를 훑어볼 것.
- **사이트 글(2026-10-20 추가)**: `article.py`도 생성 직후 같은 확인을 거친다(`kind="article"`, 본문 +300자까지).
  사이트 글은 대본보다 4배 길고 배경을 "보충"하라고 해서 새 수치가 끼어든다 — 10/17 농·축협 글의
  "예금자보호 1인당 5,000만 원"(2025-09부터 1억 원), 교차로 글의 "징역"(교특법은 금고)·"과실 100%"를 수동 정정했다.
  이미 올라간 글 재확인: Actions → Article recheck(수동, count·offset) — 고친 글을 archive에 커밋, 다음 사이트 빌드에 반영.
  주의: 검색 없이 확인하는 모델은 최근 제도 변경(예: 예금자보호 한도 상향)을 모를 수 있다.

### 배경 사진 (`pexels.py`, `cf_image.py`) — 2026-10-19 추가

- `pexels.py`(카드·릴스 공용): 후보 10장 중 사진 설명에 간판·로고·외국 은행·외국 화폐가 있으면 건너뛴다
  (10/19 카드에 HSBC 간판, "korean won bills desk" 1순위가 유로 지폐였다). 검색어에 있는 일반 단어는 봐준다.
- `cf_image.py`: Pexels가 못 줄 때만 클라우드플레어 Workers AI(flux-2-klein-9b, 세로 768×1024)로 대체.
  1,145장면 중 Pexels 실패 0건이라 평소엔 안 쓰인다. 무료 하루 10,000 Neurons — 넘으면 과금 없이 429.
  **한도는 UTC 자정 초기화가 아니라 사용 시점 기준(약 24시간 롤링)으로 풀리는 것으로 보인다**
  (10/19 00:36 UTC 대량 시험 → 10/20 00:21엔 여전히 429, 01:46엔 성공). 시험으로 한도를 다 쓰지 말 것.
  시크릿: `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`. 시험: Actions → Image test (Cloudflare).

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

### 릴스 도달 급락 (2026-08-31 ~ 09-23) — 2026-09-28 분석

- 주간 릴스 도달 중앙값이 7~8월 116~162에서 8/31 주부터 64~83으로 계단식으로 떨어졌다.
  9/24 이후 발행분은 107~160으로 회복됐다. 9월 릴스 35편의 공유는 전부 0이다
  (8월은 37회였다. `total_interactions`와 합계가 맞으므로 수집 오류는 아니다).
- **우리 코드 탓이 아니다.** 8/22~9/12 사이 파이프라인 코드 변경이 0건이다.
- **발행 시각 자체도 원인이 아니다.** 9월엔 16~20시 발행이 중앙값 34(20편 중 11편이 도달 40 미만)로
  무너졌지만, 8월엔 같은 16~20시 발행이 중앙값 118(40 미만 0편)이었다.
- **길이와의 관계**: 9월 45초 미만 릴스는 도달 중앙값 44(n=19), 45초 이상은 104(n=29)였다.
  다만 짧은 릴스가 급락 기간에 몰려 있어 교락돼 있다 — 인과로 단정하지 말 것.
  짧은 릴스는 재생성 되먹임 버그 때문에 생겼고 2026-09-28에 고쳤다(`generate_reel.py` 48~58초).
  이후 45초 미만이 사라진 상태에서 도달이 어떻게 되는지가 다음 근거다.

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

**추가 변경 (2026-09-28, 인스타 앱에서 수동):** 바이오 링크에
`https://keun4jang.github.io/glend-cards/` 추가. 바이오가 "👇 지난 자료 모아보기"로
끝나는데 링크가 비어 있어 CTA가 끊겨 있었다(2026-09-28 점검에서 발견).
판정 시 9/14~9/27(링크 없음)과 9/28 이후(링크 있음)를 따로 볼 수 있게 남겨 둔다.
인스타 웹에서는 링크 칸이 잠겨 있어 수정할 수 없다 — 앱에서만 된다.

**추가 변경 (2026-10-19, 인스타 앱에서 수동):** 바이오 링크를 **삭제**하고 "👇 지난 자료 모아보기" 줄과
"매일 아침"(실제 릴스는 저녁·자정 발행이라 사실과 다름)을 뺐다. 이유: 링크 추가 후에도 프로필 방문이 거의 0이라
링크로 들어온 사람이 없었고, 주소(`keun4jang.github.io`)에 운영자 개인 깃허브 아이디가 노출됐다.
판정 시 구간: 9/14~9/27(링크 없음) / 9/28~10/18(링크 있음) / 10/19~(링크 없음, 소개 문구 수정).
현재 소개: "놓치면 사라지는 정부지원금·환급 정보 / 신청처·조건·기한까지 한 장에 정리 / 💾 저장해두면 신청할 때 그대로 쓰는…"
(사이트는 검색 유입용으로 계속 운영한다 — 인스타에서 홍보하지 않을 뿐.)

**진단 근거:** 콘텐츠는 사람을 데려오고 있었다(프로필까지 292명). 팔로우가 안 난 건
도달 부족이 아니라 프로필에서 놓친 것이다. 그래서 콘텐츠를 더 만드는 것보다
프로필 한 번 고치는 게 레버리지가 크다고 판단했다.

**판정 방법:** `insights.py`의 `[4] 팔로우 깔때기`가 매 리포트에 전환율을 찍는다.
변경 이후 프로필 방문이 20 이상 쌓인 뒤(대략 2~3주) 2.1%와 비교한다.
주간 리포트는 최근 25개만 봐서 표본이 작으니, 확정 판정은
`archive/instagram_posts.csv`를 2026-09-14 전/후로 갈라서 해야 한다.

**⚠️ 판정 기준 조정 (2026-09-28):** 위 "방문 20"은 3주 안에 도달할 수 없다.
- 9월 카드 9편 전부 도달 3~15, 프로필방문 0. 카드에서 프로필방문이 마지막으로 난 건 2026-08-13이다.
  계정 전체 30일 profile_views도 1이다. **프로필까지 오는 사람 자체가 거의 없다.**
- 즉 기준선(292방문)은 과거 도달이 컸던 시기의 누적이고, 지금은 병목이 프로필보다
  **앞단(도달→프로필 유입)** 에 있다. 프로필을 고쳐도 볼 사람이 없으면 효과가 안 보인다.
- 그래서 판정을 이렇게 바꾼다:
  1. 주 지표(방문→팔로우 전환율)는 방문 20이 쌓일 때까지 **판정 보류**. 10/5에 결론 내지 말 것.
  2. 보조 지표로 **주간 팔로워 순증**을 본다. 변경 전 기준선: 2026-07-30 51명 →
     2026-09-14 60명 = **주당 +1.4명**(6.5주, 주간 리포트 기준).
     단 9/21→9/28의 61→59(-2)는 팔로잉 263→20 정리로 맞팔이 빠진 일회성 효과일 수 있으니
     그 주는 따로 표시하고 이후 추세로 본다.
  3. 최종 판정 시점은 변경 후 7주(2026-11-02)로 늘린다(기준선 기간과 같은 길이).
     그때도 방문이 20 미만이면 "프로필은 병목이 아니었다 — 유입이 병목"으로 결론 낸다.
- 성과 CSV는 `harvest.yml`이 월요일 크론 01:00 UTC지만 실제로는 약 06:00 UTC에 끝난다.
  판정은 그 뒤에 돌려야 이번 주 데이터가 들어간다.

**중간 점검 (2026-10-05, 변경 후 3주) — 결론 아님, 최종은 11/2:**
- 주 지표: 9/14 이후 카드 10편 프로필방문 **1**, 팔로우 0 → **판정 보류**(방문 20 기준에 한참 못 미침).
  바이오 링크 추가(9/28) 이후 카드 4편은 방문 0. 카드 도달 자체가 중앙값 10(9/28 이후 6.5)이라 링크 효과를 볼 표본이 없다.
- 보조 지표(주간 팔로워): 9/14 60 → 9/21 61(+1) → 9/28 59(-2, 팔로잉 정리 주) → 10/5 60(+1).
  3주 순증 0 vs 기준선 주당 +1.4. 정리 주를 빼면 주당 +1로 기준선과 비슷 — 개선도 악화도 말할 수 없다.
- 해석: 프로필 변경의 효과를 측정할 유입 자체가 없다. 11/2에도 방문 20 미만이면 위 3번대로
  "프로필은 병목이 아니었다 — 유입이 병목"으로 결론 낸다.

### B. 카드4 저장 포맷 — 2026-09-14 변경, 3주 뒤 판정

**기준선:** 게시물 338개 중 저장 6개(1.8%). 저장·공유가 붙은 카드는 평균 도달 191,
없는 카드는 15로 **12.4배** 차이 — 저장이 안 되면 도달이 팔로워 안에 갇힌다.

**변경:** 카드4 항목을 문장("정부24에서 신청하세요")에서 "라벨 · 값" 4개
(신청처·대상·서류·기한)로 바꾸고, `save_value_issues()`로 숫자·라벨 구조를
기계 검증해 미달이면 사유를 되먹여 재생성한다. 프롬프트에 적기만 했던 이전
시도가 실패했기 때문에 이번엔 실제로 센다.

**판정 방법:** 저장 발생 비율(현재 1.8%)과 저장 있는 게시물의 도달을 비교한다.

**중간 점검 (2026-10-05, 변경 후 3주):**
- 변경 후 카드 10편 중 저장 1편(10%, 9/16 음주운전 벌금) vs 변경 전 342편 중 7편(2.0%).
  비율은 5배지만 **표본 10편에 저장 1건은 우연 범위다** — 2% 확률로도 10편 중 1편 이상 나올 확률이 약 18%.
- 변경 후 카드 도달 중앙값 10(9/28 이후 4편은 6.5)으로 변경 전(15)보다 낮다. 저장 있는 카드의 도달(변경 전 평균 215)과
  비교할 표본이 없다(저장 카드 1편 도달 17).
- **결론 보류.** 주 3회라 표본이 쌓이는 속도가 느리다 — 30편(약 10주, 2026-11-23 전후)은 돼야 2%와 구별할 수 있다.

### C. 릴스 공유 설계 — 2026-09-29 변경, 3주 뒤(2026-10-20) 판정

**기준선(릴스, `archive/instagram_posts.csv`):**
- 1,000도달당 공유: 2026-06~09 전체 **2.30** / 8월 **3.29** / 9월 **0.27**(49편 중 공유 1건)
- 공유가 1건 이상 붙은 릴스 비율: 8월 17% / 9월 2%

**변경:** "이 영상을 누구에게 보낼지"를 콘텐츠가 대신 정해 준다(레퍼런스: "피부 하얘지는 법"이
아니라 "피부 까만 사람 특징 → 피부 까만 친구에게 공유"). `generate_reel.py`가
- 주제 선택 기준에 "보내줄 한 사람이 떠오르는가"를 넣고, 단순 시사 뉴스는 피하게 했다.
- `share_target`(관계 + 상황, 예: "전세 사는 친구")을 받아 `share_issues()`로 기계 검증한다
  (막연한 "주변·지인·여러분"이나 관계 없는 표현은 사유를 되먹여 재생성).
- 결론 장면 자막 아래 "→ OO에게 공유"를 띄우고(`render_reel.py`), 캡션 해시태그 위에
  "📤 OO에게 보내주세요"를 보장한다. 막연하던 "주변에 ~한 분이 있다면 공유" 문구를 대체.
- 카드뉴스는 실험 B(카드4) 판정 전이라 건드리지 않았다.

**판정 방법:** 2026-09-29 이후 릴스의 1,000도달당 공유와 공유 1건 이상 비율을 위 기준선과 비교.
**교락 주의:** 같은 주에 릴스 길이 하한(48초, 9/28)도 들어갔다. 길이는 주로 도달·시청에,
공유 설계는 공유에 작용하므로 "도달 대비 공유"로 정규화해서 본다.

**첫 주 관찰 (2026-10-05, 판정 아님):**
- share_target이 붙은 릴스 10편(9/30 18:33~10/4): 공유 4건(2편), 도달 합 1,326 → **1,000도달당 3.0**, 공유 붙은 비율 20%.
  9월(0.27 / 2%)보다 높고 8월(3.29 / 17%) 수준이지만 **10편·공유 4건이라 아직 우연과 구별 불가.** 판정은 10/20.
- 공유가 붙은 2편: "밤마다 화장실 가는 가족"(전립선, 공유 3·저장 1, 도달 161), "월세 내는 자취생 친구"(공유 1·저장 1, 도달 156).
- 검증 누락 1건: "대구 사는 신혼부부"는 관계 단어 목록에 없어 결론 장면 공유 줄이 빠졌다(캡션엔 모델이 직접 넣음).
  신혼부부·예비부부 같은 대상 표현을 목록에 넣을지 판정 때 함께 볼 것.
- 같은 주 릴스 길이: 9/28 이후 14편 전부 46.8~57.7초(45초 미만 0편). 48초 미만 1편은 9/29 DMZ(PR #8 수정 전).
  도달 중앙값 112.5(n=14)로 9/24 이후 회복이 유지된다. 주제 중복은 9/29 DMZ 1건(수정 전)뿐.
- **판정 시 교락 표시:** 2026-10-11에 릴스 디자인을 바꿨다 — 첫 3초 후킹 배경을 회색 단색에서 1번 장면 사진(어둡게)으로,
  아웃트로를 로고만 7초에서 "팔로우 멘트 + 💾저장 📤공유 ➕팔로우" 화면으로(`render_reel.py`, `templates/reel.html`).
  아웃트로 버튼이 공유를 직접 유도하므로 10/11 이전·이후를 나눠서도 볼 것. 길이(아웃트로 내레이션)는 그대로다.
