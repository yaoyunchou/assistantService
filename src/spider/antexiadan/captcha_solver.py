"""安特登录滑块：远程 AI 识别缺口距离（默认 Nest /ai/chat），在当前 Playwright 页拖动。

验证码整体在腾讯 iframe 内（#tcaptcha_iframe / #tcaptcha_iframe_dy），
截图只截验证码弹框/iframe，不截全页；拖动仍在本页完成。
"""
from __future__ import annotations

import json
import random
import re
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from config import Config
from utils.logger import get_logger

logger = get_logger('AntexiadanCaptcha')

# 外层弹框 / iframe（优先截弹框，再截 iframe）
_DIALOG_SELECTORS = (
    '#t_dialog',
    '.tcaptcha-transform',
    '#tcaptcha_transform',
    'div.tcaptcha-transform',
)
_IFRAME_SELECTORS = (
    '#tcaptcha_iframe',
    '#tcaptcha_iframe_dy',
    'iframe#tcaptcha_iframe',
    'iframe[id*="tcaptcha"]',
    'iframe[src*="captcha.qq.com"]',
    'iframe[src*="turing.captcha"]',
    'iframe[src*="cap_union"]',
)

# iframe 内滑块按钮（安特实测：#tcOperation > div.tc-fg-item.tc-slider-normal）
_SLIDER_SELECTORS = (
    '#tcOperation > div.tc-fg-item.tc-slider-normal',
    '#tcOperation div.tc-slider-normal',
    'div.tc-fg-item.tc-slider-normal',
    '.tc-slider-normal',
    '#tcaptcha_drag_thumb',
    '#tcaptcha_drag_button',
    '.tcaptcha-drag-thumb',
    '.tcaptcha-drag-button',
    '#tcOperation .tcaptcha-drag-thumb',
    '#tcOperation div[style*="cursor"]',
    '[class*="drag-thumb"]',
    '[class*="slide-btn"]',
    '[class*="slider-btn"]',
)

_REFRESH_SELECTORS = (
    '#reload',
    '.tcaptcha-btn-refresh',
    'a#reload',
    '[class*="refresh"]',
    'div.tc-reload',
)


def _max_attempts() -> int:
    n = int(getattr(Config, 'ANTEXIADAN_CAPTCHA_MAX_ATTEMPTS', 5) or 5)
    return max(1, min(n, 10))


def _screenshot_dir() -> Path:
    try:
        from utils.path_helper import get_safe_data_path
        d = get_safe_data_path('antexiadan/captcha')
    except Exception:
        d = Path('data/antexiadan/captcha')
    d.mkdir(parents=True, exist_ok=True)
    return d


def _parse_distance(text: str) -> Optional[int]:
    raw = (text or '').strip()
    if not raw:
        return None
    for m in re.finditer(r'\{[^{}]*\}', raw, re.S):
        try:
            obj = json.loads(m.group(0))
            if isinstance(obj, dict) and 'distancePx' in obj:
                return int(float(obj['distancePx']))
            if isinstance(obj, dict) and 'distance' in obj:
                return int(float(obj['distance']))
        except Exception:
            continue
    m = re.search(r'distancePx["\s:=]+(\d{2,4})', raw, re.I)
    if m:
        return int(m.group(1))
    m = re.search(r'(\d{2,4})\s*px', raw, re.I)
    if m:
        return int(m.group(1))
    return None


def _captcha_ai_configured() -> bool:
    from integrations.nest_client import nest_auth_configured
    return nest_auth_configured()


def _captcha_ai_missing_message() -> str:
    return 'Nest AI 未配置：请设置 NEST_DEVICE_KEY 或 NEST_USERNAME/NEST_PASSWORD'


def _captcha_user_prompt(attempt: int) -> str:
    return (
        '这是安特登录页的「安全验证」滑块拼图截图（腾讯验证码弹框区域）。'
        '画面上方有背景图与缺口，下方有蓝色滑块按钮。\n'
        '请估算：需要把底部蓝色滑块按钮向右拖动多少像素，才能让拼图块对齐缺口。\n'
        f'这是第 {attempt} 次尝试；若图中拼图块已偏右，请按当前画面重新估算。\n'
        '只回复一行 JSON，不要其它文字，格式严格为：\n'
        '{"distancePx": 整数, "confidence": 0到1的小数}\n'
        'distancePx 一般在 80~280 之间。'
    )


