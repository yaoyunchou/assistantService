"""闲鱼发布页操作。

发布页在 iframe 内（已验证 shell 只有 iframe 路由），因此所有操作都针对业务 frame。
发布表单的精确选择器未能在未登录态取得，这里用语义/文本定位并在找不到控件时
抛出带诊断信息的异常，而不是静默点错位置。补全方式见 docs/goofish/闲鱼后台-探测记录.md。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from spider.goofish.config import (
    DEFAULT_TIMEOUT_MS,
    SEL_IMAGE_UPLOAD_INPUT,
    SUBMIT_TIMEOUT_MS,
    TEXT_DISMISS_POPUPS,
    TEXT_SUBMIT_BUTTONS,
    UPLOAD_BETWEEN_SEC,
)
from spider.goofish.page_guard import dismiss_popups
from utils.logger import get_logger

logger = get_logger('GoofishPublishPage')


class PublishPageError(RuntimeError):
    """发布页操作失败，附带定位诊断。"""


def _diagnostic(frame, what: str) -> str:
    """构造可操作的错误信息，指明如何补全选择器。"""
    try:
        url = (frame.url or '')[:200]
    except Exception:
        url = '(未知)'
    return (
        f'未能在发布页定位{what}。frame={url}\n'
        '闲鱼发布表单选择器需在登录态探测确认：\n'
        '  1. 调用 POST /api/goofish/probe 采集接口与页面结构\n'
        '  2. 按 docs/goofish/闲鱼后台-探测记录.md 补全 src/spider/goofish/config.py 中的选择器'
    )


def dismiss_guides(frame) -> int:
    return dismiss_popups(frame, TEXT_DISMISS_POPUPS)


def find_file_input(frame):
    """返回可用的文件上传 input（可能 hidden，用 set_input_files 不需要可见）。"""
    try:
        loc = frame.locator(SEL_IMAGE_UPLOAD_INPUT)
        if loc.count() > 0:
            return loc.first
    except Exception:
        pass
    return None


def upload_images(frame, images: List[Path], *, on_progress=None) -> Dict[str, Any]:
    """逐张上传图片。

    闲鱼图片上传控件通常接受多选，优先一次性传；失败则逐张重试。
    """
    if not images:
        raise PublishPageError('商品无图片，无法发布')

    file_input = find_file_input(frame)
    if file_input is None:
        raise PublishPageError(_diagnostic(frame, '图片上传控件 input[type=file]'))

    paths = [str(p) for p in images]
    uploaded = 0
    errors: List[str] = []

    try:
        file_input.set_input_files(paths, timeout=DEFAULT_TIMEOUT_MS)
        uploaded = len(paths)
        logger.info('闲鱼图片批量上传已提交 count=%d', uploaded)
        frame.wait_for_timeout(UPLOAD_BETWEEN_SEC * 1000)
    except Exception as exc:
        logger.warning('批量上传失败，改为逐张上传: %s', exc)
        uploaded = 0
        for idx, path in enumerate(paths, start=1):
            try:
                file_input = find_file_input(frame) or file_input
                file_input.set_input_files(path, timeout=DEFAULT_TIMEOUT_MS)
                uploaded += 1
                if on_progress:
                    on_progress(idx, len(paths))
                frame.wait_for_timeout(UPLOAD_BETWEEN_SEC * 1000)
            except Exception as inner:
                errors.append(f'{Path(path).name}: {inner}')

    if uploaded == 0:
        raise PublishPageError(
            '图片上传全部失败：\n' + '\n'.join(errors[:5])
        )

    return {'ok': True, 'uploaded': uploaded, 'expected': len(paths), 'errors': errors}


def _fill_first_match(frame, candidates: List[Any], value: str, *, what: str) -> bool:
    """按候选定位器顺序尝试填值，成功返回 True。"""
    if value is None or str(value) == '':
        return False
    for locator in candidates:
        try:
            if locator.count() == 0:
                continue
            target = locator.first
            target.fill(str(value), timeout=DEFAULT_TIMEOUT_MS)
            logger.info('已填写%s', what)
            return True
        except Exception:
            continue
    return False


def fill_title_and_description(frame, product) -> Dict[str, Any]:
    """填写标题与描述。

    闲鱼发布页把「描述」作为主输入区（textarea），标题多为单行 input 或
    由描述首行推导。这里两者都尝试，并记录实际命中情况。
    """
    filled: Dict[str, Any] = {'title': False, 'description': False}

    desc = product.description or product.title
    desc_candidates = [
        frame.get_by_placeholder(re.compile('描述|介绍|说说|详情')),
        frame.locator('textarea'),
    ]
    filled['description'] = _fill_first_match(frame, desc_candidates, desc, what='商品描述')

    title_candidates = [
        frame.get_by_placeholder(re.compile('标题')),
        frame.locator('input[type="text"]'),
    ]
    filled['title'] = _fill_first_match(frame, title_candidates, product.title, what='商品标题')

    if not filled['description'] and not filled['title']:
        raise PublishPageError(_diagnostic(frame, '标题/描述输入框'))
    return filled


def fill_price(frame, product) -> Dict[str, Any]:
    """填写想卖价与原价。"""
    filled: Dict[str, Any] = {'price': False, 'original_price': False}

    price_candidates = [
        frame.get_by_placeholder(re.compile('价|要卖|想卖')),
        frame.locator('input[type="number"]'),
    ]
    filled['price'] = _fill_first_match(frame, price_candidates, product.price, what='想卖价')

    if product.original_price:
        orig_candidates = [frame.get_by_placeholder(re.compile('原价'))]
        filled['original_price'] = _fill_first_match(
            frame, orig_candidates, product.original_price, what='原价'
        )

    if not filled['price']:
        raise PublishPageError(_diagnostic(frame, '价格输入框'))
    return filled


def select_by_text(frame, text: str, *, what: str) -> bool:
    """按可见文本点选（成色、分类、包邮等枚举项）。"""
    if not text:
        return False
    try:
        loc = frame.get_by_text(text, exact=True)
        if loc.count() > 0:
            loc.first.click(timeout=DEFAULT_TIMEOUT_MS)
            logger.info('已选择%s=%s', what, text)
            return True
    except Exception as exc:
        logger.debug('选择%s=%s 失败: %s', what, text, exc)
    return False


def fill_attributes(frame, product) -> Dict[str, Any]:
    """填写成色、分类、包邮、发货地等枚举/文本属性。

    这些控件在闲鱼发布页多为自定义下拉，缺省值来自 config，
    未命中时只记录不中断（避免因非致命字段整单失败）。
    """
    result = {
        'condition': select_by_text(frame, product.condition, what='成色'),
        'category': select_by_text(frame, product.category, what='分类'),
        'free_shipping': select_by_text(
            frame, '包邮' if product.free_shipping else '不包邮', what='包邮'
        ),
    }
    if product.ship_from:
        result['ship_from'] = _fill_first_match(
            frame,
            [frame.get_by_placeholder(re.compile('发货地|所在地|位置'))],
            product.ship_from,
            what='发货地',
        )
    unmatched = [k for k, v in result.items() if not v]
    if unmatched:
        logger.warning('以下属性未命中控件（需探测补全选择器）: %s', unmatched)
    return result


def find_submit_button(frame):
    for text in TEXT_SUBMIT_BUTTONS:
        try:
            loc = frame.get_by_role('button', name=re.compile(re.escape(text)))
            if loc.count() > 0:
                return loc.first, text
        except Exception:
            pass
        try:
            loc = frame.get_by_text(text, exact=True)
            if loc.count() > 0:
                return loc.first, text
        except Exception:
            pass
    return None, ''


def submit(frame) -> Dict[str, Any]:
    """点击发布并等待结果。"""
    button, label = find_submit_button(frame)
    if button is None:
        raise PublishPageError(_diagnostic(frame, f'发布按钮（尝试文案: {TEXT_SUBMIT_BUTTONS}）'))

    button.click(timeout=DEFAULT_TIMEOUT_MS)
    logger.info('已点击发布按钮: %s', label)
    frame.wait_for_timeout(3000)
    return {'ok': True, 'clicked': label}


_ID_PATTERNS = (
    re.compile(r'[?&]id=(\d{6,})'),
    re.compile(r'item[/_-]?id["\']?\s*[:=]\s*["\']?(\d{6,})'),
    re.compile(r'/item/(\d{6,})'),
)


def extract_item_id(frame, *, timeout_ms: int = SUBMIT_TIMEOUT_MS) -> str:
    """从 URL 或页面内容提取新商品 ID。"""
    deadline_steps = max(1, timeout_ms // 2000)
    for _ in range(deadline_steps):
        for source in _candidate_sources(frame):
            for pattern in _ID_PATTERNS:
                match = pattern.search(source)
                if match:
                    return match.group(1)
        frame.wait_for_timeout(2000)
    return ''


def _candidate_sources(frame) -> List[str]:
    sources: List[str] = []
    try:
        sources.append(frame.url or '')
    except Exception:
        pass
    try:
        page = frame.page
        sources.append(page.url or '')
        for f in page.frames:
            sources.append(f.url or '')
    except Exception:
        pass
    try:
        sources.append(frame.evaluate('() => document.body ? document.body.innerHTML.slice(0, 20000) : ""'))
    except Exception:
        pass
    return [s for s in sources if s]
