"""
archive/의 기사들을 정적 사이트(docs/)로 빌드 → GitHub Pages 무료 호스팅.

왜 인스타가 아니라 검색인가:
  인스타에서 실패한 지점은 "팔로우할 이유가 없다"였다. 검색은 그 이유가 필요 없다 —
  '경차 유류세 환급 신청방법'을 검색한 사람에게 답이 있으면 팔로워 0명이어도 들어온다.
  대신 검색은 '얇은 콘텐츠'를 거르므로 article.py가 1500자 이상으로 다시 쓴 글만 싣는다.

출력: docs/index.html, docs/<slug>/index.html, docs/sitemap.xml, docs/robots.txt
"""
import html
import json
import re
import urllib.parse
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE = Path(__file__).parent
ARCHIVE = BASE / "archive"
DOCS = BASE / "docs"
KST = timezone(timedelta(hours=9))

SITE_NAME = "GLEND 생활정보"
SITE_DESC = "정부지원금·생활경제·건강 정보를 신청 방법과 조건 중심으로 정리합니다."
BASE_URL = "https://keun4jang.github.io/glend-cards"

# 디자인 원칙(2026-10-17, frontend-design·redesign-existing-projects 스킬 기준):
#  - 인스타 카드와 같은 집안으로 보이게: 카드4의 형광 연두(#CFFF04)와 Pretendard.
#  - 연두는 "형광펜" 한 곳에만 쓴다 — 본문 굵은 글씨(신청 조건·금액·기한) 밑줄 칠.
#    검색으로 들어온 사람이 훑어 읽을 때 눈이 멈춰야 할 곳이 그 줄이다.
#  - 나머지는 조용하게: 흰 바탕, 카드 상자·그림자·대문자 라벨·화살표 없음.
CSS = """*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#fff;--fg:#1b1e22;--muted:#5f6670;--line:#e4e6e9;--soft:#f5f6f7;--mark:#cfff04;--mark-ink:#1b1e22;--link:#2f6b12}
@media(prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#16191c;--fg:#e9ebee;--muted:#9ba3ad;--line:#2a2f35;--soft:#1d2125;--mark:rgba(207,255,4,.28);--mark-ink:#f2ffb8;--link:#c6f04a}}
html{-webkit-text-size-adjust:100%;scroll-behavior:smooth}
body{background:var(--bg);color:var(--fg);font-family:"Pretendard Variable",Pretendard,-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Malgun Gothic",sans-serif;font-size:17px;line-height:1.8;font-feature-settings:"tnum" 0}
.skip{position:absolute;left:-999px;top:8px;background:var(--fg);color:var(--bg);padding:8px 12px;border-radius:6px;z-index:10}
.skip:focus{left:12px}
:focus-visible{outline:3px solid var(--fg);outline-offset:3px;border-radius:3px}
.wrap{max-width:680px;margin:0 auto;padding:20px 20px 88px}
header{display:flex;align-items:baseline;gap:10px;padding-bottom:18px;margin-bottom:40px;border-bottom:2px solid var(--fg)}
header a{color:var(--fg);text-decoration:none;font-weight:800;font-size:20px;letter-spacing:-.03em}
header a b{background:#cfff04;color:#1b1e22;padding:0 .18em;border-radius:2px}
header span{color:var(--muted);font-size:14px}
h1{font-size:clamp(28px,6.4vw,38px);line-height:1.28;font-weight:800;letter-spacing:-.035em;margin:0 0 14px;word-break:keep-all;text-wrap:balance}
h2{font-size:22px;line-height:1.4;font-weight:700;letter-spacing:-.025em;margin:48px 0 14px;word-break:keep-all;text-wrap:balance}
h3{font-size:18px;font-weight:700;letter-spacing:-.02em;margin:28px 0 8px;word-break:keep-all}
p{margin:0 0 16px;word-break:keep-all;text-wrap:pretty}
article p,article li{max-width:38em}
ul,ol{margin:0 0 18px 1.2em}li{margin-bottom:8px;word-break:keep-all;padding-left:2px}
li::marker{color:var(--muted)}
strong{font-weight:700;background:linear-gradient(transparent 58%,var(--mark) 58%,var(--mark) 92%,transparent 92%);color:var(--mark-ink);padding:0 1px;-webkit-box-decoration-break:clone;box-decoration-break:clone}
table{width:100%;border-collapse:collapse;margin:4px 0 22px;font-size:15px;line-height:1.6;display:block;overflow-x:auto;font-variant-numeric:tabular-nums}
th,td{padding:10px 12px;text-align:left;vertical-align:top;border-bottom:1px solid var(--line);word-break:keep-all}
thead th{border-bottom:2px solid var(--fg);font-weight:700;white-space:nowrap}
td strong{background:none;padding:0}
.meta{color:var(--muted);font-size:14px;margin-bottom:32px;font-variant-numeric:tabular-nums}
.meta span+span::before{content:"";display:inline-block;width:3px;height:3px;border-radius:50%;background:currentColor;vertical-align:middle;margin:0 8px}
.back{display:inline-block;margin-bottom:22px;color:var(--muted);font-size:14px;text-decoration:underline;text-underline-offset:3px}
.back:hover{color:var(--fg)}
.lead{color:var(--muted);font-size:16px;max-width:30em;margin-bottom:28px}
.tools{margin:0 0 8px}
.tools input{width:100%;font:inherit;font-size:16px;padding:12px 14px;border:1.5px solid var(--line);border-radius:10px;background:var(--bg);color:var(--fg)}
.tools input:focus{outline:none;border-color:var(--fg)}
.cats{display:flex;flex-wrap:wrap;gap:6px;margin:12px 0 0}
.cats button{font:inherit;font-size:14px;padding:6px 13px;border-radius:6px;border:1.5px solid var(--line);background:var(--bg);color:var(--fg);cursor:pointer;min-height:36px}
.cats button[aria-pressed=true]{background:var(--fg);color:var(--bg);border-color:var(--fg)}
.cats button:active{transform:translateY(1px)}
#count{color:var(--muted);font-size:14px;margin:18px 0 0;font-variant-numeric:tabular-nums}
.month h2{font-size:15px;color:var(--muted);font-weight:600;letter-spacing:0;margin:36px 0 0;padding-bottom:8px;border-bottom:1px solid var(--line)}
.list{list-style:none;margin:0}
.list li{margin:0;padding:0;border-bottom:1px solid var(--line)}
.list a{display:block;padding:18px 0 20px;text-decoration:none;color:var(--fg)}
.list small{display:block;color:var(--muted);font-size:13px;margin-bottom:4px;font-variant-numeric:tabular-nums}
.list strong{display:block;background:none;padding:0;font-size:18px;line-height:1.45;letter-spacing:-.025em;margin-bottom:6px;word-break:keep-all;text-wrap:balance}
.list span{color:var(--muted);font-size:15px;line-height:1.65;word-break:keep-all;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.list a:hover strong{text-decoration:underline;text-decoration-thickness:2px;text-underline-offset:4px}
.tags{margin-top:36px;color:var(--muted);font-size:14px}
.tags span{display:inline-block;margin:0 12px 4px 0}
.follow{margin:48px 0 0;padding:22px 22px 24px;background:var(--soft);border-left:6px solid var(--mark);border-radius:4px}
.follow p{margin:0 0 6px;font-weight:700;font-size:18px;letter-spacing:-.02em}
.follow span{display:block;color:var(--muted);font-size:15px;margin-bottom:12px}
.follow a{color:var(--link);font-weight:700}
.more h2{font-size:18px;margin:48px 0 4px}
footer{margin-top:64px;padding-top:20px;border-top:1px solid var(--line);color:var(--muted);font-size:13px;line-height:1.7}
footer p{margin:0 0 6px}
footer a{color:inherit}
a{color:var(--link)}
@media(max-width:480px){body{font-size:16.5px}.wrap{padding:16px 16px 72px}header{margin-bottom:28px}h2{font-size:20px;margin-top:40px}}
"""

