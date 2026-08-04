"""Nest CMS REST：鉴权 + AI /ai/chat（安特滑块等多模态识图）。"""
from __future__ import annotations

import base64
import json
import logging
import threading
from typing import Any, Dict, Optional, Tuple, Union

from utils.logger import get_logger

logger = get_logger('integrations.nest_client')

_token_lock = threading.Lock()
_cached_access_token: Optional[str] = None
_cached_refresh_token: Optional[str] = None

DEFAULT_NEST_API_BASE = 'https://nestapi.xfysj.top/xcx/api/v1'


def resolve_nest_api_base() -> str:
    """Nest REST 根路径（含 /xcx/api/v1）。"""
    from config import Config

    explicit = (getattr(Config, 'NEST_API_BASE', None) or '').strip().rstrip('/')
    if explicit:
        logger.debug('Nest API base (NEST_API_BASE): %s', explicit)
        return explicit

    host = (getattr(Config, 'WS_CLIENT_HOST', None) or '').strip().rstrip('/')
    if not host:
        return DEFAULT_NEST_API_BASE

    lowered = host.lower()
    if lowered in ('localhost', '127.0.0.1', '0.0.0.0'):
        return DEFAULT_NEST_API_BASE
    if 'nestapi' not in lowered and 'xfysj' not in lowered:
        return DEFAULT_NEST_API_BASE

    if host.startswith('http://') or host.startswith('https://'):
        base = host
    else:
        base = f'https://{host}'

    if '/xcx/api/' in base:
        return base.rstrip('/')
    return f'{base}/xcx/api/v1'


def nest_auth_configured() -> bool:
    from config import Config

    if (getattr(Config, 'NEST_JWT', None) or '').strip():
        return True
    if (getattr(Config, 'NEST_DEVICE_KEY', None) or '').strip():
        return True
    if (getattr(Config, 'NEST_USERNAME', None) or '').strip() and (
        getattr(Config, 'NEST_PASSWORD', None) or ''
    ).strip():
        return True
    return False


def _http_json(
    url: str,
    *,
    method: str = 'GET',
    body: Optional[dict] = None,
    headers: Optional[dict] = None,
    timeout: int = 90,
) -> Tuple[int, Any]:
    import http.client
    from urllib.parse import urlparse

    data = json.dumps(body, ensure_ascii=False).encode('utf-8') if body is not None else None
    body_len = len(data) if data else 0
    parsed = urlparse(url)
    host = parsed.hostname or 'localhost'
    port = parsed.port or (443 if parsed.scheme == 'https' else 80)
    path = parsed.path or '/'
    if parsed.query:
        path = f'{path}?{parsed.query}'

    hdrs = {
        'Content-Type': 'application/json; charset=utf-8',
        'Accept': 'application/json',
        **(headers or {}),
    }
    logger.info(
        'Nest HTTP %s %s (request_body=%s bytes, timeout=%ss)',
        method, url, body_len, timeout,
    )

    if parsed.scheme == 'https':
        conn = http.client.HTTPSConnection(host, port, timeout=timeout)
    else:
        conn = http.client.HTTPConnection(host, port, timeout=timeout)

    try:
        logger.info('Nest 连接 %s:%s …', host, port)
        conn.request(method, path, body=data, headers=hdrs)
        logger.info(
            'Nest 已发送 %s %s（%s bytes），等待服务端响应头；'
            '若 Nest 无 HTTP 访问日志，请开 access log 或看 /ai/chat 控制器而非 Agent 任务列表',
            method, path, body_len,
        )
        resp = conn.getresponse()
        raw = resp.read().decode('utf-8', errors='replace')
        logger.info(
            'Nest HTTP %s %s -> HTTP %s (%s bytes response)',
            method, url, resp.status, len(raw),
        )
        if not raw:
            return resp.status, {}
        try:
            return resp.status, json.loads(raw)
        except json.JSONDecodeError:
            return resp.status, {'raw': raw}
    except http.client.HTTPException as e:
        logger.error('Nest HTTP %s %s 协议错误: %s', method, url, e)
        raise
    except OSError as e:
        logger.error('Nest HTTP %s %s 网络错误: %s', method, url, e)
        raise
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _extract_token(payload: Any) -> Optional[str]:
    if not isinstance(payload, dict):
        return None
    for key in ('access_token', 'accessToken', 'token'):
        val = payload.get(key)
        if val:
            return str(val)
    data = payload.get('data')
    if isinstance(data, dict):
        return _extract_token(data)
    return None


def _extract_refresh_token(payload: Any) -> Optional[str]:
    if not isinstance(payload, dict):
        return None
    for key in ('refresh_token', 'refreshToken'):
        val = payload.get(key)
        if val:
            return str(val)
    data = payload.get('data')
    if isinstance(data, dict):
        return _extract_refresh_token(data)
    return None


def _auth_http_ok(status: int) -> bool:
    return status in (200, 201)


