"""
콘텐츠 JSON 로더 — 로컬에 있으면 로컬, 없으면 media 브랜치에서 가져옴.
(산출물이 main이 아닌 media 브랜치에 있으므로 업로드 전용 실행에서도 캡션을 읽을 수 있게)
"""
import json
import os
import time
import requests

RAW = "https://raw.githubusercontent.com/keun4jang/glend-cards/media"
NO_CACHE = {"Cache-Control": "no-cache", "Pragma": "no-cache"}


def cache_bust(url):
    """CDN/프록시 캐시가 옛 산출물을 주지 않도록 고유 쿼리 추가"""
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}v={int(time.time())}"


def load_content(filename):
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    url = cache_bust(f"{RAW}/{filename}")
    print(f"  (로컬에 {filename} 없음 → media 브랜치에서 가져옴)")
    r = requests.get(url, headers=NO_CACHE, timeout=30)
    if r.status_code != 200:
        raise FileNotFoundError(f"{filename} 을 로컬과 media 브랜치 어디에서도 찾지 못했습니다 ({r.status_code})")
    return r.json()