CATEGORY = {"1": "생활경제", "2": "사건사고", "3": "건강"}

# 웹폰트: 카드·릴스와 같은 Pretendard. 한글은 용량이 커서 필요한 글자만 받는 dynamic subset을 쓴다
# (jsDelivr 무료 CDN). 못 받아도 시스템 고딕으로 그대로 읽힌다.
FONT_CSS = ("https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/"
            "pretendardvariable-dynamic-subset.min.css")
# 파비콘: 연두 바탕에 G — 별도 파일 없이 SVG 데이터 URI로 넣는다.
FAVICON = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E"
           "%3Crect width='64' height='64' rx='12' fill='%23cfff04'/%3E%3Ctext x='32' y='46' "
           "font-family='Arial,sans-serif' font-size='42' font-weight='900' text-anchor='middle' "
           "fill='%231b1e22'%3EG%3C/text%3E%3C/svg%3E")

# 검색엔진 소유권 확인 메타 태그.
# docs/는 매일 다시 생성되는 빌드 산출물이라, 여기(빌드 코드)에 넣어야 재빌드에도 살아남는다.
# 수동으로 docs/index.html에 넣으면 다음 날 사라져 소유권이 풀린다.
# 지우면 확인이 해제되므로 등록 후에도 계속 유지할 것.
VERIFY_META = {
    "google-site-verification": "aP36GhDa7FjuF2yftaHI72n4wUyh7zKJ3yqjeQzUGto",
    # 네이버 서치어드바이저를 등록하면 여기에 추가:
    # "naver-site-verification": "...",
}


