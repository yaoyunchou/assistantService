"""
如意助手本地 HTTP 调用（axios 风格字段），供 Socket.IO 远端指令使用。
相对 URL 会解析到当前 Flask 监听地址（ASSISTANT_HTTP_BASE 或 http://HOST:PORT）。
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from utils.logger import get_logger

logger = get_logger('AssistantHttpInvoke')

# 响应体文本模式下的最大字符数（避免巨量 HTML 拖垮 Socket）
DEFAULT_MAX_RESPONSE_CHARS = 512 * 1024


def _assistant_bind_host(host: str) -> str:
    if host in ("0.0.0.0", "::", "", "*"):
        return "127.0.0.1"
    return host


def get_assistant_http_origin() -> str:
    """本机如意助手 HTTP 根地址，不含尾部斜杠。"""
    try:
        from config import Config

        base = (getattr(Config, "ASSISTANT_HTTP_BASE", None) or "").strip()
        if base:
            return base.rstrip("/")
        h = _assistant_bind_host(str(Config.HOST))
        port = int(Config.PORT)
        return f"http://{h}:{port}"
    except Exception as e:
        logger.warning(f"读取 ASSISTANT_HTTP_BASE 失败，使用默认: {e}")
        return "http://127.0.0.1:8887"


def resolve_assistant_http_url(url: str) -> str:
    """
    若 url 已是绝对 http(s) 地址则原样返回；
    否则拼到如意助手 origin 上（支持 /path 或 path）。
    """
    u = (url or "").strip()
    if not u:
        raise ValueError("url 不能为空")
    lower = u.lower()
    if lower.startswith("http://") or lower.startswith("https://"):
        return u
    path = u if u.startswith("/") else f"/{u}"
    return get_assistant_http_origin() + path


def _parse_response_body(resp: Any, max_chars: int) -> Any:
    ct = (resp.headers.get("Content-Type") or "").lower()
    text = resp.text
    if len(text) > max_chars:
        return text[:max_chars] + f"\n... [truncated, total {len(text)} chars]"
    if "application/json" in ct:
        try:
            return resp.json()
        except Exception:
            return text
    return text


def execute_http_like_axios(
    payload: Dict[str, Any],
    *,
    max_response_chars: int = DEFAULT_MAX_RESPONSE_CHARS,
) -> Dict[str, Any]:
    """
    按 axios 风格执行 HTTP 请求并返回可经 Socket 回传的结构。

    支持字段：
    - messageId / message_id：回包原样带回，便于关联
    - method：默认 GET
    - url：必填；可为绝对 URL 或相对路径（相对则指向本助手）
    - params：查询参数
    - headers：请求头
    - json：若存在则作为 JSON body（requests json=）
    - data：原始 body；若 dict 且未提供 json，则默认按 JSON 编码
    - timeout：秒，默认 60

    返回：
    - messageId, ok, status, headers（精简）, data（解析后的 body）, error
    """
    import requests

    mid = payload.get("messageId")
    if mid is None:
        mid = payload.get("message_id")

    def wrap(
        *,
        ok: bool,
        status: Optional[int],
        headers: Optional[Dict[str, str]],
        data: Any,
        error: Optional[str],
    ) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "messageId": mid,
            "ok": ok,
            "status": status,
            "data": data,
            "error": error,
        }
        if headers is not None:
            out["headers"] = headers
        return out

    try:
        method = (payload.get("method") or "GET").upper()
        url = resolve_assistant_http_url(str(payload.get("url") or ""))
        timeout = float(payload.get("timeout", 60))
        params = payload.get("params")
        headers_in = payload.get("headers")
        headers: Optional[Dict[str, str]] = None
        if isinstance(headers_in, dict):
            headers = {str(k): str(v) for k, v in headers_in.items()}

        kwargs: Dict[str, Any] = {"timeout": timeout}
        if params is not None:
            kwargs["params"] = params
        if headers is not None:
            kwargs["headers"] = headers

        json_body = payload.get("json")
        data_body = payload.get("data")

        if json_body is not None:
            kwargs["json"] = json_body
        elif data_body is not None:
            if isinstance(data_body, (dict, list)):
                kwargs["json"] = data_body
            else:
                kwargs["data"] = data_body

        resp = requests.request(method, url, **kwargs)
        rh = {
            k: v
            for k, v in resp.headers.items()
            if k.lower() in ("content-type", "content-length")
        }
        body = _parse_response_body(resp, max_response_chars)
        ok = 200 <= resp.status_code < 300
        return wrap(
            ok=ok,
            status=resp.status_code,
            headers=rh,
            data=body,
            error=None if ok else f"HTTP {resp.status_code}",
        )
    except Exception as e:
        logger.exception("assistant_http 执行失败")
        return wrap(
            ok=False,
            status=None,
            headers=None,
            data=None,
            error=str(e),
        )
