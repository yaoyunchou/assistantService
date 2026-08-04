#!/usr/bin/env python3
"""生成与 nest_client / captcha_solver 一致的 /ai/chat JSON 体（供 curl --data-binary @file）。"""
from __future__ import annotations

import base64
import json
import os
import sys
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


def main() -> int:
    _load_dotenv()
    from spider.antexiadan.captcha_solver import _CAPTCHA_SYSTEM_JSON, _captcha_user_prompt

    img_path = ROOT / 'antexiadan' / 'captcha' / 'captcha_1785491027_1.png'
    if len(sys.argv) > 1:
        img_path = Path(sys.argv[1])
    if not img_path.is_file():
        print(f'图片不存在: {img_path}', file=sys.stderr)
        return 2

    attempt = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    image_bytes = img_path.read_bytes()
    b64 = base64.b64encode(image_bytes).decode('ascii')
    body = {
        'systemPrompt': _CAPTCHA_SYSTEM_JSON,
        'message': [
            {'type': 'text', 'text': _captcha_user_prompt(attempt)},
            {
                'type': 'image_url',
                'image_url': {
                    'url': f'data:image/png;base64,{b64}',
                    'detail': 'high',
                },
            },
        ],
    }
    out = ROOT / 'nest_ai_chat_body.json'
    raw = json.dumps(body, ensure_ascii=False)
    out.write_text(raw, encoding='utf-8')
    print(f'已写入: {out} ({len(raw)} 字符)')
    print()
    print('--- 1) 登录（把 device_key 换成 .env 里的 NEST_DEVICE_KEY）---')
    print(
        'curl -s -X POST "http://localhost:8080/api/v1/auth/login-with-device-key" '
        '-H "Content-Type: application/json" '
        '-d "{\\"device_key\\":\\"keyId.secret\\"}"'
    )
    print()
    print('--- 2) 多模态 /ai/chat（把 YOUR_ACCESS_TOKEN 换成上一步返回的 token）---')
    print(
        'curl -s -X POST "http://localhost:8080/api/v1/ai/chat" '
        '-H "Content-Type: application/json; charset=utf-8" '
        '-H "Authorization: Bearer YOUR_ACCESS_TOKEN" '
        f'--data-binary "@{out.name}"'
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
