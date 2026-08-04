#!/usr/bin/env python3
"""同一张图重复调用 Nest，看 distancePx 是否稳定。"""
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

    cases = [
        ('标准弹框', ROOT / 'antexiadan/captcha/captcha_1783570046_1.png'),
        ('_crop2', ROOT / 'antexiadan/captcha/_crop2.png'),
        ('edgebest', ROOT / 'antexiadan/captcha/captcha_1783570474_1_edgebest.png'),
    ]
    repeats = 5

    for label, img in cases:
        if not img.is_file():
            print(f'[跳过] {label}: 无文件')
            continue
        print(f'\n=== {label} ({img.name}) x{repeats} ===')
        vals = []
        for n in range(1, repeats + 1):
            try:
                raw = nest_ai_chat(
                    user_text=_captcha_user_prompt(n),
                    system_prompt=_CAPTCHA_SYSTEM_JSON,
                    image_bytes=img.read_bytes(),
                    timeout=120,
                )
                d = _parse_distance(raw)
                vals.append(d)
                print(f'  #{n}: distancePx={d} confidence片段={raw[raw.find("confidence"):raw.find("confidence")+24] if "confidence" in raw else raw[:60]}')
            except Exception as e:
                print(f'  #{n}: FAIL {e}')
                vals.append(None)
        ok = [v for v in vals if v is not None]
        print(f'  汇总: {ok} unique={sorted(set(ok))}')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
