"""从参考商品页抓取化妆品备案号等字段。"""
from __future__ import annotations

import re

from playwright.sync_api import Page

from utils.logger import get_logger

logger = get_logger('TaobaoReferencePage')

_FILING_PATTERNS = (
    r'化妆品备案编号[：:\s]*([A-Z0-9\u4e00-\u9fa5/\-]+)',
    r'备案编号[：:\s]*([A-Z0-9\u4e00-\u9fa5/\-]+)',
    r'国妆[网备字]*[：:\s]*([A-Z0-9\u4e00-\u9fa5/\-]+)',
)


def fetch_filing_number(page: Page, product_url: str) -> str:
    """打开参考商品页，从页面文本或参数区提取备案号。"""
    if not product_url or 'item.taobao.com' not in product_url and 'item.tmall.com' not in product_url:
        return ''
    try:
        page.goto(product_url, wait_until='domcontentloaded', timeout=45_000)
        page.wait_for_timeout(2500)
        text = page.evaluate('() => document.body.innerText || ""') or ''
        for pat in _FILING_PATTERNS:
            m = re.search(pat, text)
            if m:
                val = m.group(1).strip()
                logger.info('抓取到备案号: %s', val)
                return val
        # 参数区兜底
        params_text = page.evaluate("""
            () => {
              const els = document.querySelectorAll('[class*="ItemParams"], [class*="params"]');
              return Array.from(els).map(e => e.innerText).join('\\n');
            }
        """) or ''
        for pat in _FILING_PATTERNS:
            m = re.search(pat, params_text)
            if m:
                return m.group(1).strip()
    except Exception as e:
        logger.warning('抓取备案号失败: %s', e)
    return ''
