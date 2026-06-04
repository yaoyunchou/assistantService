"""
AI 大脑 — Cursor SDK Agent 封装
基于真实的 cursor-sdk API（查阅 cursor_sdk.Agent / SendOptions / StdioMcpServerConfig）。

关键 API 要点（已通过 help() 验证）：
  - Agent.create(model, api_key, local=LocalAgentOptions(cwd=...))  # 无 mcp_servers
  - Agent.resume(agent_id)                                           # 只传 agent_id
  - agent.send(message, SendOptions(mcp_servers={name: config}))    # mcp_servers 在这里
  - run.stream()  -> Iterator[SDKMessage]
  - run.text()    -> str（阻塞等待完整结果）
  - SDKMessage 子类型：SDKAssistantMessage / SDKThinkingMessage / SDKToolUseMessage

其他模块通过 src/ai/__init__.py 的公共 API 调用，不直接使用本模块。
"""
from __future__ import annotations

import json
import logging
import os
import sys
import threading
from pathlib import Path
from typing import Callable, Dict, Iterator, List, Optional

logger = logging.getLogger('ai.agent')

# ─────────────────────────────────────────────────────────────
# Windows 兼容补丁
# cursor_sdk._bridge._read_discovery 使用 selectors.DefaultSelector，
# 在 Windows 上底层是 select.select()，仅支持 socket，不支持 pipe。
# 替换为线程阻塞读取版本，解决 WinError 10038。
# ─────────────────────────────────────────────────────────────

def _patch_bridge_for_windows() -> None:
    if sys.platform != 'win32':
        return
    try:
        import queue as _queue
        import cursor_sdk._bridge as _bridge_mod
        from cursor_sdk.errors import CursorSDKError as _CursorSDKError

        def _read_discovery_win(process, timeout: float):
            """Windows 兼容版：用线程阻塞读管道，绕过 select.select 限制。"""
            if process.stderr is None:
                raise _CursorSDKError("Bridge process stderr is unavailable")

            result_q: _queue.Queue = _queue.Queue()
            stderr_lines: list = []

            def _reader():
                try:
                    # process.stderr 以 text=True 打开，直接按行迭代
                    for line in process.stderr:
                        stderr_lines.append(line)
                        discovery = _bridge_mod.parse_discovery_line(line)
                        if discovery is not None:
                            result_q.put(('ok', discovery))
                            return
                    result_q.put(('exit', None))
                except Exception as exc:
                    result_q.put(('error', exc))

            t = threading.Thread(target=_reader, daemon=True)
            t.start()

            try:
                kind, value = result_q.get(timeout=timeout)
            except _queue.Empty:
                raise _CursorSDKError('Timed out waiting for bridge discovery')

            if kind == 'ok':
                return value
            if kind == 'exit':
                raise _CursorSDKError(
                    'Bridge exited before discovery: ' + ''.join(stderr_lines)
                )
            raise value  # kind == 'error'

        _bridge_mod._read_discovery = _read_discovery_win
        logger.debug('已应用 Windows cursor-sdk bridge 兼容补丁')
    except Exception as e:
        logger.warning('Windows bridge 补丁应用失败（将使用原始实现）: %s', e)


_patch_bridge_for_windows()

# ─────────────────────────────────────────────────────────────
# 会话持久化（agent_id ↔ session_name）
# ─────────────────────────────────────────────────────────────
_sessions_file: Optional[Path] = None
_sessions_lock = threading.Lock()


def _get_sessions_file() -> Path:
    global _sessions_file
    if _sessions_file is None:
        from utils.path_helper import get_safe_data_path
        _sessions_file = get_safe_data_path('ai/sessions.json')
        _sessions_file.parent.mkdir(parents=True, exist_ok=True)
    return _sessions_file


def _load_sessions() -> Dict[str, str]:
    f = _get_sessions_file()
    if not f.exists():
        return {}
    try:
        return json.loads(f.read_text(encoding='utf-8'))
    except Exception as e:
        logger.warning('读取 sessions.json 失败: %s', e)
        return {}


def _save_session(session_name: str, agent_id: str) -> None:
    with _sessions_lock:
        sessions = _load_sessions()
        sessions[session_name] = agent_id
        try:
            _get_sessions_file().write_text(
                json.dumps(sessions, ensure_ascii=False, indent=2),
                encoding='utf-8',
            )
        except Exception as e:
            logger.warning('保存 sessions.json 失败: %s', e)


def _delete_session(session_name: str) -> None:
    with _sessions_lock:
        sessions = _load_sessions()
        sessions.pop(session_name, None)
        try:
            _get_sessions_file().write_text(
                json.dumps(sessions, ensure_ascii=False, indent=2),
                encoding='utf-8',
            )
        except Exception as e:
            logger.warning('删除 session 失败: %s', e)


