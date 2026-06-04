"""
飞书私信渠道

封装 FeishuMessageSender，提供统一的私信发送接口。
"""
from __future__ import annotations

from typing import Optional

from notify.event import NotifyEvent, NotifyLevel
from utils.logger import get_logger

logger = get_logger("NotifyFeishuDM")

# 级别 → 消息前缀映射
_LEVEL_PREFIX = {
    NotifyLevel.INFO: "【通知】",
    NotifyLevel.SUCCESS: "【成功】",
    NotifyLevel.WARNING: "【警告】",
    NotifyLevel.ERROR: "【错误】",
}


def send(event: NotifyEvent) -> bool:
    """
    通过飞书私信渠道发送通知。

    Args:
        event: 通知事件

    Returns:
        是否发送成功
    """
    try:
        from tools.feishu.message_sender import get_message_sender
    except ImportError:
        logger.error("无法导入 FeishuMessageSender，请检查依赖")
        return False

    sender = get_message_sender()
    if not sender.is_available():
        logger.debug("飞书 DM 未配置或已禁用，跳过私信通知")
        return False

    prefix = _LEVEL_PREFIX.get(event.level, "【通知】")
    parts = [f"{prefix}{event.title}"]
    if event.description:
        parts.append(event.description)

    message = "\n".join(parts)
    return sender.send_custom_message(message, user_id=event.user_id)
