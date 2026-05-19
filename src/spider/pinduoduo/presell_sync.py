"""
拼多多 ERP 预售订单页：采集订单列表（仅浏览器 + 脚本，不代调用业务库接口）。

================================================================================
流程概览
================================================================================
1. 使用 Playwright 打开 Config.PINDUODUO_ERP_PRESELL_URL（ERP 预售订单页）。
2. 若 URL 含 login：走登录拦截流程（返回二维码）。
3. 等待表格表体挂载后，注入并执行 ``pdd-erp-order-presell-list.js``：
   - 通过 ``window.__PDD_ERP_PRESELL_RUN_MODE = 'python'`` 让脚本只采集数据。

**服务端入库**：由 Nest 等通过 Socket.IO 下发 ``assistant_http``，请求本机
``POST /api/pinduoduo/erp-presell/collect``，响应体中的 ``orders`` 与脚本 ``syncBody`` 一致。
详见 ``docs/socketio-assistant-http.md``。

依赖：
    - 页面脚本：同目录下 ``scripts/pdd-erp-order-presell-list.js``
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

logger = get_logger('PinduoduoPresellSync')

_PRESELL_JS_PATH = (
    Path(__file__).resolve().parent / 'scripts' / 'pdd-erp-order-presell-list.js'
)

_EVAL_WRAPPER = """
async (args) => {
  window.__PDD_ERP_PRESELL_RUN_MODE = 'python';
  if (args.autoScroll != null) {
    window.__PDD_ERP_PRESELL_AUTO_SCROLL = Boolean(args.autoScroll);
  }
  if (args.scrollStep != null) {
    window.__PDD_ERP_PRESELL_SCROLL_STEP = Number(args.scrollStep);
  }
  if (args.scrollPauseMs != null) {
    window.__PDD_ERP_PRESELL_SCROLL_PAUSE_MS = Number(args.scrollPauseMs);
  }
  const source = args.source;
  const run = new Function('return ' + source);
  return await run();
}
"""


def _load_presell_script() -> str:
    """读取 JS 文件，去掉 BOM 与文件头块注释。"""
    raw = _PRESELL_JS_PATH.read_text(encoding='utf-8')
    raw = raw.lstrip('\ufeff')
    raw = re.sub(r'^/\*[\s\S]*?\*/\s*', '', raw, count=1)
    return raw.strip()


def collect_presell_orders(
    page: Page,
    *,
    auto_scroll: bool = False,
    scroll_step: Optional[int] = None,
    scroll_pause_ms: Optional[int] = None,
    evaluate_timeout_ms: float = 300_000.0,
) -> Dict[str, Any]:
    """
    打开 ERP 预售订单页 → 执行脚本 → 返回 ``orders``（与脚本 ``syncBody.orders`` 结构一致）。

    Returns:
        含 ``success``、``orders``、``order_count``、``extract_log`` 等；
        失败时含 ``message`` / 登录拦截结构。
    """
    erp_url = Config.PINDUODUO_ERP_PRESELL_URL

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
            title='预售订单采集',
            link_url=erp_url,
            link_text='打开 ERP 预售订单页',
            success_message_with_qr=(
                '打开预售订单页时被要求登录，请用拼多多 APP 扫码；'
                '二维码已返回前端展示，并已尝试飞书提醒。'
            ),
        )

    try:
        page.wait_for_selector(
            '[data-testid="beast-core-table-body-tr"], '
            '.page-inner-content.order-manage, '
            '[data-testid="beast-core-table"]',
            timeout=90_000,
            state='attached',
        )
    except Exception as e:
        logger.warning('等待 ERP 预售订单表格超时: %s', e)
        if 'login' in (page.url or '').lower():
            return handle_pdd_login_intercept(
                page,
                title='预售订单采集',
                link_url=erp_url,
                link_text='打开 ERP 预售订单页',
                success_message_with_qr=(
                    '打开预售订单页时被要求登录，请用拼多多 APP 扫码；'
                    '二维码已返回前端展示，并已尝试飞书提醒。'
                ),
            )
        return {
            'success': False,
            'intercepted': False,
            'message': f'未检测到 ERP 预售订单表格，可能页面结构变更或账号未登录: {e}',
            'page_url': page.url,
        }

    time.sleep(1.5)

    source = _load_presell_script()
    args: Dict[str, Any] = {
        'source': source,
        'autoScroll': auto_scroll,
    }
    if scroll_step is not None:
        args['scrollStep'] = int(scroll_step)
    if scroll_pause_ms is not None:
        args['scrollPauseMs'] = int(scroll_pause_ms)

    ctx = page.context
    restore_ms = 30_000.0
    try:
        ctx.set_default_timeout(int(evaluate_timeout_ms))
        raw = page.evaluate(_EVAL_WRAPPER, args)
    except Exception as e:
        logger.error('预售订单 JS 执行失败: %s', e)
        return {
            'success': False,
            'intercepted': False,
            'message': f'JS 执行失败: {e}',
        }
    finally:
        try:
            ctx.set_default_timeout(int(restore_ms))
        except Exception:
            pass

    if not isinstance(raw, dict):
        return {
            'success': False,
            'intercepted': False,
            'message': f'JS 返回非预期类型: {type(raw).__name__}',
        }

    orders: List[Dict[str, Any]] = raw.get('orders') or []
    log:    List[str]            = raw.get('log') or []

    logger.info('预售订单脚本执行完毕，共 %d 条，log: %s', len(orders), log[-3:] if log else [])

    return {
        'success': True,
        'intercepted': False,
        'orders': orders,
        'order_count': len(orders),
        'extract_log': log,
        'page_url': page.url,
    }
