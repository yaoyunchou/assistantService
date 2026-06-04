"""
AI 大脑 — 公共 API
系统中所有需要 AI 能力的模块，只从这里导入。

用法示例：
    # 简单 LLM 问答（用 AI_API_KEY，OpenAI 兼容）
    from ai import ask
    result = ask("帮我分析这段文字：...", system="你是一个分析助手")

    # Cursor SDK Agent（用 CURSOR_API_KEY，支持工具调用）
    from ai import run_agent
    result = run_agent("帮我打开拼多多 ERP 并截图", tools=["playwright"])

    # 爬虫遇障时移交 Agent（传入当前页面状态）
    from ai import run_agent
    result = run_agent(
        "页面出现验证码，请帮我处理并继续操作",
        tools=["playwright"],
        browser_context={"url": page.url, "cookies": cookies, "screenshot": screenshot_bytes},
    )

    # 流式输出（用于 SSE/WebSocket）
    from ai import run_agent_stream
    for event in run_agent_stream("帮我分析订单数据", tools=[]):
        print(event)  # {'type': 'text', 'content': '...'}
"""
from __future__ import annotations

from typing import Callable, Dict, Iterator, List, Optional


# ─────────────────────────────────────────────────────────────
# ① 简单 LLM 问答（同步，使用 AI_API_KEY / OpenAI 兼容接口）
# ─────────────────────────────────────────────────────────────

def ask(
    prompt: str,
    *,
    system: str = '',
    model: str = '',
    max_tokens: int = 500,
) -> str:
    """
    同步 LLM 问答。

    Args:
        prompt: 用户问题/提示词
        system: 系统提示词（可选）
        model: 模型名称，为空时使用 Config.AI_STOCK_LINK_MODEL
        max_tokens: 最大 token 数

    Returns:
        助手回复字符串；调用失败时返回空字符串并写日志

    Raises:
        RuntimeError: AI_API_KEY 未配置或 openai 包未安装
    """
    from ai.client import get_default_client
    return get_default_client().complete(
        prompt,
        system=system,
        model=model,
        max_tokens=max_tokens,
    )


def ask_stream(
    prompt: str,
    *,
    system: str = '',
    model: str = '',
    max_tokens: int = 2000,
) -> Iterator[str]:
    """流式 LLM 问答，逐块 yield 文本"""
    from ai.client import get_default_client
    yield from get_default_client().complete_stream(
        prompt,
        system=system,
        model=model,
        max_tokens=max_tokens,
    )


# ─────────────────────────────────────────────────────────────
# ② Cursor SDK Agent（必须配置 CURSOR_API_KEY）
# ─────────────────────────────────────────────────────────────

def run_agent(
    instruction: str,
    *,
    tools: List[str] = None,
    session_name: Optional[str] = None,
    browser_context: Optional[Dict] = None,
    stream_callback: Optional[Callable[[str], None]] = None,
) -> str:
    """
    同步运行 Cursor SDK Agent。

    Args:
        instruction: 自然语言任务描述
        tools: 可用工具，如 ['playwright']（启用浏览器控制）
        session_name: 持久化会话名称，同名 session 会 resume 同一 agent
        browser_context: 爬虫移交协议，格式：
            {
                'url': str,               # 当前页面 URL
                'cookies': list[dict],    # Playwright cookies（直接传 context.cookies() 结果）
                'screenshot': bytes,      # 可选，当前截图
            }
        stream_callback: 流式输出回调，每收到一段文本调用一次

    Returns:
        Agent 最终回复文本

    Raises:
        RuntimeError: CURSOR_API_KEY 未配置或 cursor-sdk 未安装
    """
    from ai import agent as _agent_mod
    return _agent_mod.run(
        instruction,
        tools=tools or [],
        session_name=session_name,
        browser_context=browser_context,
        stream_callback=stream_callback,
    )


def run_agent_stream(
    instruction: str,
    *,
    tools: List[str] = None,
    session_name: Optional[str] = None,
    browser_context: Optional[Dict] = None,
) -> Iterator[Dict]:
    """
    流式运行 Cursor SDK Agent，yield dict 事件。

    事件类型：
        {'type': 'text', 'content': '...'}           助手文本片段
        {'type': 'thinking', 'content': '...'}        思考过程
        {'type': 'tool_call', 'name': '...', 'status': '...'} 工具调用状态
        {'type': 'done', 'result': '...'}             运行结束，含最终结果
        {'type': 'error', 'message': '...'}           错误信息
    """
    from ai import agent as _agent_mod
    yield from _agent_mod.run_stream(
        instruction,
        tools=tools or [],
        session_name=session_name,
        browser_context=browser_context,
    )


# ─────────────────────────────────────────────────────────────
# ③ 会话管理
# ─────────────────────────────────────────────────────────────

def list_sessions() -> Dict[str, str]:
    """返回所有持久化的 Agent 会话（session_name -> agent_id）"""
    from ai import agent as _agent_mod
    return _agent_mod.list_sessions()


def delete_session(session_name: str) -> None:
    """删除指定 Agent 会话"""
    from ai.agent import _delete_session
    _delete_session(session_name)
