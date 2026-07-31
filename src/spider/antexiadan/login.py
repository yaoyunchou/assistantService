"""安特 PC 商城（pc.antexiadan.com）Playwright 登录门禁。

流程：ensure_logged_in(page)
  1. 打开 homepage，若未跳到登录页 → 已登录
  2. 若在登录页 → 切「密码登录」，用 .env 账号密码自动登录
  3. 若弹出「安全验证」滑块（#t_mask）→ Nest /ai/chat 识图并拖动（最多 5 次）
  4. 仍失败 → 发飞书 Webhook，返回错误
  5. 登录成功后再继续后续脚本

环境变量：
  ANTEXIADAN_USERNAME                 手机号/账号
  ANTEXIADAN_PASSWORD                 密码
  ANTEXIADAN_CAPTCHA_MAX_ATTEMPTS     AI 尝试次数（默认 5）
  NEST_DEVICE_KEY / NEST_USERNAME     Nest /ai/chat 鉴权（推荐 device-key）
  FEISHU_WEBHOOK_ANTEXIADAN           失败通知 Webhook（可选）
"""
from __future__ import annotations

from typing import Any, Dict

from config import Config
from spider.antexiadan.captcha_solver import solve_captcha_with_agent
from utils.logger import get_logger

logger = get_logger('AntexiadanLogin')

_HOMEPAGE_URL = 'https://pc.antexiadan.com/homepage'
_LOGIN_URL = 'https://pc.antexiadan.com/login'

# 腾讯/天御类滑块：遮罩 #t_mask，弹层含「安全验证」
_CAPTCHA_SELECTORS = (
    '#t_mask',
    '.t-mask',
    '#t_dialog',
    '.tcaptcha-transform',
    'iframe[src*="captcha"]',
    'iframe[src*="turing"]',
)


def is_login_page(page) -> bool:
    """当前是否在安特登录页。"""
    url = (page.url or '').lower()
    if 'login' in url:
        return True
    try:
        if page.get_by_placeholder('请输入手机号').count() > 0:
            return True
    except Exception:
        pass
    return False


def has_captcha(page) -> bool:
    """是否出现安全验证滑块（含腾讯 iframe）。已离开登录页则视为无验证码。"""
    if not is_login_page(page):
        return False
    for sel in _CAPTCHA_SELECTORS:
        try:
            loc = page.locator(sel)
            if loc.count() > 0 and loc.first.is_visible():
                return True
        except Exception:
            continue
    # 腾讯验证码 iframe（须可见，避免登录后 DOM 残留误判）
    for sel in (
        '#tcaptcha_iframe',
        '#tcaptcha_iframe_dy',
        'iframe[id*="tcaptcha"]',
        'iframe[src*="captcha.qq.com"]',
    ):
        try:
            loc = page.locator(sel)
            if loc.count() > 0 and loc.first.is_visible():
                return True
        except Exception:
            continue
    try:
        verify = page.get_by_text('安全验证', exact=False)
        drag = page.get_by_text('拖动下方滑块', exact=False)
        if verify.count() > 0 and verify.first.is_visible():
            if drag.count() > 0 and drag.first.is_visible():
                return True
            if page.locator('#t_mask, .t-mask, #tcaptcha_iframe').first.is_visible():
                return True
    except Exception:
        pass
    return False


def _focus_page(page) -> None:
    try:
        page.bring_to_front()
    except Exception:
        pass


def handle_captcha(page) -> Dict[str, Any]:
    """处理安全验证：远程 AI 最多 N 次；失败发 Webhook。"""
    if not has_captcha(page):
        return {'ok': True, 'needCaptcha': False}
    _focus_page(page)
    logger.warning('检测到安特安全验证滑块，交由远程 AI 自动尝试…')
    return solve_captcha_with_agent(page, has_captcha_fn=has_captcha)


def is_logged_in(page) -> bool:
    """打开 homepage 后判断是否已登录（未落在登录页即视为已登录）。"""
    try:
        page.goto(_HOMEPAGE_URL, wait_until='domcontentloaded', timeout=60_000)
    except Exception as e:
        logger.warning('打开安特首页异常: %s', e)
    page.wait_for_timeout(800)
    return not is_login_page(page)


