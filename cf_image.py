"""
클라우드플레어 Workers AI로 이미지 생성 (무료 플랜: 하루 10,000 Neurons, 넘으면 과금 없이 오류).

용도: Pexels가 사진을 못 줄 때(장애·한도·검색 결과 없음)의 대체 배경. 1,145장면 중 실패는 0건이라
평소엔 쓰이지 않는다 — 기본 사진(계산기) 한 장으로 때우던 자리를 장면에 맞는 이미지로 채우는 보험이다.
2026-10-19 무료 모델 9개 비교에서 flux-2-klein-9b가 한국 아파트·김밥·돈 장면 모두 가장 자연스러웠고
가짜 글자가 없었다(2.4초/장).
필요한 시크릿: CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID (없으면 조용히 건너뜀)
사용: python cf_image.py "프롬프트(영어)" out.jpg [모델]   /   python cf_image.py list
"""
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request

MODEL = os.getenv("CF_IMAGE_MODEL", "@cf/black-forest-labs/flux-2-klein-9b")


def _post(url, token, payload, multipart=False):
    if multipart:
        boundary = "----glend" + str(int(time.time() * 1000))
        parts = []
        for k, v in payload.items():
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n')
        body = ("".join(parts) + f"--{boundary}--\r\n").encode()
        ctype = f"multipart/form-data; boundary={boundary}"
    else:
        body, ctype = json.dumps(payload).encode(), "application/json"
    req = urllib.request.Request(url, data=body,
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": ctype})
    with urllib.request.urlopen(req, timeout=180) as r:
        return r.read(), r.headers.get("Content-Type", "")


def _creds():
    acct = os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
    token = os.getenv("CLOUDFLARE_API_TOKEN", "").strip()
    if not acct or not token:
        raise RuntimeError("CLOUDFLARE_ACCOUNT_ID / CLOUDFLARE_API_TOKEN 없음")
    return acct, token


def generate(prompt, model=MODEL, width=None, height=None, steps=None):
    """이미지 바이트를 돌려준다. 모델마다 입력·출력 형식이 달라 둘 다 처리한다."""
    acct, token = _creds()
    url = f"https://api.cloudflare.com/client/v4/accounts/{acct}/ai/run/{model}"
    payload = {"prompt": prompt}
    if width:
        payload.update(width=width, height=height)
    if steps:
        payload["steps"] = steps
    try:
        body, ctype = _post(url, token, payload)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        if "multipart" in detail.lower():           # flux-2 계열은 form-data 입력
            try:
                body, ctype = _post(url, token, payload, multipart=True)
            except urllib.error.HTTPError as e2:
                raise RuntimeError(f"HTTP {e2.code}: {e2.read().decode('utf-8', 'replace')[:300]}") from None
        else:
            raise RuntimeError(f"HTTP {e.code}: {detail}") from None
    if "json" in ctype:
        data = json.loads(body)
        if not data.get("success", True):
            raise RuntimeError(f"실패: {data.get('errors')}")
        res = data.get("result", data)
        return base64.b64decode(res["image"])
    return body   # 일부 모델은 이미지 바이트(PNG)를 바로 돌려준다


def ai_photo(query, out_path):
    """Pexels 대체용 배경 이미지. 성공하면 렌더러가 읽을 file:// 주소, 실패하면 None(예외 없음)."""
    if not (os.getenv("CLOUDFLARE_ACCOUNT_ID") and os.getenv("CLOUDFLARE_API_TOKEN")):
        return None
    prompt = (f"Photorealistic photo of {query}. Natural light, realistic, vertical composition, "
              "no text, no letters, no logos, no watermark")
    for size in ((768, 1024), (None, None)):        # 세로 먼저, 안 되면 모델 기본 크기
        try:
            img = generate(prompt, width=size[0], height=size[1])
            os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
            with open(out_path, "wb") as f:
                f.write(img)
            return "file://" + os.path.abspath(out_path)
        except Exception as e:
            last = e
    print(f"  (AI 이미지 실패: {str(last)[:120]})", flush=True)
    return None


def list_models():
    acct, token = _creds()
    url = f"https://api.cloudflare.com/client/v4/accounts/{acct}/ai/models/search?task=Text-to-Image&per_page=50"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return [m["name"] for m in json.loads(r.read()).get("result", [])]


if __name__ == "__main__":
    if sys.argv[1] == "list":
        print("\n".join(list_models()))
        sys.exit(0)
    prompt, out = sys.argv[1], sys.argv[2]
    model = sys.argv[3] if len(sys.argv) > 3 else MODEL
    t = time.time()
    img = generate(prompt, model=model)
    open(out, "wb").write(img)
    print(f"[cf_image] OK {model} — {len(img)//1024}KB, {time.time() - t:.1f}초 → {out}")