def enc(url):
    """URL의 한글·비ASCII 경로를 퍼센트 인코딩.

    사이트맵 규격(sitemaps.org)은 URL을 이스케이프하도록 요구한다.
    한글 경로를 날것으로 넣으면 구글이 사이트맵을 '가져올 수 없음'으로 처리하고
    발견된 페이지가 0이 된다(실제로 그랬다). 브라우저는 알아서 인코딩하지만
    사이트맵·canonical에는 인코딩된 형태로 넣어야 한다.
    """
    p = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((
        p.scheme, p.netloc,
        urllib.parse.quote(p.path, safe="/-_.~"),
        urllib.parse.quote(p.query, safe="=&"), p.fragment))


def md_to_html(md):
    """의존성 없이 쓰는 최소 마크다운 변환 (H2/H3, 불릿, 번호, 표, 굵게)"""
    out, lines, i = [], md.split("\n"), 0
    while i < len(lines):
        ln = lines[i].rstrip()
        if not ln.strip():
            i += 1
            continue
        if ln.startswith("### "):
            out.append(f"<h3>{inline(ln[4:])}</h3>"); i += 1; continue
        if ln.startswith("## "):
            out.append(f"<h2>{inline(ln[3:])}</h2>"); i += 1; continue
        if ln.startswith("# "):
            out.append(f"<h2>{inline(ln[2:])}</h2>"); i += 1; continue
        if ln.lstrip().startswith("|") and i + 1 < len(lines) and set(lines[i+1].replace("|","").strip()) <= set("-: "):
            head = [c.strip() for c in ln.strip().strip("|").split("|")]
            i += 2
            rows = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")]); i += 1
            th = "".join(f"<th>{inline(c)}</th>" for c in head)
            tb = "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in rows)
            out.append(f"<table><thead><tr>{th}</tr></thead><tbody>{tb}</tbody></table>"); continue
        if re.match(r"\s*[-*]\s+", ln):
            items = []
            while i < len(lines) and re.match(r"\s*[-*]\s+", lines[i]):
                items.append(re.sub(r"\s*[-*]\s+", "", lines[i]).rstrip()); i += 1
            out.append("<ul>" + "".join(f"<li>{inline(x)}</li>" for x in items) + "</ul>"); continue
        if re.match(r"\s*\d+[.)]\s+", ln):
            items = []
            while i < len(lines) and re.match(r"\s*\d+[.)]\s+", lines[i]):
                items.append(re.sub(r"\s*\d+[.)]\s+", "", lines[i]).rstrip()); i += 1
            out.append("<ol>" + "".join(f"<li>{inline(x)}</li>" for x in items) + "</ol>"); continue
        para = [ln]
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(r"\s*([-*]|\d+[.)]|#|\|)", lines[i]):
            para.append(lines[i].rstrip()); i += 1
        out.append(f"<p>{inline(' '.join(para))}</p>")
    return "\n".join(out)


