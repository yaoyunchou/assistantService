"""
Socket.IO / WebSocket 客户端管理 API
"""
from flask import Blueprint, request, jsonify
from flasgger import swag_from
from config import Config
from utils.websocket_client import get_websocket_client
from utils.config_manager import get_config_manager
from utils.logger import get_logger

routes_logger = get_logger('Routes')
bp = Blueprint('websocket', __name__, url_prefix='/api/websocket')


@bp.route('/status', methods=['GET'])
@swag_from({
    'tags': ['WebSocket'],
    'summary': '获取 Socket.IO 客户端连接状态',
    'responses': {200: {'description': 'success', 'schema': {'type': 'object'}}},
})
def websocket_status():
    """获取 WebSocket 客户端连接状态"""
    try:
        client = get_websocket_client()
        status = client.get_status()
        return jsonify({'success': True, 'status': status}), 200
    except Exception as e:
        routes_logger.error(f"获取 WebSocket 状态异常: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/config', methods=['GET'])
@swag_from({
    'tags': ['WebSocket'],
    'summary': '获取 Socket.IO 客户端配置',
    'responses': {200: {'description': 'success', 'schema': {'type': 'object'}}},
})
def websocket_config_get():
    """获取 WebSocket 客户端配置"""
    try:
        client = get_websocket_client()
        config = client.get_config()
        return jsonify({'success': True, 'config': config}), 200
    except Exception as e:
        routes_logger.error(f"获取 WebSocket 配置异常: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/config', methods=['POST'])
@swag_from({
    'tags': ['WebSocket'],
    'summary': '更新并保存 Socket.IO 客户端配置',
    'parameters': [{
        'in': 'body',
        'name': 'body',
        'schema': {
            'type': 'object',
            'properties': {
                'enabled': {'type': 'boolean'},
                'host': {'type': 'string'},
                'port': {'type': 'integer'},
                'path': {'type': 'string'},
            },
        },
    }],
    'responses': {200: {'description': 'success'}},
})
def websocket_config_post():
    """更新 WebSocket 客户端配置并保存到 app_config.json"""
    try:
        data = request.get_json() or {}
        client = get_websocket_client()
        cfg_manager = get_config_manager()

        if 'enabled' in data:
            Config.WS_CLIENT_ENABLED = bool(data['enabled'])
        if 'host' in data:
            Config.WS_CLIENT_HOST = str(data['host']).strip()
        if 'port' in data:
            port = int(data['port'])
            if 1 <= port <= 65535:
                Config.WS_CLIENT_PORT = port
        if 'path' in data:
            Config.WS_CLIENT_PATH = str(data['path']).strip() or '/ws'

        full_config = cfg_manager.get_config()
        cfg_manager.save_config(full_config)

        return jsonify({'success': True, 'config': client.get_config()}), 200
    except Exception as e:
        routes_logger.error(f"更新 WebSocket 配置异常: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/connect', methods=['POST'])
@swag_from({
    'tags': ['WebSocket'],
    'summary': '发起 Socket.IO 连接',
    'parameters': [{
        'in': 'body',
        'name': 'body',
        'schema': {
            'type': 'object',
            'properties': {
                'host': {'type': 'string'},
                'port': {'type': 'integer'},
                'path': {'type': 'string'},
            },
        },
    }],
    'responses': {200: {'description': 'success'}},
})
def websocket_connect():
    """发起 WebSocket 连接（可选传入 host/port/path 覆盖当前配置）"""
    try:
        data = request.get_json() or {}
        host = data.get('host')
        port = data.get('port')
        path = data.get('path')
        client = get_websocket_client()
        result = client.connect(
            host=host,
            port=int(port) if port is not None else None,
            path=path if path is not None else None,
        )
        return jsonify(result), 200
    except Exception as e:
        routes_logger.error(f"WebSocket 连接异常: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/disconnect', methods=['POST'])
@swag_from({
    'tags': ['WebSocket'],
    'summary': '断开 Socket.IO 连接',
    'responses': {200: {'description': 'success'}},
})
def websocket_disconnect():
    """断开 WebSocket 连接"""
    try:
        client = get_websocket_client()
        result = client.disconnect()
        return jsonify(result), 200
    except Exception as e:
        routes_logger.error(f"WebSocket 断开异常: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500
