"""步骤日志与失败截图。"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from playwright.sync_api import Page

from spider.goofish.config import LOG_ROOT


class StepLogger:
    def __init__(self, slug: str):
        day = datetime.now().strftime('%Y-%m-%d')
        self.dir = LOG_ROOT / day / (slug or 'unknown')
        self.dir.mkdir(parents=True, exist_ok=True)
        self.jsonl_path = self.dir / 'step.jsonl'

    def log(self, step: str, **payload: Any) -> None:
        record = {
            'step': step,
            'ts': datetime.now().isoformat(timespec='seconds'),
            **payload,
        }
        try:
            with self.jsonl_path.open('a', encoding='utf-8') as f:
                f.write(json.dumps(record, ensure_ascii=False, default=str) + '\n')
        except Exception:
            pass

    def screenshot(self, page: Page, name: str) -> Path:
        path = self.dir / f'{name}.png'
        try:
            page.screenshot(path=str(path), full_page=True)
        except Exception:
            pass
        return path

    def save_json(self, name: str, payload: Dict[str, Any]) -> Path:
        path = self.dir / f'{name}.json'
        try:
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, default=str),
                encoding='utf-8',
            )
        except Exception:
            pass
        return path
