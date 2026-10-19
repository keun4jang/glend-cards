"""
Pexels 배경 사진 검색 — 카드(generate.py)·릴스(generate_reel.py) 공용.

간판·로고 거르기 (2026-10-19 추가):
  10/19 카드 2장(한국 금융권 전자금융사고)에 외국 은행 HSBC 간판이 크게 나왔다.
  검색어가 "bank building exterior"처럼 일반적이면 해외 은행·가게 간판 사진이 1순위로 온다.
  사진 속 글자를 직접 볼 수는 없으니, Pexels가 주는 사진 설명(alt)에 브랜드·간판 단어가 있으면
  건너뛰고 다음 후보를 쓴다. 후보가 전부 걸리면 None — 호출한 쪽이 대체 이미지로 넘어간다.
"""
import os
import re

import requests

CANDIDATES = 10

# 사진 설명(alt)에 이런 말이 있으면 쓰지 않는다 — 간판·로고·외국 브랜드·외국 돈
_BLOCK = re.compile(
    r"\b(logo|logos|sign|signs|signage|signboard|storefront|shopfront|billboard|brand|branding|emblem|"
    r"trademark|neon sign|banner|hsbc|citi|citibank|chase|barclays|santander|wells fargo|"
    r"bank of america|jpmorgan|ubs|deutsche|bnp|ing bank|commerzbank|lloyds|natwest|"
    r"visa|mastercard|american express|amex|paypal|western union|starbucks|mcdonald'?s|"
    r"coca[- ]cola|pepsi|apple store|amazon|walmart|ikea|nike|adidas|"
    r"dollars?|euros?|pounds? sterling|us currency|yuan|rupees?)\b", re.I)


def blocked(photo):
    text = " ".join([photo.get("alt") or "", photo.get("url") or ""]).replace("-", " ")
    m = _BLOCK.search(text)
    return m.group(0) if m else ""


def get_photo(query):
    """세로 사진 URL(large2x). 실패하거나 후보가 전부 걸리면 None."""
    try:
        res = requests.get(
            "https://api.pexels.com/v1/search",
            headers={"Authorization": os.getenv("PEXELS_API_KEY", "").strip()},
            params={"query": query, "per_page": CANDIDATES, "orientation": "portrait"},
            timeout=30,
        )
        if res.status_code != 200:
            print(f"  (사진 검색 실패: {query} -> HTTP {res.status_code})")
            return None
        photos = res.json().get("photos", [])
        for i, p in enumerate(photos):
            why = blocked(p)
            if why:
                print(f"    - 후보 {i + 1} 건너뜀('{why}'): {(p.get('alt') or '')[:60]}")
                continue
            return p["src"]["large2x"]
        if photos:
            print(f"  (사진 후보 {len(photos)}장이 모두 간판·로고·외국 화폐: {query})")
    except Exception as e:
        print("  (사진 검색 실패:", query, "->", e, ")")
    return None
