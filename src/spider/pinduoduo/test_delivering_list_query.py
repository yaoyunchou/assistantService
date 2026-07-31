"""
待发货列表脚本单元测试：虚拟滚动漏单复现与修复校验。

模拟 2026-07-15 共 50 单、视口仅挂载约 12 行；注入真实
`pdd-erp-order-delivering-list-query.js`，断言滚动去重后收齐 50 条。

运行（推荐，仓库根目录）：
  set PYTHONPATH=src
  python -m unittest spider.pinduoduo.test_delivering_list_query -v

或直接：
  python src/spider/pinduoduo/test_delivering_list_query.py
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

# 必须在导入 spider 包之前把 src 加入 path（避免 spider.__init__ 找不到 utils）
_HERE = Path(__file__).resolve().parent
_SRC = _HERE.parent.parent  # .../src
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from playwright.sync_api import sync_playwright

_SCRIPT = _HERE / 'scripts' / 'pdd-erp-order-delivering-list-query.js'
_FIXTURE = _HERE / 'scripts' / 'fixtures' / 'delivering-virtual-list.html'
_TOTAL = 50

_EVAL = """
async (args) => {
  delete window.__PDD_ERP_DELIVERING_LIST_AUTO_SCROLL;
  delete window.__PDD_ERP_DELIVERING_LIST_SCROLL_MAX_STEPS;
  delete window.__PDD_ERP_DELIVERING_LIST_SCROLL_PAUSE_MS;
  delete window.__PDD_ERP_DELIVERING_LIST_RESTORE_SCROLL;
  delete window.__PDD_ERP_DELIVERING_LIST_MIN_WAIT_MS;
  delete window.__PDD_ERP_DELIVERING_LIST_MAX_WAIT_MS;
  if (args.autoScroll !== undefined) {
    window.__PDD_ERP_DELIVERING_LIST_AUTO_SCROLL = args.autoScroll;
  }
  if (args.scrollMaxSteps != null) {
    window.__PDD_ERP_DELIVERING_LIST_SCROLL_MAX_STEPS = Number(args.scrollMaxSteps);
  }
  if (args.scrollPauseMs != null) {
    window.__PDD_ERP_DELIVERING_LIST_SCROLL_PAUSE_MS = Number(args.scrollPauseMs);
  }
  if (args.minWaitMs != null) {
    window.__PDD_ERP_DELIVERING_LIST_MIN_WAIT_MS = Number(args.minWaitMs);
  }
  if (args.maxWaitMs != null) {
    window.__PDD_ERP_DELIVERING_LIST_MAX_WAIT_MS = Number(args.maxWaitMs);
  }
  const source = args.source;
  const run = new Function('return ' + source);
  return await run();
}
"""


def _load_script_source(path: Path) -> str:
    raw = path.read_text(encoding='utf-8').lstrip('\ufeff')
    raw = re.sub(r'^/\*[\s\S]*?\*/\s*', '', raw, count=1)
    return raw.strip()


class DeliveringListQueryScrollTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.script_source = _load_script_source(_SCRIPT)
        cls.fixture_url = _FIXTURE.resolve().as_uri()

    def _run_script(self, *, auto_scroll: bool) -> dict:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.goto(self.fixture_url, wait_until='domcontentloaded')
                page.wait_for_selector('tr[data-testid="beast-core-table-body-tr"]', timeout=5000)
                visible = page.evaluate('() => window.__FIXTURE_VISIBLE')
                total = page.evaluate('() => window.__FIXTURE_TOTAL')
                self.assertEqual(total, _TOTAL)
                self.assertLess(visible, _TOTAL, 'fixture 必须模拟虚拟列表（可见 < 总数）')

                raw = page.evaluate(
                    _EVAL,
                    {
                        'source': self.script_source,
                        'autoScroll': auto_scroll,
                        'scrollPauseMs': 40,
                        'scrollMaxSteps': 80,
                        'minWaitMs': 0,
                        'maxWaitMs': 800,
                    },
                )
                self.assertIsInstance(raw, dict)
                return raw
            finally:
                browser.close()

    def test_static_mode_only_viewport_incomplete(self) -> None:
        """关闭滚动时只能拿到视口内行数，必然 < 50。"""
        raw = self._run_script(auto_scroll=False)
        self.assertTrue(raw.get('ok'))
        rows = raw.get('rows') or []
        self.assertLess(
            len(rows),
            _TOTAL,
            f'静态模式不应收齐全部，实际={len(rows)} log={raw.get("log")}',
        )
        self.assertGreaterEqual(len(rows), 1)

    def test_scroll_mode_collects_all_50(self) -> None:
        """开启滚动去重后应收齐 50 单（模拟 2026-07-15）。"""
        raw = self._run_script(auto_scroll=True)
        self.assertTrue(raw.get('ok'), raw.get('log'))
        rows = raw.get('rows') or []
        order_nos = [r.get('orderNo') for r in rows if isinstance(r, dict)]
        self.assertEqual(
            len(rows),
            _TOTAL,
            f'期望 50 条，实际 {len(rows)}；scroll={raw.get("scroll")} log={raw.get("log")}',
        )
        self.assertEqual(len(set(order_nos)), _TOTAL, 'orderNo 应全部唯一')
        sample = rows[0]
        self.assertTrue(str(sample.get('orderNo', '')).startswith('260715'))
        goods = sample.get('goods') or []
        self.assertGreaterEqual(len(goods), 1)
        self.assertIn('测试商品', goods[0].get('title') or '')


if __name__ == '__main__':
    unittest.main(verbosity=2)
