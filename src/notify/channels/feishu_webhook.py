"""
飞书 Webhook 渠道

封装 qudao_notify，提供统一的 Webhook 卡片通知接口。
"""
from __future__ import annotations

from notify.event import NotifyEvent, NotifyLevel
from utils.logger import get_logger

logger = get_logger("NotifyFeishuWebhook")

# 级别 → 卡片颜色映射
_LEVEL_TEMPLATE = {
    NotifyLevel.INFO: "blue",
    NotifyLevel.SUCCESS: "green",
    NotifyLevel.WARNING: "orange",
    NotifyLevel.ERROR: "red",
}


def send(event: NotifyEvent) -> bool:
    """
    通过飞书 Webhook 渠道发送卡片通知。

    Args:
        event: 通知事件

    Returns:
        是否发送成功
    """
    try:
        from tools.feishu.webhook.qudao_notify import (
            get_webhook_url,
            send_channel_notification,
        )
    except ImportError:
        logger.error("无法导入 qudao_notify，请检查依赖")
        return False

    webhook_url = get_webhook_url(event.source)
    if not webhook_url:
        logger.debug("来源 '%s' 未配置 Webhook URL，跳过通知", event.source)
        return False

    template = _LEVEL_TEMPLATE.get(event.level, "blue")

    result = send_channel_notification(
        event.source,
        title=event.title,
        description=event.description,
        link_url=event.link_url,
        link_text=event.link_text,
        header_template=template,
        image_base64=event.image_base64,
    )
    return result is not None and result.get("ok", False)
