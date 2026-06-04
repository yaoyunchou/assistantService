"""
AI 通知过滤器

在通知发出前，调用 AI 模块分析事件，决定是否值得打扰用户。

当前策略：
  - ERROR 级别：始终发送，不过滤
  - WARNING / SUCCESS / INFO：询问 AI 是否值得通知
  - AI 分析失败（网络错误/未配置）：降级为直接发送，不阻断通知

AI 判断依据（写入 prompt）：
  - 事件来源（source）
  - 级别（level）
  - 标题和描述
  - extra 中的附加上下文（如错误次数、是否已知问题等）
"""
from __future__ import annotations

from notify.event import NotifyEvent, NotifyLevel
from utils.logger import get_logger

logger = get_logger("NotifyFilter")

# ERROR 级别：无论如何必须发送
_ALWAYS_NOTIFY_LEVELS = {NotifyLevel.ERROR}

_AI_FILTER_PROMPT = """
你是一个系统监控助手，负责判断一条系统通知是否真的需要推送给用户。

通知信息：
- 来源模块：{source}
- 级别：{level}
- 标题：{title}
- 描述：{description}
- 附加信息：{extra}

判断规则：
1. 如果是明确的任务失败、登录失效、数据异常等需要人工介入的问题，回答 YES
2. 如果是常规成功通知、低价值信息、偶发性小问题，回答 NO
3. 只回答 YES 或 NO，不要其他内容

是否应该发送此通知？
""".strip()


def should_notify(event: NotifyEvent) -> bool:
    """
    判断此次通知事件是否应该发送。

    Returns:
        True  → 继续发送
        False → 静默（会写日志）
    """
    # ERROR 级别强制发送
    if event.level in _ALWAYS_NOTIFY_LEVELS:
        return True

    # 尝试调用 AI 过滤
    try:
        return _ai_should_notify(event)
    except Exception as e:
        # AI 调用失败时降级：直接发送，确保通知不丢失
        logger.debug("AI 过滤调用失败，降级为直接发送: %s", e)
        return True


def _ai_should_notify(event: NotifyEvent) -> bool:
    """调用 ai.ask() 判断是否值得通知。"""
    try:
        from ai import ask
    except ImportError:
        return True

    extra_str = ", ".join(f"{k}={v}" for k, v in (event.extra or {}).items()) or "无"

    prompt = _AI_FILTER_PROMPT.format(
        source=event.source,
        level=event.level.value,
        title=event.title,
        description=event.description[:500] if event.description else "",
        extra=extra_str,
    )

    try:
        answer = ask(prompt, max_tokens=5)
        verdict = (answer or "").strip().upper()
        should = verdict.startswith("Y")
        if not should:
            logger.info(
                "[NotifyFilter] AI 判断静默: source=%s level=%s title=%s",
                event.source, event.level, event.title,
            )
        return should
    except Exception as e:
        logger.debug("AI ask() 调用失败: %s", e)
        return True
