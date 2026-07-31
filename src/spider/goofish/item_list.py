"""在线商品列表抓取。

三级取数策略，按可靠性从高到低：
    1. config.ITEM_LIST_API 已配置 → 直接 lib.mtop 调用（可控分页，最确定）
    2. 未配置 → 打开列表页并拦截 mtop 响应自动识别接口（顺带告知应配置的 API 名）
    3. 前两者都失败 → DOM 兜底脚本 scripts/goofish-item-list.js

返回体的 source 字段会标明实际走了哪条路径。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from playwright.sync_api import Page

from spider.goofish.config import (
    ITEM_LIST_API,
    ITEM_LIST_API_VERSION,
    ITEM_LIST_URL,
    ITEM_URL_TEMPLATE,
    NAV_TIMEOUT_MS,
    PROBE_ITEM_KEYWORDS,
)
from spider.goofish.login_gate import ensure_logged_in
from spider.goofish.mtop_bridge import call_mtop, ret_is_success
from spider.goofish.page_guard import find_business_frame
from utils.logger import get_logger

logger = get_logger('GoofishItemList')

_DOM_SCRIPT = Path(__file__).resolve().parent / 'scripts' / 'goofish-item-list.js'

_MTOP_HOSTS = ('h5api.m.goofish.com', 'h5api.m.taobao.com', 'acs.m.goofish.com')

# 字段名候选（闲鱼各接口命名不完全一致，做宽松映射）
_ID_KEYS = ('itemId', 'item_id', 'id', 'auctionId', 'idleItemId')
_TITLE_KEYS = ('title', 'itemTitle', 'subject', 'name', 'desc')
_PRICE_KEYS = ('price', 'soldPrice', 'currentPrice', 'itemPrice', 'reservePrice')
_STATUS_KEYS = ('status', 'itemStatus', 'state', 'bizStatus')
_IMAGE_KEYS = ('picUrl', 'imageUrl', 'mainPic', 'cover', 'coverUrl', 'pic')
_TIME_KEYS = ('modifyTime', 'gmtModified', 'updateTime', 'publishTime', 'gmtCreate')

_STATUS_MAP = {
    'online': 'online', 'onsale': 'online', 'on_sale': 'online', '1': 'online',
    '在售': 'online', '上架': 'online', 'published': 'online',
    'offline': 'offline', 'off_shelf': 'offline', 'offshelf': 'offline',
    '已下架': 'offline', '下架': 'offline', '0': 'offline',
    'sold': 'sold', 'sold_out': 'sold', '已售出': 'sold', '已卖出': 'sold',
}


def _pick(d: Dict[str, Any], keys: Tuple[str, ...]) -> Any:
    for k in keys:
        if k in d and d[k] not in (None, ''):
            return d[k]
    # 大小写不敏感兜底
    lowered = {str(k).lower(): v for k, v in d.items()}
    for k in keys:
        v = lowered.get(k.lower())
        if v not in (None, ''):
            return v
    return None


def _norm_status(raw: Any) -> str:
    text = str(raw if raw is not None else '').strip().lower()
    if not text:
        return 'unknown'
    return _STATUS_MAP.get(text, text)


def _norm_price(raw: Any) -> Optional[float]:
    """提取价格数值。

    刻意不做「分转元」猜测：闲鱼各接口价格单位未经登录态确认，
    而该值会回显到编辑弹窗，猜错会直接改错价。单位确认后再在此处统一换算。
    """
    if raw is None:
        return None
    match = re.search(r'\d+(?:\.\d+)?', str(raw).replace(',', ''))
    if not match:
        return None
    return float(match.group(0))


def _looks_like_item(d: Any) -> bool:
    if not isinstance(d, dict):
        return False
    has_id = _pick(d, _ID_KEYS) is not None
    has_title = _pick(d, _TITLE_KEYS) is not None
    has_price = _pick(d, _PRICE_KEYS) is not None
    return has_id and (has_title or has_price)


def _normalize_item(d: Dict[str, Any]) -> Dict[str, Any]:
    item_id = str(_pick(d, _ID_KEYS) or '')
    raw_url = _pick(d, ('itemUrl', 'url', 'detailUrl', 'link'))
    item_url = str(raw_url) if raw_url else (
        ITEM_URL_TEMPLATE.format(item_id=item_id) if item_id else ''
    )
    if item_url.startswith('//'):
        item_url = 'https:' + item_url
    cover = _pick(d, _IMAGE_KEYS)
    cover_url = str(cover) if cover else ''
    if cover_url.startswith('//'):
        cover_url = 'https:' + cover_url

    return {
        'itemId': item_id,
        'title': str(_pick(d, _TITLE_KEYS) or ''),
        'price': _norm_price(_pick(d, _PRICE_KEYS)),
        'status': _norm_status(_pick(d, _STATUS_KEYS)),
        'coverUrl': cover_url,
        'itemUrl': item_url,
        'updatedAt': str(_pick(d, _TIME_KEYS) or ''),
    }


def _deep_find_item_arrays(node: Any, *, depth: int = 0, max_depth: int = 8) -> List[List[Dict[str, Any]]]:
    """在任意 JSON 里递归找出「商品对象数组」。"""
    found: List[List[Dict[str, Any]]] = []
    if depth > max_depth:
        return found
    if isinstance(node, list):
        item_like = [x for x in node if _looks_like_item(x)]
        if item_like and len(item_like) >= max(1, len(node) // 2):
            found.append(item_like)
        else:
            for child in node[:50]:
                found.extend(_deep_find_item_arrays(child, depth=depth + 1, max_depth=max_depth))
    elif isinstance(node, dict):
        for value in list(node.values())[:60]:
            found.extend(_deep_find_item_arrays(value, depth=depth + 1, max_depth=max_depth))
    return found


def extract_items_from_payload(payload: Any) -> List[Dict[str, Any]]:
    """从 mtop 响应中提取并归一化商品列表。"""
    arrays = _deep_find_item_arrays(payload)
    if not arrays:
        return []
    best = max(arrays, key=len)
    return [_normalize_item(x) for x in best]


def _parse_mtop_api(url: str) -> Optional[Dict[str, str]]:
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
    except Exception:
        return None
    if not any(h in (parsed.netloc or '') for h in _MTOP_HOSTS):
        return None
    parts = [p for p in (parsed.path or '').split('/') if p]
    if len(parts) < 3 or parts[0] != 'h5' or not parts[1].startswith('mtop.'):
        return None
    return {'api': parts[1], 'version': parts[2]}


def _fetch_via_mtop(
    page: Page,
    *,
    api: str,
    version: str,
    status: str,
    page_no: int,
    page_size: int,
    max_pages: int,
) -> Dict[str, Any]:
    """直调已配置的列表接口，按页累积。"""
    frame = find_business_frame(page) or page.main_frame
    all_items: List[Dict[str, Any]] = []
    pages_read = 0
    last_ret: Any = None

    for offset in range(max(1, max_pages)):
        current_page = page_no + offset
        data: Dict[str, Any] = {
            'pageNumber': current_page,
            'pageNo': current_page,
            'currentPage': current_page,
            'pageSize': page_size,
            'rowsPerPage': page_size,
        }
        if status:
            data['itemStatus'] = status
            data['status'] = status

        res = call_mtop(frame, api, data=data, version=version)
        last_ret = res.get('ret')
        if res.get('sessionExpired'):
            return {
                'ok': False,
                'need_login': True,
                'message': '闲鱼会话已过期，请重新登录',
                'source': 'mtop',
            }
        if not res.get('ok') or not ret_is_success(last_ret):
            if all_items:
                break
            return {
                'ok': False,
                'message': f"接口调用失败 api={api} ret={last_ret}",
                'source': 'mtop',
            }

        batch = extract_items_from_payload(res.get('data'))
        pages_read += 1
        if not batch:
            break
        all_items.extend(batch)
        if len(batch) < page_size:
            break

    return {
        'ok': True,
        'source': 'mtop',
        'api': api,
        'items': _dedupe(all_items),
        'pages_read': pages_read,
        'ret': last_ret,
    }


def _fetch_via_capture(
    page: Page,
    *,
    settle_ms: int,
    scroll_steps: int,
) -> Dict[str, Any]:
    """未配置 API 名时：打开列表页并从 mtop 响应里自动识别商品列表。"""
    captured: List[Dict[str, Any]] = []

    def on_response(response):
        info = _parse_mtop_api(response.url)
        if not info:
            return
        if not any(k in info['api'].lower() for k in PROBE_ITEM_KEYWORDS):
            return
        try:
            body = response.json()
        except Exception:
            return
        items = extract_items_from_payload(body)
        if items:
            captured.append({'api': info['api'], 'version': info['version'], 'items': items})

    page.on('response', on_response)
    try:
        page.goto(ITEM_LIST_URL, wait_until='domcontentloaded', timeout=NAV_TIMEOUT_MS)
        page.wait_for_timeout(settle_ms)
        for _ in range(max(0, scroll_steps)):
            try:
                page.mouse.wheel(0, 2200)
            except Exception:
                pass
            page.wait_for_timeout(1500)
    except Exception as exc:
        logger.warning('列表页导航异常: %s', exc)
    finally:
        try:
            page.remove_listener('response', on_response)
        except Exception:
            pass

    if not captured:
        return {'ok': False, 'source': 'capture', 'message': '未从 mtop 响应中识别到商品列表'}

    best = max(captured, key=lambda c: len(c['items']))
    merged: List[Dict[str, Any]] = []
    for entry in captured:
        if entry['api'] == best['api']:
            merged.extend(entry['items'])

    return {
        'ok': True,
        'source': 'capture',
        'api': best['api'],
        'api_version': best['version'],
        'items': _dedupe(merged),
        'hint': (
            f"已自动识别商品列表接口 {best['api']}。"
            '建议写入 src/spider/goofish/config.py 的 ITEM_LIST_API 以启用可控分页'
        ),
    }


def _load_dom_script() -> str:
    raw = _DOM_SCRIPT.read_text(encoding='utf-8')
    raw = raw.lstrip('\ufeff')
    raw = re.sub(r'^/\*[\s\S]*?\*/\s*', '', raw, count=1)
    return raw.strip()


_EVAL_DOM = """
async (args) => {
  const run = new Function('return ' + args.source);
  return await run();
}
"""


def _fetch_via_dom(page: Page) -> Dict[str, Any]:
    """DOM 兜底抓取。"""
    if not _DOM_SCRIPT.exists():
        return {'ok': False, 'source': 'dom', 'message': f'兜底脚本缺失: {_DOM_SCRIPT}'}
    try:
        source = _load_dom_script()
    except Exception as exc:
        return {'ok': False, 'source': 'dom', 'message': f'兜底脚本读取失败: {exc}'}

    frame = find_business_frame(page) or page.main_frame
    try:
        raw = frame.evaluate(_EVAL_DOM, {'source': source})
    except Exception as exc:
        return {'ok': False, 'source': 'dom', 'message': f'兜底脚本执行失败: {exc}'}

    raw = raw or {}
    items = [_normalize_item(x) if not isinstance(x, dict) or 'itemId' not in x else x
             for x in (raw.get('items') or [])]
    return {
        'ok': bool(items),
        'source': 'dom-fallback',
        'items': _dedupe(items),
        'log': raw.get('log'),
        'message': '' if items else 'DOM 兜底未抓到商品（选择器可能已变，需重新探测）',
    }


def _dedupe(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    out = []
    for item in items:
        key = item.get('itemId') or item.get('itemUrl') or item.get('title')
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def fetch_items(
    page: Page,
    *,
    status: str = '',
    page_no: int = 1,
    page_size: int = 40,
    max_pages: int = 5,
    wait_login_timeout_sec: int = 0,
    settle_ms: int = 8000,
    scroll_steps: int = 3,
    allow_dom_fallback: bool = True,
) -> Dict[str, Any]:
    """获取在线商品列表。"""
    gate = ensure_logged_in(page, target_url=ITEM_LIST_URL, wait_login_timeout_sec=wait_login_timeout_sec)
    if not gate.get('ok'):
        return {
            'ok': False,
            'need_login': gate.get('need_login', True),
            'message': gate.get('message'),
            'source': 'login',
            'items': [],
        }

    attempts: List[Dict[str, Any]] = []

    if ITEM_LIST_API:
        result = _fetch_via_mtop(
            page,
            api=ITEM_LIST_API,
            version=ITEM_LIST_API_VERSION,
            status=status,
            page_no=page_no,
            page_size=page_size,
            max_pages=max_pages,
        )
        if result.get('ok') or result.get('need_login'):
            result.setdefault('items', [])
            result['total'] = len(result.get('items') or [])
            return result
        attempts.append(result)

    captured = _fetch_via_capture(page, settle_ms=settle_ms, scroll_steps=scroll_steps)
    if captured.get('ok'):
        captured['total'] = len(captured.get('items') or [])
        if attempts:
            captured['fallback_from'] = attempts
        return captured
    attempts.append(captured)

    if allow_dom_fallback:
        dom = _fetch_via_dom(page)
        dom['total'] = len(dom.get('items') or [])
        dom['fallback_from'] = attempts
        if dom.get('ok'):
            return dom
        attempts.append(dom)

    return {
        'ok': False,
        'items': [],
        'total': 0,
        'source': 'none',
        'attempts': attempts,
        'message': (
            '未能获取商品列表。请先调用 POST /api/goofish/probe 探测真实接口，'
            '并把商品列表 API 名填入 src/spider/goofish/config.py 的 ITEM_LIST_API'
        ),
    }
