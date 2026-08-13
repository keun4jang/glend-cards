"""
인스타그램 장기 토큰 자동 갱신 (60일 만료를 무한 연장).

동작:
  1) 현재 IG_TOKEN을 graph.instagram.com/refresh_access_token 으로 갱신 (새 토큰 = 갱신일로부터 60일)
  2) 새 토큰을 GitHub Actions Secret(IG_TOKEN)에 자동 저장 (libsodium 암호화)

전제:
  - GH_PAT: fine-grained PAT, 이 저장소의 "Secrets: Read and write" 권한, 만료 없음 권장
  - 갱신 조건(공식): 토큰이 24시간 이상 지났고 && 아직 만료되지 않았을 것
  - 만료된 토큰은 갱신 불가 → 수동 재인증 필요 (그 경우 크게 실패시켜 알림)

주의: Instagram Login(graph.instagram.com) 경로 전용.
"""
import base64
import os
import sys

import requests

IG_REFRESH_URL = "https://graph.instagram.com/refresh_access_token"
GH_API = "https://api.github.com"

TOKEN = os.getenv("IG_TOKEN", "").strip()
PAT = os.getenv("GH_PAT", "").strip()
REPO = os.getenv("GITHUB_REPOSITORY", "keun4jang/glend-cards").strip()
SECRET_NAME = os.getenv("IG_TOKEN_SECRET_NAME", "IG_TOKEN").strip()
DRY_RUN = os.getenv("DRY_RUN", "false").strip().lower() == "true"


def fail(msg):
    print(f"[실패] {msg}", flush=True)
    sys.exit(1)


if not TOKEN:
    fail("IG_TOKEN이 비어 있습니다.")

# 1) 토큰 갱신
print("인스타 토큰 갱신 요청 중...", flush=True)
r = requests.get(IG_REFRESH_URL,
                 params={"grant_type": "ig_refresh_token", "access_token": TOKEN},
                 timeout=60)
data = {}
try:
    data = r.json()
except Exception:
    pass

if "access_token" not in data:
    err = (data.get("error") or {})
    msg = err.get("message", r.text[:300])
    print(f"  응답: {msg}", flush=True)
    if "expired" in msg.lower() or err.get("code") == 190:
        fail("토큰이 이미 만료되어 자동 갱신이 불가능합니다. "
             "수동으로 새 장기 토큰을 발급해 IG_TOKEN 시크릿을 교체해야 합니다.")
    if "24 hours" in msg or "hours old" in msg:
        print("  아직 24시간이 안 된 토큰이라 갱신을 건너뜁니다(정상).", flush=True)
        sys.exit(0)
    fail(f"토큰 갱신 실패: {msg}")

new_token = data["access_token"]
expires_in = int(data.get("expires_in", 0))
print(f"  갱신 성공 — 앞으로 약 {expires_in // 86400}일 유효", flush=True)

if new_token == TOKEN:
    print("  (반환된 토큰이 기존과 동일 — 시크릿 갱신 생략)", flush=True)
    sys.exit(0)

if DRY_RUN:
    print("[드라이런] 시크릿 저장은 건너뜁니다.", flush=True)
    sys.exit(0)

if not PAT:
    fail("GH_PAT이 없어 새 토큰을 시크릿에 저장할 수 없습니다. "
         "(fine-grained PAT + 이 저장소 Secrets 읽기/쓰기 권한 필요)")

# 2) GitHub Secret 업데이트 (공개키로 libsodium 암호화)
try:
    from nacl import encoding, public
except ImportError:
    fail("PyNaCl 미설치 — 워크플로우에서 'pip install pynacl requests' 필요")

hdrs = {"Authorization": f"Bearer {PAT}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"}

pk = requests.get(f"{GH_API}/repos/{REPO}/actions/secrets/public-key", headers=hdrs, timeout=30)
if pk.status_code != 200:
    fail(f"공개키 조회 실패({pk.status_code}): {pk.text[:200]} "
         "— PAT 권한(Secrets: Read and write)을 확인하세요.")
pkj = pk.json()

sealed = public.SealedBox(public.PublicKey(pkj["key"].encode(), encoding.Base64Encoder))
encrypted = base64.b64encode(sealed.encrypt(new_token.encode())).decode()

put = requests.put(f"{GH_API}/repos/{REPO}/actions/secrets/{SECRET_NAME}",
                   headers=hdrs,
                   json={"encrypted_value": encrypted, "key_id": pkj["key_id"]},
                   timeout=30)
if put.status_code not in (201, 204):
    fail(f"시크릿 저장 실패({put.status_code}): {put.text[:200]}")

print(f"✅ {SECRET_NAME} 시크릿 갱신 완료 — 다음 만료까지 약 {expires_in // 86400}일", flush=True)

# 3) GH_PAT 만료 감시 — 이 PAT가 죽으면 자동 갱신 사슬 전체가 끊긴다.
#    GitHub은 만료가 설정된 PAT에 한해 응답 헤더로 만료일을 알려준다.
pat_exp = pk.headers.get("github-authentication-token-expiration", "").strip()
if not pat_exp:
    print("[PAT] 만료 없음(무기한) — 사람 개입이 필요한 지점이 없습니다.", flush=True)
else:
    import datetime as _dt
    try:
        # 예: "2026-12-31 07:00:00 +0000" 또는 ISO 형식
        txt = pat_exp.replace(" UTC", "").strip()
        try:
            exp_dt = _dt.datetime.strptime(txt, "%Y-%m-%d %H:%M:%S %z")
        except ValueError:
            exp_dt = _dt.datetime.fromisoformat(txt)
        if exp_dt.tzinfo is None:
            exp_dt = exp_dt.replace(tzinfo=_dt.timezone.utc)
        left = (exp_dt - _dt.datetime.now(_dt.timezone.utc)).days
        print(f"[PAT] 만료까지 {left}일 ({pat_exp})", flush=True)
        if left <= 21:
            fail(f"GH_PAT이 {left}일 뒤 만료됩니다. 만료되면 토큰 자동 갱신이 멈춥니다. "
                 "GitHub > Settings > Developer settings에서 PAT를 '만료 없음'으로 재발급해 "
                 "GH_PAT 시크릿을 교체하세요.")
    except Exception as e:  # 파싱 실패는 치명적이지 않음
        print(f"[PAT] 만료일 파싱 실패({e}): {pat_exp}", flush=True)
