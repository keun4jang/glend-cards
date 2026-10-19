"""
클라우드플레어 Workers AI로 이미지 생성 (무료 플랜: 하루 10,000 Neurons, 넘으면 과금 없이 오류).

아직 파이프라인에 연결하지 않았다 — 무료로 실제 생성되는지 먼저 시험하는 단계.
필요한 시크릿: CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID
사용: python cf_image.py "프롬프트(영어)" out.jpg
"""
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request

MODEL = os.getenv("CF_IMAGE_MODEL", "@cf/black-forest-labs/flux-1-schnell")


def generate(prompt, steps=4):
    acct = os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
    token = os.getenv("CLOUDFLARE_API_TOKEN", "").strip()
    if not acct or not token:
        raise RuntimeError("CLOUDFLARE_ACCOUNT_ID / CLOUDFLARE_API_TOKEN 없음")
    url = f"https://api.cloudflare.com/client/v4/accounts/{acct}/ai/run/{MODEL}"
    req = urllib.request.Request(
        url, data=json.dumps({"prompt": prompt, "steps": steps}).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            body = r.read()
            ctype = r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:400]
        raise RuntimeError(f"HTTP {e.code}: {detail}") from None
    if "json" in ctype:
        data = json.loads(body)
        if not data.get("success", True):
            raise RuntimeError(f"실패: {data.get('errors')}")
        return base64.b64decode(data["result"]["image"])
    return body   # 일부 모델은 이미지 바이트를 바로 돌려준다


if __name__ == "__main__":
    prompt, out = sys.argv[1], sys.argv[2]
    t = time.time()
    img = generate(prompt)
    open(out, "wb").write(img)
    print(f"[cf_image] OK {MODEL} — {len(img)//1024}KB, {time.time() - t:.1f}초 → {out}")
