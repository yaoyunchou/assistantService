#!/usr/bin/env python3
"""仅测本地 Nest POST /api/v1/ai/chat（先登录，再纯文本 chat）。"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def _http_json(url: str, *, method: str = "GET", body: dict | None = None, headers: dict | None = None, timeout: int = 90):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    print(f">> {method} {url} (body={len(data) if data else 0} bytes, timeout={timeout}s)")
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
            **(headers or {}),
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
        print(f"<< HTTP {resp.status} ({len(raw)} bytes)")
        return resp.status, json.loads(raw) if raw else {}


def _token_from_login(resp: dict) -> str:
    for key in ("access_token", "accessToken", "token"):
        if resp.get(key):
            return str(resp[key])
    data = resp.get("data")
    if isinstance(data, dict):
        for key in ("access_token", "accessToken", "token"):
            if data.get(key):
                return str(data[key])
    raise RuntimeError(f"登录响应无 token: {resp}")


def _chat_text(data: dict) -> str:
    if isinstance(data, str):
        return data
    inner = data.get("data")
    if isinstance(inner, dict):
        for key in ("message", "content", "reply", "text", "answer"):
            v = inner.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()
    for key in ("content", "message", "reply", "text", "answer"):
        v = data.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    if isinstance(inner, dict):
        return _chat_text(inner)
    if inner is not None and not isinstance(inner, (dict, list)):
        return str(inner)
    return json.dumps(data, ensure_ascii=False)[:2000]


def main() -> int:
    _load_dotenv()
    base = (os.getenv("NEST_API_BASE") or "http://localhost:8080/api/v1").strip().rstrip("/")
    device_key = (os.getenv("NEST_DEVICE_KEY") or "").strip()
    if not device_key:
        print("缺少 NEST_DEVICE_KEY", file=sys.stderr)
        return 2

    print("NEST_API_BASE:", base)

    try:
        _, login_resp = _http_json(
            f"{base}/auth/login-with-device-key",
            method="POST",
            body={"device_key": device_key},
            timeout=30,
        )
    except urllib.error.HTTPError as e:
        print("登录失败:", e.code, e.read().decode()[:500])
        return 1

    token = _token_from_login(login_resp)
    print("token length:", len(token))

    headers = {"Authorization": f"Bearer {token}"}

    # 1) 纯文本 chat
    try:
        _, chat_resp = _http_json(
            f"{base}/ai/chat",
            method="POST",
            body={"message": "只回复一行 JSON：{\"ping\":1}", "systemPrompt": "只输出 JSON"},
            headers=headers,
            timeout=90,
        )
        print("--- /ai/chat 纯文本 原始 JSON ---")
        print(json.dumps(chat_resp, ensure_ascii=False)[:2500])
        print("--- 提取文本 ---")
        print(_chat_text(chat_resp))
    except Exception as e:
        print("纯文本 chat 失败:", e)
        return 1

    # 2) 可选：多模态（第二个参数 --image）
    if len(sys.argv) > 1 and sys.argv[1] == "--image":
        import base64

        img = ROOT / "antexiadan" / "captcha" / "captcha_1785491027_1.png"
        if len(sys.argv) > 2:
            img = Path(sys.argv[2])
        b64 = base64.b64encode(img.read_bytes()).decode("ascii")
        body = {
            "systemPrompt": "只输出一行 JSON",
            "message": [
                {"type": "text", "text": "描述图中滑块拼图，回复 {\"distancePx\": 整数}"},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{b64}", "detail": "high"},
                },
            ],
        }
        try:
            _, img_resp = _http_json(
                f"{base}/ai/chat",
                method="POST",
                body=body,
                headers=headers,
                timeout=300,
            )
            print("--- /ai/chat 多模态 原始 JSON ---")
            print(json.dumps(img_resp, ensure_ascii=False)[:2500])
            print("--- 提取文本 ---")
            print(_chat_text(img_resp))
        except Exception as e:
            print("多模态 chat 失败:", e)
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
