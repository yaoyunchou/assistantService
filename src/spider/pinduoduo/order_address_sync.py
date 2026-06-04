"""
拼多多订单列表页补全收件信息并回写飞书多维表格。

由「同步 PDD 订单地址」API 调用；页面内自动化依赖
`scripts/pdd-order-search-receiver.js`（设置 window.__PDD_LOOKUP_ORDER_NO 后执行）。

入口说明：
- 文件路径：`src/spider/pinduoduo/order_address_sync.py`
- 列表页：`Config.PINDUODUO_ORDERS_LIST_URL`（默认 orders/list?tab=0）
"""
from __future__ import annotations

import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from tools.feishu.feishu_table_client import FeishuTableClient
from spider.pinduoduo.feishutable import feishu_field_to_text
from utils.logger import get_logger
from config import Config

logger = get_logger('PinduoduoOrderAddressSync')

# 与本流程写回的多维表格列名一致（若表头为「手机号」「收货信息」即为此配置）
FEISHU_COL_PHONE = '手机号'
FEISHU_COL_RECEIVER_INFO = '收货信息'
# 订单时间列：按顺序取第一个有值的字段（与用户表头「订单时间」或 feishutable「订单提交时间」等对齐）
FEISHU_COL_ORDER_TIME_CANDIDATES = ('订单时间', '订单提交时间', 'order_time')

_RECEIVER_JS_PATH = Path(__file__).resolve().parent / 'scripts' / 'pdd-order-search-receiver.js'

# 浏览器端执行：注入订单号后跑脚本全文（自执行 async IIFE）
_EVAL_WRAPPER = """
async (args) => {
    const orderNo = args.orderNo;
    const source = args.source;
    window.__PDD_LOOKUP_ORDER_NO = orderNo;
    const run = new Function('return ' + source);
    return await run();
}
"""


def _load_receiver_script_source() -> str:
    raw = _RECEIVER_JS_PATH.read_text(encoding='utf-8')
    raw = raw.lstrip('\ufeff')
    raw = re.sub(r'^/\*[\s\S]*?\*/\s*', '', raw, count=1)
    return raw.strip()


def _feishu_cell_to_epoch_ms(val: Any) -> Optional[int]:
    """将飞书多维表格日期/数字单元格转为 Unix 毫秒，失败返回 None。"""
    if val is None or isinstance(val, bool):
        return None
    if isinstance(val, (int, float)):
        n = float(val)
        if n > 1e14:
            return int(n / 1000)
        if n > 1e12:
            return int(n)
        if n > 1e9:
            return int(n * 1000)
        return None
    if isinstance(val, dict):
        if val.get('value') is not None and not isinstance(val.get('value'), dict):
            return _feishu_cell_to_epoch_ms(val.get('value'))
        for k in ('time', 'timestamp', 'start'):
            if k in val:
                return _feishu_cell_to_epoch_ms(val[k])
        return None
    if isinstance(val, list) and val:
        return _feishu_cell_to_epoch_ms(val[0])
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return None
        if s.isdigit():
            return _feishu_cell_to_epoch_ms(int(s))
        for fmt in ('%Y-%m-%d %H:%M:%S', '%Y/%m/%d %H:%M:%S', '%Y-%m-%d', '%Y/%m/%d'):
            try:
                cut = s.replace('T', ' ')[:19]
                dt = datetime.strptime(cut, fmt)
                return int(dt.timestamp() * 1000)
            except ValueError:
                continue
        try:
            dt = datetime.fromisoformat(s.replace('Z', '+00:00').replace('/', '-')[:19])
            return int(dt.timestamp() * 1000)
        except ValueError:
            return None
    return None


def _order_time_ms_from_fields(fields: Dict[str, Any]) -> Optional[int]:
    for key in FEISHU_COL_ORDER_TIME_CANDIDATES:
        if key not in fields:
            continue
        ms = _feishu_cell_to_epoch_ms(fields.get(key))
        if ms is not None:
            return ms
    return None


