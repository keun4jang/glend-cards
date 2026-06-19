import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright

BASE = Path(__file__).parent
TEMPLATE = (BASE / "templates" / "card.html").resolve().as_uri()
LOGO = (BASE / "assets" / "logo.png").resolve().as_uri()
OUTPUT = BASE / "output"
OUTPUT.mkdir(exist_ok=True)

# Gemini + Pexels가 만든 내용 불러오기
with open("content.json", "r", encoding="utf-8") as f:
    content = json.load(f)

# 기본 배경 (혹시 bg가 없을 때만 사용하는 비상용)
FALLBACK = "https://images.pexels.com/photos/210607/pexels-photo-210607.jpeg"

CARDS = [
    {"type": "hook", "bg": content["card1"].get("bg", FALLBACK),
     "title": content["card1"]["title"], "sub": content["card1"]["sub"]},
    {"type": "analysis", "bg": content["card2"].get("bg", FALLBACK),
     "subtitle": content["card2"]["subtitle"], "lines": content["card2"]["lines"]},
    {"type": "insight", "bg": content["card3"].get("bg", FALLBACK),
     "title": content["card3"]["subtitle"], "lines": content["card3"]["lines"]},
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
                    area.innerHTML = `<div class="hook-title">${c.title.replace(/\\n/g,'<br>')}</div><div class="hook-sub">${c.sub}</div>`;
                } else if (c.type === 'analysis') {
                    bg.style.backgroundImage = `url(${c.bg})`;
                    const lines = c.lines.map(l => `<span class="line">${l}</span>`).join('');
                    area.innerHTML = `<div class="ana-wrap"><div class="ana-subtitle">${c.subtitle.replace(/\\n/g,'<br>')}</div><div class="ana-body">${lines}</div></div>`;
                } else if (c.type === 'insight') {
                    bg.style.backgroundImage = `url(${c.bg})`;
                    const lines = c.lines.map(l => `<span class="line">${l}</span>`).join('');
                    area.innerHTML = `<div class="ins-wrap"><div class="ins-title">${c.title.replace(/\\n/g,'<br>')}</div><div class="ins-body">${lines}</div></div>`;
                } else if (c.type === 'brand') {
                    bg.style.display = 'none';
                    overlay.style.display = 'none';
                    content.style.display = 'none';
                    const img = document.createElement('img');
                    img.className = 'brand-logo-full';
                    img.src = logo;
                    card.appendChild(img);
                    const cta = document.createElement('div');
                    cta.style.cssText = 'position:absolute;bottom:100px;left:0;right:0;z-index:10;text-align:center;font-family:Noto Sans KR,sans-serif;';
                    cta.innerHTML = '<div style="font-size:52px;font-weight:900;color:#CFFF04;letter-spacing:-1px;">매일 아침 경제 뉴스 카드</div><div style="margin-top:20px;font-size:44px;font-weight:700;color:#ffffff;">📌 팔로우하고 받아보세요</div>';
                    card.appendChild(cta);
                }

                // 가로폭 넘치는 줄 자동 축소 (안전장치)
                const maxW = 880;
                document.querySelectorAll('.line').forEach(el => {
                    el.style.display = 'block';
                    el.style.whiteSpace = 'nowrap';
                    let size = parseFloat(getComputedStyle(el).fontSize);
                    let guard = 0;
                    while (el.scrollWidth > maxW && size > 32 && guard < 60) {
                        size -= 1; el.style.fontSize = size + 'px'; guard++;
                    }
                    // 그래도 넘치면 강제 클립
                    if (el.scrollWidth > maxW) {
                        el.style.overflow = 'hidden';
                        el.style.maxWidth = maxW + 'px';
                    }
                });
            }""", [c, LOGO])
            await page.wait_for_timeout(800)
            await page.evaluate("document.fonts.ready")
            await page.wait_for_timeout(800)
            out = OUTPUT / f"card{i}.png"
            await page.screenshot(path=str(out))
            print(f"saved: {out}")
        await browser.close()

asyncio.run(render())
print("done! 🎉 뉴스 -> Gemini -> Pexels 배경까지 전부 자동으로 카드 완성!")

