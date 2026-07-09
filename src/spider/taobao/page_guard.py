"""淘宝页面 URL / DOM 判定（避免 browser_visible 与 login_intercept 循环引用）。"""
from __future__ import annotations

from typing import Any, Dict, Optional

from playwright.sync_api import Page

from utils.logger import get_logger

logger = get_logger('TaobaoPageGuard')


def is_login_page(url: str) -> bool:
    u = (url or '').lower()
    return 'login.taobao.com' in u or 'login.tmall.com' in u or 'havanaone/login' in u


def is_category_page(url: str) -> bool:
    u = (url or '').lower()
    return 'sell/ai/category.htm' in u or 'item.upload.taobao.com/sell/ai/category' in u


def is_category_upload_ready(page: Page) -> bool:
    """URL 是 category.htm 且页面已出现以图发品上传区（非登录壳）。"""
    if not is_category_page(page.url):
        return False
    try:
        data = page.evaluate(
            """() => {
              const root = document.querySelector('#ai-category-page-main-do-not-add-padding');
              const hasUploadBtn = [...document.querySelectorAll('button')].some(
                b => (b.innerText || '').includes('从本地上传')
              );
              const text = document.body ? document.body.innerText.slice(0, 2000) : '';
              const looksLogin = /密码登录|短信登录|扫码登录/.test(text) && !hasUploadBtn;
              return { hasRoot: !!root, hasUploadBtn, looksLogin };
            }"""
        )
        return bool(data.get('hasRoot') or data.get('hasUploadBtn')) and not data.get('looksLogin')
    except Exception:
        return False


def focus_browser_page(page: Page) -> None:
    try:
        page.bring_to_front()
    except Exception:
        pass
    try:
        page.evaluate('() => { try { window.focus(); } catch (e) {} }')
    except Exception:
        pass


def ensure_browser_window_default(page: Page) -> None:
    """最大化浏览器窗口。使用 no_viewport 时勿再 set_viewport_size，避免页面比例错乱。"""
    try:
        cdp = page.context.new_cdp_session(page)
        info = cdp.send('Browser.getWindowForTarget')
        cdp.send('Browser.setWindowBounds', {
            'windowId': info['windowId'],
            'bounds': {'windowState': 'maximized'},
        })
        logger.info('浏览器窗口已通过 CDP 最大化')
    except Exception as exc:
        logger.warning('CDP 最大化失败（请手动拖大 Chromium 窗口）: %s', exc)

    try:
        metrics = page.evaluate(
            """() => ({
              innerWidth: window.innerWidth,
              innerHeight: window.innerHeight,
              outerWidth: window.outerWidth,
              outerHeight: window.outerHeight,
              devicePixelRatio: window.devicePixelRatio,
            })"""
        )
        logger.info(
            '浏览器可视区域 inner=%sx%s outer=%sx%s dpr=%s',
            metrics.get('innerWidth'),
            metrics.get('innerHeight'),
            metrics.get('outerWidth'),
            metrics.get('outerHeight'),
            metrics.get('devicePixelRatio'),
        )
        if int(metrics.get('innerHeight') or 0) < 900:
            logger.warning(
                '可视高度偏小(%s)，底部上传确认条可能被挤出；请最大化 Chromium 或调低系统缩放',
                metrics.get('innerHeight'),
            )
    except Exception:
        pass


def log_browser_state(page: Page, tag: str, *, extra: Optional[Dict[str, Any]] = None) -> None:
    """记录自动化浏览器当前状态，便于对照用户手动操作时的异常。"""
    try:
        ctx = page.context
        pages = ctx.pages
        tabs = []
        for i, p in enumerate(pages):
            if p.is_closed():
                tabs.append({'index': i, 'closed': True})
                continue
            tabs.append({
                'index': i,
                'url': (p.url or '')[:200],
                'is_automation_page': p == page,
            })
        logger.info('[浏览器状态] %s tabs=%s current_url=%s extra=%s', tag, tabs, (page.url or '')[:200], extra or {})
    except Exception as ex:
        logger.debug('log_browser_state 失败 tag=%s err=%s', tag, ex)
