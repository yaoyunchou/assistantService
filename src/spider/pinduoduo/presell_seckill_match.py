"""拼多多 ERP 预售订单 × 安特限时秒杀 商品对照。

通过货号（5–6 位数字）或标题归一化模糊匹配，判断预售商品是否正在秒杀活动中。
匹配前强制校验「性别 + 品类」：双方都能识别且冲突时一律否决（含货号命中）。
联动 antexiadan_goods_search：本地有缓存直接用，无缓存则浏览器 search-goods-list。
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

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
    r'\d+天内发货|专柜代购|不支持退换|'
    r'国内一线代工|一线代工|全量检品|特价秒杀|自主产品|不包邮旅行装'
)

# 性别：长词优先，避免误伤
_GENDER_PATTERNS: List[Tuple[str, Tuple[str, ...]]] = [
    ('女', ('女士', '女款', '女式', '女装', '女人', '女生', '女童', '女')),
    ('男', ('男士', '男款', '男式', '男装', '男人', '男生', '男童', '男')),
]

# 品类：叶子互斥；「内衣」为父类，可与文胸/内裤兼容
_CATEGORY_PATTERNS: List[Tuple[str, Tuple[str, ...]]] = [
    ('文胸', ('文胸', '胸罩', '美背', 'bra', 'Bra', 'BRA')),
    ('内裤', ('内裤', '三角裤', '平角裤', '四角裤', '底裤')),
    ('内衣', ('保暖内衣', '塑身衣', '内衣')),
    ('上衣', ('上衣', 'T恤', 't恤', '衬衫', '卫衣', '外套', '开衫', '背心', '吊带', '短袖')),
    ('裤子', ('裤子', '长裤', '短裤', '休闲裤', '运动裤', '打底裤', '牛仔裤', '西装裤')),
    ('鞋子', ('运动鞋', '皮鞋', '单鞋', '高跟鞋', '帆布鞋', '靴子', '鞋子')),
    ('拖鞋', ('拖鞋', '凉拖', '棉拖', '人字拖', '洞洞鞋')),
]

# 互斥叶子品类：两边都抽到且无交集 → 冲突
_EXCLUSIVE_CATEGORIES = frozenset({'文胸', '内裤', '上衣', '裤子', '鞋子', '拖鞋'})

# title_overlap 最低公共子串长度（原 10 易被营销前缀误伤）
_MIN_TITLE_OVERLAP = 12


def _product_codes(text: str) -> set:
    return set(_CODE_RE.findall(text or ''))


def _normalize_title(text: str) -> str:
    s = _STRIP_PREFIX_RE.sub('', text or '')
    s = _NOISE_RE.sub('', s)
    return s.strip().lower()


def _presell_match_text(row: Dict[str, Any]) -> str:
    return str(row.get('goodsSpecText') or row.get('specSnippet') or '').strip()


def extract_gender(text: str) -> Optional[str]:
    """从标题提取性别：女 / 男；同时出现则返回 None（无法判定）。"""
    hits: Set[str] = set()
    raw = text or ''
    for gender, kws in _GENDER_PATTERNS:
        for kw in kws:
            if kw in raw:
                hits.add(gender)
                break
    if hits == {'女'}:
        return '女'
    if hits == {'男'}:
        return '男'
    return None


def extract_categories(text: str) -> Set[str]:
    """从标题提取品类集合。"""
    raw = text or ''
    found: Set[str] = set()
    for cat, kws in _CATEGORY_PATTERNS:
        for kw in kws:
            if kw in raw:
                found.add(cat)
                break
    return found


def _exclusive_leaves(cats: Set[str]) -> Set[str]:
    return cats & _EXCLUSIVE_CATEGORIES


def categories_compatible(presell_cats: Set[str], seckill_cats: Set[str]) -> bool:
    """品类是否兼容。

    - 任一侧无品类 → 不拦截（美妆等大量无品类）
    - 两边互斥叶子均非空：必须有交集，否则冲突（文胸≠内裤等）
    - 「内衣」为父类：可与文胸/内裤兼容；不可与上衣/裤子/鞋/拖鞋兼容
    - 其它有交集的品类集合 → 兼容
    """
    if not presell_cats or not seckill_cats:
        return True

    p_leaf = _exclusive_leaves(presell_cats)
    s_leaf = _exclusive_leaves(seckill_cats)

    if p_leaf and s_leaf:
        return bool(p_leaf & s_leaf)

    underwear_ok = frozenset({'文胸', '内裤'})

    # 预售仅父类内衣
    if '内衣' in presell_cats and not p_leaf:
        if s_leaf:
            return bool(s_leaf <= underwear_ok)
        return '内衣' in seckill_cats

    # 秒杀仅父类内衣
    if '内衣' in seckill_cats and not s_leaf:
        if p_leaf:
            return bool(p_leaf <= underwear_ok)
        return '内衣' in presell_cats

    return bool(presell_cats & seckill_cats)


def gender_compatible(presell_gender: Optional[str], seckill_gender: Optional[str]) -> bool:
    """双方都能识别性别且不一致 → 冲突；任一侧未知 → 放行。"""
    if not presell_gender or not seckill_gender:
        return True
    return presell_gender == seckill_gender


def tags_compatible(presell_text: str, seckill_text: str) -> bool:
    """性别 + 品类硬约束：冲突则不可匹配。"""
    if not gender_compatible(extract_gender(presell_text), extract_gender(seckill_text)):
        return False
    if not categories_compatible(extract_categories(presell_text), extract_categories(seckill_text)):
        return False
    return True


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
    """返回 (seckill_row, method, detail, score) 或 None。

    任意候选在货号/标题命中后，必须通过性别+品类硬约束，否则跳过。
    """
    if not presell_text:
        return None

    pcodes = _product_codes(presell_text)
    norm_p = _normalize_title(presell_text)
    best_overlap: Optional[Tuple[Dict[str, Any], str, str, int]] = None

    for row in seckill_rows:
        if not _is_seckill_active(row):
            continue
        title = str(row.get('title') or '')
        if not tags_compatible(presell_text, title):
            continue

        scodes = _product_codes(title)
        overlap_codes = pcodes & scodes
        if overlap_codes:
            code = sorted(overlap_codes, key=len, reverse=True)[0]
            return row, 'code', code, 100

        norm_s = _normalize_title(title)
        if len(norm_p) >= 12 and len(norm_s) >= 12:
            if norm_p in norm_s or norm_s in norm_p:
                return row, 'title', None, 90

        if len(norm_p) >= _MIN_TITLE_OVERLAP and len(norm_s) >= _MIN_TITLE_OVERLAP:
            max_len = min(len(norm_p), len(norm_s))
            for length in range(max_len, _MIN_TITLE_OVERLAP - 1, -1):
                for i in range(len(norm_p) - length + 1):
                    chunk = norm_p[i:i + length]
                    if chunk in norm_s:
                        if not best_overlap or length > best_overlap[3]:
                            best_overlap = (row, 'title_overlap', chunk, length)
                        break
                if best_overlap and best_overlap[0] is row:
                    break

    if best_overlap and best_overlap[3] >= _MIN_TITLE_OVERLAP:
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
            'specSnippet': prow.get('specSnippet') or '',
            'goods': prow.get('goods'),
            'payTime': prow.get('payTime'),
            'online': prow.get('online'),
            'purchased': prow.get('purchased'),
            'imgUrl': prow.get('imgUrl'),
            'matchGender': extract_gender(text),
            'matchCategories': sorted(extract_categories(text)),
        }
        if matched:
            seckill_row, method, detail, score = matched
            sk_title = str(seckill_row.get('title') or '')
            item = _attach_goods_search(
                {
                    **base,
                    'inActivity': True,
                    'matchMethod': method,
                    'matchDetail': detail,
                    'matchScore': score,
                    'seckillGender': extract_gender(sk_title),
                    'seckillCategories': sorted(extract_categories(sk_title)),
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
