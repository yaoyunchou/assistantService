"""闲鱼后台接口探测器。

商品列表/发布相关的 mtop 接口只在登录后的 iframe 业务应用里加载，未登录态无法取得
（详见 docs/goofish/闲鱼后台-探测记录.md）。本模块在登录态下捕获真实调用，
把接口名、参数与响应结构落盘，供填入 config.ITEM_LIST_API 与生成测试 fixture。
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, unquote, urlparse

from playwright.sync_api import Page

from spider.goofish.config import (
    ITEM_LIST_URL,
    NAV_TIMEOUT_MS,
    PROBE_ITEM_KEYWORDS,
    PROBE_ROOT,
)
from spider.goofish.login_gate import ensure_logged_in
from spider.goofish.page_guard import list_frames
from utils.logger import get_logger

logger = get_logger('GoofishApiProbe')

_MTOP_HOSTS = ('h5api.m.goofish.com', 'h5api.m.taobao.com', 'acs.m.goofish.com')
# 单个响应样本最多保留的字符数，避免把整页商品数据落盘
_SAMPLE_MAX_CHARS = 20_000


def _parse_mtop_url(url: str) -> Optional[Dict[str, str]]:
    """从 mtop HTTP URL 解析 api 名与版本。

    形如 https://h5api.m.goofish.com/h5/mtop.alibaba.idle.xxx/1.0/?jsv=...
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return None
    if not any(host in (parsed.netloc or '') for host in _MTOP_HOSTS):
        return None
    parts = [p for p in (parsed.path or '').split('/') if p]
    # 期望 ['h5', '<api>', '<version>']
    if len(parts) < 3 or parts[0] != 'h5':
        return None
    api = parts[1]
    version = parts[2]
    if not api.startswith('mtop.'):
        return None
    return {'api': api, 'version': version}


def _extract_request_data(url: str) -> Any:
    """mtop 的业务参数在 query 的 data 字段里（URL-encoded JSON）。"""
    try:
        qs = parse_qs(urlparse(url).query)
        raw = (qs.get('data') or [''])[0]
        if not raw:
            return None
        return json.loads(unquote(raw))
    except Exception:
        return None


def _skeleton(value: Any, *, depth: int = 0, max_depth: int = 4) -> Any:
    """生成 JSON 结构骨架：保留键名与类型，数组只取第一个元素。"""
    if depth >= max_depth:
        return '...'
    if isinstance(value, dict):
        return {k: _skeleton(v, depth=depth + 1, max_depth=max_depth) for k, v in list(value.items())[:40]}
    if isinstance(value, list):
        if not value:
            return []
        return [_skeleton(value[0], depth=depth + 1, max_depth=max_depth), f'...共 {len(value)} 项']
    if isinstance(value, str):
        return f'str({len(value)})'
    if isinstance(value, bool):
        return 'bool'
    if isinstance(value, (int, float)):
        return type(value).__name__
    if value is None:
        return 'null'
    return type(value).__name__


def probe_apis(
    page: Page,
    *,
    target_url: Optional[str] = None,
    wait_login_timeout_sec: int = 0,
    settle_ms: int = 8000,
    scroll_steps: int = 3,
) -> Dict[str, Any]:
    """打开目标页并捕获 mtop 调用。

    Returns:
        { ok, out_dir, apis: [...], candidates: [...], frames, need_login? }
    """
    url = target_url or ITEM_LIST_URL

    gate = ensure_logged_in(page, target_url=url, wait_login_timeout_sec=wait_login_timeout_sec)
    if not gate.get('ok'):
        return {
            'ok': False,
            'need_login': gate.get('need_login', True),
            'message': gate.get('message'),
            'url': gate.get('url'),
        }

    captured: List[Dict[str, Any]] = []
    seen: set = set()

    def on_response(response):
        info = _parse_mtop_url(response.url)
        if not info:
            return
        key = (info['api'], info['version'])
        try:
            body = response.json()
        except Exception:
            body = None
        record: Dict[str, Any] = {
            'api': info['api'],
            'version': info['version'],
            'status': response.status,
            'requestData': _extract_request_data(response.url),
            'ret': (body or {}).get('ret') if isinstance(body, dict) else None,
            'responseSkeleton': _skeleton(body) if body is not None else None,
        }
        if key in seen:
            # 同一接口的翻页调用只补记参数，便于看出分页字段
            for item in captured:
                if (item['api'], item['version']) == key:
                    item.setdefault('extraRequests', []).append(record['requestData'])
                    break
            return
        seen.add(key)
        record['_body'] = body
        captured.append(record)

    page.on('response', on_response)
    try:
        page.goto(url, wait_until='domcontentloaded', timeout=NAV_TIMEOUT_MS)
        page.wait_for_timeout(settle_ms)
        # 滚动触发懒加载与后续分页请求
        for _ in range(max(0, scroll_steps)):
            try:
                page.mouse.wheel(0, 2000)
            except Exception:
                pass
            page.wait_for_timeout(1500)
    except Exception as exc:
        logger.warning('探测导航异常: %s', exc)
    finally:
        try:
            page.remove_listener('response', on_response)
        except Exception:
            pass

    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    out_dir = PROBE_ROOT / stamp
    out_dir.mkdir(parents=True, exist_ok=True)

    apis_summary = []
    for item in captured:
        body = item.pop('_body', None)
        apis_summary.append(item)
        if body is not None:
            safe_name = item['api'].replace('.', '_')
            sample_path = out_dir / f'sample-{safe_name}.json'
            try:
                text = json.dumps(body, ensure_ascii=False, indent=2)[:_SAMPLE_MAX_CHARS]
                sample_path.write_text(text, encoding='utf-8')
            except Exception:
                pass

    candidates = [
        a['api'] for a in apis_summary
        if any(k in a['api'].lower() for k in PROBE_ITEM_KEYWORDS)
    ]

    frames = list_frames(page)
    try:
        (out_dir / 'apis.json').write_text(
            json.dumps(apis_summary, ensure_ascii=False, indent=2, default=str),
            encoding='utf-8',
        )
        (out_dir / 'frames.json').write_text(
            json.dumps(frames, ensure_ascii=False, indent=2),
            encoding='utf-8',
        )
    except Exception as exc:
        logger.warning('探测结果写盘失败: %s', exc)

    try:
        page.screenshot(path=str(out_dir / 'screenshot.png'), full_page=True)
    except Exception:
        pass

    logger.info('探测完成 目录=%s 捕获=%d 候选=%s', out_dir, len(apis_summary), candidates)
    return {
        'ok': True,
        'out_dir': str(out_dir),
        'url': page.url,
        'captured_count': len(apis_summary),
        'apis': apis_summary,
        'candidates': candidates,
        'frames': frames,
        'message': (
            f'捕获 {len(apis_summary)} 个 mtop 接口。'
            + (
                f"商品相关候选: {', '.join(candidates)}。请把商品列表接口名填入 "
                'src/spider/goofish/config.py 的 ITEM_LIST_API'
                if candidates
                else '未识别到商品相关接口，请检查是否已进入商品列表页'
            )
        ),
    }
