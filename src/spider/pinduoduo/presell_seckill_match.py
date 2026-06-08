"""拼多多 ERP 预售订单 × 安特限时秒杀 商品对照。

通过货号（5–6 位数字）或标题归一化模糊匹配，判断预售商品是否正在秒杀活动中。
联动 antexiadan_goods_search：本地有缓存直接用，无缓存则浏览器 search-goods-list。
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from spider.antexiadan.goods_search import (
    collect_presell_keywords,
    ensure_goods_search_batch,
    extract_search_keyword,
)
from spider.antexiadan.seckill_store import list_products
from spider.pinduoduo.presell_store import list_presell_records
from utils.logger import get_logger

logger = get_logger('PresellSeckillMatch')

_CODE_RE = re.compile(r'\d{5,6}')
_STRIP_PREFIX_RE = re.compile(
    r'^(彼选)?匠品?(同款)?|【[^】]*】|\[[^\]]*\]|限时抢购|限时秒杀'
)
_NOISE_RE = re.compile(
    r'[\s,，x×*·/\\|（）()【】\[\]{}:：;；!?！?。.、\-—_+]|'
    r'\d+天内发货|专柜代购|不支持退换'
)


def _product_codes(text: str) -> set:
    return set(_CODE_RE.findall(text or ''))


def _normalize_title(text: str) -> str:
    s = _STRIP_PREFIX_RE.sub('', text or '')
    s = _NOISE_RE.sub('', s)
    return s.strip().lower()


def _presell_match_text(row: Dict[str, Any]) -> str:
    return str(row.get('goodsSpecText') or row.get('specSnippet') or '').strip()


def _is_seckill_active(row: Dict[str, Any], *, now: Optional[datetime] = None) -> bool:
    """活动是否仍在有效期内（排除已结束或 end_time 已过）。"""
    if str(row.get('activity_status') or '') == '已结束':
        return False

    current = now or datetime.now()
    end_time = row.get('end_time')
    if end_time:
        if isinstance(end_time, datetime):
            end_dt = end_time
        else:
            try:
                end_dt = datetime.strptime(str(end_time)[:19], '%Y-%m-%d %H:%M:%S')
            except ValueError:
                end_dt = None
        if end_dt and end_dt < current:
            return False

    end_unix = row.get('end_unix')
    if end_unix:
        try:
            if int(end_unix) < int(current.timestamp()):
                return False
        except (TypeError, ValueError):
            pass
    return True


def _match_presell_to_seckill(
    presell_text: str,
    seckill_rows: List[Dict[str, Any]],
) -> Optional[Tuple[Dict[str, Any], str, Any, int]]:
    """返回 (seckill_row, method, detail, score) 或 None。"""
    if not presell_text:
        return None

    pcodes = _product_codes(presell_text)
    norm_p = _normalize_title(presell_text)
    best_overlap: Optional[Tuple[Dict[str, Any], str, str, int]] = None

    for row in seckill_rows:
        if not _is_seckill_active(row):
            continue
        title = str(row.get('title') or '')
        scodes = _product_codes(title)
        overlap_codes = pcodes & scodes
        if overlap_codes:
            code = sorted(overlap_codes, key=len, reverse=True)[0]
            return row, 'code', code, 100

        norm_s = _normalize_title(title)
        if len(norm_p) >= 12 and len(norm_s) >= 12:
            if norm_p in norm_s or norm_s in norm_p:
                return row, 'title', None, 90

        if len(norm_p) >= 10 and len(norm_s) >= 10:
            max_len = min(len(norm_p), len(norm_s))
            for length in range(max_len, 9, -1):
                for i in range(len(norm_p) - length + 1):
                    chunk = norm_p[i:i + length]
                    if chunk in norm_s:
                        if not best_overlap or length > best_overlap[3]:
                            best_overlap = (row, 'title_overlap', chunk, length)
                        break
                if best_overlap and best_overlap[0] is row:
                    break

    if best_overlap and best_overlap[3] >= 10:
        return best_overlap
    return None


def _serialize_seckill(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'seckill_id': row.get('seckill_id'),
        'goods_id': row.get('goods_id'),
        'title': row.get('title'),
        'activity_status': row.get('activity_status'),
        'group_title': row.get('group_title'),
        'slot_time': row.get('slot_time'),
        'price_display': row.get('price_display'),
        'start_time': str(row.get('start_time') or ''),
        'end_time': str(row.get('end_time') or ''),
        'goods_url': row.get('goods_url'),
        'seckill_image': row.get('seckill_image'),
    }


def _attach_goods_search(
    base: Dict[str, Any],
    *,
    search_keyword: Optional[str],
    search_result: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """合并安特商品搜索信息到对照行。"""
    item = {**base, 'searchKeyword': search_keyword}
    if not search_result:
        item['goodsSearch'] = None
        item['searchError'] = None if not search_keyword else '未执行搜索'
        return item

    item['goodsSearch'] = search_result.get('goodsSearch')
    item['searchFromCache'] = bool(search_result.get('fromCache'))
    if search_result.get('ok'):
        item['searchError'] = None
    else:
        item['searchError'] = search_result.get('error')
    return item


def compare_presell_with_seckill(
    *,
    online: bool = True,
    mark_filter: str = 'unmarked',
    seckill_status: str = '秒杀中',
    presell_page_size: int = 200,
    seckill_limit: int = 500,
    browser_pool=None,
    use_goods_search: bool = True,
) -> Dict[str, Any]:
    """预售表 vs 安特秒杀表对照。

    seckill_status: 默认「秒杀中」；传空字符串则与全部秒杀商品比对。
    use_goods_search: 为 True 时联动 antexiadan_goods_search（方案 A：无缓存走浏览器）。
    """
    presell_result = list_presell_records(
        online=online,
        mark_filter=mark_filter,
        page=1,
        page_size=presell_page_size,
    )
    presell_rows: List[Dict[str, Any]] = presell_result.get('items') or []

    seckill_rows = list_products(
        activity_status=seckill_status or None,
        exclude_ended=True,
        limit=seckill_limit,
    )

    order_keywords = collect_presell_keywords(presell_rows) if use_goods_search else {}
    search_map: Dict[str, Dict[str, Any]] = {}
    if use_goods_search and order_keywords:
        search_map = ensure_goods_search_batch(
            list(order_keywords.values()),
            browser_pool=browser_pool,
        )

    in_activity: List[Dict[str, Any]] = []
    not_in_activity: List[Dict[str, Any]] = []

    for prow in presell_rows:
        text = _presell_match_text(prow)
        matched = _match_presell_to_seckill(text, seckill_rows)
        order_no = str(prow.get('orderNo') or '')
        search_kw = order_keywords.get(order_no) or extract_search_keyword(text)
        search_result = search_map.get(search_kw) if search_kw else None
        base = {
            'orderNo': prow.get('orderNo'),
            'erpOrderNo': prow.get('erpOrderNo'),
            'goodsSpecText': text,
            'payTime': prow.get('payTime'),
            'online': prow.get('online'),
            'purchased': prow.get('purchased'),
            'imgUrl': prow.get('imgUrl'),
        }
        if matched:
            seckill_row, method, detail, score = matched
            item = _attach_goods_search(
                {
                    **base,
                    'inActivity': True,
                    'matchMethod': method,
                    'matchDetail': detail,
                    'matchScore': score,
                    'seckill': _serialize_seckill(seckill_row),
                },
                search_keyword=search_kw,
                search_result=search_result,
            )
            in_activity.append(item)
        else:
            not_in_activity.append(_attach_goods_search(
                {**base, 'inActivity': False},
                search_keyword=search_kw,
                search_result=search_result,
            ))

    logger.info(
        '预售×秒杀对照: presell=%d seckill(%s)=%d 命中=%d',
        len(presell_rows),
        seckill_status or '全部',
        len(seckill_rows),
        len(in_activity),
    )

    return {
        'presellTotal': len(presell_rows),
        'presellFilter': {
            'online': online,
            'markFilter': mark_filter,
        },
        'seckillTotal': len(seckill_rows),
        'seckillActivityStatus': seckill_status or None,
        'inActivityCount': len(in_activity),
        'notInActivityCount': len(not_in_activity),
        'inActivity': in_activity,
        'notInActivity': not_in_activity,
    }
