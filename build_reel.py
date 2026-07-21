"""
릴스 영상 조립기.
  reel_content_{idx}.json + output/reel{idx}/scene*.png
  -> 장면별 나레이션(TTS) 생성 + Ken Burns 줌 + 이어붙이기 + 배경음악
  -> output/reel{idx}/reel.mp4

전제: ffmpeg/ffprobe 설치돼 있음(로컬 or CI). narrate.py 사용.
"""
import os
import sys
import json
import math
import subprocess
from pathlib import Path

import narrate

BASE = Path(__file__).parent
POST_INDEX = sys.argv[1] if len(sys.argv) > 1 else "1"
OUT = BASE / "output" / f"reel{POST_INDEX}"
OUT.mkdir(parents=True, exist_ok=True)
MUSIC = BASE / "assets" / "music" / "bg.mp3"

FPS = 30
PAD_SEC = 0.6          # 나레이션 끝난 뒤 여유
MIN_SCENE_SEC = 2.2    # 장면 최소 길이

with open(f"reel_content_{POST_INDEX}.json", "r", encoding="utf-8") as f:
    content = json.load(f)
scenes = content["scenes"]


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print("[ffmpeg 오류]", " ".join(cmd))
        print(r.stderr[-1500:])
        raise SystemExit(1)
    return r


def audio_duration(path):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


clip_paths = []
for i, scene in enumerate(scenes, start=1):
    png = OUT / f"scene{i}.png"
    if not png.exists():
        print(f"[중단] {png} 없음. 먼저 render_reel.py 실행 필요.")
        raise SystemExit(1)

    # 1) 나레이션 생성
    narr = OUT / f"narr{i}.mp3"
    print(f"[scene{i}] 나레이션 생성... ({narrate.ENGINE})")
    narrate.synthesize(scene["narration"], str(narr))
    dur = max(MIN_SCENE_SEC, audio_duration(str(narr)) + PAD_SEC)
    frames = int(math.ceil(dur * FPS))

    # 2) Ken Burns 줌(느린 확대) + 나레이션 = 장면 클립
    clip = OUT / f"clip{i}.mp4"
    zoom = "min(zoom+0.0010,1.10)"
    vf = (
        "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
        f"zoompan=z='{zoom}':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"s=1080x1920:fps={FPS},setsar=1"
    )
    run([
        "ffmpeg", "-y", "-loop", "1", "-t", f"{dur:.2f}", "-i", str(png),
        "-i", str(narr),
        "-filter_complex", f"[0:v]{vf}[v]",
        "-map", "[v]", "-map", "1:a",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS),
        "-c:a", "aac", "-b:a", "128k", "-shortest", str(clip),
    ])
    clip_paths.append(clip)
    print(f"  clip{i} OK ({dur:.1f}s)")

# 3) 장면 이어붙이기
concat_list = OUT / "concat.txt"
concat_list.write_text("".join(f"file '{c.name}'\n" for c in clip_paths), encoding="utf-8")
joined = OUT / "joined.mp4"
run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
     "-c", "copy", str(joined)])

# 4) 배경음악 믹스(있으면)
final = OUT / "reel.mp4"
if MUSIC.exists():
    print("배경음악 믹스 중...")
    run([
        "ffmpeg", "-y", "-i", str(joined), "-stream_loop", "-1", "-i", str(MUSIC),
        "-filter_complex",
        "[1:a]volume=0.10[m];[0:a][m]amix=inputs=2:duration=first:dropout_transition=3[a]",
        "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
        "-shortest", str(final),
    ])
else:
    print("(assets/music/bg.mp3 없음 → 나레이션만으로 진행)")
    os.replace(joined, final)

size_mb = final.stat().st_size / 1024 / 1024
print(f"\n🎬 완성! {final} ({size_mb:.1f}MB)")
if size_mb > 95:
    print("⚠️ 100MB에 근접 — GitHub 푸시 제한 주의.")
