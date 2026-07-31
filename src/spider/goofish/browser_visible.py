"""闲鱼操作前确保浏览器窗口可见，并跳转到闲鱼后台。

BrowserPool 只有一个长驻 page，与拼多多/淘宝共用，因此每次都必须显式 goto，
不能假设页面还停留在上次的位置。
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from playwright.sync_api import Page

from spider.goofish.config import NAV_TIMEOUT_MS, PUBLISH_URL
from spider.goofish.page_guard import (
    check_login_via_mtop,
    ensure_browser_window_default,
    focus_browser_page,
    is_login_url,
    list_frames,
)
from utils.logger import get_logger

logger = get_logger('GoofishBrowserVisible')


def prepare_goofish_browser(
    pool,
    *,
    open_url: Optional[str] = None,
    timeout: float = 60.0,
) -> Dict[str, Any]:
    """切到可见窗口并打开闲鱼后台。"""
    if pool is None:
        return {'ok': False, 'error': '浏览器池未初始化'}

    target_url = open_url or PUBLISH_URL
    vis = pool.ensure_visible(timeout=min(timeout, 20.0))

    def _open(page: Page):
        page.goto(target_url, wait_until='domcontentloaded', timeout=NAV_TIMEOUT_MS)
        page.wait_for_timeout(2500)
        ensure_browser_window_default(page)
        focus_browser_page(page)

        probe = check_login_via_mtop(page)
        logged_in = bool(probe.get('logged_in'))
        current = page.url or ''
        logger.info('闲鱼后台已打开: %s logged_in=%s', current, logged_in)

        return {
            'ok': True,
            'message': (
                '已进入闲鱼卖家后台，可以开始操作'
                if logged_in
                else '已打开闲鱼卖家后台，请在 Chromium 窗口完成登录'
            ),
            'url': current,
            'target_url': target_url,
            'logged_in': logged_in,
            'login_page': is_login_url(current),
            'frames': list_frames(page),
            'hint': '请在如意助手弹出的 Chromium 窗口登录（不是你日常用的 Chrome）',
        }

    nav = pool.execute(_open, timeout=timeout)
    return {
        **vis,
        **nav,
        'was_headless': vis.get('was_headless'),
        'restarted': vis.get('restarted'),
    }
