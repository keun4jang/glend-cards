"""
디자인 미리보기 — 발행된 릴스·카드를 지금 템플릿으로 다시 렌더해 한 장짜리 시트로 모은다.
아트디렉터(.claude/agents/art-director.md)가 디자인을 바꾸기 전·후를 비교할 때 쓴다. 게시는 하지 않는다.

  python design_preview.py                 # 최근 릴스 2편 + 카드 1편
  python design_preview.py --reels 3 --cards 0
  python design_preview.py --photos DIR    # 사진을 DIR의 jpg로 바꿔 렌더(Pexels가 막힌 샌드박스용)

결과: output/preview/reel_<날짜>.png, card_<날짜>.png (가로 6칸, 칸당 360×640 / 카드는 432×540)
로컬에서 크롬이 따로 깔려 있으면 CHROMIUM_PATH=/경로/chrome 을 함께 준다(render*.py가 읽는다).
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from PIL import Image

BASE = Path(__file__).parent
OUT = BASE / "output" / "preview"
SLOT = "97"   # 미리보기 전용 인덱스 — 실제 발행 인덱스(1~3)와 겹치지 않게


def latest(kind, n):
    files = sorted(glob.glob(str(BASE / "archive" / "*" / f"*-{kind}[0-9]-*.json")))
    return files[-n:] if n else []


def swap_photos(content, photos):
    """배경 주소를 로컬 사진으로 바꾼다(순서대로 돌려 쓴다)."""
    k = 0
    def nxt():
        nonlocal k
        k += 1
        return Path(photos[(k - 1) % len(photos)]).resolve().as_uri()
    for sc in content.get("scenes", []):
        if sc.get("bg"):
            sc["bg"] = nxt()
    for n in range(1, 5):
        c = content.get(f"card{n}") or {}
        if c.get("bg"):
            c["bg"] = nxt()


def sheet(frames, w, h, out):
    cols = 6
    rows = (len(frames) + cols - 1) // cols
    im = Image.new("RGB", (cols * w, rows * h), "white")
    for i, f in enumerate(frames):
        im.paste(f.resize((w, h)), ((i % cols) * w, (i // cols) * h))
    im.save(out)
    print(f"  -> {out.relative_to(BASE)}")


def reel_frames(d):
    frames = [Image.open(d / "cover.png").convert("RGB")]
    nums = sorted({int(m.group(1)) for f in d.glob("scene*.png") if (m := re.match(r"scene(\d+)_", f.name))})
    for i in nums:
        full = d / f"scene{i}_full.png"
        if full.exists():
            frames.append(Image.open(full).convert("RGB"))
            continue
        bg = Image.open(d / f"scene{i}_bg.png").convert("RGBA")
        fg = Image.open(d / f"scene{i}_fg.png").convert("RGBA")
        frames.append(Image.alpha_composite(bg, fg).convert("RGB"))
    return frames


def run(script, content_name, content, photos):
    if photos:
        swap_photos(content, photos)
    (BASE / content_name).write_text(json.dumps(content, ensure_ascii=False), encoding="utf-8")
    try:
        r = subprocess.run([sys.executable, script, SLOT], cwd=BASE, capture_output=True, text=True, timeout=600)
    finally:
        (BASE / content_name).unlink(missing_ok=True)
    over = [ln for ln in r.stdout.splitlines() if "넘침" in ln]
    for ln in over:
        print("  ", ln)
    if r.returncode != 0:
        print(r.stdout[-1500:], r.stderr[-1500:])
        raise SystemExit(f"{script} 실패")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reels", type=int, default=2)
    ap.add_argument("--cards", type=int, default=1)
    ap.add_argument("--photos", help="배경으로 쓸 jpg 폴더(선택)")
    a = ap.parse_args()
    photos = sorted(glob.glob(os.path.join(a.photos, "*.jpg"))) if a.photos else []
    OUT.mkdir(parents=True, exist_ok=True)

    for f in latest("reel", a.reels):
        name = Path(f).name[:16]
        print(f"[릴스] {Path(f).name}")
        run("render_reel.py", f"reel_content_{SLOT}.json", json.load(open(f, encoding="utf-8"))["content"], photos)
        sheet(reel_frames(BASE / "output" / f"reel{SLOT}"), 360, 640, OUT / f"reel_{name}.png")

    for f in latest("card", a.cards):
        name = Path(f).name[:16]
        print(f"[카드] {Path(f).name}")
        run("render.py", f"content_{SLOT}.json", json.load(open(f, encoding="utf-8"))["content"], photos)
        d = BASE / "output" / f"post{SLOT}"
        frames = [Image.open(d / f"card{i}.png").convert("RGB") for i in range(1, 6) if (d / f"card{i}.png").exists()]
        sheet(frames, 432, 540, OUT / f"card_{name}.png")


if __name__ == "__main__":
    main()
