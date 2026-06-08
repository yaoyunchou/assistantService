"""安特商品搜索（search-goods-list）。

通过已登录浏览器拦截 pcapi 的 key/version，再请求 search-goods-list 并写入
antexiadan_goods_search。不依赖 .env 中的 ANTEXI_API_KEY。
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

from config import Config
from spider.antexiadan.goods_search_store import (
    get_by_keyword,
    get_by_keywords,
    init_db,
    serialize_row,
    upsert_from_api_response,
)
from utils.logger import get_logger

logger = get_logger('AntexiadanGoodsSearch')

_CODE_RE = re.compile(r'\d{5,6}')

_PCAPI_HOST = 'pcapi.antexiadan.com'
_HOMEPAGE_URL = 'https://pc.antexiadan.com/homepage'


def extract_search_keyword(text: str) -> Optional[str]:
    """从预售标题提取搜索词（最长 5–6 位数字货号）。"""
    codes = _CODE_RE.findall(text or '')
    if not codes:
        return None
    return sorted(codes, key=len, reverse=True)[0]


def capture_pcapi_credentials(page) -> Dict[str, str]:
    """打开安特首页，从 pcapi 请求中拦截 key 与 version。"""
    captured: Dict[str, str] = {}

    def on_request(req):
        if _PCAPI_HOST not in req.url or captured.get('key'):
            return
        try:
            qs = parse_qs(urlparse(req.url).query)
            key = (qs.get('key') or [None])[0]
            version = (qs.get('version') or [None])[0]
            if key:
                captured['key'] = str(key)
                if version:
                    captured['version'] = str(version)
                logger.info('安特：拦截 pcapi key（长度 %d）', len(key))
        except Exception:
            pass

    page.on('request', on_request)
    try:
        page.goto(_HOMEPAGE_URL, wait_until='domcontentloaded', timeout=60_000)
    except Exception:
        pass
    for _ in range(20):
        if captured.get('key'):
            break
        page.wait_for_timeout(500)

    page.remove_listener('request', on_request)
    if captured.get('key') and not captured.get('version'):
        captured['version'] = Config.ANTEXI_API_VERSION
    return captured


def fetch_search_goods_list(
    keyword: str,
    *,
    api_key: str,
    version: Optional[str] = None,
    page_size: int = 16,
    page_index: int = 1,
) -> Dict[str, Any]:
    """直连 pcapi search-goods-list（key 来自浏览器拦截）。"""
    kw = str(keyword or '').strip()
    key = str(api_key or '').strip()
    if not kw:
        raise ValueError('keyword 不能为空')
    if not key:
        raise ValueError('缺少 pcapi key')

    ver = (version or Config.ANTEXI_API_VERSION or '20251218').strip()
    qs = urlencode({'key': key, 'version': ver})
    url = f'https://{_PCAPI_HOST}/v1/selection/search-goods-list?{qs}'
    body = urlencode({
        'class_id': '',
        'keyword': kw,
        'page_size': str(page_size),
        'page_index': str(page_index),
    }).encode('utf-8')

    req = Request(
        url,
        data=body,
        method='POST',
        headers={
            'Accept': 'application/json',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'Referer': 'https://pc.antexiadan.com/',
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
            ),
        },
    )
    with urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode('utf-8'))

    if data.get('flag') != 200:
        raise ValueError(f"search-goods-list flag={data.get('flag')} msg={data.get('msg')}")
    return data


def search_and_cache(
    keyword: str,
    *,
    api_key: str,
    version: Optional[str] = None,
) -> Dict[str, Any]:
    """搜索并 UPSERT 到 antexiadan_goods_search。"""
    api_body = fetch_search_goods_list(keyword, api_key=api_key, version=version)
    row = upsert_from_api_response(keyword, api_body)
    return serialize_row(row) or {}


def ensure_goods_search(
    keyword: str,
    *,
    browser_pool=None,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    """本地有缓存则直接返回；否则通过浏览器搜索并入库。"""
    kw = str(keyword or '').strip()
    if not kw:
        return {'ok': False, 'keyword': '', 'fromCache': False, 'goodsSearch': None, 'error': '无搜索词'}

    if not force_refresh:
        cached = get_by_keyword(kw)
        if cached:
            return {
                'ok': True,
                'keyword': kw,
                'fromCache': True,
                'goodsSearch': serialize_row(cached),
            }

    if not browser_pool:
        return {
            'ok': False,
            'keyword': kw,
            'fromCache': False,
            'goodsSearch': None,
            'error': '本地无缓存且浏览器池未初始化',
        }

    def _run(page):
        creds = capture_pcapi_credentials(page)
        if not creds.get('key'):
            return {
                'ok': False,
                'error': '未能拦截 pcapi key，请确认浏览器已登录 pc.antexiadan.com',
            }
        try:
            row = search_and_cache(
                kw,
                api_key=creds['key'],
                version=creds.get('version'),
            )
            return {'ok': True, 'goodsSearch': row}
        except ValueError as e:
            return {'ok': False, 'error': str(e)}

    try:
        result = browser_pool.execute(_run, timeout=90)
    except Exception as e:
        return {
            'ok': False,
            'keyword': kw,
            'fromCache': False,
            'goodsSearch': None,
            'error': f'浏览器搜索异常: {e}',
        }

    if not result.get('ok'):
        return {
            'ok': False,
            'keyword': kw,
            'fromCache': False,
            'goodsSearch': None,
            'error': result.get('error') or '搜索失败',
        }

    return {
        'ok': True,
        'keyword': kw,
        'fromCache': False,
        'goodsSearch': result.get('goodsSearch'),
    }


def ensure_goods_search_batch(
    keywords: List[str],
    *,
    browser_pool=None,
    force_refresh: bool = False,
) -> Dict[str, Dict[str, Any]]:
    """批量 ensure：一次浏览器会话拦截 key，再逐个搜索缺失 keyword。"""
    keys = [str(k).strip() for k in keywords if str(k).strip()]
    unique: List[str] = list(dict.fromkeys(keys))
    out: Dict[str, Dict[str, Any]] = {}

    if not unique:
        return out

    try:
        init_db()
    except Exception as e:
        logger.warning('[antexiadan] init_db 跳过: %s', e)

    cached_map: Dict[str, Dict[str, Any]] = {}
    if not force_refresh:
        cached_map = get_by_keywords(unique)

    for kw in unique:
        if kw in cached_map:
            out[kw] = {
                'ok': True,
                'keyword': kw,
                'fromCache': True,
                'goodsSearch': serialize_row(cached_map[kw]),
            }

    missing = [kw for kw in unique if kw not in out]
    if not missing:
        return out

    if not browser_pool:
        for kw in missing:
            out[kw] = {
                'ok': False,
                'keyword': kw,
                'fromCache': False,
                'goodsSearch': None,
                'error': '本地无缓存且浏览器池未初始化',
            }
        return out

    def _run_batch(page):
        creds = capture_pcapi_credentials(page)
        if not creds.get('key'):
            return {
                'ok': False,
                'error': '未能拦截 pcapi key，请确认浏览器已登录 pc.antexiadan.com',
                'results': {},
            }
        results: Dict[str, Any] = {}
        errors: Dict[str, str] = {}
        for kw in missing:
            try:
                results[kw] = search_and_cache(
                    kw,
                    api_key=creds['key'],
                    version=creds.get('version'),
                )
            except Exception as e:
                errors[kw] = str(e)
        return {'ok': True, 'results': results, 'errors': errors}

    try:
        batch = browser_pool.execute(_run_batch, timeout=max(90, 30 + len(missing) * 10))
    except Exception as e:
        err = f'浏览器搜索异常: {e}'
        for kw in missing:
            out[kw] = {
                'ok': False,
                'keyword': kw,
                'fromCache': False,
                'goodsSearch': None,
                'error': err,
            }
        return out

    if not batch.get('ok'):
        err = batch.get('error') or '搜索失败'
        for kw in missing:
            out[kw] = {
                'ok': False,
                'keyword': kw,
                'fromCache': False,
                'goodsSearch': None,
                'error': err,
            }
        return out

    for kw, row in (batch.get('results') or {}).items():
        out[kw] = {
            'ok': True,
            'keyword': kw,
            'fromCache': False,
            'goodsSearch': row,
        }
    for kw, err in (batch.get('errors') or {}).items():
        out[kw] = {
            'ok': False,
            'keyword': kw,
            'fromCache': False,
            'goodsSearch': None,
            'error': err,
        }
    for kw in missing:
        out.setdefault(kw, {
            'ok': False,
            'keyword': kw,
            'fromCache': False,
            'goodsSearch': None,
            'error': '搜索无结果',
        })
    return out


def collect_presell_keywords(presell_rows: List[Dict[str, Any]]) -> Dict[str, str]:
    """orderNo -> keyword（无货号则不在 map 中）。"""
    mapping: Dict[str, str] = {}
    for row in presell_rows:
        text = str(row.get('goodsSpecText') or row.get('specSnippet') or '').strip()
        kw = extract_search_keyword(text)
        order_no = str(row.get('orderNo') or '')
        if kw and order_no:
            mapping[order_no] = kw
    return mapping
