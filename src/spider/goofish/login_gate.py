"""闲鱼卖家工作台登录门禁。

判定优先级：mtop 探针 > URL/DOM。闲鱼是 hash 路由 SPA 且业务页在 iframe 内，
单靠 URL 或 body 文本判定不可靠（登录页主 frame 的 innerText 实测为空）。
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional

from playwright.sync_api import Page

from spider.goofish.config import (
    DEFAULT_WAIT_LOGIN_SEC,
    NAV_TIMEOUT_MS,
    PUBLISH_URL,
)
from spider.goofish.page_guard import (
    check_login_via_mtop,
    ensure_browser_window_default,
    focus_browser_page,
    has_login_dom,
    is_login_url,
)
from utils.logger import get_logger

logger = get_logger('GoofishLogin')

_LOGIN_HINT = '请在如意助手弹出的 Chromium 窗口完成闲鱼卖家登录（不是你日常用的 Chrome）'


def _goto(page: Page, url: str) -> None:
    page.goto(url, wait_until='domcontentloaded', timeout=NAV_TIMEOUT_MS)
    # SPA 需要等 JS 挂载与 lib.mtop 就绪
    page.wait_for_timeout(2500)


def _probe(page: Page) -> Dict[str, Any]:
    """等 lib.mtop 就绪后做一次登录探针。"""
    for _ in range(10):
        result = check_login_via_mtop(page)
        if result.get('conclusive'):
            return result
        page.wait_for_timeout(700)
    return check_login_via_mtop(page)


def ensure_logged_in(
    page: Page,
    *,
    target_url: Optional[str] = None,
    wait_login_timeout_sec: int = 0,
    skip_if_logged_in: bool = False,
) -> Dict[str, Any]:
    """确保已登录闲鱼卖家后台。

    Args:
        target_url: 门禁通过后停留的页面，默认发布页
        wait_login_timeout_sec: >0 时轮询等待人工扫码
        skip_if_logged_in: 已登录则不再跳转（省一次导航）

    Returns:
        { ok, logged_in, need_login?, message, url, merchant? }
    """
    url = target_url or PUBLISH_URL

    if skip_if_logged_in:
        probe = check_login_via_mtop(page)
        if probe.get('conclusive') and probe.get('logged_in'):
            return {
                'ok': True,
                'logged_in': True,
                'message': '已登录闲鱼卖家后台',
                'url': page.url,
                'merchant': probe.get('merchant'),
            }

    try:
        _goto(page, url)
    except Exception as exc:
        logger.warning('打开闲鱼后台失败: %s', exc)
        return {
            'ok': False,
            'logged_in': False,
            'need_login': True,
            'message': f'打开闲鱼后台失败: {exc}',
            'url': page.url,
        }

    ensure_browser_window_default(page)
    focus_browser_page(page)

    probe = _probe(page)
    if probe.get('logged_in'):
        return {
            'ok': True,
            'logged_in': True,
            'message': '已登录闲鱼卖家后台',
            'url': page.url,
            'merchant': probe.get('merchant'),
        }

    logged_out = probe.get('conclusive') or is_login_url(page.url) or has_login_dom(page)
    if not logged_out:
        # 探针无法断定（限流/风控），如实上报而不臆断
        return {
            'ok': False,
            'logged_in': False,
            'need_login': False,
            'message': (
                '无法确认登录态（mtop 探针未返回明确结果）。'
                f"请在 Chromium 窗口检查页面状态。详情: {probe.get('error') or probe.get('ret')}"
            ),
            'url': page.url,
        }

    logger.warning('闲鱼卖家后台未登录: %s', page.url)

    if wait_login_timeout_sec > 0:
        return _wait_login_poll(page, url, wait_login_timeout_sec)

    return {
        'ok': False,
        'logged_in': False,
        'need_login': True,
        'message': f'闲鱼卖家后台未登录。{_LOGIN_HINT}',
        'hint': _LOGIN_HINT,
        'url': page.url,
    }


def _wait_login_poll(page: Page, target_url: str, timeout_sec: int) -> Dict[str, Any]:
    timeout_sec = min(max(timeout_sec, 5), 1800)
    logger.info('等待用户在 Chromium 窗口完成闲鱼登录（最多 %s 秒）', timeout_sec)
    focus_browser_page(page)

    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        page.wait_for_timeout(3000)
        probe = check_login_via_mtop(page)
        if probe.get('logged_in'):
            try:
                _goto(page, target_url)
            except Exception:
                pass
            return {
                'ok': True,
                'logged_in': True,
                'message': '登录完成',
                'url': page.url,
                'merchant': probe.get('merchant'),
            }

    # 轮询是有人值守的场景，超时说明人没来扫码，发条飞书提醒
    notify_login_required()
    return {
        'ok': False,
        'logged_in': False,
        'need_login': True,
        'message': f'等待登录超时（{timeout_sec} 秒）。{_LOGIN_HINT}',
        'hint': _LOGIN_HINT,
        'url': page.url,
    }


def notify_login_required() -> None:
    """发飞书「需要重新登录」提醒（失败不影响主流程）。"""
    try:
        from notify import login_alert
        login_alert('goofish')
    except Exception as exc:
        logger.debug('闲鱼登录提醒发送失败: %s', exc)
