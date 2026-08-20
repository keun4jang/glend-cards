"""
발행 텍스트 영구 보관.

왜 필요한가:
  media 브랜치는 부모 없는 단일 커밋을 강제 푸시한다(저장소 비대화 방지 — 실제로
  47일 만에 446MB가 쌓인 적이 있어 도입한 구조다). 그 대가로 어제 만든 대본이
  오늘 사라진다. 실제로 게시물 374개의 대본·캡션이 하나도 남지 않았다.

  영상·이미지는 무거우니 media 브랜치에 그대로 두고, **텍스트만** main에 쌓는다.
  게시물당 2~4KB라 374개를 다 모아도 1MB 남짓 — 비대화 문제가 없다.

  이 텍스트가 검색 자산(정적 사이트) 발행의 원료이자, "어떤 주제·각도가 먹혔는지"를
  나중에 성과와 대조할 유일한 재료다.
"""
import datetime
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).parent
ARCHIVE_DIR = BASE / "archive"
KST = datetime.timezone(datetime.timedelta(hours=9))


def slugify(text, maxlen=40):
    """한글 주제를 파일명으로 — 한글은 살리고 경로에 위험한 문자만 제거"""
    t = re.sub(r"<[^>]+>", "", text or "").strip()
    t = re.sub(r"[^\w\s가-힣-]", "", t)
    t = re.sub(r"\s+", "-", t)
    return t[:maxlen].strip("-") or "untitled"


def _sh(args, check=False):
    r = subprocess.run(args, capture_output=True, text=True)
    if check and r.returncode != 0:
        print(f"[archive 오류] {' '.join(args)}\n{r.stdout}{r.stderr}", flush=True)
    return r


def save(kind, index, content, extra=None):
    """kind: 'card' | 'reel'. content: 생성된 콘텐츠 dict. 파일 경로 반환(실패 시 None)."""
    try:
        now = datetime.datetime.now(KST)
        topic = content.get("topic", "")
        rec = {
            "kind": kind,
            "index": str(index),
            "published_kst": now.isoformat(timespec="seconds"),
            "topic": topic,
            "content": content,
        }
        if extra:
            rec.update(extra)

        d = ARCHIVE_DIR / f"{now:%Y-%m}"
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"{now:%Y-%m-%d}-{kind}{index}-{slugify(topic)}.json"
        path.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[archive] 저장: {path.relative_to(BASE)}", flush=True)
        return path
    except Exception as e:                      # 아카이브 실패로 발행을 막지 않는다
        print(f"[archive] 저장 실패(무시하고 계속): {e}", flush=True)
        return None


def commit_push(message):
    """main 브랜치에 아카이브만 커밋·푸시. 다른 잡과 동시에 돌 수 있어 rebase 재시도."""
    if not ARCHIVE_DIR.exists():
        return True
    if os.getenv("GITHUB_ACTIONS"):
        _sh(["git", "config", "user.name", "github-actions"])
        _sh(["git", "config", "user.email", "actions@github.com"])

    _sh(["git", "add", "archive"])
    staged = _sh(["git", "diff", "--cached", "--name-only", "--", "archive"]).stdout.strip()
    if not staged:
        print("[archive] 새로 추가된 항목 없음", flush=True)
        return True

    if _sh(["git", "commit", "-m", message]).returncode != 0:
        print("[archive] 커밋할 변경 없음", flush=True)
        return True

    branch = os.getenv("GITHUB_REF_NAME", "main")
    for attempt in range(1, 5):
        if _sh(["git", "push", "origin", f"HEAD:{branch}"]).returncode == 0:
            print("[archive] 푸시 완료", flush=True)
            return True
        # 같은 시각에 다른 잡이 밀어넣었을 수 있다 → 리베이스 후 재시도
        print(f"[archive] 푸시 충돌/실패, 리베이스 후 재시도 {attempt}/4", flush=True)
        _sh(["git", "fetch", "origin", branch])
        if _sh(["git", "rebase", f"origin/{branch}"]).returncode != 0:
            _sh(["git", "rebase", "--abort"])
        time.sleep(2 ** attempt)
    print("[archive] 푸시 최종 실패 — 아카이브는 로컬에만 남음(발행에는 영향 없음)", flush=True)
    return False


if __name__ == "__main__":
    # 수동 실행: python archive.py <card|reel> <index>
    kind = sys.argv[1] if len(sys.argv) > 1 else "card"
    idx = sys.argv[2] if len(sys.argv) > 2 else "1"
    fn = f"content_{idx}.json" if kind == "card" else f"reel_content_{idx}.json"
    data = json.loads(Path(BASE / fn).read_text(encoding="utf-8"))
    save(kind, idx, data)
    commit_push(f"archive: {kind}{idx} {datetime.datetime.now(KST):%Y-%m-%d}")
