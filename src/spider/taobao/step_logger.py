"""步骤日志与失败截图。"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from playwright.sync_api import Page

from spider.taobao.config import LOG_ROOT


class StepLogger:
    def __init__(self, slug: str):
        day = datetime.now().strftime('%Y-%m-%d')
        self.dir = LOG_ROOT / day / slug
        self.dir.mkdir(parents=True, exist_ok=True)
        self.jsonl_path = self.dir / 'step.jsonl'

    def log(self, step: str, **payload: Any) -> None:
        record = {
            'step': step,
            'ts': datetime.now().isoformat(timespec='seconds'),
            **payload,
        }
        with self.jsonl_path.open('a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

    def screenshot(self, page: Page, name: str) -> Path:
        path = self.dir / f'{name}.png'
        try:
            page.screenshot(path=str(path), full_page=True)
        except Exception:
            pass
        return path

    def save_audit(self, audit: Dict[str, Any]) -> None:
        (self.dir / 'audit.json').write_text(
            json.dumps(audit, ensure_ascii=False, indent=2),
            encoding='utf-8',
        )
