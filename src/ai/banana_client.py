"""
AI 大脑 — Banana Agent 客户端

封装 `https://test-sso.bananain.cn/ali-oss/api/v1/agent/ask/` 接口，
供 `src/ai/__init__.py` 的公共 API（ask / ask_vision / run_agent）使用。

特点：
- 一次问答模式（非流式）
- 鉴权简单：`Authorization: Bearer <AK>`，无需登录换取 token
- 多模态：`images: [{url}]`，`url` 支持远程 URL 与 `data:image/...;base64,...` 两种形式
- 响应：`{"success": true, "result": "..."}`

其他模块通过 `src/ai/__init__.py` 调用，不直接 import 本模块。
"""
from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from typing import Any, Dict, Iterator, Optional, Union

logger = logging.getLogger('ai.banana')

DEFAULT_API_BASE = 'https://test-sso.bananain.cn/ali-oss/api/v1'
ASK_PATH = '/agent/ask/'


def _resolve_api_base() -> str:
    """返回 Banana Agent API 根路径（不含尾部 /）。"""
    try:
        from config import Config

        explicit = (getattr(Config, 'BANANA_AI_API_BASE', None) or '').strip().rstrip('/')
        if explicit:
            return explicit
    except Exception:
        pass
    return DEFAULT_API_BASE


def _resolve_ak() -> str:
    """返回 Banana Agent AK。未配置时抛 RuntimeError。"""
    try:
        from config import Config

        ak = (getattr(Config, 'BANANA_AI_AK', None) or '').strip()
    except Exception:
        ak = ''
    if not ak:
        raise RuntimeError(
            'BANANA_AI_AK 未配置，无法调用 AI 接口（请在 .env 设置 BANANA_AI_AK=ak_xxx）'
        )
    return ak


def _http_post_json(url: str, body: Dict[str, Any], *, headers: Dict[str, str], timeout: int) -> Dict[str, Any]:
    """原生 HTTP POST，返回解析后的 JSON。"""
    import http.client
    from urllib.parse import urlparse

    data = json.dumps(body, ensure_ascii=False).encode('utf-8')
    parsed = urlparse(url)
    host = parsed.hostname or 'test-sso.bananain.cn'
    port = parsed.port or (443 if parsed.scheme == 'https' else 80)
    path = parsed.path or ASK_PATH
    if parsed.query:
        path = f'{path}?{parsed.query}'

    hdrs = {
        'Content-Type': 'application/json; charset=utf-8',
        'Accept': 'application/json',
        **headers,
    }
    logger.info(
        'Banana AI POST %s (body=%s bytes, timeout=%ss)',
        url, len(data), timeout,
    )

    if parsed.scheme == 'https':
        conn = http.client.HTTPSConnection(host, port, timeout=timeout)
    else:
        conn = http.client.HTTPConnection(host, port, timeout=timeout)

    try:
        conn.request('POST', path, body=data, headers=hdrs)
        resp = conn.getresponse()
        raw = resp.read().decode('utf-8', errors='replace')
        logger.info(
            'Banana AI -> HTTP %s (%s bytes)',
            resp.status, len(raw),
        )
        if not raw:
            return {'success': False, 'error': f'空响应 HTTP {resp.status}'}
        try:
            parsed_json = json.loads(raw)
        except json.JSONDecodeError:
            return {'success': False, 'error': f'非 JSON 响应: {raw[:500]}'}
        if isinstance(parsed_json, list):
            return {'success': True, 'result': '\n'.join(str(x) for x in parsed_json)}
        return parsed_json if isinstance(parsed_json, dict) else {'success': True, 'result': str(parsed_json)}
    except http.client.HTTPException as e:
        logger.error('Banana AI 协议错误: %s', e)
        raise
    except OSError as e:
        logger.error('Banana AI 网络错误: %s', e)
        raise
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _extract_text(payload: Any) -> str:
    """从响应中提取助手回复文本。

    响应格式：`{"success": true, "result": "..."}`
    兼容多种字段名与嵌套结构，避免接口小变动即报错。
    """
    if isinstance(payload, str):
        return payload.strip()
    if not isinstance(payload, dict):
        return str(payload).strip() if payload is not None else ''

    # success=false 时优先返回 error/message
    success = payload.get('success')
    if success is False:
        for key in ('error', 'message', 'msg'):
            val = payload.get(key)
            if val:
                raise RuntimeError(f'Banana AI 调用失败: {val}')

    for key in ('result', 'content', 'reply', 'text', 'answer', 'output', 'message', 'msg'):
        val = payload.get(key)
        if val is None:
            continue
        if isinstance(val, str):
            return val.strip()
        if isinstance(val, dict):
            for sub in ('content', 'text', 'answer', 'result'):
                sv = val.get(sub)
                if isinstance(sv, str):
                    return sv.strip()
        if isinstance(val, list):
            # OpenAI 风格 choices 兜底
            for item in val:
                if isinstance(item, dict):
                    msg = item.get('message') or {}
                    if isinstance(msg, dict) and msg.get('content'):
                        return str(msg['content']).strip()
    # OpenAI 风格 choices 兜底（顶层）
    choices = payload.get('choices')
    if isinstance(choices, list):
        for item in choices:
            if isinstance(item, dict):
                msg = item.get('message') or {}
                if isinstance(msg, dict) and msg.get('content'):
                    return str(msg['content']).strip()
    # data 嵌套
    data = payload.get('data')
    if isinstance(data, str):
        return data.strip()
    if isinstance(data, dict):
        return _extract_text(data)
    return ''


