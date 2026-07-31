"""
已弃用：本地 Cursor SDK Agent。

`run` / `run_stream` 转发至 `integrations.nest_client`；请优先 `from ai import run_agent`。
"""
from __future__ import annotations

import logging
from typing import Callable, Dict, Iterator, List, Optional

logger = logging.getLogger('ai.agent')


def run(
    instruction: str,
    *,
    tools: List[str] = None,
    session_name: Optional[str] = None,
    browser_context: Optional[Dict] = None,
    stream_callback: Optional[Callable[[str], None]] = None,
) -> str:
    from ai import run_agent

    return run_agent(
        instruction,
        tools=tools,
        session_name=session_name,
        browser_context=browser_context,
        stream_callback=stream_callback,
    )


def run_stream(
    instruction: str,
    *,
    tools: List[str] = None,
    session_name: Optional[str] = None,
    browser_context: Optional[Dict] = None,
) -> Iterator[Dict]:
    from ai import run_agent_stream

    yield from run_agent_stream(
        instruction,
        tools=tools,
        session_name=session_name,
        browser_context=browser_context,
    )


def list_sessions() -> Dict[str, str]:
    from ai import list_sessions as _list

    return _list()


def _delete_session(session_name: str) -> None:
    from ai import delete_session

    delete_session(session_name)
