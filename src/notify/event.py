"""
通知事件数据结构

定义通知的级别、渠道和事件模型。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class NotifyLevel(str, Enum):
    """通知级别"""
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


class NotifyChannel(str, Enum):
    """通知渠道"""
    FEISHU_DM = "feishu_dm"          # 飞书私信
    FEISHU_WEBHOOK = "feishu_webhook" # 飞书机器人 Webhook


@dataclass
class NotifyEvent:
    """
    通知事件：描述一次通知的所有必要信息。

    Attributes:
        source:       来源模块标识，如 'pinduoduo'、'scheduler'、'tu'
        level:        通知级别（INFO / SUCCESS / WARNING / ERROR）
        title:        通知标题（Webhook 卡片标头 / DM 消息首行）
        description:  正文内容，支持飞书 lark_md 语法
        channel:      目标渠道，默认 FEISHU_WEBHOOK
        user_id:      DM 渠道的接收人 open_id，None 时用 FEISHU_USER_ID 默认值
        link_url:     卡片底部跳转链接（Webhook 渠道有效）
        link_text:    跳转按钮文案
        image_base64: 可选截图 / 二维码（base64 或 data URL）
        extra:        任意附加元数据，供 filter.py 做决策参考
    """
    source: str
    level: NotifyLevel
    title: str
    description: str = ""
    channel: NotifyChannel = NotifyChannel.FEISHU_WEBHOOK
    user_id: Optional[str] = None
    link_url: str = ""
    link_text: str = "查看详情"
    image_base64: Optional[str] = None
    extra: dict = field(default_factory=dict)
