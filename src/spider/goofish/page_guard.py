"""闲鱼页面判定与 frame 定位。

闲鱼卖家工作台 shell 只有 iframe 路由，发布/商品列表等业务页都在 iframe 内，
因此 DOM 操作必须先拿到业务 frame；登录判定则优先走 mtop 探针而非 URL/DOM。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from playwright.sync_api import Frame, Page

from spider.goofish.config import (
    API_LOGIN_INFO,
    BUSINESS_FRAME_URL_KEYWORDS,
    LOGIN_TITLE_KEYWORD,
    LOGIN_URL_HASH,
    SEL_LOGIN_BOX,
    SEL_LOGIN_IFRAME_WRAP,
    SEL_PUBLISH_FORM_ANCHORS,
)
from spider.goofish.mtop_bridge import call_mtop, has_mtop, ret_is_success
from utils.logger import get_logger

logger = get_logger('GoofishPageGuard')


def is_login_url(url: str) -> bool:
    """URL 层面的快速短路判定（不作为唯一依据）。"""
    u = (url or '').lower()
    return LOGIN_URL_HASH in u or 'passport.goofish.com' in u or '/login' in u


def has_login_dom(page: Page) -> bool:
    """页面是否呈现登录框（已验证的稳定 ID）。"""
    for sel in (SEL_LOGIN_IFRAME_WRAP, SEL_LOGIN_BOX):
        try:
            if page.locator(sel).count() > 0:
                return True
        except Exception:
            continue
    return False


def check_login_via_mtop(page: Page) -> Dict[str, Any]:
    """用 mtop 探针判定登录态（最可靠）。

    Returns:
        { logged_in, conclusive, merchant?, ret?, error? }
    """
    if not has_mtop(page.main_frame):
        return {'logged_in': False, 'conclusive': False, 'error': 'lib.mtop 未就绪'}

    res = call_mtop(page.main_frame, API_LOGIN_INFO)
    if res.get('sessionExpired'):
        return {'logged_in': False, 'conclusive': True, 'ret': res.get('ret')}
    if res.get('ok') and ret_is_success(res.get('ret')):
        return {
            'logged_in': True,
            'conclusive': True,
            'merchant': res.get('data'),
            'ret': res.get('ret'),
        }
    # 其它错误（限流、风控）无法断定登录态
    return {
        'logged_in': False,
        'conclusive': False,
        'ret': res.get('ret'),
        'error': res.get('error'),
    }


def list_frames(page: Page) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    try:
        for i, f in enumerate(page.frames):
            out.append({'index': str(i), 'url': (f.url or '')[:300], 'name': f.name or ''})
    except Exception:
        pass
    return out


def find_business_frame(page: Page) -> Optional[Frame]:
    """定位承载业务页的 iframe；找不到时回落主 frame。"""
    try:
        frames = page.frames
    except Exception:
        return page.main_frame

    candidates = []
    for f in frames:
        if f == page.main_frame:
            continue
        url = (f.url or '').lower()
        if not url or url.startswith('about:'):
            continue
        # 排除登录/统计/风控类 iframe
        if any(x in url for x in ('passport.', 'xdomain-storage', 'baxia', 'mmstat', 'alicdn.com/platform')):
            continue
        if any(k in url for k in BUSINESS_FRAME_URL_KEYWORDS):
            candidates.append(f)

    if candidates:
        return candidates[0]
    return page.main_frame


def is_publish_ready(page: Page) -> bool:
    """发布页是否就绪：已登录 + 业务 frame 内出现表单锚点。"""
    if is_login_url(page.url) or has_login_dom(page):
        return False
    frame = find_business_frame(page)
    if frame is None:
        return False
    for sel in SEL_PUBLISH_FORM_ANCHORS:
        try:
            if frame.locator(sel).count() > 0:
                return True
        except Exception:
            continue
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
    """最大化浏览器窗口（使用 no_viewport 时勿再 set_viewport_size）。"""
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


def log_browser_state(page: Page, tag: str, *, extra: Optional[Dict[str, Any]] = None) -> None:
    try:
        logger.info(
            '[浏览器状态] %s url=%s frames=%s extra=%s',
            tag,
            (page.url or '')[:200],
            len(page.frames),
            extra or {},
        )
    except Exception as exc:
        logger.debug('log_browser_state 失败 tag=%s err=%s', tag, exc)


def dismiss_popups(frame, texts) -> int:
    """关闭引导类弹层，返回关闭数量。"""
    closed = 0
    for text in texts:
        try:
            loc = frame.get_by_text(text, exact=True)
            if loc.count() > 0 and loc.first.is_visible():
                loc.first.click(timeout=2000)
                closed += 1
        except Exception:
            continue
    return closed
