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

from content_io import load_content
content = load_content(f"reel_content_{POST_INDEX}.json")

FALLBACK = "https://images.pexels.com/photos/210607/pexels-photo-210607.jpeg"
# 화면 상단 고정 제목(짧게). title 없으면 topic 사용.
TITLE = (content.get("title") or content.get("topic") or "").strip()


def strip_notes(text):
    t = re.sub(r'\s*\(\s*\d+\s*자\s*\)\s*$', '', (text or "").strip())
    return t.replace("**", "").replace("__", "")


def cover_title_html(text):
    """커버 제목: 줄별로 글자 수 비례 폰트 축소 (한 줄 6자 기준 150px)"""
    spans = []
    for line in strip_notes(text).split("\n"):
        n = len(re.sub(r'<[^>]+>', '', line))
        size = 165 if n <= 7 else max(92, int(165 * 7 / n))
        spans.append(f'<span class="line" style="font-size:{size}px">{line}</span>')
    return "".join(spans)


async def render_cover(page):
    """썸네일 커버 — 카드뉴스 1장 스타일. cover 없으면 후킹 문장으로 폴백."""
    cover = content.get("cover") or {}
    c_title = cover.get("title") or TITLE
    bg = (content["scenes"][0].get("bg") if content.get("scenes") else None) or FALLBACK

    await page.goto(TEMPLATE)
    await page.evaluate("""([bg, titleHtml]) => new Promise((resolve) => {
        document.body.style.background = '#000';
        for (const id of ['overlay','brand-top','subtitle-wrap','hook','outro'])
            document.getElementById(id).style.display = 'none';
        const b = document.getElementById('bg');
        b.style.opacity = '1';
        b.style.backgroundImage = `url(${bg})`;
        const ov = document.createElement('div'); ov.className = 'cover-overlay';
        document.getElementById('card').appendChild(ov);
        const c = document.createElement('div'); c.className = 'cover';
        c.innerHTML = `<div class="cover-title">${titleHtml}</div>`;
        document.getElementById('card').appendChild(c);
        const im = new Image();
        const fin = () => resolve();
        im.onload = fin; im.onerror = fin; im.src = bg;
        setTimeout(fin, 12000);
    })""", [bg, cover_title_html(c_title)])
    await page.wait_for_timeout(500)
    await page.evaluate("document.fonts.ready")
    await page.wait_for_timeout(300)
    out = OUTPUT / "cover.png"
    await page.screenshot(path=str(out))
    print(f"saved: {out} (커버 썸네일)")


async def render():
    n = len(content["scenes"])
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1080, "height": 1920}, device_scale_factor=1)
        await render_cover(page)
        for i, scene in enumerate(content["scenes"], start=1):
            is_outro = bool(scene.get("outro"))
            is_hook = (i == 1) and not is_outro

            if is_outro:
                await page.goto(TEMPLATE)
                await page.evaluate("""(logo) => {
                    for (const id of ['bg','overlay','brand-top','subtitle-wrap','hook'])
                        document.getElementById(id).style.display = 'none';
                    const o = document.getElementById('outro');
                    o.style.display = 'flex';
                    document.getElementById('outro-logo').src = logo;
                }""", LOGO)
                await page.wait_for_timeout(500)
                out = OUTPUT / f"scene{i}_full.png"
                await page.screenshot(path=str(out))
                print(f"saved: {out} (아웃트로)")
                continue

            if is_hook:
                text = strip_notes(scene.get("narration", ""))
                await page.goto(TEMPLATE)
                await page.evaluate("""([logo, txt]) => {
                    for (const id of ['bg','overlay','subtitle-wrap','outro'])
                        document.getElementById(id).style.display = 'none';
                    document.getElementById('hook').style.display = 'flex';
                    document.getElementById('hook-text').innerHTML = txt;
                    document.getElementById('brand-logo').src = logo;
                }""", [LOGO, text])
                await page.wait_for_timeout(500)
                await page.evaluate("document.fonts.ready")
                await page.wait_for_timeout(300)
                out = OUTPUT / f"scene{i}_full.png"
                await page.screenshot(path=str(out))
                print(f"saved: {out} (후킹)")
                continue

            # 콘텐츠 장면
            bg_url = scene.get("bg", FALLBACK)
            subtitle = strip_notes(scene.get("narration", ""))

            # 1) 배경(사진 50% 불투명, 검정 위) — 사진이 완전히 로드된 뒤 캡처
            await page.goto(TEMPLATE)
            await page.evaluate("""(bg) => new Promise((resolve) => {
                document.body.style.background = '#000';
                for (const id of ['overlay','brand-top','subtitle-wrap','hook','outro'])
                    document.getElementById(id).style.display = 'none';
                const b = document.getElementById('bg');
                b.style.opacity = '0.5';
                b.style.backgroundImage = `url(${bg})`;
                const img = new Image();
                let done = false;
                const finish = () => { if (!done) { done = true; resolve(); } };
                img.onload = finish;
                img.onerror = finish;
                img.src = bg;
                setTimeout(finish, 12000);
            })""", bg_url)
            await page.wait_for_timeout(400)
            bg_png = OUTPUT / f"scene{i}_bg.png"
            await page.screenshot(path=str(bg_png))

            # 2) 전경(옅은 그라데이션 + 로고 + 자막) — 투명 배경
            await page.goto(TEMPLATE)
            await page.evaluate("""([logo, sub, title]) => {
                for (const id of ['bg','hook','outro'])
                    document.getElementById(id).style.display = 'none';
                document.getElementById('brand-logo').src = logo;
                document.getElementById('subtitle').innerHTML = sub;
                if (title) {
                    document.getElementById('reel-title').style.display = 'flex';
                    document.getElementById('reel-title-text').textContent = title;
                }
            }""", [LOGO, subtitle, TITLE])
            await page.wait_for_timeout(500)
            await page.evaluate("document.fonts.ready")
            await page.wait_for_timeout(300)
            fg_png = OUTPUT / f"scene{i}_fg.png"
            await page.screenshot(path=str(fg_png), omit_background=True)

            print(f"saved: scene{i}_bg.png + scene{i}_fg.png")
        await browser.close()


asyncio.run(render())
print("done!")
