"""Nest client helpers."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from integrations.nest_client import extract_chat_text, resolve_nest_api_base  # noqa: E402


def test_extract_chat_text_from_data_content():
    text = extract_chat_text({'code': 200, 'data': {'content': '{"distancePx": 150}'}})
    assert '150' in text


def test_resolve_nest_api_base_default():
    base = resolve_nest_api_base()
    assert base.endswith('/xcx/api/v1')


if __name__ == '__main__':
    test_extract_chat_text_from_data_content()
    test_resolve_nest_api_base_default()
    print('ok')
