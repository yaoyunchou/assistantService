"""淘宝卖家中心登录检测与人工介入。"""
from __future__ import annotations

import time
from typing import Any, Dict

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

logger = get_logger('TaobaoLogin')

_CAPTCHA_SELECTORS = [
    '#nc_1_n1z',
    '[class*="captcha"]',
    '[class*="verify"]',
    'iframe[src*="captcha"]',
]


def ensure_logged_in(
    page: Page,
    *,
    pause_on_captcha: bool = True,
    wait_login_timeout_sec: int = 0,
    skip_if_upload_ready: bool = False,
) -> Dict[str, Any]:
    if skip_if_upload_ready and is_category_upload_ready(page):
        return {
            'ok': True,
            'message': '已在以图发品页（上传区已就绪）',
            'url': page.url,
        }

    page.goto(CATEGORY_URL, wait_until='domcontentloaded', timeout=60_000)
    page.wait_for_timeout(2000)
    ensure_browser_window_default(page)
    focus_browser_page(page)

    if is_category_upload_ready(page):
        return {'ok': True, 'message': '已进入以图发品页（category.htm）', 'url': page.url}

    if is_login_page(page.url) or not is_category_upload_ready(page):
        logger.warning('需要登录淘宝卖家账号（请在 Chromium 窗口登录，非日常 Chrome）: %s', page.url)
        if wait_login_timeout_sec > 0:
            polled = _wait_login_poll(page, wait_login_timeout_sec)
            if not polled.get('ok'):
                return polled
        elif pause_on_captcha:
            _wait_manual_login(page)
        else:
            return {
                'ok': False,
                'need_login': True,
                'message': (
                    'Playwright 浏览器未登录淘宝卖家账号。'
                    '请点击「打开以图发品」，在弹出的 Chromium 窗口登录（不是日常 Chrome）'
                ),
                'url': page.url,
            }

    if _has_captcha(page) and pause_on_captcha and wait_login_timeout_sec <= 0:
        logger.warning('检测到验证码，等待人工处理')
        _wait_manual_captcha(page)
    elif _has_captcha(page) and wait_login_timeout_sec > 0:
        polled = _wait_login_poll(page, min(wait_login_timeout_sec, 120))
        if not polled.get('ok'):
            return polled

    if is_category_upload_ready(page):
        return {'ok': True, 'message': '已进入以图发品页（category.htm）', 'url': page.url}

    if is_login_page(page.url):
        return {
            'ok': False,
            'need_login': True,
            'message': '登录未完成，请在 Chromium 窗口完成淘宝卖家登录后重试',
            'url': page.url,
        }

    return {
        'ok': False,
        'need_login': True,
        'message': '未检测到以图发品上传区，请确认在 Chromium 窗口打开 category.htm 并已登录',
        'url': page.url,
    }


def _wait_login_poll(page: Page, timeout_sec: int) -> Dict[str, Any]:
    logger.info('等待用户在 Chromium 窗口完成登录（最多 %s 秒）', timeout_sec)
    if is_login_page(page.url) or not is_category_upload_ready(page):
        page.goto(LOGIN_URL, wait_until='domcontentloaded', timeout=60_000)
        page.wait_for_timeout(1000)
        focus_browser_page(page)

    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        page.wait_for_timeout(3000)
        try:
            page.goto(CATEGORY_URL, wait_until='domcontentloaded', timeout=30_000)
            page.wait_for_timeout(2000)
            focus_browser_page(page)
        except Exception as ex:
            logger.debug('轮询登录跳转异常: %s', ex)
            continue
        if is_category_upload_ready(page):
            return {'ok': True, 'message': '已进入以图发品页（category.htm）', 'url': page.url}

    return {
        'ok': False,
        'need_login': True,
        'message': f'等待登录超时（{timeout_sec} 秒），请在 Chromium 窗口完成卖家登录后重试',
        'url': page.url,
    }


def _has_captcha(page: Page) -> bool:
    for sel in _CAPTCHA_SELECTORS:
        try:
            if page.locator(sel).count() > 0:
                return True
        except Exception:
            continue
    return False


def _wait_manual_login(page: Page) -> None:
    page.goto(LOGIN_URL, wait_until='domcontentloaded', timeout=60_000)
    focus_browser_page(page)
    print('\n[淘宝上架] 请在 Chromium 窗口完成淘宝/千牛登录，完成后回到终端按回车继续…')
    input()
    page.goto(CATEGORY_URL, wait_until='domcontentloaded', timeout=60_000)
    page.wait_for_timeout(2000)


def _wait_manual_captcha(page: Page) -> None:
    print('\n[淘宝上架] 检测到验证码/滑块，请手动完成后按回车继续…')
    input()
    page.wait_for_timeout(1500)