_CAPTCHA_SYSTEM_JSON = (
    '你是滑块验证码识图助手。只输出一行 JSON，格式 {"distancePx": 整数, "confidence": 0到1}，不要其它文字。'
)


def _estimate_distance_with_agent(screenshot_path: Path, attempt: int) -> Optional[int]:
    from integrations.nest_client import nest_ai_chat

    try:
        image_bytes = screenshot_path.read_bytes()
        result = nest_ai_chat(
            user_text=_captcha_user_prompt(attempt),
            system_prompt=_CAPTCHA_SYSTEM_JSON,
            image_bytes=image_bytes,
            image_mime='image/png',
            timeout=120,
        )
        logger.info('Nest AI 滑块识别回复(attempt=%s): %s', attempt, (result or '')[:300])
        return _parse_distance(result or '')
    except Exception as e:
        logger.error('Nest AI 识别滑块失败: %s', e, exc_info=True)
        return None


def _clip_from_box(box: Dict[str, float]) -> Optional[Dict[str, float]]:
    try:
        x = max(0.0, float(box['x']))
        y = max(0.0, float(box['y']))
        w = float(box['width'])
        h = float(box['height'])
        if w < 50 or h < 50:
            return None
        return {'x': x, 'y': y, 'width': w, 'height': h}
    except Exception:
        return None


def _screenshot_element(page, locator, shot_path: Path, *, label: str) -> bool:
    """截单个元素；失败再用 page.screenshot(clip=bounding_box)。"""
    try:
        box = locator.bounding_box(timeout=1500)
    except Exception:
        box = None
    if not box:
        return False
    clip = _clip_from_box(box)
    if not clip:
        return False
    try:
        locator.screenshot(path=str(shot_path))
        logger.info(
            '已截验证码区域(%s) css=%.0fx%.0f @ (%.0f,%.0f)',
            label, clip['width'], clip['height'], clip['x'], clip['y'],
        )
        return True
    except Exception as e:
        logger.debug('元素 screenshot 失败(%s): %s，改用 clip', label, e)
    try:
        page.screenshot(path=str(shot_path), clip=clip)
        logger.info(
            '已 clip 截验证码区域(%s) css=%.0fx%.0f @ (%.0f,%.0f)',
            label, clip['width'], clip['height'], clip['x'], clip['y'],
        )
        return True
    except Exception as e:
        logger.debug('clip 截图失败(%s): %s', label, e)
        return False


def _screenshot_captcha(page, shot_path: Path) -> bool:
    """只截验证码弹框/iframe，不截全页。"""
    for sel in _DIALOG_SELECTORS:
        try:
            loc = page.locator(sel).first
            if _screenshot_element(page, loc, shot_path, label=f'dialog:{sel}'):
                return True
        except Exception:
            continue

    for sel in _IFRAME_SELECTORS:
        try:
            loc = page.locator(sel).first
            if _screenshot_element(page, loc, shot_path, label=f'iframe:{sel}'):
                return True
        except Exception:
            continue

    # 再扫 page.frames，用 owner iframe 元素截图
    try:
        for fr in page.frames:
            url = (fr.url or '').lower()
            name = (fr.name or '').lower()
            if not any(k in url for k in ('captcha.qq.com', 'turing.captcha', 'cap_union', 'tcaptcha')) \
                    and 'tcaptcha' not in name:
                continue
            try:
                el = fr.frame_element()
                if el and _screenshot_element(page, el, shot_path, label=f'frame:{url[:60]}'):
                    return True
            except Exception:
                continue
    except Exception as e:
        logger.debug('扫 frames 截图失败: %s', e)

    logger.warning('未定位到验证码弹框/iframe，截图失败（拒绝全页截图）')
    return False


