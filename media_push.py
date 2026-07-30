"""
산출물(output/)을 'media' 브랜치에 단일 커밋 스냅샷으로 강제 푸시.
- main 히스토리에 이미지/영상이 쌓이지 않아 저장소 비대화 방지 (media는 항상 커밋 1개)
- 작업 트리를 건드리지 않음 (임시 인덱스 사용) → 이후 파이프라인 단계에 영향 없음
- 기존 media 브랜치 내용을 읽어와 덮어쓰기(overlay)하므로 다른 잡의 산출물 보존
"""
import os
import sys
import glob
import time
import datetime
import subprocess

MEDIA_BRANCH = "media"
IDX_FILE = "/tmp/media.index"


def _sh(args, env=None, check=True):
    r = subprocess.run(args, env=env, capture_output=True, text=True)
    if check and r.returncode != 0:
        print(f"[media_push 오류] {' '.join(args)}\n{r.stdout}{r.stderr}", flush=True)
        sys.exit(1)
    return r.stdout.strip()


def push_media():
    env = dict(os.environ)
    env["GIT_INDEX_FILE"] = IDX_FILE
    if os.path.exists(IDX_FILE):
        os.remove(IDX_FILE)

    subprocess.run(["git", "fetch", "origin", MEDIA_BRANCH], capture_output=True)
    has_media = subprocess.run(
        ["git", "rev-parse", "--verify", f"origin/{MEDIA_BRANCH}"],
        capture_output=True).returncode == 0

    # 기존 media 트리 위에 이번 산출물을 얹음 (다른 잡의 파일 보존)
    if has_media:
        _sh(["git", "read-tree", f"origin/{MEDIA_BRANCH}"], env=env)

    # 최종 산출물만 (중간 파일 scene/clip/narr 등 제외)
    artifacts = sorted(glob.glob("output/post*/card*.png") + glob.glob("output/reel*/reel.mp4")
                       + glob.glob("content_*.json") + glob.glob("reel_content_*.json"))
    if not artifacts:
        print("[media_push] 추가할 산출물이 없음 — 건너뜀", flush=True)
        return True
    _sh(["git", "add", "-f", "--"] + artifacts, env=env)

    tree = _sh(["git", "write-tree"], env=env)
    now = datetime.datetime.now(datetime.timezone.utc)
    commit = _sh(["git", "commit-tree", tree, "-m", f"media snapshot {now:%Y-%m-%d %H:%M} UTC"], env=env)

    # 부모 없는 단일 커밋을 강제 푸시 → 히스토리 누적 없음. 네트워크 오류 대비 재시도.
    for attempt in range(1, 4):
        r = subprocess.run(["git", "push", "-f", "origin", f"{commit}:refs/heads/{MEDIA_BRANCH}"])
        if r.returncode == 0:
            print(f"media 브랜치 스냅샷 푸시 완료 ({commit[:10]})", flush=True)
            return True
        print(f"  media 푸시 실패, 재시도 {attempt}/3...", flush=True)
        time.sleep(5 * attempt)
    print("[중단] media 브랜치 푸시 최종 실패.", flush=True)
    sys.exit(1)


if __name__ == "__main__":
    push_media()
