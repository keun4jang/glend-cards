import asyncio
import json
import re
import sys
from pathlib import Path
from playwright.async_api import async_playwright

BASE = Path(__file__).parent
TEMPLATE = (BASE / "templates" / "reel.html").resolve().as_uri()
LOGO = (BASE / "assets" / "logo.png").resolve().as_uri()

POST_INDEX = sys.argv[1] if len(sys.argv) > 1 else "1"
OUTPUT = BASE / "output" / f"reel{POST_INDEX}"
OUTPUT.mkdir(parents=True, exist_ok=True)

with open(f"reel_content_{POST_INDEX}.json", "r", encoding="utf-8") as f:
    content = json.load(f)

FALLBACK = "https://images.pexels.com/photos/210607/pexels-photo-210607.jpeg"

HOOK_BASE_FONT, HOOK_MAX_CHARS = 150, 7   # 후킹 제목
TEXT_BASE_FONT, TEXT_MAX_CHARS = 92, 13   # 일반 장면 문구


def strip_notes(text):
    """혹시 남은 '(16자)' 류 메모 제거"""
    return re.sub(r'\s*\(\s*\d+\s*자\s*\)\s*$', '', (text or "").strip())


def char_count(line):
    return len(re.sub(r'<[^>]+>', '', line))


def sized(text, base, maxc, minsize):
    """줄바꿈으로 나눠 각 줄에 글자수 비례 폰트 적용(자동 줄바꿈 방지)"""
    spans = []
    for line in strip_notes(text).split("\n"):
        n = char_count(line)
        size = base if n <= maxc else max(minsize, int(base * maxc / n))
        spans.append(f'<span class="line" style="font-size:{size}px">{line}</span>')
    return "".join(spans)


def build_scene(i, scene):
    n = len(content["scenes"])
    if i == 1:
        kind = "hook"
    elif i == n:
        kind = "outro"
    else:
        kind = "text"
    return {
        "kind": kind,
        "bg": scene.get("bg", FALLBACK),
        "text_html": sized(scene["text"], HOOK_BASE_FONT if kind == "hook" else TEXT_BASE_FONT,
                           HOOK_MAX_CHARS if kind == "hook" else TEXT_MAX_CHARS,
                           70 if kind == "hook" else 48),
    }


SCENES = [build_scene(i, s) for i, s in enumerate(content["scenes"], start=1)]


async def render():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1080, "height": 1920}, device_scale_factor=1)
        for i, sc in enumerate(SCENES, start=1):
            await page.goto(TEMPLATE)
            await page.evaluate("""([sc, logo]) => {
                const bg = document.getElementById('bg');
                const overlay = document.getElementById('overlay');
                const brandTop = document.getElementById('brand-top');
                const area = document.getElementById('body-area');
                const content = document.getElementById('content');
                document.getElementById('brand-logo').src = logo;
                bg.style.backgroundImage = `url(${sc.bg})`;

                if (sc.kind === 'hook') {
                    area.innerHTML = `<div class="hook-title">${sc.text_html}</div>`;
                } else if (sc.kind === 'outro') {
                    brandTop.style.display = 'none';
                    content.style.display = 'none';
                    const wrap = document.createElement('div');
                    wrap.className = 'brand-outro';
                    wrap.innerHTML = `<img src="${logo}"><div class="cta">${sc.text_html}</div>`;
                    document.getElementById('card').appendChild(wrap);
                } else {
                    area.innerHTML = `<div class="scene-text">${sc.text_html}</div>`;
                }
            }""", [sc, LOGO])
            await page.wait_for_timeout(700)
            await page.evaluate("document.fonts.ready")
            await page.wait_for_timeout(500)
            out = OUTPUT / f"scene{i}.png"
            await page.screenshot(path=str(out))
            print(f"saved: {out}")
        await browser.close()


asyncio.run(render())
print("done!")