def list_sessions() -> Dict[str, str]:
    return _load_sessions()


# ─────────────────────────────────────────────────────────────
# MCP 服务器配置（传给 SendOptions，不是 Agent.create）
# ─────────────────────────────────────────────────────────────

def _build_mcp_servers(
    tools: List[str],
    browser_context: Optional[Dict] = None,
) -> Optional[Dict]:
    """构建 mcp_servers 字典，用于 SendOptions(mcp_servers=...)"""
    if 'playwright' not in tools:
        return None

    try:
        from cursor_sdk import StdioMcpServerConfig
    except ImportError:
        raise RuntimeError('cursor-sdk 未安装，请执行: pip install cursor-sdk')

    mcp_script = Path(__file__).parent / 'mcp' / 'playwright_server.py'

    chrome_path = ''
    try:
        from utils.browser_path import CHROME_EXECUTABLE_PATH
        chrome_path = CHROME_EXECUTABLE_PATH or ''
    except Exception:
        pass

    cookies_dir = ''
    try:
        from utils.path_helper import get_safe_data_path
        cookies_dir = str(get_safe_data_path('.'))
    except Exception:
        pass

    env = {
        'CHROME_EXECUTABLE_PATH': chrome_path,
        'AI_COOKIES_DIR': cookies_dir,
    }

    # 爬虫移交协议：把 browser_context 写入临时文件，通过环境变量传给子进程
    if browser_context:
        import base64
        import tempfile
        ctx_file = Path(tempfile.mktemp(suffix='.json'))
        try:
            ctx_data = {
                'url': browser_context.get('url', ''),
                'cookies': browser_context.get('cookies', []),
            }
            raw_shot = browser_context.get('screenshot')
            if raw_shot:
                if isinstance(raw_shot, bytes):
                    ctx_data['screenshot_b64'] = base64.b64encode(raw_shot).decode()
                elif isinstance(raw_shot, str):
                    ctx_data['screenshot_b64'] = raw_shot
            ctx_file.write_text(json.dumps(ctx_data), encoding='utf-8')
            env['AI_BROWSER_CONTEXT_FILE'] = str(ctx_file)
        except Exception as e:
            logger.warning('序列化 browser_context 失败: %s', e)

    return {
        'playwright': StdioMcpServerConfig(
            command=sys.executable,
            args=[str(mcp_script)],
            env=env,
        )
    }


# ─────────────────────────────────────────────────────────────
# 工厂：创建或恢复 Agent（不传 mcp_servers，那是 SendOptions 的事）
# ─────────────────────────────────────────────────────────────

def _get_or_create_agent(
    session_name: Optional[str],
    model: str,
    api_key: str,
    cwd: str,
):
    """返回 (agent, is_new)"""
    try:
        from cursor_sdk import Agent, LocalAgentOptions
    except ImportError:
        raise RuntimeError('cursor-sdk 未安装，请执行: pip install cursor-sdk')

    sessions = _load_sessions()
    existing_id = sessions.get(session_name) if session_name else None

    if existing_id:
        try:
            logger.info('恢复 Agent 会话: %s -> %s', session_name, existing_id)
            agent = Agent.resume(existing_id)
            return agent, False
        except Exception as e:
            logger.warning('恢复会话失败（%s），创建新 Agent: %s', existing_id, e)
            _delete_session(session_name)

    logger.info('创建新 Agent%s', f'（会话: {session_name}）' if session_name else '')
    agent = Agent.create(
        model=model,
        api_key=api_key,
        local=LocalAgentOptions(cwd=cwd),
    )
    return agent, True


# ─────────────────────────────────────────────────────────────
# 公共 run / run_stream
# ─────────────────────────────────────────────────────────────

def run(
    instruction: str,
    *,
    tools: List[str] = None,
    session_name: Optional[str] = None,
    browser_context: Optional[Dict] = None,
    stream_callback: Optional[Callable[[str], None]] = None,
) -> str:
    """同步运行 Agent，返回最终回复文本。"""
    tools = tools or []
    try:
        from cursor_sdk import SendOptions, LocalSendOptions
    except ImportError:
        raise RuntimeError('cursor-sdk 未安装，请执行: pip install cursor-sdk')

    from config import Config
    if not Config.CURSOR_API_KEY:
        raise RuntimeError('CURSOR_API_KEY 未配置，无法使用 Cursor Agent 功能')

    cwd = str(Path(__file__).parent.parent.parent)
    agent, _ = _get_or_create_agent(
        session_name, Config.CURSOR_MODEL, Config.CURSOR_API_KEY, cwd
    )

    if session_name:
        _save_session(session_name, agent.agent_id)

    full_instruction = _build_instruction(instruction, browser_context)
    mcp_servers = _build_mcp_servers(tools, browser_context)

    send_opts = SendOptions(
        model=Config.CURSOR_MODEL,
        mcp_servers=mcp_servers,
    )

    try:
        run_handle = agent.send(full_instruction, send_opts)

        if stream_callback:
            for msg in run_handle.stream():
                _dispatch_stream_message(msg, text_cb=stream_callback)
            result = run_handle.text()
        else:
            result = run_handle.text()

        return result or ''
    except Exception as e:
        logger.error('Agent run 失败: %s', e, exc_info=True)
        raise