def _parse_js_receiver_result(raw: Any) -> Tuple[bool, Optional[str], Optional[str], Optional[str]]:
    """
    解析 pdd-order-search-receiver.js 返回值。
    Returns: (should_skip_feishu, phone, address, skip_reason)

    失败形态含 result:null 与 error 或 reason；成功形态为 手机/收货信息/orderNo，无 result 字段。
    """
    if not isinstance(raw, dict):
        return True, None, None, '脚本返回非对象'

    if raw.get('result') is None and (raw.get('error') is not None or raw.get('reason') is not None):
        reason = raw.get('error') or raw.get('reason') or '无结果'
        return True, None, None, str(reason)

    phone = raw.get('手机')
    addr = raw.get('收货信息')
    phone_s = str(phone).strip() if phone is not None else ''
    addr_s = str(addr).strip() if addr is not None else ''

    if not phone_s and not addr_s:
        return True, None, None, '未解析到手机号与收货信息'

    return False, phone_s or None, addr_s or None, None


def _run_receiver_js(page: Page, order_sn: str, *, timeout_ms: float = 120_000) -> Any:
    """执行前端脚本；Page.evaluate 无 timeout 参数，临时放大 context 默认超时。"""
    source = _load_receiver_script_source()
    ctx = page.context
    restore_ms = 30000
    url = ''
    try:
        url = page.url or ''
    except Exception:
        pass

    t0 = time.monotonic()
    logger.info(
        '[pdd-receiver-js] 开始 evaluate 订单=%s timeout_ms=%s page.url=%s script_path=%s script_len=%s',
        order_sn,
        int(timeout_ms),
        url,
        _RECEIVER_JS_PATH,
        len(source),
    )

    try:
        ctx.set_default_timeout(int(timeout_ms))
        result = page.evaluate(
            _EVAL_WRAPPER,
            {'orderNo': order_sn, 'source': source},
        )
        elapsed_ms = (time.monotonic() - t0) * 1000

        if isinstance(result, dict):
            keys = list(result.keys())
            phone_preview = result.get('手机')
            addr = result.get('收货信息')
            addr_len = len(str(addr)) if addr is not None else 0
            err = result.get('error') or result.get('reason')
            logger.info(
                '[pdd-receiver-js] 完成 订单=%s elapsed_ms=%.0f keys=%s 手机=%s 收货信息长度=%s err/reason=%s',
                order_sn,
                elapsed_ms,
                keys,
                phone_preview,
                addr_len,
                (str(err)[:200] + '…') if err and len(str(err)) > 200 else err,
            )
            brief = f'orderNo={result.get("orderNo")!r} result={result.get("result")!r}'
            logger.debug('[pdd-receiver-js] 摘要 %s', brief)
        else:
            logger.warning(
                '[pdd-receiver-js] 完成但返回非 dict 订单=%s elapsed_ms=%.0f type=%s repr=%s',
                order_sn,
                elapsed_ms,
                type(result).__name__,
                repr(result)[:500],
            )

        return result
    except Exception as e:
        elapsed_ms = (time.monotonic() - t0) * 1000
        try:
            url = page.url or url
        except Exception:
            pass
        logger.exception(
            '[pdd-receiver-js] evaluate 异常 订单=%s elapsed_ms=%.0f page.url=%s: %s',
            order_sn,
            elapsed_ms,
            url,
            e,
        )
        raise
    finally:
        ctx.set_default_timeout(restore_ms)
        logger.debug('[pdd-receiver-js] 已恢复 context 默认超时 %sms', restore_ms)


