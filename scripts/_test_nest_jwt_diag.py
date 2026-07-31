#!/usr/bin/env python3
"""JWT 联调诊断（不打印 token）。"""
from __future__ import annotations

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


def main() -> int:
    _load_dotenv()
    jwt = (os.getenv('NEST_JWT') or '').strip()
    print('NEST_JWT length:', len(jwt))
    if jwt:
        print('NEST_JWT looks like JWT:', jwt.count('.') >= 2)

    from integrations.nest_client import resolve_nest_api_base, nest_ai_chat, invalidate_nest_token

    invalidate_nest_token()
    base = resolve_nest_api_base()
    print('API base:', base)

    if not jwt:
        print('NEST_JWT 为空')
        return 2

    # 1) 纯文本
    try:
        text = nest_ai_chat(user_text='只回复两个字：成功', system_prompt='', timeout=90)
        print('--- text chat OK ---')
        print(text[:500])
    except Exception as e:
        print('text chat FAIL:', e)

    # 2) 带图
    img = ROOT / 'antexiadan' / 'captcha' / '_crop2.png'
    if img.is_file():
        try:
            from spider.antexiadan.captcha_solver import _parse_distance

            text = nest_ai_chat(
                user_text='滑块拼图：只回复 JSON {"distancePx": 整数}',
                system_prompt='只输出 JSON',
                image_bytes=img.read_bytes(),
                timeout=120,
            )
            print('--- image chat OK ---')
            print(text[:500])
            print('distancePx:', _parse_distance(text))
        except Exception as e:
            print('image chat FAIL:', e)

    # 3) health
    try:
        with urllib.request.urlopen(f'{base.replace("/api/v1", "")}/health'.replace('/xcx/xcx', '/xcx'), timeout=15) as r:
            print('health', r.status)
    except Exception:
        try:
            with urllib.request.urlopen('https://nestapi.xfysj.top/xcx/api/v1/health', timeout=15) as r:
                print('health', r.status, r.read()[:80])
        except Exception as e:
            print('health skip:', e)

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