def run_stream(
    instruction: str,
    *,
    tools: List[str] = None,
    session_name: Optional[str] = None,
    browser_context: Optional[Dict] = None,
) -> Iterator[Dict]:
    """
    流式运行 Agent，yield dict 事件：
      {'type': 'text',      'content': '...'}
      {'type': 'thinking',  'content': '...'}
      {'type': 'tool_call', 'name': '...', 'status': '...', 'result': ...}
      {'type': 'done',      'result': '...'}
      {'type': 'error',     'message': '...'}
    """
    tools = tools or []
    try:
        from cursor_sdk import SendOptions
    except ImportError:
        yield {'type': 'error', 'message': 'cursor-sdk 未安装，请执行: pip install cursor-sdk'}
        return

    from config import Config
    if not Config.CURSOR_API_KEY:
        yield {'type': 'error', 'message': 'CURSOR_API_KEY 未配置，无法使用 Cursor Agent 功能'}
        return

    try:
        cwd = str(Path(__file__).parent.parent.parent)
        agent, _ = _get_or_create_agent(
            session_name, Config.CURSOR_MODEL, Config.CURSOR_API_KEY, cwd
        )

        if session_name:
            _save_session(session_name, agent.agent_id)

        full_instruction = _build_instruction(instruction, browser_context)
        mcp_servers = _build_mcp_servers(tools, browser_context)

        send_opts = SendOptions(
            model=Config.CURSOR_MODEL,
            mcp_servers=mcp_servers,
        )

        run_handle = agent.send(full_instruction, send_opts)

        for msg in run_handle.stream():
            event = _sdk_message_to_event(msg)
            if event:
                yield event

        result_text = run_handle.text()
        yield {'type': 'done', 'result': result_text or ''}

    except Exception as e:
        logger.error('Agent stream 运行失败: %s', e, exc_info=True)
        yield {'type': 'error', 'message': str(e)}


# ─────────────────────────────────────────────────────────────
# 内部工具函数
# ─────────────────────────────────────────────────────────────

def _build_instruction(instruction: str, browser_context: Optional[Dict]) -> str:
    """如有移交协议，在指令中附加上下文提示"""
    if browser_context and browser_context.get('url'):
        return (
            f'{instruction}\n\n'
            f'[当前页面 URL]: {browser_context["url"]}\n'
            '（已为你加载了该页面的登录 Cookie，请使用 playwright navigate 工具导航到此 URL 开始操作）'
        )
    return instruction


def _dispatch_stream_message(msg, text_cb: Callable[[str], None]) -> None:
    """同步流式回调版：解析 SDKMessage 并调用 text_cb"""
    msg_type = getattr(msg, 'type', None)
    if msg_type == 'assistant':
        for block in msg.message.content:
            if getattr(block, 'type', None) == 'text' and block.text:
                text_cb(block.text)
    elif msg_type == 'thinking' and getattr(msg, 'text', None):
        text_cb(f'[思考中] {msg.text}')
    elif msg_type == 'tool_call':
        name = getattr(msg, 'name', '')
        status = getattr(msg, 'status', '')
        text_cb(f'[工具] {name}: {status}')


def _sdk_message_to_event(msg) -> Optional[Dict]:
    """把 SDKMessage 转成前端 SSE 事件 dict"""
    msg_type = getattr(msg, 'type', None)

    if msg_type == 'assistant':
        parts = []
        for block in msg.message.content:
            if getattr(block, 'type', None) == 'text' and block.text:
                parts.append(block.text)
        if parts:
            return {'type': 'text', 'content': ''.join(parts)}

    elif msg_type == 'thinking':
        text = getattr(msg, 'text', '')
        if text:
            return {'type': 'thinking', 'content': text}

    elif msg_type == 'tool_call':
        return {
            'type': 'tool_call',
            'name': getattr(msg, 'name', ''),
            'status': getattr(msg, 'status', ''),
            'result': getattr(msg, 'result', None),
        }

    return None
