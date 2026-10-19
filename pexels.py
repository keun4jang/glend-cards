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


# 목록에 없는 은행·가게도 많다(10/19 실측: RHB·BBVA·Caixa Bank가 그대로 통과). 그래서 모양으로도 거른다.
# 은행 건물 외관·입구는 거의 항상 간판이 보인다.
_BANKFRONT = re.compile(r"\bbank(?:'s)? (?:branch|building|facade|entrance|exterior|headquarters|office|tower|sign)|"
                        r"\b(?:facade|entrance|exterior|branch|headquarters|front) of (?:the |a |an )?[\w' ]{0,30}\bbank\b", re.I)
_NAMED_BANK = re.compile(r"\b[A-Z][a-z]+ (?:National |Islamic |Savings |Central )?Bank\b")   # "Caixa Bank" 등 고유명사
_ACRONYM = re.compile(r"\b[A-Z]{2,6}\b")                                                     # "RHB", "BBVA", "CIBC" 등
_ACRONYM_OK = {"ATM", "TV", "LED", "PC", "ID", "QR", "ER", "ICU", "IV", "CPR", "DNA", "GPS", "SUV", "EV",
               "MRI", "CT", "AI", "OK", "UV", "USB", "PDF", "DIY", "BBQ", "SOS", "KTX", "KRW"}


def blocked(photo, query=""):
    """걸린 단어(없으면 빈 문자열). 검색어에 있는 일반 단어는 봐준다 — "warning sign street"는 표지판을 찾는 것이다."""
    allowed = {w.lower() for w in re.findall(r"[A-Za-z]+", query or "")}
    hit = _blocked(photo)
    if hit and all(w.lower() in allowed or w.lower().rstrip("s") in allowed for w in re.findall(r"[A-Za-z]+", hit)):
        return ""
    return hit


def _blocked(photo):
    alt = photo.get("alt") or ""
    text = " ".join([alt, photo.get("url") or ""]).replace("-", " ")
    for rx in (_BLOCK, _BANKFRONT):
        m = rx.search(text)
        if m:
            return m.group(0)
    m = _NAMED_BANK.search(alt)
    if m:
        return m.group(0)
    for m in _ACRONYM.finditer(alt):
        if m.group(0) not in _ACRONYM_OK:
            return m.group(0)
    return ""


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
            why = blocked(p, query)
            if why:
                print(f"    - 후보 {i + 1} 건너뜀('{why}'): {(p.get('alt') or '')[:60]}")
                continue
            return p["src"]["large2x"]
        if photos:
            print(f"  (사진 후보 {len(photos)}장이 모두 간판·로고·외국 화폐: {query})")
    except Exception as e:
        print("  (사진 검색 실패:", query, "->", e, ")")
    return None
