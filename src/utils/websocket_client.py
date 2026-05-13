"""
Socket.IO 客户端管理
对接 docs/websocket-api.md：监听事件 forward；path 默认 /socket.io/（与 engine.io 一致）。
action 映射：websocket_action_config.execute_action。
assistant_http：见 docs/socketio-assistant-http.md，远端发指令由本机按 axios 字段请求本地 HTTP，并 emit assistant_http_response。
"""
import json
import sys
import threading
import time
from pathlib import Path
from typing import Any, Optional, Dict
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from utils.logger import get_logger
from utils.websocket_action_config import execute_action
from utils.assistant_http_invoke import execute_http_like_axios

logger = get_logger('WebSocketClient')


def normalize_socketio_path(path: Optional[str]) -> str:
    """
    python-socketio 的 ``socketio_path`` 需以 ``/`` 开头、以 ``/`` 结尾（如 ``/socket.io/``）。
    配置里可写 ``socket.io`` 或 ``/socket.io``，连接前会规范化。
    """
    try:
        from config import Config

        default = getattr(Config, 'WS_CLIENT_PATH_DEFAULT', '/socket.io/')
    except Exception:
        default = '/socket.io/'
    p = (path or default).strip()
    if not p:
        p = default
    if not p.startswith('/'):
        p = '/' + p
    if not p.endswith('/'):
        p = p + '/'
    return p


# 全局单例
_ws_client_instance: Optional['WebSocketClientManager'] = None
_lock = threading.Lock()

# connect(assistant_key=...) 缺省时表示「沿用 Config」，与显式传入 None（本次不要 query）区分
_ASSISTANT_KEY_USE_CONFIG = object()


def build_socket_io_server_url(host: str, port: int) -> str:
    """
    拼 Socket.IO 客户端连接用的根 URL。

    Config.WS_CLIENT_HOST 允许带协议（如 https://nestapi.example.com），禁止再拼成
    ``http://https://...`` 导致握手失败。

    - **含协议的 URL 且未写端口**：按惯例使用 **https→443、http→80**，不再误用 ``WS_CLIENT_PORT``（避免 https 域名仍被拼成 ``:8080``）。
    - **仅域名/IP、无协议**：使用 ``http://{host}:{port}``，其中 ``port`` 为 ``Config.WS_CLIENT_PORT``。
    - 最终字符串对 **443 / 80** 省略端口段（与浏览器一致，等同于「默认端口不用写」）。
    """
    raw = (host or '').strip()
    if not raw:
        return f'http://127.0.0.1:{int(port)}'
    if '://' in raw:
        u = urlparse(raw if raw.split('://', 1)[0].lower() in ('http', 'https') else f'http://{raw}')
        hostname = u.hostname
        if not hostname:
            return f'http://127.0.0.1:{int(port)}'
        scheme = (u.scheme or 'http').lower()
        if u.port is not None:
            eff_port = int(u.port)
        elif scheme == 'https':
            eff_port = 443
        elif scheme == 'http':
            eff_port = 80
        else:
            eff_port = int(port)
        if (scheme == 'https' and eff_port == 443) or (scheme == 'http' and eff_port == 80):
            return f'{scheme}://{hostname}'
        return f'{scheme}://{hostname}:{eff_port}'
    return f'http://{raw}:{int(port)}'


def append_assistant_key_query(url: str, assistant_key: Optional[str]) -> str:
    """
    在 Socket.IO 根 URL 上附加 ``assistantKey``，供 Nest 等网关注册连接（与 path 无关，只影响 HTTP 握手 query）。
    见 docs/pinduoduo-erp-remote-api.md §2。
    """
    k = (assistant_key or '').strip()
    if not k:
        return url
    parts = urlparse(url)
    q = dict(parse_qsl(parts.query, keep_blank_values=True))
    q['assistantKey'] = k
    new_query = urlencode(q)
    return urlunparse((
        parts.scheme, parts.netloc, parts.path, parts.params, new_query, parts.fragment,
    ))


def _log_socket_url_for_log(url: str) -> str:
    """日志中脱敏 query 里的 assistantKey。"""
    try:
        p = urlparse(url)
        if not p.query:
            return url
        q = dict(parse_qsl(p.query, keep_blank_values=True))
        if 'assistantKey' in q:
            q['assistantKey'] = '***'
        if 'assistant_key' in q:
            q['assistant_key'] = '***'
        return urlunparse((
            p.scheme, p.netloc, p.path, p.params, urlencode(q), p.fragment,
        ))
    except Exception:
        return url


