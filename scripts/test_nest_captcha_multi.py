#!/usr/bin/env python3
"""多张验证码图对比 Nest 返回的 distancePx（不写 token）。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'src'))


def _load_dotenv() -> None:
    p = ROOT / '.env'
    if not p.is_file():
        return
    for line in p.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, _, v = line.partition('=')
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def main() -> int:
    _load_dotenv()
    from integrations.nest_client import nest_ai_chat
    from spider.antexiadan.captcha_solver import _parse_distance, _captcha_user_prompt, _CAPTCHA_SYSTEM_JSON

    cap_dir = ROOT / 'antexiadan' / 'captcha'
    files = sorted(cap_dir.glob('captcha_*.png'))[:8]
    if not files:
        print('无 captcha_*.png')
        return 1

    print(f'测试 {len(files)} 张图（同一次会话会多次调 Nest）\n')
    results = []
    for i, img in enumerate(files, 1):
        try:
            raw = nest_ai_chat(
                user_text=_captcha_user_prompt(i),
                system_prompt=_CAPTCHA_SYSTEM_JSON,
                image_bytes=img.read_bytes(),
                timeout=120,
            )
            dist = _parse_distance(raw)
            results.append(dist)
            print(f'{img.name}: distancePx={dist}  raw={raw[:120]}')
        except Exception as e:
            print(f'{img.name}: FAIL {e}')
            results.append(None)

    uniq = {r for r in results if r is not None}
    print(f'\n不同 distancePx 取值: {sorted(uniq)}')
    if len(uniq) <= 1 and None not in results:
        print('>>> 多张图得到相同数值，更像是模型在「猜默认值」而非真看图。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