def _image_to_data_url(image: Union[str, Path, bytes], *, mime_type: str = 'image/png') -> str:
    """把本地图片转成 data URL。若传入已是 URL/data URL 则原样返回。"""
    if isinstance(image, bytes):
        b64 = base64.b64encode(image).decode('ascii')
        return f'data:{mime_type};base64,{b64}'

    s = str(image)
    # 远程 URL 或已是 data URL：原样返回
    if s.startswith('http://') or s.startswith('https://') or s.startswith('data:'):
        return s

    raw = Path(s).read_bytes()
    b64 = base64.b64encode(raw).decode('ascii')
    # 简单按扩展名推断 mime
    ext = Path(s).suffix.lower()
    mime_map = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp', '.gif': 'image/gif'}
    mime = mime_map.get(ext, mime_type)
    return f'data:{mime};base64,{b64}'


def banana_ask(
    prompt: str,
    *,
    system: str = '',
    images: Optional[list] = None,
    timeout: int = 120,
) -> str:
    """同步一次问答。

    Args:
        prompt: 用户问题
        system: 系统提示词
        images: 多模态图片列表，元素为以下任一形式：
            - 远程 URL 字符串：`https://example.com/a.jpg`
            - 本地图片路径字符串/Path：`captcha/shot.png`
            - 原始 bytes
        timeout: 超时秒数

    Returns:
        助手回复纯文本

    Raises:
        RuntimeError: AK 未配置 / 接口返回 success=false / 网络错误
    """
    ak = _resolve_ak()
    base = _resolve_api_base()
    url = f'{base}{ASK_PATH}'

    # 构造 images 数组：
    # - 远程 http(s) URL → {url: http_url}
    # - 本地图片 → {dataUrl: 'data:{mime};base64,...'}（接口实测支持 url / base64 / dataUrl 三种）
    image_items: list = []
    if images:
        for img in images:
            if isinstance(img, dict):
                # 已是结构化对象，原样透传
                image_items.append(img)
                continue
            u = _image_to_data_url(img)
            if not u:
                continue
            if u.startswith('http://') or u.startswith('https://'):
                image_items.append({'url': u})
            else:
                # data URL（本地图片转 base64）
                image_items.append({'dataUrl': u})

    body: Dict[str, Any] = {'prompt': prompt}
    if system:
        body['system'] = system
    if image_items:
        body['images'] = image_items

    headers = {'Authorization': f'Bearer {ak}'}
    payload = _http_post_json(url, body, headers=headers, timeout=timeout)
    text = _extract_text(payload)
    if not text:
        raise RuntimeError(f'Banana AI 响应无文本内容: {payload}')
    return text


def banana_ask_stream(
    prompt: str,
    *,
    system: str = '',
    images: Optional[list] = None,
    timeout: int = 180,
) -> Iterator[str]:
    """流式兼容层：Banana Agent 为一次问答，整段返回后一次 yield。"""
    yield banana_ask(prompt, system=system, images=images, timeout=timeout)
