"""
AI 大脑 — 公共 API（统一走 Nest CMS：/xcx/api/v1/ai/*）

本仓库不再本地运行 Cursor SDK Agent。请配置 NEST_DEVICE_KEY（或账号密码）后，
通过 nestapi 的 /ai/chat、/ai/generate 等接口完成问答与识图。
"""
from __future__ import annotations

import logging
from typing import Callable, Dict, Iterator, List, Optional

logger = logging.getLogger('ai')


def _require_nest() -> None:
    from integrations.nest_client import nest_auth_configured

    if not nest_auth_configured():
        raise RuntimeError(
            'Nest AI 未配置：请设置 NEST_DEVICE_KEY 或 NEST_USERNAME/NEST_PASSWORD（见 .env.example）'
        )


def ask(
    prompt: str,
    *,
    system: str = '',
    model: str = '',
    max_tokens: int = 500,
) -> str:
    """同步 LLM 问答 → Nest POST /ai/chat（model/max_tokens 由 Nest 侧路由）。"""
    _require_nest()
    from integrations.nest_client import nest_ai_complete

    if model:
        logger.debug('ask() 忽略本地 model=%s，使用 Nest 默认模型', model)
    return nest_ai_complete(
        user_text=prompt,
        system_prompt=system or '',
        timeout=max(60, min(max_tokens // 2, 180)),
    )


def ask_vision(
    prompt: str,
    image,
    *,
    system: str = '',
    model: str = '',
    max_tokens: int = 200,
) -> str:
    """视觉识图 → Nest /ai/chat（图片 base64 上传）。"""
    _require_nest()
    from pathlib import Path

    from integrations.nest_client import nest_ai_complete

    if isinstance(image, (str, Path)):
        image_bytes = Path(image).read_bytes()
        mime = 'image/png'
    else:
        image_bytes = image
        mime = 'image/png'
    return nest_ai_complete(
        user_text=prompt,
        system_prompt=system or '',
        image_bytes=image_bytes,
        image_mime=mime,
        timeout=max(60, min(max_tokens * 2, 180)),
    )


def ask_stream(
    prompt: str,
    *,
    system: str = '',
    model: str = '',
    max_tokens: int = 2000,
) -> Iterator[str]:
    """流式问答：Nest 当前无 SSE，整段返回后一次 yield。"""
    yield ask(prompt, system=system, model=model, max_tokens=max_tokens)


def run_agent(
    instruction: str,
    *,
    tools: List[str] = None,
    session_name: Optional[str] = None,
    browser_context: Optional[Dict] = None,
    stream_callback: Optional[Callable[[str], None]] = None,
) -> str:
    """
    原 Cursor Agent 入口，现统一为 Nest /ai/chat。
    tools（如 playwright）不会在本地执行，仅作兼容参数并写日志。
    browser_context 可带 screenshot / screenshot_b64，会作为多模态图片一并发送。
    """
    _require_nest()
    if tools:
        logger.warning('Nest AI 不在本机执行 tools=%s，已忽略（请用 Playwright 脚本完成浏览器操作）', tools)
    if session_name:
        logger.debug('Nest AI 无本地 session resume，忽略 session_name=%s', session_name)

    from integrations.nest_client import nest_ai_complete, _image_bytes_from_browser_context

    user_text = instruction
    if browser_context:
        url = (browser_context.get('url') or '').strip()
        if url:
            user_text = f'当前页面 URL：{url}\n\n{user_text}'

    image_bytes = _image_bytes_from_browser_context(browser_context)
    result = nest_ai_complete(
        user_text=user_text,
        system_prompt='',
        image_bytes=image_bytes,
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
    """Nest 模式无本地 Agent 会话，返回空。"""
    return {}


def delete_session(session_name: str) -> None:
    """兼容旧 API，无操作。"""
    logger.debug('delete_session(%s) 在 Nest 模式下无效果', session_name)
