#!/usr/bin/env python3
"""已弃用：请用 test_nest_chat_local.py（HTTP 直调）或 test_nest_captcha_image.py（与线上一致）。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    print(
        'scripts/_run_nest_local_smoke.py 已弃用。\n'
        '  纯文本 + 多模态对照: python scripts/test_nest_chat_local.py [--image]\n'
        '  滑块同款 prompt:       python scripts/test_nest_captcha_image.py <png>\n',
        file=sys.stderr,
    )
    captcha = ROOT / 'antexiadan' / 'captcha' / 'captcha_1785491027_1.png'
    cmd = [sys.executable, str(ROOT / 'scripts' / 'test_nest_chat_local.py')]
    if captcha.is_file():
        cmd.append('--image')
        cmd.append(str(captcha))
    return subprocess.call(cmd, cwd=str(ROOT))


if __name__ == '__main__':
    raise SystemExit(main())