def _looks_like_device_key(value: str) -> bool:
    """device_key 格式为 keyId.secret，不是 JWT。"""
    s = (value or '').strip()
    if not s or s.startswith('eyJ'):
        return False
    return '.' in s and len(s) > 20


def _login_fresh() -> Tuple[str, Optional[str]]:
    from config import Config

    base = resolve_nest_api_base()
    device_key = (getattr(Config, 'NEST_DEVICE_KEY', None) or '').strip()
    jwt = (getattr(Config, 'NEST_JWT', None) or '').strip()
    if not device_key and jwt and _looks_like_device_key(jwt):
        logger.warning('NEST_JWT 形似设备密钥，已按 login-with-device-key 处理；建议改为 NEST_DEVICE_KEY')
        device_key = jwt

    if device_key:
        status, resp = _http_json(
            f'{base}/auth/login-with-device-key',
            method='POST',
            body={'device_key': device_key},
        )
        token = _extract_token(resp)
        if _auth_http_ok(status) and token:
            logger.info('Nest 设备密钥登录成功')
            return token, _extract_refresh_token(resp)
        raise RuntimeError(f'Nest 设备密钥登录失败 HTTP {status}: {resp}')

    if jwt:
        return jwt, None

    username = (getattr(Config, 'NEST_USERNAME', None) or '').strip()
    password = (getattr(Config, 'NEST_PASSWORD', None) or '').strip()
    if username and password:
        status, resp = _http_json(
            f'{base}/auth/login',
            method='POST',
            body={'username': username, 'password': password},
        )
        token = _extract_token(resp)
        if _auth_http_ok(status) and token:
            logger.info('Nest 用户名密码登录成功')
            return token, _extract_refresh_token(resp)
        raise RuntimeError(f'Nest 登录失败 HTTP {status}: {resp}')

    raise RuntimeError('Nest 鉴权未配置：请设置 NEST_DEVICE_KEY 或 NEST_USERNAME/NEST_PASSWORD 或 NEST_JWT')


def _refresh_access_token(refresh_token: str) -> Tuple[str, Optional[str]]:
    base = resolve_nest_api_base()
    status, resp = _http_json(
        f'{base}/auth/refresh',
        method='POST',
        body={'refresh_token': refresh_token},
    )
    token = _extract_token(resp)
    if _auth_http_ok(status) and token:
        logger.info('Nest refresh_token 刷新成功')
        return token, _extract_refresh_token(resp) or refresh_token
    raise RuntimeError(f'Nest 刷新 token 失败 HTTP {status}: {resp}')


def get_access_token(*, force_login: bool = False) -> str:
    global _cached_access_token, _cached_refresh_token

    with _token_lock:
        if not force_login and _cached_access_token:
            return _cached_access_token

        access, refresh = _login_fresh()
        _cached_access_token = access
        if refresh:
            _cached_refresh_token = refresh
        return access


def invalidate_nest_token() -> None:
    """清除 access_token 缓存（保留 refresh_token 供 401 后刷新）。"""
    global _cached_access_token
    with _token_lock:
        _cached_access_token = None


def extract_chat_text(payload: Any) -> str:
    """从 Nest /ai/chat 响应中提取助手文本。"""
    if isinstance(payload, str):
        return payload.strip()
    if not isinstance(payload, dict):
        return ''

    code = payload.get('code')
    if code is not None and code not in (0, 200) and payload.get('data') is None:
        msg = payload.get('message') or payload.get('msg') or ''
        if msg:
            return str(msg)

    data = payload.get('data', payload)
    if isinstance(data, str):
        return data.strip()
    if isinstance(data, dict):
        for key in ('message', 'content', 'reply', 'text', 'answer', 'result', 'output'):
            val = data.get(key)
            if val is None:
                continue
            if isinstance(val, str):
                return val.strip()
            if isinstance(val, dict) and val.get('content'):
                return str(val['content']).strip()
    if data is not None and not isinstance(data, (dict, list)):
        return str(data).strip()
    return ''


def _build_chat_message(
    user_text: str,
    image_bytes: Optional[bytes],
    *,
    mime_type: str = 'image/png',
) -> Union[str, list]:
    if not image_bytes:
        return user_text
    b64 = base64.b64encode(image_bytes).decode('ascii')
    data_url = f'data:{mime_type};base64,{b64}'
    return [
        {'type': 'text', 'text': user_text},
        {'type': 'image_url', 'image_url': {'url': data_url, 'detail': 'high'}},
    ]


