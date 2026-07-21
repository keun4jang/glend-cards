"""
릴스 영상 조립기 (v2).
  - 콘텐츠 장면: 사진(Ken Burns 줌) 위에 고정 자막/로고 오버레이 + 나레이션
  - 아웃트로 장면: 검정 배경 + 로고(정지) + 나레이션(좋아요/팔로우), 자막 없음
  -> output/reel{idx}/reel.mp4
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
PAD_SEC = 0.5
MIN_SCENE_SEC = 2.0

with open(f"reel_content_{POST_INDEX}.json", "r", encoding="utf-8") as f:
    content = json.load(f)
scenes = content["scenes"]


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print("[ffmpeg 오류]", " ".join(cmd))
        print(r.stderr[-1800:])
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
    is_outro = bool(scene.get("outro"))

    # 나레이션 생성
    narr = OUT / f"narr{i}.mp3"
    print(f"[scene{i}] 나레이션 생성... ({narrate.ENGINE})")
    narrate.synthesize(scene["narration"], str(narr))
    dur = max(MIN_SCENE_SEC, audio_duration(str(narr)) + PAD_SEC)
    frames = int(math.ceil(dur * FPS))
    clip = OUT / f"clip{i}.mp4"

    if is_outro:
        full = OUT / f"scene{i}_full.png"
        run([
            "ffmpeg", "-y", "-loop", "1", "-t", f"{dur:.2f}", "-i", str(full),
            "-i", str(narr),
            "-filter_complex", f"[0:v]scale=1080:1920,setsar=1,fps={FPS}[v]",
            "-map", "[v]", "-map", "1:a",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS),
            "-c:a", "aac", "-b:a", "128k", "-shortest", str(clip),
        ])
    else:
        bg = OUT / f"scene{i}_bg.png"
        fg = OUT / f"scene{i}_fg.png"
        for f in (bg, fg):
            if not f.exists():
                print(f"[중단] {f} 없음. 먼저 render_reel.py 실행 필요.")
                raise SystemExit(1)
        zoom = "min(zoom+0.0010,1.10)"
        vf = (
            f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
            f"zoompan=z='{zoom}':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"s=1080x1920:fps={FPS},setsar=1[z];[z][1:v]overlay=0:0[v]"
        )
        run([
            "ffmpeg", "-y", "-loop", "1", "-t", f"{dur:.2f}", "-i", str(bg),
            "-loop", "1", "-t", f"{dur:.2f}", "-i", str(fg),
            "-i", str(narr),
            "-filter_complex", vf,
            "-map", "[v]", "-map", "2:a",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS),
            "-c:a", "aac", "-b:a", "128k", "-shortest", str(clip),
        ])

    clip_paths.append(clip)
    print(f"  clip{i} OK ({dur:.1f}s){' [아웃트로]' if is_outro else ''}")

# 장면 이어붙이기
concat_list = OUT / "concat.txt"
concat_list.write_text("".join(f"file '{c.name}'\n" for c in clip_paths), encoding="utf-8")
joined = OUT / "joined.mp4"
run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
     "-c", "copy", str(joined)])

# 배경음악(있으면)
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
    print("⚠️ 100MB 근접 — GitHub 푸시 제한 주의.")
