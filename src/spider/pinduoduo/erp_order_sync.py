"""
拼多多官方 ERP「全部订单」表格抓取并写入飞书多维表格（浏览器侧入口）。

================================================================================
流程概览
================================================================================
1. 使用 Playwright 打开 Config.PINDUODUO_ERP_ORDER_ALL_URL（默认 ERP 全部订单页）。
2. 若 URL 含 login：走登录拦截（飞书应用消息 + 可选 Webhook 卡片 + 返回二维码）。
3. 等待 beast-core 表头挂载后，注入并执行 ``pdd-erp-order-all-table.js``：
   - 通过 ``window.__PDD_ERP_ORDER_ALL_RUN_MODE = 'python'`` 让脚本只采集数据、
     不在页内 POST（由 Python 调用 ``sync_erp_order_rows_to_feishu`` 写飞书）。
4. 将脚本返回的 ``rows`` 交给 ``feishutable.sync_erp_order_rows_to_feishu``：
   - 按「平台订单号」判断新建或增量更新（具体字段策略见该函数文档）。

依赖：
    - 页面脚本：同目录下 ``scripts/pdd-erp-order-all-table.js``
    - 飞书写入：``spider.pinduoduo.feishutable.sync_erp_order_rows_to_feishu``
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from playwright.sync_api import Page

from config import Config
from spider.pinduoduo.feishutable import sync_erp_order_rows_to_feishu
from utils.logger import get_logger

logger = get_logger('PinduoduoErpOrderSync')

# ---------------------------------------------------------------------------
# 脚本路径与浏览器端包装函数
# ---------------------------------------------------------------------------
_ERP_JS_PATH = Path(__file__).resolve().parent / 'scripts' / 'pdd-erp-order-all-table.js'

# Playwright page.evaluate 传入的异步函数：在运行 IIFE 前设置运行模式与可选滚动参数。
# 脚本全文为 ``(async function () { ... })();``，用 new Function 得到可 await 的 Promise。
_EVAL_WRAPPER = """
async (args) => {
  window.__PDD_ERP_ORDER_ALL_RUN_MODE = 'python';
  if (args.scrollMaxSteps != null && args.scrollMaxSteps !== '') {
    window.__PDD_ERP_ORDER_ALL_SCROLL_MAX_STEPS = Number(args.scrollMaxSteps);
  }
  if (args.scrollPauseMs != null && args.scrollPauseMs !== '') {
    window.__PDD_ERP_ORDER_ALL_SCROLL_PAUSE_MS = Number(args.scrollPauseMs);
  }
  const source = args.source;
  const run = new Function('return ' + source);
  return await run();
}
"""


def _load_erp_script_source() -> str:
    """读取 JS 文件，去掉 BOM 与文件头块注释，便于嵌入 evaluate。"""
    raw = _ERP_JS_PATH.read_text(encoding='utf-8')
    raw = raw.lstrip('\ufeff')
    raw = re.sub(r'^/\*[\s\S]*?\*/\s*', '', raw, count=1)
    return raw.strip()


def _handle_login_intercept(
    page: Page,
    *,
    title: str,
    link_url: str,
    link_text: str,
) -> Optional[Dict[str, Any]]:
    """
    当前页已被重定向到登录时的统一处理。

    - 飞书应用内消息（若已配置）：提醒需登录。
    - 截取登录二维码；若配置了拼多多渠道 Webhook，则发卡片（含图）。
    - 返回给前端的 dict 中带 ``intercepted``、``qrcode``，与订单地址同步页行为一致。
    """
    from spider.pinduoduo.client import PinduoduoClient

    pd_client = PinduoduoClient(page=page)
    if pd_client.feishu_sender.is_available():
        try:
            pd_client.feishu_sender.send_pinduoduo_login_alert()
            logger.info('已发送拼多多需登录的飞书提醒')
        except Exception as ex:
            logger.warning('飞书登录提醒发送失败: %s', ex)

    qr_data = pd_client.show_login_qrcode(skip_initial_navigation=True)
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
                    system_title=title,
                    description='需要登录拼多多商家后台，请尽快扫码。',
                    link_url=link_url,
                    link_text=link_text,
                    image_base64=qr_data,
                    custom_bot_keyword=get_custom_bot_keyword(CHANNEL_PINDUODUO),
                )
            except Exception as ex:
                logger.warning('飞书 Webhook 登录通知发送失败: %s', ex, exc_info=True)
        else:
            logger.debug('未配置拼多多 Webhook，跳过')

        return {
            'success': False,
            'intercepted': True,
            'message': '打开 ERP 订单页时被要求登录，请用拼多多 APP 扫码；二维码已返回前端展示，并已尝试飞书提醒。',
            'qrcode': qr_data,
            'page_url': page.url,
        }

    return {
        'success': False,
        'intercepted': True,
        'message': '已跳转登录页但未成功截取二维码，请在本页点击「重新登录」完成扫码后再试。',
        'qrcode': None,
        'page_url': page.url,
    }


def sync_erp_orders_to_feishu(
    page: Page,
    app_token: Optional[str] = None,
    table_id: Optional[str] = None,
    *,
    scroll_max_steps: Optional[int] = None,
    scroll_pause_ms: Optional[int] = None,
    evaluate_timeout_ms: float = 600_000.0,
) -> Dict[str, Any]:
    """
    主入口：打开 ERP 全部订单页 → 执行采集脚本 → 将 ``rows`` 同步到飞书。

    Args:
        page: 浏览器池中的 Playwright Page（已与拼多多登录态共享）。
        app_token / table_id: 飞书多维表格；默认来自 Config。
        scroll_max_steps / scroll_pause_ms: 可选，映射到脚本全局变量，控制虚拟列表滚动采集强度。
        evaluate_timeout_ms: 脚本可能耗时很长（滚动+解析），临时放大 context 默认超时。

    Returns:
        含 ``success``、``message``、``row_count``、``feishu_sync``（飞书批处理统计）等；
        登录拦截时 ``intercepted=True`` 且可能含 ``qrcode``。
    """
    # 目标表与页面 URL（可在 .env / Config 覆盖）
    app_token = app_token or Config.PINDUODUO_FEISHU_APP_TOKEN
    table_id = table_id or Config.PINDUODUO_ERP_FEISHU_TABLE_ID
    erp_url = Config.PINDUODUO_ERP_ORDER_ALL_URL

    # --- 打开 ERP 页并尽量前置窗口，便于本地观察自动化 ---
    page.goto(erp_url, wait_until='domcontentloaded', timeout=120000)
    try:
        page.bring_to_front()
    except Exception as e:
        logger.debug('bring_to_front: %s', e)

    try:
        page.wait_for_load_state('domcontentloaded', timeout=15000)
    except Exception:
        pass

    # --- 登录拦截：与 mms 其它流程一致，URL 含 login 即视为未登录 ---
    cur = (page.url or '').lower()
    if 'login' in cur:
        return _handle_login_intercept(
            page,
            title='订单同步（ERP）',
            link_url=erp_url,
            link_text='打开 ERP 全部订单',
        )

    # --- 等待表格表头：无则可能是未开通 ERP、结构变更或仍被拦在登录 ---
    try:
        page.wait_for_selector(
            '[data-testid="beast-core-table-middle-thead"]',
            timeout=90000,
            state='attached',
        )
    except Exception as e:
        logger.warning('等待 ERP 表格表头超时: %s', e)
        if 'login' in (page.url or '').lower():
            return _handle_login_intercept(
                page,
                title='订单同步（ERP）',
                link_url=erp_url,
                link_text='打开 ERP 全部订单',
            )
        return {
            'success': False,
            'intercepted': False,
            'message': f'未检测到 ERP 订单表格（请确认账号已开通官方 ERP 且当前页可打开全部订单）: {e}',
            'page_url': page.url,
        }

    # 表头出现后稍等，减少 SPA 尚未渲染完 tbody 就执行脚本的概率
    time.sleep(1.5)

    # --- 执行采集脚本（长耗时，临时提高默认超时）---
    source = _load_erp_script_source()
    args: Dict[str, Any] = {'source': source}
    if scroll_max_steps is not None:
        args['scrollMaxSteps'] = int(scroll_max_steps)
    if scroll_pause_ms is not None:
        args['scrollPauseMs'] = int(scroll_pause_ms)

    ctx = page.context
    restore_ms = 30000.0
    try:
        ctx.set_default_timeout(int(evaluate_timeout_ms))
        raw = page.evaluate(_EVAL_WRAPPER, args)
    finally:
        try:
            ctx.set_default_timeout(int(restore_ms))
        except Exception:
            pass

    # --- 解析脚本返回值 ---
    if not isinstance(raw, dict):
        return {
            'success': False,
            'intercepted': False,
            'message': f'脚本返回异常类型: {type(raw).__name__}',
            'page_url': page.url,
        }

    if raw.get('error'):
        return {
            'success': False,
            'intercepted': False,
            'message': str(raw.get('error')),
            'extract': raw,
            'page_url': page.url,
        }

    rows: List[Dict[str, Any]] = raw.get('rows') or []
    if not rows:
        return {
            'success': True,
            'intercepted': False,
            'message': '页面无数据行（可能列表为空或表格结构变更）',
            'row_count': 0,
            'extract': raw,
            'page_url': page.url,
            'feishu_sync': None,
        }

    # --- 飞书：新建 / 增量更新策略在 sync_erp_order_rows_to_feishu 内实现 ---
    feishu_result = sync_erp_order_rows_to_feishu(rows, app_token=app_token, table_id=table_id)
    return {
        'success': bool(feishu_result.get('success')),
        'intercepted': False,
        'message': feishu_result.get('message', ''),
        'row_count': len(rows),
        'extract_meta': {
            'count': raw.get('count'),
            'log': raw.get('log'),
            'scroll': raw.get('scroll'),
            'pageHint': raw.get('pageHint'),
        },
        'page_url': page.url,
        'feishu_sync': feishu_result,
    }
