"""
拼多多官方 ERP「待审核订单」列表抓取与提交审核；待发货页打印并发货脚本。

页面：
    - 审核：https://mms.pinduoduo.com/erp/order/audit
    - 待发货：https://mms.pinduoduo.com/erp/order/delivering
    - 已发货：https://mms.pinduoduo.com/erp/order/delivered（今日已打印快递单等）
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from playwright.sync_api import Page

from config import Config
from spider.pinduoduo.login_intercept import handle_pdd_login_intercept
from utils.logger import get_logger

logger = get_logger('PinduoduoErpAudit')

_AUDIT_JS_PATH = Path(__file__).resolve().parent / 'scripts' / 'pdd-erp-order-audit-goods.js'
_DELIVER_JS_PATH = Path(__file__).resolve().parent / 'scripts' / 'pdd-erp-order-delivering-print-ship.js'
_DELIVERING_LIST_JS_PATH = Path(__file__).resolve().parent / 'scripts' / 'pdd-erp-order-delivering-list-query.js'
_DELIVERED_QUERY_JS_PATH = Path(__file__).resolve().parent / 'scripts' / 'pdd-erp-order-delivered-query.js'

_EVAL_PENDING = """
async (args) => {
  window.__PDD_ERP_AUDIT_GOODS_RUN_MODE = 'python';
  window.__PDD_ERP_AUDIT_GOODS_DO_AUDIT = false;
  delete window.__PDD_ERP_AUDIT_GOODS_FILTER_ORDER_NOS;
  delete window.__PDD_ERP_AUDIT_GOODS_CHECK_ORDER_NOS;
  if (args.scrollMaxSteps != null && args.scrollMaxSteps !== '') {
    window.__PDD_ERP_AUDIT_GOODS_SCROLL_MAX_STEPS = Number(args.scrollMaxSteps);
  }
  if (args.scrollPauseMs != null && args.scrollPauseMs !== '') {
    window.__PDD_ERP_AUDIT_GOODS_SCROLL_PAUSE_MS = Number(args.scrollPauseMs);
  }
  const source = args.source;
  const run = new Function('return ' + source);
  return await run();
}
"""

_EVAL_SUBMIT = """
async (args) => {
  window.__PDD_ERP_AUDIT_GOODS_RUN_MODE = 'python';
  const nos = args.orderNos || [];
  window.__PDD_ERP_AUDIT_GOODS_FILTER_ORDER_NOS = nos;
  window.__PDD_ERP_AUDIT_GOODS_CHECK_ORDER_NOS = nos;
  window.__PDD_ERP_AUDIT_GOODS_DO_AUDIT = true;
  if (args.scrollMaxSteps != null && args.scrollMaxSteps !== '') {
    window.__PDD_ERP_AUDIT_GOODS_SCROLL_MAX_STEPS = Number(args.scrollMaxSteps);
  }
  if (args.scrollPauseMs != null && args.scrollPauseMs !== '') {
    window.__PDD_ERP_AUDIT_GOODS_SCROLL_PAUSE_MS = Number(args.scrollPauseMs);
  }
  const source = args.source;
  const run = new Function('return ' + source);
  return await run();
}
"""

_EVAL_DELIVER = """
async (args) => {
  delete window.__PDD_ERP_DELIVERING_LIST_AUTO_SCROLL;
  delete window.__PDD_ERP_DELIVERING_LIST_SCROLL_MAX_STEPS;
  delete window.__PDD_ERP_DELIVERING_LIST_SCROLL_PAUSE_MS;
  delete window.__PDD_ERP_DELIVERING_LIST_RESTORE_SCROLL;
  if (args.autoScroll !== undefined) {
    window.__PDD_ERP_DELIVERING_LIST_AUTO_SCROLL = args.autoScroll;
  }
  if (args.scrollMaxSteps != null && args.scrollMaxSteps !== '') {
    window.__PDD_ERP_DELIVERING_LIST_SCROLL_MAX_STEPS = Number(args.scrollMaxSteps);
  }
  if (args.scrollPauseMs != null && args.scrollPauseMs !== '') {
    window.__PDD_ERP_DELIVERING_LIST_SCROLL_PAUSE_MS = Number(args.scrollPauseMs);
  }
  if (args.restoreScroll !== undefined) {
    window.__PDD_ERP_DELIVERING_LIST_RESTORE_SCROLL = args.restoreScroll;
  }
  const source = args.source;
  const run = new Function('return ' + source);
  return await run();
}
"""

_EVAL_DELIVERED_QUERY = """
async (args) => {
  delete window.__PDD_ERP_DELIVERED_FILTER_PRINT_STATUS;
  delete window.__PDD_ERP_DELIVERED_TIME_TYPE;
  delete window.__PDD_ERP_DELIVERED_DATE_SHORTCUT;
  delete window.__PDD_ERP_DELIVERED_AUTO_SCROLL;
  delete window.__PDD_ERP_DELIVERED_SCROLL_MAX_STEPS;
  delete window.__PDD_ERP_DELIVERED_SCROLL_PAUSE_MS;
  if (args.filterPrintStatus !== undefined && args.filterPrintStatus !== null) {
    window.__PDD_ERP_DELIVERED_FILTER_PRINT_STATUS = args.filterPrintStatus;
  }
  if (args.timeType != null && args.timeType !== '') {
    window.__PDD_ERP_DELIVERED_TIME_TYPE = args.timeType;
  }
  if (args.dateShortcut != null && args.dateShortcut !== '') {
    window.__PDD_ERP_DELIVERED_DATE_SHORTCUT = args.dateShortcut;
  }
  if (args.autoScroll !== undefined) {
    window.__PDD_ERP_DELIVERED_AUTO_SCROLL = args.autoScroll;
  }
  if (args.scrollMaxSteps != null && args.scrollMaxSteps !== '') {
    window.__PDD_ERP_DELIVERED_SCROLL_MAX_STEPS = Number(args.scrollMaxSteps);
  }
  if (args.scrollPauseMs != null && args.scrollPauseMs !== '') {
    window.__PDD_ERP_DELIVERED_SCROLL_PAUSE_MS = Number(args.scrollPauseMs);
  }
  const source = args.source;
  const run = new Function('return ' + source);
  return await run();
}
"""


def _load_script_source(path: Path) -> str:
    raw = path.read_text(encoding='utf-8')
    raw = raw.lstrip('\ufeff')
    raw = re.sub(r'^/\*[\s\S]*?\*/\s*', '', raw, count=1)
    return raw.strip()


def _open_audit_page(page: Page) -> Optional[Dict[str, Any]]:
    audit_url = Config.PINDUODUO_ERP_ORDER_AUDIT_URL
    page.goto(audit_url, wait_until='domcontentloaded', timeout=120000)
    try:
        page.bring_to_front()
    except Exception as e:
        logger.debug('bring_to_front: %s', e)
    try:
        page.wait_for_load_state('domcontentloaded', timeout=15000)
    except Exception:
        pass

    cur = (page.url or '').lower()
    if 'login' in cur:
        return handle_pdd_login_intercept(
            page,
            title='ERP 待审核订单',
            link_url=audit_url,
            link_text='打开 ERP 待审核',
            success_message_with_qr=(
                '打开待审核页时被要求登录，请用拼多多 APP 扫码；二维码已返回前端展示，并已尝试飞书提醒。'
            ),
        )
    return None


def _wait_audit_table(page: Page) -> Optional[Dict[str, Any]]:
    audit_url = Config.PINDUODUO_ERP_ORDER_AUDIT_URL
    try:
        page.wait_for_selector(
            '[data-testid="beast-core-table-middle-thead"]',
            timeout=90000,
            state='attached',
        )
    except Exception as e:
        logger.warning('等待审核表格表头超时: %s', e)
        if 'login' in (page.url or '').lower():
            return handle_pdd_login_intercept(
                page,
                title='ERP 待审核订单',
                link_url=audit_url,
                link_text='打开 ERP 待审核',
                success_message_with_qr=(
                    '打开待审核页时被要求登录，请用拼多多 APP 扫码；二维码已返回前端展示，并已尝试飞书提醒。'
                ),
            )
        return {
            'success': False,
            'intercepted': False,
            'message': f'未检测到审核订单表格（请确认 ERP 权限与页面结构）: {e}',
            'page_url': page.url,
        }
    time.sleep(1.5)
    return None


def fetch_pending_audit_rows(
    page: Page,
    *,
    scroll_max_steps: Optional[int] = None,
    scroll_pause_ms: Optional[int] = None,
    evaluate_timeout_ms: float = 600_000.0,
) -> Dict[str, Any]:
    """打开审核页并执行采集脚本，返回 rows（待审核列表）。"""
    blocked = _open_audit_page(page)
    if blocked:
        return blocked

    tbl = _wait_audit_table(page)
    if tbl:
        return tbl

    source = _load_script_source(_AUDIT_JS_PATH)
    args: Dict[str, Any] = {'source': source}
    if scroll_max_steps is not None:
        args['scrollMaxSteps'] = int(scroll_max_steps)
    if scroll_pause_ms is not None:
        args['scrollPauseMs'] = int(scroll_pause_ms)

    ctx = page.context
    restore_ms = 30000.0
    try:
        ctx.set_default_timeout(int(evaluate_timeout_ms))
        raw = page.evaluate(_EVAL_PENDING, args)
    finally:
        try:
            ctx.set_default_timeout(int(restore_ms))
        except Exception:
            pass

    if not isinstance(raw, dict):
        return {
            'success': False,
            'intercepted': False,
            'message': f'脚本返回异常类型: {type(raw).__name__}',
            'page_url': page.url,
        }

    if raw.get('ok') is False:
        return {
            'success': False,
            'intercepted': False,
            'message': str(raw.get('error') or '脚本执行失败'),
            'extract': raw,
            'page_url': page.url,
        }

    rows: List[Dict[str, Any]] = raw.get('rows') or []
    return {
        'success': True,
        'intercepted': False,
        'message': f'共 {len(rows)} 条待审核',
        'rows': rows,
        'extract': {'count': raw.get('count'), 'log': raw.get('log')},
        'page_url': page.url,
    }


def submit_audit_orders(
    page: Page,
    order_nos: List[str],
    *,
    scroll_max_steps: Optional[int] = None,
    scroll_pause_ms: Optional[int] = None,
    evaluate_timeout_ms: float = 600_000.0,
) -> Dict[str, Any]:
    """对给定平台订单号勾选并点击审核。"""
    nos = [str(x).strip() for x in order_nos if str(x).strip()]
    if not nos:
        return {
            'success': False,
            'intercepted': False,
            'message': 'order_nos 不能为空',
        }

    blocked = _open_audit_page(page)
    if blocked:
        return blocked

    tbl = _wait_audit_table(page)
    if tbl:
        return tbl

    source = _load_script_source(_AUDIT_JS_PATH)
    args: Dict[str, Any] = {'source': source, 'orderNos': nos}
    if scroll_max_steps is not None:
        args['scrollMaxSteps'] = int(scroll_max_steps)
    if scroll_pause_ms is not None:
        args['scrollPauseMs'] = int(scroll_pause_ms)

    ctx = page.context
    restore_ms = 30000.0
    try:
        ctx.set_default_timeout(int(evaluate_timeout_ms))
        raw = page.evaluate(_EVAL_SUBMIT, args)
    finally:
        try:
            ctx.set_default_timeout(int(restore_ms))
        except Exception:
            pass

    if not isinstance(raw, dict):
        return {
            'success': False,
            'intercepted': False,
            'message': f'脚本返回异常类型: {type(raw).__name__}',
            'page_url': page.url,
        }

    if raw.get('ok') is False:
        return {
            'success': False,
            'intercepted': False,
            'message': str(raw.get('error') or '脚本执行失败'),
            'extract': raw,
            'page_url': page.url,
        }

    audit_result = raw.get('auditResult') or {}
    rows: List[Dict[str, Any]] = raw.get('rows') or []
    check_result = raw.get('checkResult') or []

    audited_ok = bool(audit_result.get('ok'))
    return {
        'success': audited_ok,
        'intercepted': False,
        'message': audit_result.get('reason') or ('审核已提交' if audited_ok else '审核未完成'),
        'audit_result': audit_result,
        'check_result': check_result,
        'rows': rows,
        'extract': {'log': raw.get('log')},
        'page_url': page.url,
    }


def run_delivering_list_query(
    page: Page,
    *,
    evaluate_timeout_ms: float = 120_000.0,
    auto_scroll: Optional[bool] = None,
    scroll_max_steps: Optional[int] = None,
    scroll_pause_ms: Optional[int] = None,
) -> Dict[str, Any]:
    """待发货页抓取表格（不写库、不打单）；默认滚动虚拟列表按 orderNo 去重收齐。"""
    ship_url = Config.PINDUODUO_ERP_ORDER_DELIVERING_URL
    page.goto(ship_url, wait_until='domcontentloaded', timeout=120000)
    try:
        page.bring_to_front()
    except Exception as e:
        logger.debug('bring_to_front: %s', e)

    cur = (page.url or '').lower()
    if 'login' in cur:
        return handle_pdd_login_intercept(
            page,
            title='ERP 待发货列表',
            link_url=ship_url,
            link_text='打开 ERP 待发货',
            success_message_with_qr=(
                '打开待发货页时被要求登录，请用拼多多 APP 扫码；二维码已返回前端展示，并已尝试飞书提醒。'
            ),
        )

    source = _load_script_source(_DELIVERING_LIST_JS_PATH)
    args: Dict[str, Any] = {'source': source}
    if auto_scroll is not None:
        args['autoScroll'] = auto_scroll
    if scroll_max_steps is not None:
        args['scrollMaxSteps'] = int(scroll_max_steps)
    if scroll_pause_ms is not None:
        args['scrollPauseMs'] = int(scroll_pause_ms)

    ctx = page.context
    restore_ms = 30000.0
    try:
        ctx.set_default_timeout(int(evaluate_timeout_ms))
        raw = page.evaluate(_EVAL_DELIVER, args)
    finally:
        try:
            ctx.set_default_timeout(int(restore_ms))
        except Exception:
            pass

    if not isinstance(raw, dict):
        return {
            'success': False,
            'intercepted': False,
            'message': f'脚本返回异常类型: {type(raw).__name__}',
            'rows': [],
            'page_url': page.url,
        }

    ok = bool(raw.get('ok'))
    empty = bool(raw.get('empty'))
    rows = raw.get('rows') if isinstance(raw.get('rows'), list) else []
    if not ok:
        msg = str(raw.get('error') or '抓取失败')
    elif empty:
        msg = '待发货列表当前为空'
    else:
        msg = f'已抓取 {len(rows)} 条（虚拟滚动去重）'

    return {
        'success': ok,
        'intercepted': False,
        'empty': empty,
        'message': msg,
        'rows': rows,
        'count': len(rows),
        'scroll': raw.get('scroll'),
        'script_result': raw,
        'page_url': page.url,
        'source': 'erp_delivering_page',
    }


def run_delivering_print_ship(
    page: Page,
    *,
    evaluate_timeout_ms: float = 120_000.0,
) -> Dict[str, Any]:
    """待发货页执行「全选 → 打印快递单 → 打印并发货」脚本。"""
    ship_url = Config.PINDUODUO_ERP_ORDER_DELIVERING_URL
    page.goto(ship_url, wait_until='domcontentloaded', timeout=120000)
    try:
        page.bring_to_front()
    except Exception as e:
        logger.debug('bring_to_front: %s', e)

    cur = (page.url or '').lower()
    if 'login' in cur:
        return handle_pdd_login_intercept(
            page,
            title='ERP 待发货打印',
            link_url=ship_url,
            link_text='打开 ERP 待发货',
            success_message_with_qr=(
                '打开待发货页时被要求登录，请用拼多多 APP 扫码；二维码已返回前端展示，并已尝试飞书提醒。'
            ),
        )

    source = _load_script_source(_DELIVER_JS_PATH)
    args: Dict[str, Any] = {'source': source}

    ctx = page.context
    restore_ms = 30000.0
    try:
        ctx.set_default_timeout(int(evaluate_timeout_ms))
        raw = page.evaluate(_EVAL_DELIVER, args)
    finally:
        try:
            ctx.set_default_timeout(int(restore_ms))
        except Exception:
            pass

    if not isinstance(raw, dict):
        return {
            'success': False,
            'intercepted': False,
            'message': f'脚本返回异常类型: {type(raw).__name__}',
            'page_url': page.url,
        }

    ok = bool(raw.get('ok'))
    empty = bool(raw.get('empty'))
    inner = bool(raw.get('success'))
    order_nos_raw = raw.get('orderNos') or raw.get('order_nos') or []
    marked_audit_rows = 0
    if ok and not empty and inner and isinstance(order_nos_raw, list) and order_nos_raw:
        try:
            from spider.pinduoduo import audit_store

            marked_audit_rows = audit_store.mark_print_ship_batch(
                [str(x).strip() for x in order_nos_raw if str(x).strip()]
            )
        except Exception as ex:
            logger.warning('打印成功后写入本地审核 printed_at 失败: %s', ex)

    if not ok:
        msg = str(raw.get('error') or '脚本执行失败')
    elif empty:
        msg = '待发货列表为空，无单可打印'
    elif inner:
        msg = '已执行打印并发货流程'
    else:
        msg = raw.get('error') or '打印流程结束（请查看 script_result.log）'
    out = {
        'success': ok,
        'intercepted': False,
        'empty': empty,
        'print_ship_success': inner,
        'message': msg,
        'script_result': raw,
        'page_url': page.url,
        'order_nos_from_page': order_nos_raw if isinstance(order_nos_raw, list) else [],
        'audit_marked_printed': marked_audit_rows,
    }
    return out


def _open_delivered_page(page: Page) -> Optional[Dict[str, Any]]:
    """打开已发货订单页；若跳转登录则走统一拦截。"""
    delivered_url = Config.PINDUODUO_ERP_ORDER_DELIVERED_URL
    # commit 先于 domcontentloaded，弱网下减少误超时；再补一轮网络空闲等待
    try:
        page.goto(delivered_url, wait_until='commit', timeout=180000)
    except Exception:
        page.goto(delivered_url, wait_until='domcontentloaded', timeout=180000)
    try:
        page.wait_for_load_state('domcontentloaded', timeout=60000)
    except Exception as e:
        logger.debug('delivered wait domcontentloaded: %s', e)
    try:
        page.bring_to_front()
    except Exception as e:
        logger.debug('bring_to_front: %s', e)
    try:
        page.wait_for_load_state('domcontentloaded', timeout=15000)
    except Exception:
        pass

    cur = (page.url or '').lower()
    if 'login' in cur:
        return handle_pdd_login_intercept(
            page,
            title='ERP 已发货订单',
            link_url=delivered_url,
            link_text='打开 ERP 已发货',
            success_message_with_qr=(
                '打开已发货页时被要求登录，请用拼多多 APP 扫码；二维码已返回前端展示，并已尝试飞书提醒。'
            ),
        )
    return None


def _notify_delivered_printed_query(
    *,
    intercepted: bool,
    success: bool,
    message: str,
    row_count: int,
    page_url: str,
) -> None:
    """执行结束后经拼多多渠道 Webhook 推送摘要（登录拦截由 handle_pdd_login_intercept 另行通知）。"""
    if intercepted:
        return
    try:
        from notify import task_result as _task_result

        delivered_url = Config.PINDUODUO_ERP_ORDER_DELIVERED_URL
        lines = [
            f'**概览**：{message}',
            f'**订单条数**：{row_count}',
        ]
        _task_result(
            "pinduoduo",
            "ERP 已发货 · 今日打印单查询",
            '\n'.join(lines),
            success=success,
            link_url=page_url or delivered_url,
            link_text='打开 ERP 已发货',
        )
    except Exception as e:
        logger.warning('已发货查询 Webhook 通知失败: %s', e)


def fetch_delivered_today_printed_rows(
    page: Page,
    *,
    filter_print_status: Optional[str] = None,
    time_type: Optional[str] = None,
    date_shortcut: Optional[str] = None,
    auto_scroll: Optional[bool] = None,
    scroll_max_steps: Optional[int] = None,
    scroll_pause_ms: Optional[int] = None,
    evaluate_timeout_ms: float = 600_000.0,
) -> Dict[str, Any]:
    """
    已发货页：筛选「今日 + 已打印快递单」（可选覆盖）并抓取表格行。

    脚本：``pdd-erp-order-delivered-query.js``
    """
    blocked = _open_delivered_page(page)
    if blocked:
        return blocked

    delivered_url = Config.PINDUODUO_ERP_ORDER_DELIVERED_URL

    # 表格未尽快出现时可能仍在登录页（URL 未含 login）
    try:
        page.wait_for_selector('#timeType', timeout=90000, state='attached')
    except Exception as e:
        logger.warning('等待已发货筛选表单超时: %s', e)
        if 'login' in (page.url or '').lower():
            caught = handle_pdd_login_intercept(
                page,
                title='ERP 已发货订单',
                link_url=delivered_url,
                link_text='打开 ERP 已发货',
                success_message_with_qr=(
                    '打开已发货页时被要求登录，请用拼多多 APP 扫码；二维码已返回前端展示，并已尝试飞书提醒。'
                ),
            )
            if caught:
                return caught
        err = (
            '未检测到已发货筛选表单（请确认已登录且有 ERP 权限），'
            f'{e}'
        )
        result = {
            'success': False,
            'intercepted': False,
            'message': err,
            'rows': [],
            'page_url': page.url,
        }
        _notify_delivered_printed_query(
            intercepted=False,
            success=False,
            message=err,
            row_count=0,
            page_url=page.url or '',
        )
        return result

    source = _load_script_source(_DELIVERED_QUERY_JS_PATH)
    args: Dict[str, Any] = {'source': source}
    if filter_print_status is not None:
        args['filterPrintStatus'] = filter_print_status
    if time_type is not None:
        args['timeType'] = time_type
    if date_shortcut is not None:
        args['dateShortcut'] = date_shortcut
    if auto_scroll is not None:
        args['autoScroll'] = auto_scroll
    if scroll_max_steps is not None:
        args['scrollMaxSteps'] = int(scroll_max_steps)
    if scroll_pause_ms is not None:
        args['scrollPauseMs'] = int(scroll_pause_ms)

    ctx = page.context
    restore_ms = 30000.0
    raw: Any = None
    try:
        ctx.set_default_timeout(int(evaluate_timeout_ms))
        raw = page.evaluate(_EVAL_DELIVERED_QUERY, args)
    except Exception as e:
        logger.exception('已发货查询脚本 evaluate 异常')
        msg = str(e)
        result = {
            'success': False,
            'intercepted': False,
            'message': msg,
            'rows': [],
            'page_url': page.url,
        }
        _notify_delivered_printed_query(
            intercepted=False,
            success=False,
            message=msg,
            row_count=0,
            page_url=page.url or '',
        )
        return result
    finally:
        try:
            ctx.set_default_timeout(int(restore_ms))
        except Exception:
            pass

    if not isinstance(raw, dict):
        msg = f'脚本返回异常类型: {type(raw).__name__}'
        result = {
            'success': False,
            'intercepted': False,
            'message': msg,
            'rows': [],
            'page_url': page.url,
        }
        _notify_delivered_printed_query(
            intercepted=False,
            success=False,
            message=msg,
            row_count=0,
            page_url=page.url or '',
        )
        return result

    ok = bool(raw.get('ok'))
    rows: List[Dict[str, Any]] = raw.get('rows') or []
    row_count = len(rows)
    page_total = raw.get('pageTotal')
    incomplete = bool(raw.get('incomplete'))
    if ok:
        if page_total is not None:
            msg = f'共 {row_count} 条（页脚 {page_total}）'
            if incomplete:
                msg += '，未抓全'
        else:
            msg = f'共 {row_count} 条（已发货筛选）'
    else:
        msg = str(raw.get('error') or '脚本执行失败')

    result = {
        'success': ok,
        'intercepted': False,
        'message': msg,
        'rows': rows,
        'count': row_count,
        'pageTotal': page_total,
        'incomplete': incomplete,
        'extract': {'count': raw.get('count'), 'log': raw.get('log')},
        'page_url': page.url,
    }

    _notify_delivered_printed_query(
        intercepted=False,
        success=ok,
        message=msg,
        row_count=row_count,
        page_url=page.url or '',
    )
    return result
