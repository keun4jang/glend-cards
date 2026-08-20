"""
IndexNow — 검색엔진에 새 URL을 직접 통보 (계정·로그인 불필요).

왜 이걸 쓰나:
  서치콘솔/서치어드바이저는 계정 소유자만 등록할 수 있다. 반면 IndexNow는
  사이트에 키 파일 하나만 올려두면 누구의 로그인도 없이 URL을 알릴 수 있다.
  Bing·Yandex·**네이버**가 지원한다(네이버는 2023-07부터). 구글은 미지원이라
  구글은 robots.txt의 사이트맵 선언과 서치콘솔에 의존해야 한다.

동작:
  1) 키 파일(<key>.txt)이 사이트 루트에 공개돼 있어야 소유권이 인정된다
     -> build_site.py가 docs/에 생성한다
  2) api.indexnow.org 에 URL 목록을 POST
  3) 프로젝트 페이지(/glend-cards/)라 keyLocation을 명시해야 한다

비용: 0원. 호출 제한도 사실상 없다(하루 1만 URL 수준).
"""
import json
import os
import sys
import urllib.parse
from pathlib import Path

import requests

BASE = Path(__file__).parent
KEY_FILE = BASE / "indexnow_key.txt"
SITE = "https://keun4jang.github.io/glend-cards"
ENDPOINT = "https://api.indexnow.org/indexnow"


def get_key():
    """키는 비밀이 아니다 — 사이트에 공개로 올라가야 소유권 증명이 된다."""
    if KEY_FILE.exists():
        k = KEY_FILE.read_text(encoding="utf-8").strip()
        if k:
            return k
    import secrets
    k = secrets.token_hex(16)          # 32자 16진수 (규격: 8~128자)
    KEY_FILE.write_text(k, encoding="utf-8")
    print(f"[indexnow] 새 키 생성: {k}")
    return k


def urls_from_sitemap():
    p = BASE / "docs" / "sitemap.xml"
    if not p.exists():
        return []
    import re
    return re.findall(r"<loc>([^<]+)</loc>", p.read_text(encoding="utf-8"))


def submit(urls=None, dry_run=False):
    key = get_key()
    urls = urls or urls_from_sitemap()
    if not urls:
        print("[indexnow] 보낼 URL이 없습니다.")
        return True

    payload = {
        "host": urllib.parse.urlparse(SITE).netloc,
        "key": key,
        "keyLocation": f"{SITE}/{key}.txt",
        "urlList": urls,
    }
    print(f"[indexnow] {len(urls)}개 URL 통보 (key {key[:8]}...)")
    for u in urls[:5]:
        print("   ", urllib.parse.unquote(u))
    if len(urls) > 5:
        print(f"    ... 외 {len(urls)-5}개")
    if dry_run:
        print("[indexnow] 드라이런 — 전송하지 않음")
        return True

    try:
        r = requests.post(ENDPOINT, json=payload, timeout=40,
                          headers={"Content-Type": "application/json; charset=utf-8"})
    except Exception as e:
        print(f"[indexnow] 전송 실패(무시하고 계속): {e}")
        return False

    # 200/202 = 접수됨. 4xx는 키 파일 미배포·URL 불일치 등 — 원인을 그대로 남긴다.
    ok = r.status_code in (200, 202)
    print(f"[indexnow] 응답 {r.status_code} {'(접수됨)' if ok else ''} {r.text[:200]}")
    if r.status_code == 403:
        print(f"[indexnow] 키 파일이 공개돼 있는지 확인: {SITE}/{key}.txt")
    return ok


if __name__ == "__main__":
    submit(dry_run="--dry-run" in sys.argv)