def do_login(page) -> Dict[str, Any]:
    """在登录页执行密码登录。"""
    username = (Config.ANTEXIADAN_USERNAME or '').strip()
    password = (Config.ANTEXIADAN_PASSWORD or '').strip()
    if not username or not password:
        return {
            'ok': False,
            'needLogin': True,
            'error': (
                '安特未登录且缺少账号密码：请在 .env 配置 '
                'ANTEXIADAN_USERNAME / ANTEXIADAN_PASSWORD'
            ),
        }

    if not is_login_page(page):
        try:
            page.goto(_LOGIN_URL, wait_until='domcontentloaded', timeout=60_000)
        except Exception as e:
            return {'ok': False, 'needLogin': True, 'error': f'打开登录页失败: {e}'}
        page.wait_for_timeout(500)

    try:
        # 默认是「验证码登录」，先切到「密码登录」
        tab = page.get_by_role('tab', name='密码登录')
        if tab.count() > 0:
            tab.first.click()
            page.wait_for_timeout(400)

        phone = page.get_by_placeholder('请输入手机号')
        pwd = page.get_by_placeholder('请输入密码')
        if phone.count() == 0 or pwd.count() == 0:
            return {
                'ok': False,
                'needLogin': True,
                'error': '登录页未找到手机号/密码输入框，请确认页面结构未变更',
            }

        phone.first.fill('')
        phone.first.fill(username)
        pwd.first.fill('')
        pwd.first.fill(password)

        btn = page.get_by_role('button', name='登 录')
        if btn.count() == 0:
            btn = page.get_by_role('button', name='登录')
        if btn.count() == 0:
            return {'ok': False, 'needLogin': True, 'error': '登录页未找到登录按钮'}

        btn.first.click()
        page.wait_for_timeout(1200)

        if has_captcha(page):
            captcha = handle_captcha(page)
            if not captcha.get('ok'):
                return captcha

        # 等待离开登录页（最多约 20 秒；期间若再出滑块继续处理）
        for _ in range(40):
            if not is_login_page(page):
                logger.info('安特自动登录成功，当前 URL=%s', page.url)
                return {'ok': True, 'loggedIn': True, 'needLogin': False, 'needCaptcha': False}
            if has_captcha(page):
                captcha = handle_captcha(page)
                if not captcha.get('ok'):
                    return captcha
            if not is_login_page(page):
                break
            page.wait_for_timeout(500)

        if is_login_page(page):
            if has_captcha(page):
                return {
                    'ok': False,
                    'needLogin': True,
                    'needCaptcha': True,
                    'error': '仍停留在登录页且安全验证未完成',
                }
            tip = ''
            try:
                for sel in ['.el-message', '.el-form-item__error', '.error', '[class*="error"]']:
                    loc = page.locator(sel)
                    if loc.count() > 0:
                        text = (loc.first.inner_text(timeout=500) or '').strip()
                        if text:
                            tip = text
                            break
            except Exception:
                pass
            err = '自动登录失败：仍停留在登录页'
            if tip:
                err = f'{err}（{tip}）'
            return {'ok': False, 'needLogin': True, 'error': err}

        logger.info('安特自动登录成功，当前 URL=%s', page.url)
        return {'ok': True, 'loggedIn': True, 'needLogin': False, 'needCaptcha': False}
    except Exception as e:
        logger.error('安特自动登录异常: %s', e, exc_info=True)
        return {'ok': False, 'needLogin': True, 'error': f'自动登录异常: {e}'}


def ensure_logged_in(page) -> Dict[str, Any]:
    """登录门禁：已登录直接通过；未登录则自动登录后再通过。"""
    if is_logged_in(page):
        logger.info('安特已登录，跳过自动登录')
        return {'ok': True, 'loggedIn': True, 'needLogin': False}

    logger.info('安特未登录，开始自动登录…')
    result = do_login(page)
    if not result.get('ok'):
        return result

    if not is_logged_in(page):
        return {
            'ok': False,
            'needLogin': True,
            'error': '自动登录后仍无法进入 homepage，请检查账号或页面状态',
        }
    return {'ok': True, 'loggedIn': True, 'needLogin': False}
