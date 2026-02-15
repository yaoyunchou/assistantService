"""
Socket.IO 客户端管理
对接 docs/websocket-api.md：连接服务端 path /ws，监听默认事件 forward。
action 映射：从独立配置文件 ws_actions.json 读取 action -> url，收到 action 时本地 POST 该 url。
"""
import json
import sys
import threading
import time
from pathlib import Path
from typing import Optional, Dict, Any

from utils.logger import get_logger
from utils.websocket_action_config import execute_action

logger = get_logger('WebSocketClient')

# 全局单例
_ws_client_instance: Optional['WebSocketClientManager'] = None
_lock = threading.Lock()


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
        """从 Config 读取当前配置。"""
        try:
            from config import Config
            return {
                'enabled': Config.WS_CLIENT_ENABLED,
                'host': Config.WS_CLIENT_HOST,
                'port': Config.WS_CLIENT_PORT,
                'path': getattr(Config, 'WS_CLIENT_PATH', '/ws'),
            }
        except Exception as e:
            logger.warning(f"读取 WebSocket 配置失败: {e}")
            return {'enabled': True, 'host': '127.0.0.1', 'port': 8080, 'path': '/ws'}

    def connect(self, host: Optional[str] = None, port: Optional[int] = None, path: Optional[str] = None) -> Dict[str, Any]:
        """
        发起 Socket.IO 连接。若已在连接中则先断开再连。
        host/port/path 为 None 时使用 Config 中的配置。
        对接规范：path 默认 /ws，监听事件 forward。
        """
        try:
            from config import Config
            h = host if host is not None else Config.WS_CLIENT_HOST
            p = port if port is not None else Config.WS_CLIENT_PORT
            path_val = path if path is not None else getattr(Config, 'WS_CLIENT_PATH', '/ws')
        except Exception as e:
            logger.warning(f"获取配置失败: {e}")
            return {'success': False, 'error': str(e)}

        self.disconnect()
        self._stop_event.clear()
        self._last_error = None
        with self._lock:
            self._connecting = True

        url = f"http://{h}:{p}"

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
                    logger.info(f"Socket.IO 已连接: {url} path={path_val}, sid={getattr(sio, 'sid', None)}")

                @sio.event
                def forward(data):
                    self._last_message_time = time.time()
                    with self._lock:
                        self._last_forward_payload = data if isinstance(data, dict) else {'raw': data}
                    logger.debug(f"Socket.IO 收到 forward: {data}")
                
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
                    logger.warning(f"Socket.IO 连接错误: {self._last_error}")

                self._sio = sio
                logger.info(f"Socket.IO 客户端正在连接: {url}, path={path_val}, transports=websocket,polling")
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
        return {'success': True, 'url': url, 'path': path_val}

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
