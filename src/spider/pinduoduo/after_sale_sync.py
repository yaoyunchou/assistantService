"""
拼多多 ERP 售后退货页：采集退货物流信息并写入飞书多维表格。

================================================================================
流程概览
================================================================================
1. 使用 Playwright 打开 Config.PINDUODUO_ERP_AFTER_SALE_URL（ERP 售后管理页）。
2. 若 URL 含 login：走登录拦截流程。
3. 等待表格表体挂载后，注入并执行 ``pdd-after-sale-return-logistics.js``：
   - 通过 ``window.__PDD_LOGISTICS_RUN_MODE = 'python'`` 让脚本只采集数据。
4. 将脚本返回的 ``results`` 交给 ``feishutable.sync_after_sale_logistics_to_feishu``：
   - 按「订单号」判断新建或覆盖更新。

依赖：
    - 页面脚本：同目录下 ``scripts/pdd-after-sale-return-logistics.js``
    - 飞书写入：``spider.pinduoduo.feishutable.sync_after_sale_logistics_to_feishu``
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from playwright.sync_api import Page

from config import Config
from spider.pinduoduo.feishutable import sync_after_sale_logistics_to_feishu
from spider.pinduoduo.login_intercept import handle_pdd_login_intercept
from utils.logger import get_logger

logger = get_logger('PinduoduoAfterSaleSync')

_AFTER_SALE_JS_PATH = (
    Path(__file__).resolve().parent / 'scripts' / 'pdd-after-sale-return-logistics.js'
)

_EVAL_WRAPPER = """
async (args) => {
  window.__PDD_LOGISTICS_RUN_MODE = 'python';
  if (args.filterText != null && args.filterText !== '') {
    window.__PDD_LOGISTICS_FILTER_TEXT = args.filterText;
  }
  if (args.hoverWait != null) {
    window.__PDD_LOGISTICS_HOVER_WAIT = Number(args.hoverWait);
  }
  if (args.scrollStep != null) {
    window.__PDD_LOGISTICS_SCROLL_STEP = Number(args.scrollStep);
  }
  if (args.scrollWait != null) {
    window.__PDD_LOGISTICS_SCROLL_WAIT = Number(args.scrollWait);
  }
  const source = args.source;
  const run = new Function('return ' + source);
  return await run();
}
"""


def _load_after_sale_script() -> str:
    """读取 JS 文件，去掉 BOM 与文件头块注释。"""
    raw = _AFTER_SALE_JS_PATH.read_text(encoding='utf-8')
    raw = raw.lstrip('\ufeff')
    raw = re.sub(r'^/\*[\s\S]*?\*/\s*', '', raw, count=1)
    return raw.strip()


def _send_sync_report(
    feishu_result: Dict[str, Any],
    *,
    item_count: int,
    erp_url: str,
) -> None:
    """同步完成后发送飞书 Webhook 通知。"""
    try:
        from notify import task_result as _task_result

        success = bool(feishu_result.get('success'))
        created = feishu_result.get('create_count', 0)
        updated = feishu_result.get('update_count', 0)
        failed  = feishu_result.get('fail_count', 0)
        msg     = feishu_result.get('message', '')

        lines = [
            f'**采集条数**：{item_count}',
            f'**新建**：{created}　**更新**：{updated}　**失败**：{failed}',
        ]
        if msg:
            lines.append(f'**详情**：{msg}')

        _task_result(
            "pinduoduo",
            "退货物流同步 · 运行报告",
            '\n'.join(lines),
            success=success,
            link_url=erp_url,
            link_text='打开 ERP 售后管理页',
        )
    except Exception as e:
        logger.warning('发送退货物流同步报告失败（不影响主流程）: %s', e)


def _navigate_and_collect(
    page: Page,
    *,
    filter_text: Optional[str] = None,
    hover_wait: Optional[int] = None,
    scroll_step: Optional[int] = None,
    scroll_wait: Optional[int] = None,
    evaluate_timeout_ms: float = 300_000.0,
) -> Dict[str, Any]:
    """
    内部：打开售后管理页 → 执行 JS 脚本 → 返回原始采集结果。
    不做飞书同步，供「仅采集」和「采集+同步」两个入口复用。
    """
    erp_url = Config.PINDUODUO_ERP_AFTER_SALE_URL

    page.goto(erp_url, wait_until='domcontentloaded', timeout=120_000)
    try:
        page.bring_to_front()
    except Exception as e:
        logger.debug('bring_to_front: %s', e)

    try:
        page.wait_for_load_state('domcontentloaded', timeout=15_000)
    except Exception:
        pass

    cur = (page.url or '').lower()
    if 'login' in cur:
        return handle_pdd_login_intercept(
            page,
            title='退货物流采集',
            link_url=erp_url,
            link_text='打开 ERP 售后管理页',
            success_message_with_qr=(
                '打开售后管理页时被要求登录，请用拼多多 APP 扫码；'
                '二维码已返回前端展示，并已尝试飞书提醒。'
            ),
        )

    try:
        page.wait_for_selector(
            '[data-testid="beast-core-table-body-tr"], '
            '.page-inner-content.after-sale-manage',
            timeout=90_000,
            state='attached',
        )
    except Exception as e:
        logger.warning('等待 ERP 售后表格超时: %s', e)
        if 'login' in (page.url or '').lower():
            return handle_pdd_login_intercept(
                page,
                title='退货物流采集',
                link_url=erp_url,
                link_text='打开 ERP 售后管理页',
                success_message_with_qr=(
                    '打开售后管理页时被要求登录，请用拼多多 APP 扫码；'
                    '二维码已返回前端展示，并已尝试飞书提醒。'
                ),
            )
        return {
            'success': False,
            'intercepted': False,
            'message': f'未检测到 ERP 售后表格，可能页面结构变更或账号未登录: {e}',
            'page_url': page.url,
        }

    time.sleep(1.5)

    source = _load_after_sale_script()
    args: Dict[str, Any] = {'source': source}
    if filter_text is not None:
        args['filterText'] = filter_text
    if hover_wait is not None:
        args['hoverWait'] = int(hover_wait)
    if scroll_step is not None:
        args['scrollStep'] = int(scroll_step)
    if scroll_wait is not None:
        args['scrollWait'] = int(scroll_wait)

    ctx = page.context
    restore_ms = 30_000.0
    try:
        ctx.set_default_timeout(int(evaluate_timeout_ms))
        raw = page.evaluate(_EVAL_WRAPPER, args)
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

    if not raw.get('ok'):
        return {
            'success': False,
            'intercepted': False,
            'message': raw.get('error') or '脚本执行失败',
            'extract': raw,
            'page_url': page.url,
        }

    results: List[Dict[str, Any]] = raw.get('results') or []
    skipped: List[str] = raw.get('skipped') or []
    stats = raw.get('stats') or {}

    return {
        'success': True,
        'intercepted': False,
        'message': f'采集完成：{len(results)} 条有物流，{len(skipped)} 条无物流',
        'results': results,
        'skipped': skipped,
        'item_count': len(results),
        'skipped_count': len(skipped),
        'stats': stats,
        'extract_log': raw.get('log'),
        'page_url': page.url,
    }


def collect_after_sale_logistics(
    page: Page,
    app_token: Optional[str] = None,
    table_id: Optional[str] = None,
    *,
    filter_text: Optional[str] = None,
    hover_wait: Optional[int] = None,
    scroll_step: Optional[int] = None,
    scroll_wait: Optional[int] = None,
    evaluate_timeout_ms: float = 300_000.0,
) -> Dict[str, Any]:
    """
    采集 + 自动同步飞书：打开 ERP 售后退货页 → 执行脚本 → 返回数据同时写入飞书。

    同步规则：
    - 订单号不存在 → 新建
    - 订单号已存在且「是否处理」未勾选 → 更新物流字段
    - 订单号已存在且「是否处理」已勾选 → 跳过，保留原记录

    Returns:
        含 ``success``、``results``（物流数组）、``item_count``、``skipped_count``、
        ``feishu_sync``（飞书同步统计，含 skip_handled_count）。
    """
    import time as _time

    app_token = app_token or Config.PINDUODUO_FEISHU_APP_TOKEN
    table_id  = table_id  or Config.PINDUODUO_ERP_AFTER_SALE_FEISHU_TABLE_ID

    collect_result = _navigate_and_collect(
        page,
        filter_text=filter_text,
        hover_wait=hover_wait,
        scroll_step=scroll_step,
        scroll_wait=scroll_wait,
        evaluate_timeout_ms=evaluate_timeout_ms,
    )

    if not collect_result.get('success'):
        return collect_result

    results: List[Dict[str, Any]] = collect_result.get('results') or []

    # 注入采集时间戳
    now_ms = int(_time.time() * 1000)
    for r in results:
        if not r.get('collectedAt'):
            r['collectedAt'] = now_ms

    feishu_result: Optional[Dict[str, Any]] = None
    if results:
        feishu_result = sync_after_sale_logistics_to_feishu(
            results, app_token=app_token, table_id=table_id
        )
        _send_sync_report(feishu_result, item_count=len(results), erp_url=Config.PINDUODUO_ERP_AFTER_SALE_URL)

    return {
        **collect_result,
        'feishu_sync': feishu_result,
    }


def sync_after_sale_logistics(
    page: Page,
    app_token: Optional[str] = None,
    table_id: Optional[str] = None,
    *,
    filter_text: Optional[str] = None,
    hover_wait: Optional[int] = None,
    scroll_step: Optional[int] = None,
    scroll_wait: Optional[int] = None,
    evaluate_timeout_ms: float = 300_000.0,
) -> Dict[str, Any]:
    """
    采集 + 同步：打开 ERP 售后退货页 → 执行脚本 → 将 ``results`` 同步到飞书。

    Returns:
        含 ``success``、``message``、``item_count``、``skipped_count``、``feishu_sync`` 等。
    """
    app_token = app_token or Config.PINDUODUO_FEISHU_APP_TOKEN
    table_id  = table_id  or Config.PINDUODUO_ERP_AFTER_SALE_FEISHU_TABLE_ID
    erp_url   = Config.PINDUODUO_ERP_AFTER_SALE_URL

    collect_result = _navigate_and_collect(
        page,
        filter_text=filter_text,
        hover_wait=hover_wait,
        scroll_step=scroll_step,
        scroll_wait=scroll_wait,
        evaluate_timeout_ms=evaluate_timeout_ms,
    )

    if not collect_result.get('success'):
        return collect_result

    results: List[Dict[str, Any]] = collect_result.get('results') or []

    if not results:
        return {
            **collect_result,
            'feishu_sync': None,
        }

    feishu_result = sync_after_sale_logistics_to_feishu(
        results, app_token=app_token, table_id=table_id
    )
    _send_sync_report(feishu_result, item_count=len(results), erp_url=erp_url)

    return {
        **collect_result,
        'success': bool(feishu_result.get('success')),
        'message': feishu_result.get('message', ''),
        'feishu_sync': feishu_result,
    }
