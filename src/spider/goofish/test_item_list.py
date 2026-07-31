"""闲鱼商品列表解析测试（离线，不依赖登录）。

覆盖两条取数路径的解析逻辑：
  1. mtop 响应 → item_list.extract_items_from_payload（纯 Python，无浏览器）
  2. DOM 兜底脚本 goofish-item-list.js（用本地 fixture HTML 跑真实脚本）

运行（仓库根目录）：
  set PYTHONPATH=src
  python -m unittest spider.goofish.test_item_list -v

或直接：
  python src/spider/goofish/test_item_list.py
"""
from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

# 必须在导入 spider 包之前把 src 加入 path
_HERE = Path(__file__).resolve().parent
_SRC = _HERE.parent.parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from spider.goofish.item_list import extract_items_from_payload  # noqa: E402

_FIXTURE_DIR = _HERE / 'scripts' / 'fixtures'
_MTOP_FIXTURE = _FIXTURE_DIR / 'item-list-mtop.json'
_HTML_FIXTURE = _FIXTURE_DIR / 'item-list.html'
_DOM_SCRIPT = _HERE / 'scripts' / 'goofish-item-list.js'

_EVAL_DOM = """
async (args) => {
  window.__GOOFISH_ITEM_LIST_MAX_SCROLL = 1;
  window.__GOOFISH_ITEM_LIST_SCROLL_PAUSE = 10;
  const run = new Function('return ' + args.source);
  return await run();
}
"""


class MtopParsingTest(unittest.TestCase):
    """mtop 响应解析：字段命名不统一时仍能正确归一化。"""

    @classmethod
    def setUpClass(cls):
        payload = json.loads(_MTOP_FIXTURE.read_text(encoding='utf-8'))
        cls.items = extract_items_from_payload(payload)
        cls.by_id = {item['itemId']: item for item in cls.items}

    def test_finds_all_items(self):
        self.assertEqual(len(self.items), 3, f'应解析出 3 个商品，实际 {len(self.items)}')

    def test_maps_alternate_id_keys(self):
        """itemId / id / auctionId 三种主键命名都要认。"""
        self.assertEqual(
            set(self.by_id.keys()),
            {'801000000001', '801000000002', '801000000003'},
        )

    def test_maps_alternate_title_keys(self):
        """title / itemTitle / subject 都要认。"""
        self.assertEqual(self.by_id['801000000001']['title'], '全新未拆封 机械键盘 87键')
        self.assertEqual(self.by_id['801000000002']['title'], '二手 显示器 27寸 2K')
        self.assertEqual(self.by_id['801000000003']['title'], '闲置 平板电脑 保护套')

    def test_maps_alternate_price_keys(self):
        """price / soldPrice / currentPrice 都要认，且不做分转元猜测。"""
        self.assertEqual(self.by_id['801000000001']['price'], 299.0)
        self.assertEqual(self.by_id['801000000002']['price'], 1088.50)
        self.assertEqual(self.by_id['801000000003']['price'], 45.0)

    def test_normalizes_status(self):
        """英文与中文状态都要归一到 online/offline/sold。"""
        self.assertEqual(self.by_id['801000000001']['status'], 'online')
        self.assertEqual(self.by_id['801000000002']['status'], 'offline')
        self.assertEqual(self.by_id['801000000003']['status'], 'sold')

    def test_completes_protocol_relative_urls(self):
        """//img.alicdn.com/... 要补成 https://。"""
        self.assertTrue(self.by_id['801000000001']['coverUrl'].startswith('https://'))
        self.assertTrue(self.by_id['801000000003']['coverUrl'].startswith('https://'))

    def test_builds_item_url_when_absent(self):
        for item in self.items:
            self.assertIn(item['itemId'], item['itemUrl'])

    def test_ignores_non_item_arrays(self):
        """响应里的无关数组（如 ret）不应被当成商品列表。"""
        noise = {'ret': ['SUCCESS'], 'data': {'tabs': [{'name': '在售'}, {'name': '已下架'}]}}
        self.assertEqual(extract_items_from_payload(noise), [])


class DomFallbackTest(unittest.TestCase):
    """DOM 兜底脚本：不依赖带构建哈希的 class 也能抓到商品。"""

    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise unittest.SkipTest(f'playwright 未安装: {exc}')

        source = _DOM_SCRIPT.read_text(encoding='utf-8').lstrip('\ufeff')
        source = re.sub(r'^/\*[\s\S]*?\*/\s*', '', source, count=1).strip()

        # 复用应用的驱动查找逻辑（项目 playwright_drivers 优先），
        # 避免依赖 `playwright install` 才有的 headless-shell
        from utils.browser_path import find_chrome_executable
        chrome = find_chrome_executable()

        cls._pw = sync_playwright().start()
        launch_kwargs = {'headless': True}
        if chrome:
            launch_kwargs['executable_path'] = chrome
        try:
            cls._browser = cls._pw.chromium.launch(**launch_kwargs)
        except Exception as exc:
            cls._pw.stop()
            raise unittest.SkipTest(f'无法启动 Chromium（请先 playwright install chromium）: {exc}')
        page = cls._browser.new_page()
        page.goto(_HTML_FIXTURE.as_uri())
        cls.result = page.evaluate(_EVAL_DOM, {'source': source})
        cls.items = cls.result.get('items') or []
        cls.by_id = {item['itemId']: item for item in cls.items}

    @classmethod
    def tearDownClass(cls):
        for closer in (getattr(cls, '_browser', None), getattr(cls, '_pw', None)):
            try:
                closer.close() if hasattr(closer, 'close') else closer.stop()
            except Exception:
                pass

    def test_script_succeeds(self):
        self.assertTrue(self.result.get('success'), f"脚本未成功: {self.result.get('log')}")

    def test_finds_only_real_items(self):
        """帮助中心 / 店铺主页等干扰链接不能算商品。"""
        self.assertEqual(len(self.items), 3, f'应抓到 3 个商品，实际 {len(self.items)}: {self.by_id.keys()}')

    def test_parses_price_and_status(self):
        self.assertEqual(self.by_id['801000000001']['price'], 299)
        self.assertEqual(self.by_id['801000000001']['status'], 'online')
        self.assertEqual(self.by_id['801000000002']['status'], 'offline')
        self.assertEqual(self.by_id['801000000003']['status'], 'sold')

    def test_parses_title_and_cover(self):
        self.assertEqual(self.by_id['801000000001']['title'], '全新未拆封 机械键盘 87键')
        self.assertIn('cover-a.jpg', self.by_id['801000000001']['coverUrl'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
