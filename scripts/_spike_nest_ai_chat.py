#!/usr/bin/env python3
"""One-off spike: Nest POST /ai/chat multimodal (do not commit secrets)."""
from __future__ import annotations

import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'src'))


def _load_dotenv() -> None:
    env_path = ROOT / '.env'
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, _, v = line.partition('=')
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def _http_json(url: str, *, method: str = 'GET', body: dict | None = None, headers: dict | None = None, timeout: int = 90):
    data = json.dumps(body, ensure_ascii=False).encode('utf-8') if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            'Content-Type': 'application/json; charset=utf-8',
            'Accept': 'application/json',
            **(headers or {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode('utf-8', errors='replace')
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode('utf-8', errors='replace')
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {'raw': raw[:500]}
        return e.code, parsed


def main() -> int:
    _load_dotenv()
    base = os.getenv('NEST_API_BASE', 'https://nestapi.xfysj.top/xcx/api/v1').rstrip('/')
    token = (os.getenv('NEST_JWT') or '').strip()
    if not token:
        print('SKIP: no NEST_JWT / NEST_DEVICE_KEY for live spike')
        return 0

    img_path = ROOT / 'antexiadan' / 'captcha' / 'captcha_1783570834_2.png'
    if not img_path.is_file():
        print('SKIP: no sample captcha png')
        return 0

    b64 = base64.b64encode(img_path.read_bytes()).decode()
    text = (
        '这是安特登录滑块拼图截图。估算蓝色滑块向右拖动多少像素才能让拼图对齐缺口。'
        '只回复一行 JSON：{"distancePx": 整数, "confidence": 0到1}'
    )
    system = '你只输出 JSON，不要其它文字。'

    variants = [
        {
            'label': 'array_text_image_base64',
            'body': {
                'systemPrompt': system,
                'message': [
                    {'type': 'text', 'text': text},
                    {'type': 'image', 'image': b64},
                ],
            },
        },
        {
            'label': 'array_text_image_url',
            'body': {
                'systemPrompt': system,
                'message': [
                    {'type': 'text', 'text': text},
                    {'type': 'image_url', 'image_url': f'data:image/png;base64,{b64}'},
                ],
            },
        },
        {
            'label': 'array_openai_style',
            'body': {
                'systemPrompt': system,
                'message': [
                    {'type': 'text', 'text': text},
                    {
                        'type': 'image_url',
                        'image_url': {'url': f'data:image/png;base64,{b64}'},
                    },
                ],
            },
        },
    ]

    headers = {'Authorization': f'Bearer {token}'}
    url = f'{base}/ai/chat'
    for v in variants:
        status, resp = _http_json(url, method='POST', body=v['body'], headers=headers, timeout=120)
        preview = json.dumps(resp, ensure_ascii=False)[:400]
        print(f"[{v['label']}] HTTP {status} {preview}")
        if status == 200:
            print('OK variant:', v['label'])
            return 0
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
