"""淘宝操作前确保浏览器窗口可见，并跳转到淘宝页面。"""
from __future__ import annotations

from typing import Any, Dict, Optional

from playwright.sync_api import Page

from spider.taobao.config import CATEGORY_URL, LOGIN_URL
from spider.taobao.page_guard import (
    ensure_browser_window_default,
    focus_browser_page,
    is_category_page,
    is_category_upload_ready,
    is_login_page,
)
from utils.logger import get_logger

logger = get_logger('TaobaoBrowserVisible')


def prepare_taobao_browser(
    pool,
    *,
    open_url: Optional[str] = None,
    timeout: float = 60.0,
) -> Dict[str, Any]:
    if pool is None:
        return {'ok': False, 'error': '浏览器池未初始化'}

    target_url = open_url or CATEGORY_URL
    vis = pool.ensure_visible(timeout=min(timeout, 20.0))

    def _open_taobao(page: Page):
        page.goto(target_url, wait_until='domcontentloaded', timeout=60_000)
        page.wait_for_timeout(2000)
        ensure_browser_window_default(page)
        focus_browser_page(page)
        current = page.url or ''
        ready = is_category_upload_ready(page)
        logged_in = ready or (is_category_page(current) and not is_login_page(current))
        logger.info('淘宝浏览器已打开: %s ready=%s', current, ready)
        return {
            'ok': True,
            'message': (
                '已进入以图发品页，可以开始上架'
                if ready
                else '已打开淘宝上传入口，请在 Chromium 窗口完成卖家登录'
            ),
            'url': current,
            'target_url': target_url,
            'logged_in': ready,
            'upload_ready': ready,
            'hint': '请在如意助手弹出的 Chromium 窗口登录（不是你日常用的 Chrome）',
        }

    nav = pool.execute(_open_taobao, timeout=timeout)
    return {**vis, **nav, 'was_headless': vis.get('was_headless'), 'restarted': vis.get('restarted')}


def prepare_visible_browser(pool, *, timeout: float = 30.0) -> Dict[str, Any]:
    return prepare_taobao_browser(pool, open_url=CATEGORY_URL, timeout=timeout)


def open_url_visible(pool, url: str, *, timeout: float = 60.0) -> Dict[str, Any]:
    return prepare_taobao_browser(pool, open_url=url, timeout=timeout)
