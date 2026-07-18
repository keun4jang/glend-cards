import asyncio
import json
import re
import sys
from pathlib import Path
from playwright.async_api import async_playwright

BASE = Path(__file__).parent
TEMPLATE = (BASE / "templates" / "card.html").resolve().as_uri()
LOGO = (BASE / "assets" / "logo.png").resolve().as_uri()

POST_INDEX = sys.argv[1] if len(sys.argv) > 1 else "1"
OUTPUT = BASE / "output" / f"post{POST_INDEX}"
OUTPUT.mkdir(parents=True, exist_ok=True)

with open(f"content_{POST_INDEX}.json", "r", encoding="utf-8") as f:
    content = json.load(f)

FALLBACK = "https://images.pexels.com/photos/210607/pexels-photo-210607.jpeg"

BASE_FONT = 64   # 기본 본문 폰트 크기(px)
MAX_CHARS = 16   # 이 글자 수까지 기본 크기 유지

TITLE_BASE_FONT = 150  # 카드1 제목 기본 폰트 크기(px)
TITLE_MAX_CHARS = 7    # 이 글자 수까지 기본 크기 유지

def char_count(line):
    """HTML 태그 제거 후 실제 글자 수"""
    return len(re.sub(r'<[^>]+>', '', line))

def font_size(line):
    """글자 수에 비례해 폰트 크기 축소, 최소 36px"""
    n = char_count(line)
    if n <= MAX_CHARS:
        return BASE_FONT
    return max(36, int(BASE_FONT * MAX_CHARS / n))

def title_font_size(line):
    """카드1 제목 글자 수에 비례해 폰트 크기 축소, 최소 70px"""
    n = char_count(line)
    if n <= TITLE_MAX_CHARS:
        return TITLE_BASE_FONT
    return max(70, int(TITLE_BASE_FONT * TITLE_MAX_CHARS / n))

def sized_lines(lines):
    """각 줄에 font-size 인라인 스타일 적용"""
    return [
        f'<span class="line" style="font-size:{font_size(l)}px">{l}</span>'
        for l in lines
    ]

def sized_title(text):
    """줄바꿈 문자로 나눈 뒤 각 줄에 축소된 font-size 적용 (자동 줄바꿈 방지)"""
    return "".join(
        f'<span class="line" style="font-size:{title_font_size(l)}px">{l}</span>'
        for l in text.split("\n")
    )

CARDS = [
    {"type": "hook", "bg": content["card1"].get("bg", FALLBACK),
     "title_html": sized_title(content["card1"]["title"]), "sub": content["card1"]["sub"]},
    {"type": "analysis", "bg": content["card2"].get("bg", FALLBACK),
     "subtitle": content["card2"]["subtitle"],
     "lines_html": "".join(sized_lines(content["card2"]["lines"]))},
    {"type": "insight", "bg": content["card3"].get("bg", FALLBACK),
     "title": content["card3"]["subtitle"],
     "lines_html": "".join(sized_lines(content["card3"]["lines"]))},
    {"type": "brand"},
]

async def render():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1080, "height": 1350}, device_scale_factor=2)
        for i, c in enumerate(CARDS, start=1):
            await page.goto(TEMPLATE)
            await page.evaluate("""([c, logo]) => {
                const card = document.getElementById('card');
                const bg = document.getElementById('bg');
                const overlay = document.getElementById('overlay');
                const content = document.getElementById('content');
                const area = document.getElementById('body-area');

                if (c.type === 'hook') {
                    bg.style.backgroundImage = `url(${c.bg})`;
                    area.innerHTML = `<div class="hook-title">${c.title_html}</div><div class="hook-sub">${c.sub}</div>`;
                } else if (c.type === 'analysis') {
                    bg.style.backgroundImage = `url(${c.bg})`;
                    area.innerHTML = `<div class="ana-wrap"><div class="ana-subtitle">${c.subtitle.replace(/\\n/g,'<br>')}</div><div class="ana-body">${c.lines_html}</div></div>`;
                } else if (c.type === 'insight') {
                    bg.style.backgroundImage = `url(${c.bg})`;
                    area.innerHTML = `<div class="ins-wrap"><div class="ins-title">${c.title.replace(/\\n/g,'<br>')}</div><div class="ins-body">${c.lines_html}</div></div>`;
                } else if (c.type === 'brand') {
                    bg.style.display = 'none';
                    overlay.style.display = 'none';
                    content.style.display = 'none';
                    const img = document.createElement('img');
                    img.className = 'brand-logo-full';
                    img.src = logo;
                    card.appendChild(img);
                }
            }""", [c, LOGO])
            await page.wait_for_timeout(800)
            await page.evaluate("document.fonts.ready")
            await page.wait_for_timeout(800)
            out = OUTPUT / f"card{i}.png"
            await page.screenshot(path=str(out))
            print(f"saved: {out}")
        await browser.close()

asyncio.run(render())
print("done!")
