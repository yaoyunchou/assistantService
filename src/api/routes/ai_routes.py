"""
AI 助手 API 路由
提供 LLM 问答与 Cursor SDK Agent 的 HTTP 接口。

端点：
  POST /api/ai/ask            简单 LLM 问答（同步）
  POST /api/ai/run            启动 Agent 任务（同步，返回结果）
  POST /api/ai/run-stream     启动 Agent 任务（SSE 流式输出）
  GET  /api/ai/sessions       列出所有持久化会话
  DELETE /api/ai/sessions/<name>  删除指定会话
"""
import json
import threading
from queue import Empty, Queue

from flask import Blueprint, Response, jsonify, request, stream_with_context

from utils.logger import get_logger

logger = get_logger('ai_routes')

bp = Blueprint('ai', __name__, url_prefix='/api/ai')

_SENTINEL = object()  # 流式输出结束哨兵


# ─────────────────────────────────────────────────────────────
# POST /api/ai/ask  —  简单 LLM 问答
# ─────────────────────────────────────────────────────────────

@bp.route('/ask', methods=['POST'])
def ask():
    """
    简单 LLM 问答（使用 AI_API_KEY / OpenAI 兼容接口）。

    请求体（JSON）：
      prompt   str  必填，用户问题
      system   str  可选，系统提示词
      model    str  可选，模型名称
      max_tokens int 可选，默认 500
    """
    body = request.get_json(silent=True) or {}
    prompt = (body.get('prompt') or '').strip()
    if not prompt:
        return jsonify({'success': False, 'error': 'prompt 不能为空'}), 400

    try:
        from ai import ask as ai_ask
        result = ai_ask(
            prompt,
            system=body.get('system', ''),
            model=body.get('model', ''),
            max_tokens=int(body.get('max_tokens', 500)),
        )
        return jsonify({'success': True, 'result': result})
    except RuntimeError as e:
        return jsonify({'success': False, 'error': str(e)}), 503
    except Exception as e:
        logger.error('AI ask 失败: %s', e, exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


# ─────────────────────────────────────────────────────────────
# POST /api/ai/run  —  Agent 任务（同步）
# ─────────────────────────────────────────────────────────────

@bp.route('/run', methods=['POST'])
def run():
    """
    同步运行 Cursor SDK Agent，等待完成后返回结果。

    请求体（JSON）：
      instruction     str        必填，任务描述
      tools           list[str]  可选，如 ["playwright"]
      session_name    str        可选，会话名称（支持 resume）
      browser_context dict       可选，爬虫移交协议 {url, cookies, screenshot_b64}
    """
    body = request.get_json(silent=True) or {}
    instruction = (body.get('instruction') or '').strip()
    if not instruction:
        return jsonify({'success': False, 'error': 'instruction 不能为空'}), 400

    # browser_context 的 screenshot 字段可能是 base64 字符串
    browser_context = body.get('browser_context') or None

    try:
        from ai import run_agent
        result = run_agent(
            instruction,
            tools=body.get('tools') or [],
            session_name=body.get('session_name') or None,
            browser_context=browser_context,
        )
        return jsonify({'success': True, 'result': result})
    except RuntimeError as e:
        return jsonify({'success': False, 'error': str(e)}), 503
    except Exception as e:
        logger.error('AI run 失败: %s', e, exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


# ─────────────────────────────────────────────────────────────
# POST /api/ai/run-stream  —  Agent 任务（SSE 流式）
# ─────────────────────────────────────────────────────────────

@bp.route('/run-stream', methods=['POST'])
def run_stream():
    """
    流式运行 Cursor SDK Agent，使用 Server-Sent Events 实时推送事件。

    请求体（JSON）：同 /run

    SSE 事件格式（data 字段为 JSON 字符串）：
      {"type": "text", "content": "..."}          助手文本片段
      {"type": "thinking", "content": "..."}       思考过程
      {"type": "tool_call", "name": "...", "status": "..."} 工具调用
      {"type": "done", "result": "..."}            完成
      {"type": "error", "message": "..."}          错误
    """
    body = request.get_json(silent=True) or {}
    instruction = (body.get('instruction') or '').strip()
    if not instruction:
        def _err():
            yield f'data: {json.dumps({"type": "error", "message": "instruction 不能为空"})}\n\n'
        return Response(stream_with_context(_err()), mimetype='text/event-stream')

    tools = body.get('tools') or []
    session_name = body.get('session_name') or None
    browser_context = body.get('browser_context') or None

    queue: Queue = Queue()

    def _worker():
        try:
            from ai import run_agent_stream
            for event in run_agent_stream(
                instruction,
                tools=tools,
                session_name=session_name,
                browser_context=browser_context,
            ):
                queue.put(event)
        except Exception as e:
            queue.put({'type': 'error', 'message': str(e)})
        finally:
            queue.put(_SENTINEL)

    t = threading.Thread(target=_worker, daemon=True)
    t.start()

    def _generate():
        while True:
            try:
                event = queue.get(timeout=120)
            except Empty:
                yield f'data: {json.dumps({"type": "error", "message": "超时"})}\n\n'
                break
            if event is _SENTINEL:
                break
            yield f'data: {json.dumps(event, ensure_ascii=False)}\n\n'
            if event.get('type') in ('done', 'error'):
                break

    return Response(
        stream_with_context(_generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
        },
    )


# ─────────────────────────────────────────────────────────────
# GET /api/ai/sessions  —  列出会话
# ─────────────────────────────────────────────────────────────

@bp.route('/sessions', methods=['GET'])
def list_sessions():
    """列出所有持久化的 Agent 会话"""
    from ai import list_sessions as ai_list_sessions
    sessions = ai_list_sessions()
    return jsonify({'success': True, 'sessions': sessions})


# ─────────────────────────────────────────────────────────────
# DELETE /api/ai/sessions/<name>  —  删除会话
# ─────────────────────────────────────────────────────────────

@bp.route('/sessions/<session_name>', methods=['DELETE'])
def delete_session(session_name: str):
    """删除指定名称的 Agent 会话"""
    from ai import delete_session as ai_delete_session
    ai_delete_session(session_name)
    return jsonify({'success': True, 'message': f'会话 {session_name} 已删除'})
