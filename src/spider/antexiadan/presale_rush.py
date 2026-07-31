"""安特预售抢购：候选商品、计划创建、加购/结算编排。

流程：
  - 开售前 20 分钟：详情页加入购物车
  - 开售时刻：购物车结算/提交订单（第三方支付页停住并通知）
"""
from __future__ import annotations

import re
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from config import Config
from spider.antexiadan.login import ensure_logged_in, handle_captcha, has_captcha
from utils.logger import get_logger

logger = get_logger('AntexiadanPresaleRush')

_CART_URL = 'https://pc.antexiadan.com/cart'
_HOMEPAGE = 'https://pc.antexiadan.com/homepage'

_ADD_CART_TEXTS = ('加入购物车', '加购', '加入采购车', '加入进货单')
_CHECKOUT_TEXTS = ('去结算', '结算', '提交订单', '立即下单', '确认下单')


def _advance_minutes() -> int:
    n = int(getattr(Config, 'ANTEXIADAN_PRESALE_CART_ADVANCE_MIN', 20) or 20)
    return max(0, min(n, 120))


def _parse_qty_from_text(text: str) -> int:
    raw = (text or '').strip()
    if not raw:
        return 1
    m = re.search(r'[xX×]\s*(\d{1,4})\b', raw)
    if m:
        return max(1, int(m.group(1)))
    m = re.search(r'数量[:：\s]*(\d{1,4})', raw)
    if m:
        return max(1, int(m.group(1)))
    return 1


def _parse_presell_goods(prow: Dict[str, Any]) -> List[Dict[str, Any]]:
    """从预售行解析 goods JSON / specSnippet，得到 [{title,spec,qty}, ...]。"""
    import json as _json
    out: List[Dict[str, Any]] = []
    raw = prow.get('goods')
    parsed = None
    if isinstance(raw, list):
        parsed = raw
    elif isinstance(raw, str) and raw.strip():
        try:
            parsed = _json.loads(raw)
        except Exception:
            parsed = None
    if isinstance(parsed, list):
        for g in parsed:
            if not isinstance(g, dict):
                continue
            try:
                qty = int(g.get('qty') or 0) or 1
            except (TypeError, ValueError):
                qty = 1
            out.append({
                'title': str(g.get('title') or '').strip(),
                'spec': str(g.get('spec') or '').strip(),
                'qty': max(1, qty),
            })
    if out:
        return out
    snippet = str(prow.get('specSnippet') or '').strip()
    full = str(prow.get('goodsSpecText') or '').strip()
    spec = snippet
    if not spec and full:
        parts = full.rsplit(' ', 1)
        spec = parts[-1] if len(parts) > 1 else full
    if spec:
        out.append({
            'title': '',
            'spec': re.sub(r'[xX×]\s*\d+\s*$', '', spec).strip(' ,，'),
            'qty': _parse_qty_from_text(full or snippet),
        })
    return out


def _suggest_presell_matches() -> List[Dict[str, Any]]:
    """对照预售单，返回已命中秒杀的条目（含颜色规格、数量）。同商品不同规格各一条。"""
    out: List[Dict[str, Any]] = []
    try:
        from spider.pinduoduo.presell_seckill_match import compare_presell_with_seckill
        result = compare_presell_with_seckill(
            online=True,
            mark_filter='unmarked',
            seckill_status='预热/待开始',
            use_goods_search=False,
            seckill_limit=2000,
        )
        for item in result.get('inActivity') or []:
            # 已标记（purchased=1）= 已采购，不再出现在抢购候选
            if item.get('purchased'):
                continue
            sk = item.get('seckill') or {}
            goods_list = _parse_presell_goods(item)
            if not goods_list:
                goods_list = [{
                    'title': '',
                    'spec': '',
                    'qty': _parse_qty_from_text(str(item.get('goodsSpecText') or '')),
                }]
            # 一条预售单可能多件 goods；通常一件，按件展开
            for g in goods_list:
                start_raw = sk.get('start_time') or ''
                start_unix = 0
                # serialize 里可能没有 start_unix，从 start_time 解析
                try:
                    st = str(start_raw).replace('T', ' ')[:16]
                    if re.match(r'^\d{4}-\d{2}-\d{2}', st):
                        start_unix = int(datetime.strptime(st, '%Y-%m-%d %H:%M').timestamp())
                except Exception:
                    start_unix = 0
                out.append({
                    'seckillId': str(sk.get('seckill_id') or ''),
                    'goodsId': str(sk.get('goods_id') or ''),
                    'title': sk.get('title') or '',
                    'priceDisplay': sk.get('price_display') or '',
                    'slotTime': sk.get('slot_time') or '',
                    'groupTitle': sk.get('group_title') or '',
                    'activityStatus': sk.get('activity_status') or '',
                    'startTime': _fmt_local_time(start_raw, unix=start_unix),
                    'startUnix': start_unix,
                    'endTime': _fmt_local_time(sk.get('end_time') or ''),
                    'goodsUrl': sk.get('goods_url') or '',
                    'seckillImage': sk.get('seckill_image') or '',
                    'suggestedQty': int(g.get('qty') or 1),
                    'spec': str(g.get('spec') or '').strip(),
                    'presellOrderNo': item.get('orderNo') or '',
                    'presellGoodsSpecText': item.get('goodsSpecText') or '',
                    'matchedPresell': True,
                })
    except Exception as e:
        logger.warning('预售规格对照失败: %s', e)
    return out