def nest_ai_chat(
    *,
    user_text: str,
    system_prompt: str = '',
    image_bytes: Optional[bytes] = None,
    image_mime: str = 'image/png',
    timeout: int = 120,
    model: str = '',
) -> str:
    """
    调用 POST /ai/chat，返回助手回复纯文本。
    多模态：message 为 OpenAI 风格 text + image_url(data URL)。
    """
    global _cached_access_token, _cached_refresh_token

    base = resolve_nest_api_base()
    url = f'{base}/ai/chat'
    body: Dict[str, Any] = {
        'message': _build_chat_message(user_text, image_bytes, mime_type=image_mime),
    }
    if system_prompt:
        body['systemPrompt'] = system_prompt

    from config import Config

    use_model = (model or getattr(Config, 'NEST_CHAT_MODEL', '') or '').strip()
    if use_model:
        body['model'] = use_model

    if image_bytes:
        mm = int(getattr(Config, 'NEST_CHAT_TIMEOUT_MULTIMODAL', 360) or 360)
        timeout = max(int(timeout), mm)
        logger.info(
            'Nest /ai/chat 多模态: image_bytes=%s mime=%s model=%s user_chars=%s system_chars=%s',
            len(image_bytes),
            image_mime,
            use_model or '(Nest 默认，未传 model)',
            len(user_text or ''),
            len(system_prompt or ''),
        )
    elif use_model:
        logger.debug('Nest /ai/chat model=%s', use_model)

    token = get_access_token()
    headers = {'Authorization': f'Bearer {token}'}

    status, resp = _http_json(url, method='POST', body=body, headers=headers, timeout=timeout)
    if status == 401:
        with _token_lock:
            refresh = _cached_refresh_token
        invalidate_nest_token()
        if refresh:
            try:
                access, new_refresh = _refresh_access_token(refresh)
                with _token_lock:
                    _cached_access_token = access
                    _cached_refresh_token = new_refresh
                headers = {'Authorization': f'Bearer {access}'}
                status, resp = _http_json(url, method='POST', body=body, headers=headers, timeout=timeout)
            except Exception as e:
                logger.warning('Nest refresh 失败，尝试重新登录: %s', e)
        if status == 401:
            token = get_access_token(force_login=True)
            headers = {'Authorization': f'Bearer {token}'}
            status, resp = _http_json(url, method='POST', body=body, headers=headers, timeout=timeout)

    if not _auth_http_ok(status):
        raise RuntimeError(f'Nest /ai/chat 失败 HTTP {status}: {resp}')

    text = extract_chat_text(resp)
    if not text:
        raise RuntimeError(f'Nest /ai/chat 响应无文本内容: {resp}')
    if isinstance(resp, dict) and logger.isEnabledFor(logging.DEBUG):
        data = resp.get('data')
        if isinstance(data, dict):
            for k in ('model', 'modelId', 'model_id', 'agentModel', 'usage'):
                if k in data:
                    logger.debug('Nest /ai/chat 响应.%s=%s', k, data.get(k))
    return text


def nest_ai_generate(
    prompt: str,
    *,
    length: Optional[int] = None,
    content_type: str = '',
    keywords: str = '',
    timeout: int = 120,
) -> str:
    """POST /ai/generate（纯文本生成，无图片）。"""
    global _cached_access_token, _cached_refresh_token

    base = resolve_nest_api_base()
    url = f'{base}/ai/generate'
    body: Dict[str, Any] = {'prompt': prompt}
    if length is not None:
        body['length'] = length
    if content_type:
        body['contentType'] = content_type
    if keywords:
        body['keywords'] = keywords

    token = get_access_token()
    headers = {'Authorization': f'Bearer {token}'}
    status, resp = _http_json(url, method='POST', body=body, headers=headers, timeout=timeout)
    if status == 401:
        token = get_access_token(force_login=True)
        headers = {'Authorization': f'Bearer {token}'}
        status, resp = _http_json(url, method='POST', body=body, headers=headers, timeout=timeout)
    if not _auth_http_ok(status):
        raise RuntimeError(f'Nest /ai/generate 失败 HTTP {status}: {resp}')
    text = extract_chat_text(resp)
    if not text:
        raise RuntimeError(f'Nest /ai/generate 响应无文本: {resp}')
    return text


def nest_ai_complete(
    user_text: str,
    *,
    system_prompt: str = '',
    image_bytes: Optional[bytes] = None,
    image_mime: str = 'image/png',
    timeout: int = 120,
) -> str:
    """统一文本/多模态入口，等价于 /ai/chat。"""
    return nest_ai_chat(
        user_text=user_text,
        system_prompt=system_prompt,
        image_bytes=image_bytes,
        image_mime=image_mime,
        timeout=timeout,
    )


def _image_bytes_from_browser_context(browser_context: Optional[Dict]) -> Optional[bytes]:
    if not browser_context:
        return None
    raw = browser_context.get('screenshot') or browser_context.get('screenshot_b64')
    if not raw:
        return None
    if isinstance(raw, bytes):
        return raw
    if isinstance(raw, str):
        s = raw.strip()
        if s.startswith('data:'):
            _, _, b64 = s.partition(',')
            s = b64
        try:
            return base64.b64decode(s)
        except Exception:
            return None
    return None