def _log_frames(page) -> None:
    try:
        infos = []
        for fr in page.frames:
            infos.append(f'{fr.name or "-"}|{fr.url[:120]}')
        logger.info('当前 frames(%d): %s', len(infos), ' || '.join(infos))
    except Exception as e:
        logger.debug('列举 frames 失败: %s', e)


def _wait_captcha_iframe(page, timeout_ms: int = 8000):
    """等待腾讯验证码 iframe 出现，返回 Frame 或 None。"""
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        # 1) 按选择器找 iframe 元素 → content_frame
        for sel in _IFRAME_SELECTORS:
            try:
                handle = page.query_selector(sel)
                if not handle:
                    continue
                frame = handle.content_frame()
                if frame:
                    logger.info('命中验证码 iframe selector=%s url=%s', sel, (frame.url or '')[:120])
                    return frame
            except Exception:
                continue

        # 2) 按 URL / name 扫 page.frames
        try:
            for fr in page.frames:
                url = (fr.url or '').lower()
                name = (fr.name or '').lower()
                if any(k in url for k in ('captcha.qq.com', 'turing.captcha', 'cap_union', 'tcaptcha')):
                    logger.info('命中验证码 frame(url) url=%s', fr.url[:120])
                    return fr
                if 'tcaptcha' in name:
                    logger.info('命中验证码 frame(name) name=%s url=%s', fr.name, (fr.url or '')[:120])
                    return fr
        except Exception:
            pass

        page.wait_for_timeout(250)

    _log_frames(page)
    return None


def _frame_locator_candidates(page):
    """Playwright frame_locator 候选（推荐写法）。"""
    for sel in _IFRAME_SELECTORS:
        try:
            yield page.frame_locator(sel)
        except Exception:
            continue


def _find_in_frame_locator(page, selectors: Tuple[str, ...]):
    """用 frame_locator 在 iframe 内找可见元素，返回 Locator 或 None。"""
    for fl in _frame_locator_candidates(page):
        for sel in selectors:
            try:
                loc = fl.locator(sel)
                # frame_locator 的 count 可能抛错，用 first + bounding_box 探测
                first = loc.first
                box = first.bounding_box(timeout=1500)
                if box and box.get('width', 0) > 5 and box.get('height', 0) > 5:
                    logger.info('frame_locator 命中滑块/控件 sel=%s box=%s', sel, box)
                    return first
            except Exception:
                continue
    return None


def _find_in_frame_object(frame, selectors: Tuple[str, ...]):
    """在 Frame 对象内找元素。"""
    if frame is None:
        return None
    for sel in selectors:
        try:
            loc = frame.locator(sel)
            if loc.count() == 0:
                continue
            first = loc.first
            # iframe 内 is_visible 有时不可靠，优先 bounding_box
            box = first.bounding_box(timeout=1500)
            if box and box.get('width', 0) > 5:
                logger.info('frame 内命中 sel=%s box=%s', sel, box)
                return first
        except Exception:
            continue
    return None


def _find_slider_by_geometry(frame_or_page) -> Any:
    """按几何特征兜底：矮扁、可拖的小块。"""
    try:
        candidates = frame_or_page.locator(
            '#tcOperation > div.tc-fg-item.tc-slider-normal, '
            'div.tc-fg-item.tc-slider-normal, .tc-slider-normal, '
            '#tcaptcha_drag_thumb, #tcaptcha_drag_button, '
            'div[style*="cursor: pointer"], div[style*="cursor:pointer"], '
            '[class*="drag"], [class*="slide"]'
        )
        n = min(candidates.count(), 30)
        for i in range(n):
            el = candidates.nth(i)
            try:
                box = el.bounding_box(timeout=500)
                if not box:
                    continue
                w, h = box['width'], box['height']
                if 20 <= h <= 70 and 20 <= w <= 90:
                    logger.info('几何兜底命中滑块 box=%s', box)
                    return el
            except Exception:
                continue
    except Exception:
        pass
    return None