class WebSocketClientManager:
    """Socket.IO 客户端管理器：单例，线程安全，支持默认开启与自动重连；action 按映射表请求本地 url。"""

    def __init__(self):
        self._sio = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._connected = False
        self._connecting = False
        self._last_error: Optional[str] = None
        self._last_message_time: Optional[float] = None
        self._last_forward_payload: Optional[Dict[str, Any]] = None
        self._sid: Optional[str] = None
        self._lock = threading.Lock()
        self._auto_reconnect = True
        self._reconnect_interval = 5.0
        self._last_connect_err_log_wall: float = 0.0
        self._connect_err_suppressed: int = 0
        self._hinted_missing_assistant_key: bool = False

    def get_status(self) -> Dict[str, Any]:
        """获取当前状态（线程安全）。"""
        with self._lock:
            return {
                'connected': self._connected,
                'connecting': self._connecting,
                'last_error': self._last_error,
                'last_message_time': self._last_message_time,
                'last_forward_payload': self._last_forward_payload,
                'sid': self._sid,
            }

    def get_config(self) -> Dict[str, Any]:
        """从 Config 读取当前配置，并附加服务端预计算的实际握手地址。"""
        try:
            from config import Config
            host = Config.WS_CLIENT_HOST
            port = Config.WS_CLIENT_PORT
            path = getattr(Config, 'WS_CLIENT_PATH', Config.WS_CLIENT_PATH_DEFAULT)
            ak = getattr(Config, 'WS_CLIENT_ASSISTANT_KEY', None)
            base_url = build_socket_io_server_url(str(host), int(port))
            norm_path = normalize_socketio_path(path)
            full_url = append_assistant_key_query(base_url, ak)
            return {
                'enabled': Config.WS_CLIENT_ENABLED,
                'host': host,
                'port': port,
                'path': path,
                'assistant_key': ak,
                'resolved_base_url': base_url,
                'resolved_path': norm_path,
                'resolved_full_url': full_url,
            }
        except Exception as e:
            logger.warning(f"读取 WebSocket 配置失败: {e}")
            return {
                'enabled': True,
                'host': 'localhost',
                'port': 8080,
                'path': '/socket.io/',
                'assistant_key': 'erp-001',
                'resolved_base_url': 'http://localhost:8080',
                'resolved_path': '/socket.io/',
                'resolved_full_url': 'http://localhost:8080?assistantKey=erp-001',
            }

    def connect(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        path: Optional[str] = None,
        assistant_key: Any = _ASSISTANT_KEY_USE_CONFIG,
    ) -> Dict[str, Any]:
        """
        发起 Socket.IO 连接。若已在连接中则先断开再连。
        host/port/path 为 None 时使用 Config 中的配置。
        ``assistant_key`` 默认沿用 Config.WS_CLIENT_ASSISTANT_KEY；若显式传 ``None`` 或 ``""``
        则本次连接不在 URL 上加 assistantKey。
        """
        try:
            from config import Config
            h = host if host is not None else Config.WS_CLIENT_HOST
            p = port if port is not None else Config.WS_CLIENT_PORT
            raw_path = path if path is not None else getattr(
                Config, 'WS_CLIENT_PATH', Config.WS_CLIENT_PATH_DEFAULT
            )
            path_val = normalize_socketio_path(raw_path)
            if assistant_key is _ASSISTANT_KEY_USE_CONFIG:
                ak = getattr(Config, 'WS_CLIENT_ASSISTANT_KEY', None)
            else:
                ak = assistant_key
            if isinstance(ak, str):
                ak = ak.strip() or None
        except Exception as e:
            logger.warning(f"获取配置失败: {e}")
            return {'success': False, 'error': str(e)}

        self.disconnect()
        self._stop_event.clear()
        self._last_error = None
        with self._lock:
            self._connecting = True

        base_url = build_socket_io_server_url(str(h), int(p))
        url = append_assistant_key_query(base_url, ak)
        logger.info(
            "Socket.IO 解析后连接地址: %s（assistantKey=%s）",
            _log_socket_url_for_log(url),
            '已附加' if ak else             '未配置',
        )
        has_assistant_key = bool(ak)

        def run():
            try:
                import socketio
                sio = socketio.Client(logger=False, engineio_logger=False)

                @sio.event
                def connect():
                    with self._lock:
                        self._connected = True
                        self._connecting = False
                        self._sid = getattr(sio, 'sid', None)
                    logger.info(
                        "Socket.IO 已连接: %s path=%s sid=%s",
                        _log_socket_url_for_log(url),
                        path_val,
                        getattr(sio, 'sid', None),
                    )

                def _emit_assistant_http_response(result: Dict[str, Any]) -> None:
                    try:
                        sio.emit('assistant_http_response', result)
                    except Exception as ex:
                        logger.warning(f"emit assistant_http_response 失败: {ex}")

                def _schedule_assistant_http(payload: Dict[str, Any]) -> None:
                    def work():
                        try:
                            out = execute_http_like_axios(payload)
                            _emit_assistant_http_response(out)
                        except Exception as ex:
                            mid = payload.get('messageId')
                            if mid is None:
                                mid = payload.get('message_id')
                            _emit_assistant_http_response({
                                'messageId': mid,
                                'ok': False,
                                'status': None,
                                'data': None,
                                'error': str(ex),
                            })

                    threading.Thread(target=work, daemon=True).start()

                @sio.event
                def forward(data):
                    self._last_message_time = time.time()
                    with self._lock:
                        self._last_forward_payload = data if isinstance(data, dict) else {'raw': data}
                    logger.debug(f"Socket.IO 收到 forward: {data}")
                    if isinstance(data, dict) and data.get('type') == 'assistant_http':
                        inner = {k: v for k, v in data.items() if k != 'type'}
                        _schedule_assistant_http(inner)

                @sio.on('assistant_http')
                def on_assistant_http(data):
                    self._last_message_time = time.time()
                    payload = data if isinstance(data, dict) else {}
                    logger.debug(f"Socket.IO 收到 assistant_http: {data}")
                    _schedule_assistant_http(payload)
                
                @sio.event
                def action(data):
                    self._last_message_time = time.time()
                    payload = data if isinstance(data, dict) else {'raw': data}
                    with self._lock:
                        execute_action(payload.get('action'))
                    logger.debug(f"Socket.IO 收到 action: {data}")

                @sio.event
                def disconnect():
                    with self._lock:
                        self._connected = False
                        self._sid = None
                    logger.info("Socket.IO 已断开")

                @sio.on('connect_error')
                def on_connect_error(data):
                    self._last_error = str(data) if data else "Connection error"
                    with self._lock:
                        self._connecting = False
                    now = time.monotonic()
                    if now - self._last_connect_err_log_wall < 15.0:
                        self._connect_err_suppressed += 1
                        return
                    suppressed = self._connect_err_suppressed
                    self._connect_err_suppressed = 0
                    self._last_connect_err_log_wall = now
                    extra = (
                        f" （15s 内另有 {suppressed} 次同类失败已省略日志）"
                        if suppressed else ""
                    )
                    logger.warning(
                        "Socket.IO 连接错误: %s%s",
                        self._last_error,
                        extra,
                    )
                    if (
                        not has_assistant_key
                        and not self._hinted_missing_assistant_key
                    ):
                        self._hinted_missing_assistant_key = True
                        logger.info(
                            "若对接 Nest 网关：握手 URL 通常需携带 assistantKey；"
                            "请设置环境变量 WS_CLIENT_ASSISTANT_KEY，或在 Web「Socket.IO 客户端」页填写 assistantKey 并保存。"
                        )

                self._sio = sio
                logger.info(
                    "Socket.IO 客户端正在连接: %s path=%s transports=websocket,polling",
                    _log_socket_url_for_log(url),
                    path_val,
                )
                sio.connect(
                    url,
                    socketio_path=path_val,
                    transports=['websocket', 'polling'],
                    wait_timeout=10,
                )
            except Exception as e:
                with self._lock:
                    self._connecting = False
                self._last_error = str(e)
                logger.exception("Socket.IO 连接异常")
            finally:
                self._sio = None
                with self._lock:
                    self._connected = False
                    self._sid = None
                # 自动重连
                if self._auto_reconnect and not self._stop_event.is_set():
                    try:
                        from config import Config
                        if Config.WS_CLIENT_ENABLED:
                            logger.info(f"{self._reconnect_interval} 秒后尝试重连...")
                            time.sleep(self._reconnect_interval)
                            if not self._stop_event.is_set():
                                self.connect()
                    except Exception:
                        pass

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()
        return {
            'success': True,
            'started': True,
            'note': '仅表示已启动后台连接线程；Socket.IO 握手为异步，是否连上请以日志或 GET /api/websocket/status 为准。',
            'url': url,
            'path': path_val,
            'assistant_key_configured': bool(ak),
        }

    def disconnect(self) -> Dict[str, Any]:
        """断开连接并停止重连。"""
        self._stop_event.set()
        self._auto_reconnect = False
        sio = self._sio
        if sio is not None:
            try:
                sio.disconnect()
            except Exception as e:
                logger.debug(f"断开 Socket.IO 时: {e}")
            self._sio = None
        with self._lock:
            self._connected = False
            self._connecting = False
            self._sid = None
        self._thread = None
        logger.info("Socket.IO 客户端已断开")
        return {'success': True}

    def start_if_enabled(self) -> Dict[str, Any]:
        """若配置为启用，则使用当前配置连接（用于 Flask 启动时）。"""
        try:
            from config import Config
            if not Config.WS_CLIENT_ENABLED:
                return {'success': True, 'skipped': True, 'reason': 'disabled'}
            self._auto_reconnect = True
            return self.connect()
        except Exception as e:
            logger.exception("Socket.IO 启动失败")
            return {'success': False, 'error': str(e)}


def get_websocket_client() -> WebSocketClientManager:
    """获取 Socket.IO 客户端管理器单例。"""
    global _ws_client_instance
    with _lock:
        if _ws_client_instance is None:
            _ws_client_instance = WebSocketClientManager()
        return _ws_client_instance
