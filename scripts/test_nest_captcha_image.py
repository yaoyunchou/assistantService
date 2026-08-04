#!/usr/bin/env python3
"""用本地验证码 PNG 测试 Nest /ai/chat（不打印 token）。"""
from __future__ import annotations

import os
import re
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
    from integrations.nest_client import nest_ai_chat, nest_auth_configured
    from spider.antexiadan.captcha_solver import (
        _CAPTCHA_SYSTEM_JSON,
        _captcha_user_prompt,
        _parse_distance,
    )

    if not nest_auth_configured():
        print('未配置 Nest 鉴权：请在 .env 设置 NEST_DEVICE_KEY 或 NEST_USERNAME/NEST_PASSWORD 或 NEST_JWT')
        return 2

    img = ROOT / 'antexiadan' / 'captcha' / '_crop2.png'
    if len(sys.argv) > 1:
        img = Path(sys.argv[1])
    if not img.is_file():
        print(f'图片不存在: {img}')
        return 2

    print(f'图片: {img} ({img.stat().st_size} bytes)')
    try:
        from PIL import Image
        with Image.open(img) as im:
            print(f'尺寸: {im.size[0]}x{im.size[1]}')
    except Exception:
        pass
    attempt = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    prompt = _captcha_user_prompt(attempt)
    system = _CAPTCHA_SYSTEM_JSON
    print(f'prompt 字符数: {len(prompt)}, system 字符数: {len(system)}')
    from config import Config
    nest_model = (getattr(Config, 'NEST_CHAT_MODEL', '') or '').strip()
    from integrations.nest_client import resolve_nest_api_base
    print(f'Nest API: {resolve_nest_api_base()}')
    print(f'NEST_CHAT_MODEL: {nest_model or "(未设置)"}')
    mm_to = int(getattr(Config, 'NEST_CHAT_TIMEOUT_MULTIMODAL', 300) or 300)
    print(f'多模态超时: max(传入, NEST_CHAT_TIMEOUT_MULTIMODAL) = {mm_to}s（本地 Agent 常需 3~5 分钟，请勿 Ctrl+C）')

    try:
        text = nest_ai_chat(
            user_text=prompt,
            system_prompt=system,
            image_bytes=img.read_bytes(),
            image_mime='image/png',
        )
    except Exception as e:
        print(f'调用失败: {e}')
        return 1

    print('--- Nest 原始回复 ---')
    print(text[:2000])
    dist = _parse_distance(text)
    print('--- 解析 distancePx ---')
    print(dist)
    for key in ('pieceCenterX', 'gapCenterX'):
        m = re.search(rf'"{key}"\s*:\s*(\d+)', text or '')
        if m:
            print(f'{key}:', m.group(1))
    return 0 if dist else 1


if __name__ == '__main__':
    raise SystemExit(main())