def find_slider(page) -> Any:
    """在腾讯验证码 iframe 内定位滑块按钮。"""
    # A. frame_locator（官方推荐，跨 iframe 坐标仍是页面坐标）
    loc = _find_in_frame_locator(page, _SLIDER_SELECTORS)
    if loc:
        return loc

    # B. 等 iframe 再进 Frame
    frame = _wait_captcha_iframe(page, timeout_ms=5000)
    loc = _find_in_frame_object(frame, _SLIDER_SELECTORS)
    if loc:
        return loc
    if frame:
        loc = _find_slider_by_geometry(frame)
        if loc:
            return loc

    # C. 主页面兜底（极少情况验证不在 iframe）
    loc = _find_slider_by_geometry(page)
    if loc:
        return loc

    _log_frames(page)
    return None


def _human_drag(page, slider, distance_px: int) -> bool:
    """拟人化水平拖动（bounding_box 已是页面坐标，含 iframe 偏移）。"""
    box = slider.bounding_box()
    if not box:
        logger.warning('滑块 bounding_box 为空，无法拖动')
        return False
    start_x = box['x'] + box['width'] / 2
    start_y = box['y'] + box['height'] / 2
    dist = max(40, min(int(distance_px), 320))
    steps = random.randint(22, 32)
    logger.info('开始拖动 start=(%.1f,%.1f) dist=%s', start_x, start_y, dist)

    page.mouse.move(start_x, start_y)
    page.wait_for_timeout(random.randint(100, 220))
    page.mouse.down()
    page.wait_for_timeout(random.randint(80, 160))

    for i in range(1, steps + 1):
        t = i / steps
        eased = 1 - (1 - t) ** 2
        x = start_x + dist * eased + random.uniform(-1.5, 1.5)
        y = start_y + random.uniform(-2.0, 2.0)
        page.mouse.move(x, y)
        page.wait_for_timeout(random.randint(10, 28))

    page.wait_for_timeout(random.randint(100, 200))
    page.mouse.up()
    return True


def _click_refresh(page) -> None:
    """只在验证码 iframe 内点刷新，避免误点主页面。"""
    btn = _find_in_frame_locator(page, _REFRESH_SELECTORS)
    if not btn:
        frame = _wait_captcha_iframe(page, timeout_ms=2000)
        btn = _find_in_frame_object(frame, _REFRESH_SELECTORS) if frame else None
    if not btn:
        logger.debug('iframe 内未找到刷新按钮，跳过')
        return
    try:
        btn.click(timeout=2000)
        page.wait_for_timeout(900)
        logger.info('已点击 iframe 内滑块刷新')
    except Exception as e:
        logger.debug('刷新滑块失败: %s', e)


def _notify_captcha_failed(*, attempts: int, last_error: str, screenshot_b64: Optional[str] = None) -> None:
    try:
        from notify import NotifyChannel, NotifyEvent, NotifyLevel, notify
        desc = (
            f'安特登录「安全验证」滑块，Nest AI 自动尝试 **{attempts}** 次仍未通过。\n'
            f'请尽快在 Playwright 浏览器窗口手动完成拼图，或重新触发采集。\n'
            f'详情：{last_error}'
        )
        notify(NotifyEvent(
            source='antexiadan',
            level=NotifyLevel.ERROR,
            title='安特 · 滑块验证失败',
            description=desc,
            channel=NotifyChannel.FEISHU_WEBHOOK,
            link_url='https://pc.antexiadan.com/login',
            link_text='打开安特登录页',
            image_base64=screenshot_b64,
        ))
        logger.info('已发送安特滑块失败 Webhook')
    except Exception as e:
        logger.warning('发送滑块失败 Webhook 异常: %s', e)


def _login_gate_passed(page, has_captcha_fn) -> bool:
    """已离开登录页或验证码已消失 → 无需继续 Agent 重试。"""
    try:
        from spider.antexiadan.login import is_login_page
        if not is_login_page(page):
            logger.info('页面已离开登录页，视为登录/验证已通过')
            return True
    except Exception:
        pass
    return not has_captcha_fn(page)


def _captcha_passed_result(*, solved_by: str, attempts: int, distance_px: Optional[int] = None) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        'ok': True,
        'needCaptcha': False,
        'solvedBy': solved_by,
        'attempts': attempts,
    }
    if distance_px is not None:
        out['distancePx'] = distance_px
    return out


