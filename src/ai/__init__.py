"""
AI 大脑 — 公共 API（统一走 Banana Agent：`/ali-oss/api/v1/agent/ask/`）

本仓库不再本地运行 Cursor SDK Agent，也不再走 Nest /ai/chat。
请配置 `BANANA_AI_AK`（放在 .env，调用时以 `Authorization: Bearer <AK>` 发送）后，
通过本模块的 `ask` / `ask_vision` / `run_agent` 等函数完成问答与识图。
"""
from __future__ import annotations

import logging
from typing import Callable, Dict, Iterator, List, Optional

logger = logging.getLogger('ai')


def _require_ak() -> None:
    from ai.banana_client import _resolve_ak  # noqa: PLC0415

    # 未配置时直接抛错
    _resolve_ak()


def ask(
    prompt: str,
    *,
    system: str = '',
    model: str = '',
    max_tokens: int = 500,
) -> str:
    """同步 LLM 问答 → Banana Agent POST /agent/ask/。

    `model` 在 Banana Agent 路径下忽略（由服务端路由），仅写日志。
    `max_tokens` 映射为请求超时：`max(60, min(max_tokens // 2, 180))` 秒。
    """
    if model:
        logger.debug('ask() 忽略本地 model=%s，使用 Banana Agent 默认模型', model)
    from ai.banana_client import banana_ask  # noqa: PLC0415

    timeout = max(60, min(max_tokens // 2 if max_tokens > 0 else 120, 180))
    return banana_ask(prompt, system=system, timeout=timeout)


def ask_vision(
    prompt: str,
    image,
    *,
    system: str = '',
    model: str = '',
    max_tokens: int = 200,
) -> str:
    """视觉识图 → Banana Agent POST /agent/ask/（图片转 data URL 放入 images）。

    `image` 支持三种形式：路径字符串、`Path` 对象、原始 `bytes`。
    """
    from ai.banana_client import banana_ask  # noqa: PLC0415

    if model:
        logger.debug('ask_vision() 忽略本地 model=%s，使用 Banana Agent 默认视觉模型', model)
    timeout = max(60, min(max_tokens * 2 if max_tokens > 0 else 180, 180))
    # 多模态请求超时放大
    try:
        from config import Config

        mm = int(getattr(Config, 'BANANA_AI_TIMEOUT_MULTIMODAL', 300) or 300)
        timeout = max(timeout, mm)
    except Exception:
        pass
    return banana_ask(prompt, system=system, images=[image], timeout=timeout)


def ask_stream(
    prompt: str,
    *,
    system: str = '',
    model: str = '',
    max_tokens: int = 2000,
) -> Iterator[str]:
    """流式问答：Banana Agent 为一次问答，整段返回后一次 yield。"""
    from ai.banana_client import banana_ask_stream  # noqa: PLC0415

    yield from banana_ask_stream(prompt, system=system, timeout=180)


def run_agent(
    instruction: str,
    *,
    tools: List[str] = None,
    session_name: Optional[str] = None,
    browser_context: Optional[Dict] = None,
    stream_callback: Optional[Callable[[str], None]] = None,
) -> str:
    """
    原 Cursor Agent 入口，现统一为 Banana Agent /agent/ask/。

    tools（如 playwright）不会在本地执行，仅作兼容参数并写日志。
    browser_context 可带 screenshot / screenshot_b64，会作为多模态图片一并发送。
    """
    if tools:
        logger.warning('Banana Agent 不在本机执行 tools=%s，已忽略（请用 Playwright 脚本完成浏览器操作）', tools)
    if session_name:
        logger.debug('Banana Agent 无本地 session resume，忽略 session_name=%s', session_name)

    from ai.banana_client import banana_ask  # noqa: PLC0415

    user_text = instruction
    images: List = []
    if browser_context:
        url = (browser_context.get('url') or '').strip()
        if url:
            user_text = f'当前页面 URL：{url}\n\n{user_text}'
        shot = browser_context.get('screenshot')
        if shot:
            images.append(shot)
        shot_b64 = browser_context.get('screenshot_b64')
        if shot_b64:
            images.append(shot_b64)

    result = banana_ask(
        user_text,
        images=images or None,
        timeout=180,
    )
    if stream_callback:
        stream_callback(result)
    return result


def run_agent_stream(
    instruction: str,
    *,
    tools: List[str] = None,
    session_name: Optional[str] = None,
    browser_context: Optional[Dict] = None,
) -> Iterator[Dict]:
    """流式事件兼容层：单次 text + done。"""
    try:
        result = run_agent(
            instruction,
            tools=tools,
            session_name=session_name,
            browser_context=browser_context,
        )
        yield {'type': 'text', 'content': result}
        yield {'type': 'done', 'result': result}
    except Exception as e:
        yield {'type': 'error', 'message': str(e)}


def list_sessions() -> Dict[str, str]:
    """Banana Agent 模式无本地 Agent 会话，返回空。"""
    return {}


def delete_session(session_name: str) -> None:
    """兼容旧 API，无操作。"""
    logger.debug('delete_session(%s) 在 Banana Agent 模式下无效果', session_name)
