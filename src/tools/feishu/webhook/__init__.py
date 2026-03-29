"""
飞书自定义机器人 Webhook（群机器人 / 自定义机器人 Hook）
用于无需租户 token 的卡片通知。
"""
from .notify import (
    build_sync_notification_card,
    send_webhook_raw,
    send_sync_notification,
    upload_image_get_img_key,
)
from .qudao_notify import (
    CHANNEL_DEFAULT,
    CHANNEL_PINDUODUO,
    get_custom_bot_keyword,
    get_webhook_url,
)

__all__ = [
    'build_sync_notification_card',
    'send_webhook_raw',
    'send_sync_notification',
    'upload_image_get_img_key',
    'CHANNEL_DEFAULT',
    'CHANNEL_PINDUODUO',
    'get_custom_bot_keyword',
    'get_webhook_url',
]