def inline(t):
    t = html.escape(t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    return t


def page(title, desc, body, canonical, extra_head=""):
    verify_tags = "\n".join(
        f'<meta name="{k}" content="{html.escape(v)}">'
        for k, v in VERIFY_META.items() if v)
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(desc)}">
{verify_tags}
<link rel="canonical" href="{canonical}">
<meta property="og:type" content="article">
<meta property="og:title" content="{html.escape(title)}">
<meta property="og:description" content="{html.escape(desc)}">
<meta property="og:url" content="{canonical}">
<meta property="og:site_name" content="{SITE_NAME}">
<meta name="theme-color" content="#cfff04">
<link rel="icon" href="{FAVICON}">
<link rel="preconnect" href="https://cdn.jsdelivr.net" crossorigin>
<link rel="stylesheet" href="{FONT_CSS}">
<style>{CSS}</style>
{extra_head}
</head>
<body><a class="skip" href="#main">본문 바로가기</a><div class="wrap">
<header><a href="{BASE_URL}/"><b>GLEND</b> 생활정보</a><span>신청 방법부터 정리합니다</span></header>
<main id="main">
{body}
</main>
<footer>
<p>{SITE_NAME}. 매일 새 글은 인스타그램 <a href="https://instagram.com/glend_kr">@glend_kr</a>에 먼저 올라옵니다.</p>
<p>제도·금액·기한은 바뀔 수 있습니다. 신청 전에 공식 기관 안내를 꼭 확인하세요.</p>
</footer>
</div></body></html>"""


# URL에서 빼야 하는 군더더기 — 검색엔진이 보는 핵심 키워드를 앞으로 당긴다
_SLUG_DROP = ("정리", "방법과", "및", "그리고", "위한", "대한", "하는")


def article_slug(title, topic=""):
    """검색어에 가까운 URL 조각을 만든다.

    파일명(2026-08-20-reel1-...)을 그대로 쓰면 날짜와 내부 인덱스가 앞에 붙어
    핵심 키워드가 뒤로 밀린다. 기사 제목이 곧 검색 의도이므로 그걸 쓴다.
    한글 URL은 공유 시 퍼센트 인코딩으로 보이지만, 국내 검색엔진이 정상 처리하고
    브라우저 주소창에서는 한글로 읽힌다.
    """
    t = re.sub(r"<[^>]+>", "", title or topic or "").strip()
    # %는 URL에서 퍼센트 인코딩 이스케이프라 그대로 두면 주소가 깨진다 ("40%-절세" -> 잘못된 인코딩)
    t = t.replace("%", "퍼센트")
    t = re.sub(r"[^\w\s가-힣]", " ", t)
    words = [w for w in t.split() if w and w not in _SLUG_DROP]
    slug = "-".join(words)[:60].strip("-")
    return slug or "article"


def load_articles():
    arts, used = [], {}
    if not ARCHIVE.exists():
        return arts
    for f in sorted(ARCHIVE.rglob("*.json")):
        try:
            rec = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        art = rec.get("article")
        if not art or not art.get("title") or len(art.get("body_markdown", "")) < 600:
            continue
        slug = article_slug(art["title"], rec.get("topic", ""))
        # 제목이 겹치면 URL이 덮어써지므로 번호를 붙인다
        if slug in used:
            used[slug] += 1
            slug = f"{slug}-{used[slug]}"
        else:
            used[slug] = 1
        arts.append({
            "slug": slug,
            "title": art["title"],
            "desc": art.get("description", ""),
            "keywords": art.get("keywords", []),
            "body": art["body_markdown"],
            "date": (rec.get("published_kst") or "")[:10],
            "category": CATEGORY.get(str(rec.get("index", "")), ""),
        })
    arts.sort(key=lambda a: a["date"], reverse=True)
    return arts


VERIFY_DIR = BASE / "site_verify"


def copy_verification_files():
    """검색엔진 소유권 확인 파일을 그대로 사이트 루트에 복사.

    구글 서치콘솔·네이버 서치어드바이저는 루트에 확인용 HTML을 요구한다.
    site_verify/에 받은 파일을 넣어두면 빌드할 때마다 자동으로 docs/에 복사되므로,
    사이트를 다시 빌드해도 확인이 풀리지 않는다. (docs/는 빌드 산출물이라 수동 배치는 사라진다)
    """
    if not VERIFY_DIR.exists():
        return 0
    n = 0
    for f in VERIFY_DIR.iterdir():
        if f.is_file() and not f.name.startswith(".") and f.name.lower() != "readme.md":
            (DOCS / f.name).write_bytes(f.read_bytes())
            n += 1
    if n:
        print(f"  소유권 확인 파일 {n}개 복사")
    return n


def _kdate(d):
    try:
        y, m, dd = d.split("-")
        return f"{y}년 {int(m)}월 {int(dd)}일"
    except ValueError:
        return d


def _kmonth(k):
    try:
        y, m = k.split("-")
        return f"{y}년 {int(m)}월"
    except ValueError:
        return "날짜 미상"


def _item(a):
    href = enc(f"{BASE_URL}/{a['slug']}/")
    meta = _kdate(a["date"]).split("년 ", 1)[-1] + (f", {a['category']}" if a["category"] else "")
    return (f'<li data-cat="{a["category"]}"><a href="{href}"><small>{meta}</small>'
            f'<strong>{html.escape(a["title"])}</strong>'
            f'<span>{html.escape(a["desc"])}</span></a></li>')


INDEX_JS = """<script>
(function(){
  var tools=document.querySelector('.tools'); if(!tools) return; tools.hidden=false;
  var q=document.getElementById('q'), out=document.getElementById('count'), cat='';
  var items=[].slice.call(document.querySelectorAll('.month li'));
  var months=[].slice.call(document.querySelectorAll('.month'));
  var btns=[].slice.call(document.querySelectorAll('.cats button'));
  function run(){
    var t=q.value.trim().toLowerCase().split(/\\s+/).filter(Boolean), n=0;
    items.forEach(function(li){
      var txt=li.textContent.toLowerCase();
      var ok=(!cat||li.getAttribute('data-cat')===cat)&&t.every(function(w){return txt.indexOf(w)>-1});
      li.hidden=!ok; if(ok) n++;
    });
    months.forEach(function(m){ m.hidden=!m.querySelector('li:not([hidden])'); });
    out.textContent=n?('글 '+n+'개'):'맞는 글이 없습니다. 검색어를 한 단어로 줄이거나 분야를 전체로 바꿔 보세요.';
  }
  q.addEventListener('input',run);
  btns.forEach(function(b){ b.addEventListener('click',function(){
    cat=b.getAttribute('data-cat');
    btns.forEach(function(x){ x.setAttribute('aria-pressed', x===b?'true':'false'); });
    run();
  }); });
})();
</script>"""


def build():
    arts = load_articles()
    DOCS.mkdir(exist_ok=True)
    (DOCS / ".nojekyll").write_text("", encoding="utf-8")
    copy_verification_files()

    # IndexNow 키 파일 — 사이트에 공개돼야 소유권이 인정된다(비밀 아님)
    kf = BASE / "indexnow_key.txt"
    if kf.exists():
        key = kf.read_text(encoding="utf-8").strip()
        if key:
            (DOCS / f"{key}.txt").write_text(key, encoding="utf-8")

    for a in arts:
        d = DOCS / a["slug"]
        d.mkdir(parents=True, exist_ok=True)
        tags = "".join(f"<span>#{html.escape(k.replace(' ', ''))}</span>" for k in a["keywords"][:6])
        ld = json.dumps({
            "@context": "https://schema.org", "@type": "Article",
            "headline": a["title"], "description": a["desc"],
            "datePublished": a["date"], "inLanguage": "ko",
            "publisher": {"@type": "Organization", "name": SITE_NAME},
        }, ensure_ascii=False)
        # 같은 분야 최신 글 3개 — 검색으로 한 글만 보고 나가는 사람을 붙잡고, 내부 링크로 색인도 돕는다
        more = [x for x in arts if x is not a and x["category"] == a["category"]][:3]
        more_html = ("" if not more else
                     '<section class="more"><h2>같은 분야 다른 글</h2><ul class="list">'
                     + "".join(_item(x) for x in more) + "</ul></section>")
        body = (f'<a class="back" href="{BASE_URL}/">전체 글 목록</a>'
                f'<article><h1>{html.escape(a["title"])}</h1>'
                f'<p class="meta"><span>{_kdate(a["date"])}</span>'
                + (f'<span>{a["category"]}</span>' if a["category"] else "") + "</p>"
                + md_to_html(a["body"])
                + (f'<p class="tags">{tags}</p>' if tags else "") + "</article>"
                + '<aside class="follow"><p>이런 정보, 매일 받아보세요</p>'
                  '<span>신청 기한이 짧은 지원금은 인스타그램에 먼저 올립니다.</span>'
                  '<a href="https://instagram.com/glend_kr">인스타그램 @glend_kr 팔로우</a></aside>'
                + more_html)
        (d / "index.html").write_text(
            page(f'{a["title"]} | {SITE_NAME}', a["desc"], body,
                 enc(f'{BASE_URL}/{a["slug"]}/'),
                 f'<script type="application/ld+json">{ld}</script>'),
            encoding="utf-8")

    # 목록: 월별로 묶고(글이 120개를 넘어 한 줄로는 못 찾는다), 검색·분야 필터를 단다.
    # 필터는 JS가 켜질 때만 보인다 — JS가 없어도 전체 목록은 그대로 읽힌다.
    groups = {}
    for x in arts:
        groups.setdefault(x["date"][:7], []).append(x)
    months = "".join(
        f'<section class="month"><h2>{_kmonth(k)}</h2><ul class="list">'
        + "".join(_item(x) for x in v) + "</ul></section>"
        for k, v in groups.items())
    cats = [c for c in CATEGORY.values() if any(x["category"] == c for x in arts)]
    buttons = '<button type="button" data-cat="" aria-pressed="true">전체</button>' + "".join(
        f'<button type="button" data-cat="{c}" aria-pressed="false">{c}</button>' for c in cats)
    index_body = ("<h1>정부지원금과 생활정보,<br>신청 방법부터</h1>"
                  '<p class="lead">누가 받을 수 있는지, 어디서 신청하는지, 언제까지인지. '
                  "뉴스에서 빠지기 쉬운 이 세 가지를 먼저 적습니다.</p>"
                  + ('<div class="tools" hidden><label for="q" class="skip">글 검색</label>'
                     '<input id="q" type="search" placeholder="찾는 제도나 지원금 이름 (예: 청년, 연금, 환급)" autocomplete="off">'
                     f'<div class="cats" role="group" aria-label="분야">{buttons}</div></div>'
                     f'<p id="count" aria-live="polite">글 {len(arts)}개</p>' + months + INDEX_JS
                     if arts else "<p>아직 발행된 글이 없습니다. 첫 글은 매일 새벽에 올라옵니다.</p>"))
    (DOCS / "index.html").write_text(
        page(SITE_NAME, SITE_DESC, index_body, f"{BASE_URL}/"), encoding="utf-8")

    now = datetime.now(KST).strftime("%Y-%m-%d")
    urls = "".join(
        "<url><loc>" + enc(f"{BASE_URL}/{a['slug']}/") + "</loc>"
        f"<lastmod>{a['date'] or now}</lastmod></url>"
        for a in arts)
    (DOCS / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"<url><loc>{BASE_URL}/</loc><lastmod>{now}</lastmod></url>{urls}</urlset>",
        encoding="utf-8")
    (DOCS / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\nSitemap: {BASE_URL}/sitemap.xml\n", encoding="utf-8")

    print(f"사이트 빌드 완료: 글 {len(arts)}개 → docs/")
    return len(arts)


if __name__ == "__main__":
    build()
