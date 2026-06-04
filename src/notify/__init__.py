"""
notify — 统一通知模块

系统中所有通知消息的唯一出口。
其他模块不应直接调用 FeishuMessageSender 或 qudao_notify，
统一通过本模块的接口发送。

基本用法
--------
    from notify import notify, NotifyEvent, NotifyLevel, NotifyChannel

    # 发送任务结果（Webhook 卡片）
    notify(NotifyEvent(
        source="pinduoduo",
        level=NotifyLevel.SUCCESS,
        title="ERP 订单同步完成",
        description="**采集行数**: 42  **新建**: 10  **更新**: 32",
        link_url="https://mms.pinduoduo.com/...",
    ))

    # 发送登录失效警告（私信 + Webhook 双发）
    login_alert("pinduoduo")

    # 发送任务结果（便捷函数）
    task_result("pinduoduo", "ERP 同步", "同步了 42 条记录", success=True)

    # 发送自定义文本私信
    custom("定时任务执行完成：pdd_inventory_sync", source="scheduler")
"""
from __future__ import annotations

from typing import Optional

from notify.event import NotifyChannel, NotifyEvent, NotifyLevel
from notify.filter import should_notify
from utils.logger import get_logger

logger = get_logger("Notify")

__all__ = [
    "notify",
    "login_alert",
    "task_result",
    "custom",
    "NotifyEvent",
    "NotifyLevel",
    "NotifyChannel",
]


# ───────────────────────────── 核心入口 ─────────────────────────────

def notify(event: NotifyEvent) -> bool:
    """
    统一通知入口。

    流程：
        1. filter.should_notify() → 判断是否值得发送（AI 过滤层）
        2. 按 event.channel 分发到对应渠道
        3. 记录日志，返回是否成功

    Args:
        event: 通知事件

    Returns:
        True 表示成功发送（或被过滤静默也算正常）
    """
    if not should_notify(event):
        logger.info(
            "[notify] 已过滤 source=%s level=%s title=%s",
            event.source, event.level, event.title,
        )
        return True

    logger.info(
        "[notify] 发送 source=%s level=%s channel=%s title=%s",
        event.source, event.level, event.channel, event.title,
    )

    if event.channel == NotifyChannel.FEISHU_DM:
        from notify.channels import feishu_dm
        return feishu_dm.send(event)

    if event.channel == NotifyChannel.FEISHU_WEBHOOK:
        from notify.channels import feishu_webhook
        return feishu_webhook.send(event)

    logger.warning("[notify] 未知渠道: %s", event.channel)
    return False


# ───────────────────────────── 便捷函数 ─────────────────────────────

def login_alert(source: str, *, user_id: Optional[str] = None) -> bool:
    """
    发送「需要重新登录」警告。

    同时通过 Webhook（橙色卡片）和私信两个渠道发送。

    Args:
        source:  来源模块，如 'pinduoduo'
        user_id: 私信接收人 open_id，None 时使用 FEISHU_USER_ID 默认值
    """
    _source_name = _source_display(source)
    base = dict(
        source=source,
        level=NotifyLevel.WARNING,
        title=f"{_source_name} · 需要重新登录",
        description=f"检测到 **{_source_name}** 登录状态已失效，请及时处理。",
        link_text="前往登录",
    )

    ok_webhook = notify(NotifyEvent(**base, channel=NotifyChannel.FEISHU_WEBHOOK))

    ok_dm = notify(NotifyEvent(
        **base,
        channel=NotifyChannel.FEISHU_DM,
        user_id=user_id,
    ))

    return ok_webhook or ok_dm


def task_result(
    source: str,
    title: str,
    description: str,
    *,
    success: bool,
    link_url: str = "",
    image_base64: Optional[str] = None,
) -> bool:
    """
    发送任务执行结果通知（Webhook 卡片）。

    Args:
        source:       来源模块标识
        title:        任务名称，如 'ERP 订单同步'
        description:  结果描述，支持 lark_md 语法
        success:      True → 绿色成功卡片，False → 橙色警告卡片
        link_url:     可选跳转链接
        image_base64: 可选截图
    """
    level = NotifyLevel.SUCCESS if success else NotifyLevel.WARNING
    prefix = "✅" if success else "⚠️"
    return notify(NotifyEvent(
        source=source,
        level=level,
        title=f"{prefix} {title}",
        description=description,
        channel=NotifyChannel.FEISHU_WEBHOOK,
        link_url=link_url,
        image_base64=image_base64,
    ))


def custom(
    message: str,
    *,
    source: str = "system",
    user_id: Optional[str] = None,
    level: NotifyLevel = NotifyLevel.INFO,
) -> bool:
    """
    发送自定义文本私信。

    Args:
        message:  消息正文
        source:   来源模块（用于日志追踪）
        user_id:  接收人 open_id，None 时使用默认值
        level:    通知级别
    """
    return notify(NotifyEvent(
        source=source,
        level=level,
        title=message,
        channel=NotifyChannel.FEISHU_DM,
        user_id=user_id,
    ))


# ───────────────────────────── 内部工具 ─────────────────────────────

_SOURCE_DISPLAY = {
    "pinduoduo": "拼多多助手",
    "tu": "途强助手",
    "ali1688": "1688助手",
    "scheduler": "定时任务",
    "system": "系统",
}


def _source_display(source: str) -> str:
    return _SOURCE_DISPLAY.get(source, source)
