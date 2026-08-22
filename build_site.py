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

CSS = """*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#fff;--fg:#16191c;--muted:#5b6470;--line:#e5e8ec;--accent:#3d7a2f;--card:#fafbfc}
@media(prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#111417;--fg:#e8eaed;--muted:#9aa4b0;--line:#262b31;--accent:#a3d977;--card:#171b1f}}
body{background:var(--bg);color:var(--fg);font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Malgun Gothic",sans-serif;line-height:1.75;-webkit-text-size-adjust:100%}
.wrap{max-width:720px;margin:0 auto;padding:24px 20px 72px}
header{border-bottom:1px solid var(--line);margin-bottom:32px;padding-bottom:16px}
header a{color:var(--fg);text-decoration:none;font-weight:800;font-size:19px;letter-spacing:-.02em}
header p{color:var(--muted);font-size:13px;margin-top:4px}
h1{font-size:29px;line-height:1.35;letter-spacing:-.03em;margin:8px 0 14px;word-break:keep-all}
h2{font-size:20px;letter-spacing:-.02em;margin:34px 0 12px;padding-top:14px;border-top:1px solid var(--line);word-break:keep-all}
h3{font-size:17px;margin:22px 0 8px}
p{margin:0 0 14px;word-break:keep-all}
ul,ol{margin:0 0 16px 20px}li{margin-bottom:7px;word-break:keep-all}
table{width:100%;border-collapse:collapse;margin:0 0 18px;font-size:15px;display:block;overflow-x:auto}
th,td{border:1px solid var(--line);padding:9px 11px;text-align:left}
th{background:var(--card);font-weight:700}
.meta{color:var(--muted);font-size:13px;margin-bottom:24px}
.list{list-style:none;margin:0}
.list li{border-bottom:1px solid var(--line);margin:0}
.list a{display:block;padding:16px 0;text-decoration:none;color:var(--fg)}
.list strong{display:block;font-size:17px;letter-spacing:-.02em;margin-bottom:4px;word-break:keep-all}
.list span{color:var(--muted);font-size:14px;word-break:keep-all}
.tag{display:inline-block;font-size:12px;color:var(--muted);border:1px solid var(--line);border-radius:99px;padding:2px 9px;margin:0 5px 5px 0}
footer{margin-top:48px;padding-top:18px;border-top:1px solid var(--line);color:var(--muted);font-size:13px}
footer a{color:var(--accent)}
.back{display:inline-block;margin-bottom:18px;color:var(--accent);text-decoration:none;font-size:14px}
"""

CATEGORY = {"1": "생활경제", "2": "사건사고", "3": "건강"}

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
<style>{CSS}</style>
{extra_head}
</head>
<body><div class="wrap">
<header><a href="{BASE_URL}/">{SITE_NAME}</a><p>{SITE_DESC}</p></header>
{body}
<footer>
<p>{SITE_NAME} · 인스타그램 <a href="https://instagram.com/glend_kr">@glend_kr</a></p>
<p>제도·금액·기한은 변경될 수 있습니다. 신청 전 반드시 공식 기관 안내를 확인하세요.</p>
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
        tags = "".join(f'<span class="tag">{html.escape(k)}</span>' for k in a["keywords"][:6])
        ld = json.dumps({
            "@context": "https://schema.org", "@type": "Article",
            "headline": a["title"], "description": a["desc"],
            "datePublished": a["date"], "inLanguage": "ko",
            "publisher": {"@type": "Organization", "name": SITE_NAME},
        }, ensure_ascii=False)
        body = (f'<a class="back" href="{BASE_URL}/">← 목록</a>'
                f'<h1>{html.escape(a["title"])}</h1>'
                f'<p class="meta">{a["date"]}'
                + (f' · {a["category"]}' if a["category"] else "") + "</p>"
                + md_to_html(a["body"]) + f'<p style="margin-top:28px">{tags}</p>')
        (d / "index.html").write_text(
            page(f'{a["title"]} | {SITE_NAME}', a["desc"], body,
                 enc(f'{BASE_URL}/{a["slug"]}/'),
                 f'<script type="application/ld+json">{ld}</script>'),
            encoding="utf-8")

    def _item(a):
        href = enc(f"{BASE_URL}/{a['slug']}/")
        return (f'<li><a href="{href}"><strong>{html.escape(a["title"])}</strong>'
                f'<span>{html.escape(a["desc"])}</span></a></li>')

    items = "".join(_item(a) for a in arts)
    index_body = ("<h1>정부지원금·생활정보, 신청 방법 중심으로</h1>"
                  f'<p class="meta">글 {len(arts)}개</p>'
                  + (f'<ul class="list">{items}</ul>' if arts
                     else "<p>아직 발행된 글이 없습니다.</p>"))
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