def fetch_and_update_addresses_impl(
    page: Page,
    app_token: str,
    table_id: str,
    need_fill: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    在已处于订单列表页、且浏览器已登录拼多多商家后台的前提下，
    逐条执行 pdd-order-search-receiver.js；有手机或收货信息则更新飞书「手机号」「收货信息」列。
    """
    if not _RECEIVER_JS_PATH.is_file():
        logger.error('未找到脚本: %s', _RECEIVER_JS_PATH)
        return {
            'success': False,
            'message': f'缺少脚本文件: {_RECEIVER_JS_PATH}',
            'updated_count': 0,
            'skipped_count': len(need_fill),
            'details': [],
        }

    client = FeishuTableClient(app_token, table_id)
    updated_count = 0
    skipped_count = 0
    details: List[Dict[str, Any]] = []

    for item in need_fill:
        record_id = item.get('record_id')
        order_sn = item.get('order_sn')
        if not record_id or not order_sn:
            skipped_count += 1
            details.append({
                'record_id': record_id,
                'order_sn': order_sn,
                'skipped': True,
                'reason': '缺 record_id 或 order_sn',
            })
            continue

        try:
            
            raw = _run_receiver_js(page, str(order_sn).strip())
        except PlaywrightTimeoutError as e:
            skipped_count += 1
            details.append({
                'record_id': record_id,
                'order_sn': order_sn,
                'skipped': True,
                'reason': f'脚本超时: {e}',
            })
            logger.warning('订单 %s 脚本超时: %s', order_sn, e)
            continue
        except Exception as e:
            skipped_count += 1
            details.append({
                'record_id': record_id,
                'order_sn': order_sn,
                'skipped': True,
                'reason': str(e),
            })
            logger.exception('订单 %s 执行脚本失败', order_sn)
            continue

        skip, phone, address, skip_reason = _parse_js_receiver_result(raw)
        if skip:
            skipped_count += 1
            details.append({
                'record_id': record_id,
                'order_sn': order_sn,
                'skipped': True,
                'reason': skip_reason,
                'js': raw if isinstance(raw, dict) else None,
            })
            logger.info('订单 %s 跳过飞书同步: %s', order_sn, skip_reason)
            continue

        fields: Dict[str, Any] = {}
        if phone:
            fields[FEISHU_COL_PHONE] = phone
        if address:
            fields[FEISHU_COL_RECEIVER_INFO] = address

        if not fields:
            skipped_count += 1
            details.append({
                'record_id': record_id,
                'order_sn': order_sn,
                'skipped': True,
                'reason': '无有效字段可写',
            })
            continue

        try:
            updated = client.update_record(record_id, fields)
            # API 成功时 data.record 偶发为空 dict，不能用 if updated 判断真假
            if updated is not None:
                updated_count += 1
                details.append({
                    'record_id': record_id,
                    'order_sn': order_sn,
                    'skipped': False,
                    'updated_fields': list(fields.keys()),
                })
                logger.info('飞书已更新 record=%s 订单=%s 字段=%s', record_id, order_sn, list(fields.keys()))
            else:
                skipped_count += 1
                details.append({
                    'record_id': record_id,
                    'order_sn': order_sn,
                    'skipped': True,
                    'reason': '飞书 update_record 返回失败',
                })
        except Exception as e:
            skipped_count += 1
            details.append({
                'record_id': record_id,
                'order_sn': order_sn,
                'skipped': True,
                'reason': f'飞书更新异常: {e}',
            })
            logger.exception('飞书更新 record=%s', record_id)

    msg = f'处理 {len(need_fill)} 条：已更新 {updated_count}，跳过 {skipped_count}'
    return {
        'success': True,
        'message': msg,
        'updated_count': updated_count,
        'skipped_count': skipped_count,
        'details': details,
    }


def sync_order_addresses_from_feishu_top_records(
    page: Page,
    app_token: str,
    table_id: str,
    top_n: int = 3,
    view_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    在飞书表中 **按视图分页扫描**，找出 **最多 top_n 条**「有订单号、无手机号、且订单时间在最近 N 天内」的记录；
    找到则打开拼多多订单列表页并调用 fetch_and_update_addresses_impl。

    时间列依次尝试：**订单时间**、**订单提交时间**、**order_time**（与 Config 中天数、可选排序列一致）。
    无法解析时间的行 **不会** 进入待补列表。

    view_id 须与网页多维表格 URL 中 view= 一致。
    """
    vid = (view_id if view_id is not None else Config.PINDUODUO_FEISHU_VIEW_ID) or None
    if isinstance(vid, str) and not vid.strip():
        vid = None

    recent_days = int(getattr(Config, 'PINDUODUO_ADDRESS_SYNC_RECENT_DAYS', 2) or 2)
    cutoff_ms = int((datetime.now() - timedelta(days=recent_days)).timestamp() * 1000)

    sort_field = getattr(Config, 'PINDUODUO_ADDRESS_SYNC_SORT_FIELD', None)
    sort_effective: Optional[List[Dict[str, Any]]] = (
        [{'field_name': sort_field, 'desc': True}] if sort_field else None
    )
    sort_fallback_tried = False

    client = FeishuTableClient(app_token, table_id)
    checked: List[Dict[str, Any]] = []
    need_fill: List[Dict[str, Any]] = []
    page_token: Optional[str] = None
    page_size = min(500, max(50, top_n * 5))
    max_pages = 500
    pages = 0

    while len(need_fill) < top_n and pages < max_pages:
        listed = client.list_records(
            page_size=page_size,
            page_token=page_token,
            view_id=vid,
            sort=sort_effective,
        )
        if listed is None and sort_effective and not sort_fallback_tried:
            logger.warning('飞书 list_records（带排序列 %s）失败，改为无排序重试', sort_field)
            sort_effective = None
            sort_fallback_tried = True
            listed = client.list_records(
                page_size=page_size,
                page_token=page_token,
                view_id=vid,
                sort=None,
            )
        if listed is None:
            if pages == 0:
                return {
                    'success': False,
                    'message': '飞书「列出记录」失败（token/权限、app_token、table_id 或网络）。请检查配置与飞书开放平台权限。',
                    'checked': [],
                    'need_fill': [],
                    'view_id_used': vid,
                    'rows_scanned': 0,
                    'recent_days': recent_days,
                }
            logger.warning('飞书 list_records 在第 %s 页失败，已停止翻页', pages + 1)
            break

        items = listed.get('items') or []
        pages += 1
        page_newest_ms: Optional[int] = None

        for item in items:
            rid = item.get('record_id')
            fields = item.get('fields') or {}
            order_sn = feishu_field_to_text(fields.get('订单号'))
            phone = feishu_field_to_text(fields.get(FEISHU_COL_PHONE))
            order_ms = _order_time_ms_from_fields(fields)
            recent = order_ms is not None and order_ms >= cutoff_ms
            if order_ms is not None and (page_newest_ms is None or order_ms > page_newest_ms):
                page_newest_ms = order_ms

            checked.append({
                'record_id': rid,
                'order_sn': order_sn or None,
                'has_phone': bool(phone),
                'order_in_recent_days': recent,
            })
            if order_sn and not phone and recent and len(need_fill) < top_n:
                need_fill.append({
                    'record_id': rid,
                    'order_sn': order_sn,
                    'fields': fields,
                })

        if len(need_fill) >= top_n:
            break
        if sort_effective and page_newest_ms is not None and page_newest_ms < cutoff_ms:
            logger.info('当前页内最新订单时间已早于「最近 %s 天」窗口，停止翻页', recent_days)
            break
        if not listed.get('has_more'):
            break
        page_token = listed.get('page_token')
        if not page_token:
            break

    rows_scanned = len(checked)

    if not need_fill:
        if rows_scanned == 0:
            msg = (
                '飞书未返回任何记录（top_n=%s，view_id=%s）。'
                '若网页里明明有数据：请在 config / 请求 body 中配置与浏览器地址栏一致的 view_id；'
                '并核对 app_token、table_id。'
            ) % (top_n, vid)
        else:
            msg = (
                f'已扫描 {rows_scanned} 条：在最近 {recent_days} 天内、有「订单号」且缺「{FEISHU_COL_PHONE}」'
                f' 的行共 0 条（或订单时间列无法解析/不在候选列 '
                f'{FEISHU_COL_ORDER_TIME_CANDIDATES} 内）。本次最多处理 {top_n} 条。无需打开拼多多订单页。'
            )
        return {
            'success': True,
            'message': msg,
            'checked': checked,
            'need_fill': [],
            'view_id_used': vid,
            'rows_scanned': rows_scanned,
            'recent_days': recent_days,
        }

    list_url = Config.PINDUODUO_ORDERS_LIST_URL
    logger.info(
        '扫描 %s 条记录，选出 %s 条缺手机号（上限 %s），打开订单列表: %s',
        rows_scanned, len(need_fill), top_n, list_url,
    )
    page.goto(list_url, wait_until='domcontentloaded', timeout=120000)
    try:
        page.bring_to_front()
    except Exception as e:
        logger.debug('bring_to_front: %s', e)

    try:
        page.wait_for_load_state('domcontentloaded', timeout=10000)
    except Exception:
        pass

    cur = (page.url or '').lower()
    if 'login' in cur:
        from spider.pinduoduo.client import PinduoduoClient

        pd_client = PinduoduoClient(page=page)
        try:
            from notify import login_alert as _notify_login_alert
            _notify_login_alert("pinduoduo")
            logger.info('已发送拼多多需登录的飞书提醒')
        except Exception as ex:
            logger.warning('飞书登录提醒发送失败: %s', ex)

        qr_data = pd_client.show_login_qrcode(skip_initial_navigation=True)
        need_fill_summary = [
            {'record_id': x['record_id'], 'order_sn': x['order_sn']} for x in need_fill
        ]
        if qr_data and qr_data != 'ALREADY_LOGGED_IN':
            from tools.feishu.webhook.qudao_notify import (
                CHANNEL_PINDUODUO,
                get_custom_bot_keyword,
                get_webhook_url,
            )

            wh = get_webhook_url(CHANNEL_PINDUODUO)
            if wh:
                try:
                    from tools.feishu.webhook.notify import send_sync_notification

                    send_sync_notification(
                        webhook_url=wh,
                        system_title='订单地址同步',
                        description='需要登录拼多多商家后台，请尽快扫码。',
                        link_url='https://mms.pinduoduo.com/orders/list',
                        link_text='查看订单列表',
                        image_base64=qr_data,
                        custom_bot_keyword=get_custom_bot_keyword(CHANNEL_PINDUODUO),
                    )
                except Exception as ex:
                    logger.warning('飞书 Webhook 登录通知发送失败: %s', ex, exc_info=True)
            else:
                logger.debug('未配置拼多多 Webhook（FEISHU_WEBHOOK_PINDUODUO / 内置默认），跳过')

            return {
                'success': False,
                'intercepted': True,
                'message': '打开订单列表时被要求登录，请用拼多多 APP 扫码；二维码已返回前端展示，并已尝试飞书提醒。',
                'qrcode': qr_data,
                'checked': checked,
                'need_fill': need_fill_summary,
                'view_id_used': vid,
                'rows_scanned': rows_scanned,
                'recent_days': recent_days,
            }
        return {
            'success': False,
            'intercepted': True,
            'message': '已跳转登录页但未成功截取二维码，请在本页点击「重新登录」完成扫码后再试。',
            'qrcode': None,
            'checked': checked,
            'need_fill': need_fill_summary,
            'view_id_used': vid,
            'rows_scanned': rows_scanned,
            'recent_days': recent_days,
        }

    fill_result = fetch_and_update_addresses_impl(page, app_token, table_id, need_fill)
    out = {
        'success': fill_result.get('success', True),
        'message': fill_result.get('message', ''),
        'checked': checked,
        'need_fill': [{'record_id': x['record_id'], 'order_sn': x['order_sn']} for x in need_fill],
        'impl_detail': fill_result,
        'view_id_used': vid,
        'rows_scanned': rows_scanned,
        'recent_days': recent_days,
    }
    return out
