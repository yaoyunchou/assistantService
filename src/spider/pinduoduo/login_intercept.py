"""拼多多 MMS 页面被重定向至登录时的统一处理（飞书提醒 + Webhook 二维码）。"""
from __future__ import annotations

from typing import Any, Dict, Optional

from playwright.sync_api import Page

from notify import login_alert as _notify_login_alert, NotifyEvent, NotifyLevel, NotifyChannel
from utils.logger import get_logger

logger = get_logger('PinduoduoLoginIntercept')


def handle_pdd_login_intercept(
    page: Page,
    *,
    title: str,
    link_url: str,
    link_text: str,
    success_message_with_qr: Optional[str] = None,
    success_message_no_qr: Optional[str] = None,
) -> Dict[str, Any]:
    """
    当前已在登录页（调用方应先判断 URL 含 login）。

    Returns:
        intercepted=True，含 qrcode 或 None。
    """
    from spider.pinduoduo.client import PinduoduoClient

    pd_client = PinduoduoClient(page=page)
    try:
        _notify_login_alert("pinduoduo")
        logger.info('已发送拼多多需登录的飞书提醒')
    except Exception as ex:
        logger.warning('飞书登录提醒发送失败: %s', ex)

    qr_data = pd_client.show_login_qrcode(skip_initial_navigation=True)
    if qr_data and qr_data != 'ALREADY_LOGGED_IN':
        try:
            from notify import notify
            notify(NotifyEvent(
                source="pinduoduo",
                level=NotifyLevel.WARNING,
                title=title,
                description='需要登录拼多多商家后台，请尽快扫码。',
                channel=NotifyChannel.FEISHU_WEBHOOK,
                link_url=link_url,
                link_text=link_text,
                image_base64=qr_data,
            ))
        except Exception as ex:
            logger.warning('飞书 Webhook 登录通知发送失败: %s', ex, exc_info=True)

        msg = success_message_with_qr or (
            '打开页面时被要求登录，请用拼多多 APP 扫码；二维码已返回前端展示，并已尝试飞书提醒。'
        )
        return {
            'success': False,
            'intercepted': True,
            'message': msg,
            'qrcode': qr_data,
            'page_url': page.url,
        }

    msg = success_message_no_qr or (
        '已跳转登录页但未成功截取二维码，请在本页点击「重新登录」完成扫码后再试。'
    )
    return {
        'success': False,
        'intercepted': True,
        'message': msg,
        'qrcode': None,
        'page_url': page.url,
    }


def maybe_login_response(
    page: Page,
    *,
    title: str,
    link_url: str,
    link_text: str,
) -> Optional[Dict[str, Any]]:
    """若当前 URL 含 login 则返回拦截响应，否则返回 None。"""
    cur = (page.url or '').lower()
    if 'login' not in cur:
        return None
    return handle_pdd_login_intercept(
        page,
        title=title,
        link_url=link_url,
        link_text=link_text,
    )