def solve_captcha_with_agent(page, *, has_captcha_fn, max_attempts: int = 0) -> Dict[str, Any]:
    """最多 N 次：截验证码弹框 → Agent 估距离 → iframe 内拖动；失败发 Webhook。"""
    attempts = max_attempts or _max_attempts()
    last_error = '未知错误'
    last_shot_b64: Optional[str] = None

    if not has_captcha_fn(page):
        return {'ok': True, 'needCaptcha': False, 'solvedBy': 'none'}

    if not _captcha_ai_configured():
        last_error = _captcha_ai_missing_message()
        _notify_captcha_failed(attempts=0, last_error=last_error)
        return {
            'ok': False,
            'needLogin': True,
            'needCaptcha': True,
            'error': last_error,
        }

    # 先等 iframe 就绪
    frame = _wait_captcha_iframe(page, timeout_ms=10000)
    if not frame:
        if _login_gate_passed(page, has_captcha_fn):
            return _captcha_passed_result(solved_by='skip_after_login', attempts=0)
        last_error = '未找到腾讯验证码 iframe（#tcaptcha_iframe）'
        logger.warning(last_error)
        _notify_captcha_failed(attempts=0, last_error=last_error)
        return {
            'ok': False,
            'needLogin': True,
            'needCaptcha': True,
            'error': last_error,
        }

    for i in range(1, attempts + 1):
        if _login_gate_passed(page, has_captcha_fn):
            return _captcha_passed_result(solved_by='skip_after_login', attempts=i - 1)

        shot_path = _screenshot_dir() / f'captcha_{int(time.time())}_{i}.png'
        if not _screenshot_captcha(page, shot_path):
            last_error = f'第 {i} 次：未截到验证码弹框/iframe'
            logger.warning(last_error)
            if _login_gate_passed(page, has_captcha_fn):
                return _captcha_passed_result(solved_by='skip_after_login', attempts=i)
            continue
        try:
            import base64
            last_shot_b64 = base64.b64encode(shot_path.read_bytes()).decode()
        except Exception:
            last_shot_b64 = None

        if _login_gate_passed(page, has_captcha_fn):
            return _captcha_passed_result(solved_by='skip_after_login', attempts=i)

        distance = _estimate_distance_with_agent(shot_path, i)
        if not distance:
            last_error = f'第 {i} 次：Agent 未返回有效 distancePx'
            logger.warning(last_error)
            _click_refresh(page)
            continue

        distance = int(distance + random.randint(-3, 3))
        slider = find_slider(page)
        if not slider:
            last_error = f'第 {i} 次：iframe 内未找到滑块按钮'
            logger.warning(last_error)
            _log_frames(page)
            page.wait_for_timeout(1000)
            slider = find_slider(page)
            if not slider:
                _click_refresh(page)
                continue

        logger.info('第 %s/%s 次拖动滑块 distancePx=%s', i, attempts, distance)
        try:
            ok_drag = _human_drag(page, slider, distance)
        except Exception as e:
            ok_drag = False
            last_error = f'第 {i} 次拖动异常: {e}'
            logger.warning(last_error)

        if not ok_drag:
            _click_refresh(page)
            continue

        page.wait_for_timeout(2000)
        if _login_gate_passed(page, has_captcha_fn):
            logger.info('滑块验证已通过（第 %s 次后）', i)
            return _captcha_passed_result(
                solved_by='nest',
                attempts=i,
                distance_px=distance if distance else None,
            )

        last_error = f'第 {i} 次拖动后验证仍在'
        logger.warning(last_error)
        _click_refresh(page)
        page.wait_for_timeout(800)

    _notify_captcha_failed(
        attempts=attempts,
        last_error=last_error,
        screenshot_b64=last_shot_b64,
    )
    return {
        'ok': False,
        'needLogin': True,
        'needCaptcha': True,
        'error': f'安全验证失败：Nest AI 已尝试 {attempts} 次仍未通过（{last_error}），已发送飞书 Webhook',
        'attempts': attempts,
    }