def _fmt_local_time(value: Any, *, unix: int = 0) -> str:
    """统一成「YYYY-MM-DD HH:mm」，避免 datetime 被 jsonify 成英文 GMT。"""
    if unix and int(unix) > 0:
        try:
            return datetime.fromtimestamp(int(unix)).strftime('%Y-%m-%d %H:%M')
        except Exception:
            pass
    if isinstance(value, datetime):
        return value.strftime('%Y-%m-%d %H:%M')
    s = str(value or '').strip()
    if not s:
        return ''
    # 已是本地格式
    if re.match(r'^\d{4}-\d{2}-\d{2}', s):
        return s[:16].replace('T', ' ')
    # RFC / GMT 英文串：尽量再解析
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(s)
        if dt.tzinfo:
            dt = dt.astimezone().replace(tzinfo=None)
        return dt.strftime('%Y-%m-%d %H:%M')
    except Exception:
        return s


def list_candidates(*, limit: int = 500) -> Dict[str, Any]:
    """候选：仅「未标记预售单」对照命中的秒杀商品（带颜色/规格）。

    已标记（purchased=1）表示已采购，不展示、不建任务。
    不再补充无预售单关联的秒杀池，避免已买商品仍以「未匹配规格」形式出现。
    """
    matched = _suggest_presell_matches()
    # 补全 startUnix：对照序列化可能缺 unix，回查秒杀库
    need_ids = {m['seckillId'] for m in matched if m.get('seckillId') and not m.get('startUnix')}
    if need_ids:
        try:
            from spider.antexiadan.seckill_store import list_products
            pool = list_products(activity_status='预热/待开始', exclude_ended=True, limit=2000)
            by_sid = {str(r.get('seckill_id') or ''): r for r in pool}
            for m in matched:
                sid = m.get('seckillId') or ''
                row = by_sid.get(sid)
                if not row:
                    continue
                su = int(row.get('start_unix') or 0)
                eu = int(row.get('end_unix') or 0)
                if su:
                    m['startUnix'] = su
                    m['startTime'] = _fmt_local_time(row.get('start_time'), unix=su)
                if eu:
                    m['endTime'] = _fmt_local_time(row.get('end_time'), unix=eu)
                if not m.get('goodsUrl'):
                    m['goodsUrl'] = row.get('goods_url') or ''
                if not m.get('seckillImage'):
                    m['seckillImage'] = row.get('seckill_image') or ''
                if not m.get('priceDisplay'):
                    m['priceDisplay'] = row.get('price_display') or ''
        except Exception as e:
            logger.debug('回填开售时间失败: %s', e)

    seen = set()
    items: List[Dict[str, Any]] = []
    for m in matched:
        key = f"{m.get('seckillId')}|{m.get('presellOrderNo')}|{m.get('spec')}"
        if key in seen:
            continue
        seen.add(key)
        items.append(m)

    items = items[: max(1, int(limit or 500))]

    groups: Dict[str, List[Dict[str, Any]]] = {}
    for it in items:
        key = str(it.get('startUnix') or it.get('startTime') or 'unknown')
        groups.setdefault(key, []).append(it)
    group_list = []
    for key, gitems in sorted(groups.items(), key=lambda x: int(x[0]) if str(x[0]).isdigit() else 0):
        group_list.append({
            'startUnix': gitems[0].get('startUnix'),
            'startTime': gitems[0].get('startTime'),
            'slotTime': gitems[0].get('slotTime'),
            'count': len(gitems),
            'items': gitems,
        })
    matched_n = sum(1 for x in items if x.get('matchedPresell'))
    return {
        'ok': True,
        'total': len(items),
        'matchedPresellCount': matched_n,
        'advanceMinutes': _advance_minutes(),
        'items': items,
        'groups': group_list,
    }


