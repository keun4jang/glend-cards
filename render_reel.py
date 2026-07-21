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


def strip_notes(text):
    return re.sub(r'\s*\(\s*\d+\s*자\s*\)\s*$', '', (text or "").strip())


async def render():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1080, "height": 1920}, device_scale_factor=1)
        for i, scene in enumerate(content["scenes"], start=1):
            is_outro = bool(scene.get("outro"))

            if is_outro:
                # 검정 배경 + 로고만
                await page.goto(TEMPLATE)
                await page.evaluate("""(logo) => {
                    document.getElementById('bg').style.display = 'none';
                    document.getElementById('overlay').style.display = 'none';
                    document.getElementById('brand-top').style.display = 'none';
                    document.getElementById('subtitle-wrap').style.display = 'none';
                    const o = document.getElementById('outro');
                    o.style.display = 'flex';
                    document.getElementById('outro-logo').src = logo;
                }""", LOGO)
                await page.wait_for_timeout(500)
                out = OUTPUT / f"scene{i}_full.png"
                await page.screenshot(path=str(out))
                print(f"saved: {out} (아웃트로)")
                continue

            bg_url = scene.get("bg", FALLBACK)
            subtitle = strip_notes(scene.get("narration", ""))

            # 1) 배경(사진만) — 불투명
            await page.goto(TEMPLATE)
            await page.evaluate("""(bg) => {
                document.getElementById('overlay').style.display = 'none';
                document.getElementById('brand-top').style.display = 'none';
                document.getElementById('subtitle-wrap').style.display = 'none';
                document.getElementById('bg').style.backgroundImage = `url(${bg})`;
            }""", bg_url)
            await page.wait_for_timeout(600)
            bg_png = OUTPUT / f"scene{i}_bg.png"
            await page.screenshot(path=str(bg_png))

            # 2) 전경(그라데이션 + 로고 + 자막) — 투명 배경
            await page.goto(TEMPLATE)
            await page.evaluate("""([logo, sub]) => {
                document.getElementById('bg').style.display = 'none';
                document.getElementById('brand-logo').src = logo;
                document.getElementById('subtitle').innerHTML = `<span class="txt">${sub}</span>`;
            }""", [LOGO, subtitle])
            await page.wait_for_timeout(500)
            await page.evaluate("document.fonts.ready")
            await page.wait_for_timeout(300)
            fg_png = OUTPUT / f"scene{i}_fg.png"
            await page.screenshot(path=str(fg_png), omit_background=True)

            print(f"saved: scene{i}_bg.png + scene{i}_fg.png")
        await browser.close()


asyncio.run(render())
print("done!")