def _normalize_items(raw_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for it in raw_items or []:
        url = str(it.get('goodsUrl') or it.get('goods_url') or '').strip()
        title = str(it.get('title') or '').strip()
        if not url and not title:
            continue
        try:
            qty = int(it.get('qty') or it.get('suggestedQty') or 1)
        except (TypeError, ValueError):
            qty = 1
        qty = max(1, min(qty, 99))
        start_unix = int(it.get('startUnix') or it.get('start_unix') or 0)
        out.append({
            'seckillId': str(it.get('seckillId') or it.get('seckill_id') or ''),
            'goodsId': str(it.get('goodsId') or it.get('goods_id') or ''),
            'title': title,
            'goodsUrl': url,
            'qty': qty,
            'spec': str(it.get('spec') or '').strip(),
            'presellOrderNo': str(it.get('presellOrderNo') or it.get('orderNo') or '').strip(),
            'startUnix': start_unix,
            'startTime': str(it.get('startTime') or it.get('start_time') or ''),
            'slotTime': str(it.get('slotTime') or it.get('slot_time') or ''),
        })
    return out


def create_plans(raw_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """按 startUnix 合并，每个时间点创建加购 + 结算两条任务。"""
    items = _normalize_items(raw_items)
    if not items:
        return {'ok': False, 'error': '未选择有效商品'}

    by_start: Dict[int, List[Dict[str, Any]]] = {}
    for it in items:
        su = int(it.get('startUnix') or 0)
        if su <= 0:
            return {'ok': False, 'error': f'商品缺少开售时间: {it.get("title") or it.get("goodsId")}'}
        by_start.setdefault(su, []).append(it)

    from scheduler import add_task_and_register

    advance_sec = _advance_minutes() * 60
    now = int(time.time())
    plans = []

    for start_unix, gitems in sorted(by_start.items()):
        plan_id = str(uuid.uuid4())
        start_time = gitems[0].get('startTime') or datetime.fromtimestamp(start_unix).strftime('%Y-%m-%d %H:%M')
        payload_items = [{
            'seckillId': x['seckillId'],
            'goodsId': x['goodsId'],
            'title': x['title'],
            'goodsUrl': x['goodsUrl'],
            'qty': x['qty'],
            'spec': x.get('spec') or '',
            'presellOrderNo': x.get('presellOrderNo') or '',
        } for x in gitems]

        cart_at = start_unix - advance_sec
        if cart_at <= now:
            cart_at = now + 5

        base_data = {
            'planId': plan_id,
            'startUnix': start_unix,
            'startTime': start_time,
            'items': payload_items,
        }

        cart_task = add_task_and_register(
            name=f'安特预售加购 · {start_time}（{len(payload_items)}件）',
            task_type='antexiadan_presale_cart',
            data={**base_data, 'phase': 'cart'},
            run_at=cart_at,
        )
        checkout_task = add_task_and_register(
            name=f'安特预售结算 · {start_time}（{len(payload_items)}件）',
            task_type='antexiadan_presale_checkout',
            data={**base_data, 'phase': 'checkout'},
            run_at=start_unix if start_unix > now else now + 10,
        )
        plans.append({
            'planId': plan_id,
            'startUnix': start_unix,
            'startTime': start_time,
            'itemCount': len(payload_items),
            'cartTaskId': cart_task.get('id'),
            'cartRunAt': cart_at,
            'checkoutTaskId': checkout_task.get('id'),
            'checkoutRunAt': start_unix if start_unix > now else now + 10,
        })

    return {'ok': True, 'plans': plans, 'advanceMinutes': _advance_minutes()}


def list_plans() -> Dict[str, Any]:
    from scheduler import list_jobs
    jobs = [
        j for j in list_jobs()
        if j.get('type') in ('antexiadan_presale_cart', 'antexiadan_presale_checkout')
    ]
    by_plan: Dict[str, Dict[str, Any]] = {}
    for j in jobs:
        data = j.get('data') or {}
        pid = str(data.get('planId') or j.get('id'))
        entry = by_plan.setdefault(pid, {
            'planId': pid,
            'startUnix': data.get('startUnix'),
            'startTime': data.get('startTime'),
            'items': data.get('items') or [],
            'tasks': [],
        })
        entry['tasks'].append(j)
    plans = sorted(by_plan.values(), key=lambda x: int(x.get('startUnix') or 0))
    return {'ok': True, 'plans': plans, 'total': len(plans)}


def cancel_plan(plan_id: str) -> Dict[str, Any]:
    from scheduler import list_jobs, remove_task_and_unregister
    removed = []
    for j in list_jobs():
        data = j.get('data') or {}
        if str(data.get('planId') or '') != str(plan_id):
            continue
        tid = j.get('id')
        if tid and remove_task_and_unregister(tid):
            removed.append(tid)
    return {'ok': True, 'removed': removed, 'count': len(removed)}


# ── Playwright 操作 ──────────────────────────────────────────


def _click_by_texts(page, texts: Tuple[str, ...], *, timeout_ms: int = 3000) -> bool:
    for t in texts:
        try:
            loc = page.get_by_text(t, exact=False)
            if loc.count() > 0:
                loc.first.click(timeout=timeout_ms)
                return True
        except Exception:
            continue
    for t in texts:
        try:
            btn = page.locator(f'button:has-text("{t}"), a:has-text("{t}"), div[role="button"]:has-text("{t}")')
            if btn.count() > 0:
                btn.first.click(timeout=timeout_ms)
                return True
        except Exception:
            continue
    return False


def _set_qty(page, qty: int) -> None:
    if qty <= 1:
        return
    # 常见数量输入框
    for sel in (
        'input[type="number"]',
        'input.el-input__inner',
        '.el-input-number input',
        'input[class*="qty"]',
        'input[class*="num"]',
    ):
        try:
            loc = page.locator(sel)
            if loc.count() == 0:
                continue
            el = loc.first
            el.fill(str(qty), timeout=1500)
            return
        except Exception:
            continue
    # 点「+」
    for _ in range(max(0, qty - 1)):
        clicked = False
        for sel in ('.el-input-number__increase', 'button:has-text("+")', '[class*="increase"]'):
            try:
                loc = page.locator(sel)
                if loc.count() > 0:
                    loc.first.click(timeout=800)
                    clicked = True
                    break
            except Exception:
                continue
        if not clicked:
            break


def _select_spec(page, spec: str) -> List[str]:
    """按预售规格文案尝试点选 SKU（颜色/尺码等）。返回已点中的片段。"""
    raw = (spec or '').strip()
    if not raw:
        return []
    parts = [p.strip() for p in re.split(r'[,，/|、]', raw) if p.strip()]
    hit: List[str] = []
    for part in parts:
        # 优先精确文案
        clicked = False
        for exact in (True, False):
            try:
                loc = page.get_by_text(part, exact=exact)
                n = min(loc.count(), 8)
                for i in range(n):
                    el = loc.nth(i)
                    try:
                        box = el.bounding_box(timeout=500)
                        if not box or box.get('width', 0) < 8:
                            continue
                        el.click(timeout=1000)
                        hit.append(part)
                        clicked = True
                        page.wait_for_timeout(200)
                        break
                    except Exception:
                        continue
                if clicked:
                    break
            except Exception:
                continue
    return hit


def _maybe_handle_captcha(page) -> None:
    if has_captcha(page):
        handle_captcha(page)


def add_items_to_cart(page, items: List[Dict[str, Any]]) -> Dict[str, Any]:
    gate = ensure_logged_in(page)
    if not gate.get('ok'):
        return {'ok': False, 'error': gate.get('error') or '登录失败', **gate}

    results = []
    ok_n = 0
    for it in items:
        title = it.get('title') or it.get('goodsId') or ''
        url = (it.get('goodsUrl') or '').strip()
        qty = int(it.get('qty') or 1)
        spec = str(it.get('spec') or '').strip()
        row = {'title': title, 'goodsId': it.get('goodsId'), 'qty': qty, 'spec': spec, 'ok': False}
        if not url:
            row['error'] = '无商品链接'
            results.append(row)
            continue
        try:
            page.goto(url, wait_until='domcontentloaded', timeout=60_000)
            page.wait_for_timeout(800)
            _maybe_handle_captcha(page)
            if spec:
                hit = _select_spec(page, spec)
                row['specHit'] = hit
            _set_qty(page, qty)
            if not _click_by_texts(page, _ADD_CART_TEXTS):
                row['error'] = '未找到「加入购物车」按钮'
                results.append(row)
                continue
            page.wait_for_timeout(1000)
            _maybe_handle_captcha(page)
            row['ok'] = True
            ok_n += 1
        except Exception as e:
            row['error'] = str(e)
            logger.warning('加购失败 title=%s: %s', title, e)
        results.append(row)

    return {
        'ok': ok_n > 0,
        'successCount': ok_n,
        'failCount': len(results) - ok_n,
        'results': results,
    }


def checkout_cart(page, items: List[Dict[str, Any]]) -> Dict[str, Any]:
    gate = ensure_logged_in(page)
    if not gate.get('ok'):
        return {'ok': False, 'error': gate.get('error') or '登录失败', **gate}

    try:
        page.goto(_CART_URL, wait_until='domcontentloaded', timeout=60_000)
    except Exception:
        try:
            page.goto(_HOMEPAGE, wait_until='domcontentloaded', timeout=60_000)
            _click_by_texts(page, ('购物车', '采购车'))
        except Exception as e:
            return {'ok': False, 'error': f'打开购物车失败: {e}'}

    page.wait_for_timeout(1000)
    _maybe_handle_captcha(page)

    # 尽量勾选本批商品（按标题包含匹配）
    titles = [str(x.get('title') or '') for x in items if x.get('title')]
    checked = 0
    for title in titles:
        if not title:
            continue
        try:
            row = page.locator(f'tr:has-text("{title[:20]}"), .cart-item:has-text("{title[:20]}"), li:has-text("{title[:20]}")')
            if row.count() == 0:
                continue
            box = row.first.locator('input[type="checkbox"]').first
            if box.count() > 0 and not box.is_checked():
                box.check(timeout=1000)
                checked += 1
        except Exception:
            continue

    if not _click_by_texts(page, _CHECKOUT_TEXTS):
        return {
            'ok': False,
            'error': '未找到结算/提交按钮',
            'checked': checked,
            'url': page.url,
        }

    page.wait_for_timeout(1500)
    _maybe_handle_captcha(page)

    url = (page.url or '').lower()
    pay_hint = any(k in url for k in ('pay', 'payment', 'cashier', 'alipay', 'weixin', 'wx.tenpay'))
    page_text = ''
    try:
        page_text = (page.inner_text('body', timeout=2000) or '')[:500]
    except Exception:
        pass
    if any(k in page_text for k in ('微信支付', '支付宝', '扫码支付', '请支付', '收银台')):
        pay_hint = True

    shot_b64 = None
    try:
        import base64
        png = page.screenshot(full_page=False)
        shot_b64 = base64.b64encode(png).decode()
    except Exception:
        pass

    mark_result = _mark_presell_orders(items)

    if pay_hint:
        _notify_pay_needed(items=items, url=page.url, screenshot_b64=shot_b64)
        return {
            'ok': True,
            'needManualPay': True,
            'checked': checked,
            'url': page.url,
            'presellMarked': mark_result,
            'message': '已进入支付页，请手动完成付款；已尝试标记预售单',
        }

    return {
        'ok': True,
        'needManualPay': False,
        'checked': checked,
        'url': page.url,
        'presellMarked': mark_result,
        'message': '已点击结算/提交；已尝试标记预售单',
    }


def _mark_presell_orders(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """结算成功后，把任务关联的预售单标为已采购。"""
    order_nos = []
    for it in items or []:
        no = str(it.get('presellOrderNo') or it.get('orderNo') or '').strip()
        if no:
            order_nos.append(no)
    if not order_nos:
        return {'ok': True, 'updated': 0, 'skipped': True, 'reason': '无关联预售单号'}
    try:
        from spider.pinduoduo.presell_store import mark_purchased
        return mark_purchased(order_nos, purchased=1)
    except Exception as e:
        logger.warning('标记预售单异常: %s', e)
        return {'ok': False, 'updated': 0, 'error': str(e)}


def _notify_pay_needed(*, items: List[Dict[str, Any]], url: str, screenshot_b64: Optional[str]) -> None:
    try:
        from notify import NotifyChannel, NotifyEvent, NotifyLevel, notify
        titles = '、'.join((x.get('title') or '')[:20] for x in items[:5])
        desc = (
            f'安特预售结算已到支付环节，请尽快在浏览器完成付款。\n'
            f'商品：{titles}\n'
            f'页面：{url}'
        )
        notify(NotifyEvent(
            source='antexiadan',
            level=NotifyLevel.WARNING,
            title='安特 · 预售待支付',
            description=desc,
            channel=NotifyChannel.FEISHU_WEBHOOK,
            link_url=url or _CART_URL,
            link_text='打开页面',
            image_base64=screenshot_b64,
        ))
    except Exception as e:
        logger.warning('发送待支付通知失败: %s', e)


def run_phase(page, data: Dict[str, Any]) -> Dict[str, Any]:
    phase = str((data or {}).get('phase') or 'cart').strip().lower()
    items = (data or {}).get('items') or []
    if not items:
        return {'ok': False, 'error': '任务无商品 items'}
    if phase == 'checkout':
        return checkout_cart(page, items)
    return add_items_to_cart(page, items)
