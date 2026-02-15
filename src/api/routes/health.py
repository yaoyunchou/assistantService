"""
健康检查与开机自启 API
"""
from flask import Blueprint, jsonify, request
from flasgger import swag_from
from config import Config
from utils.startup import is_startup_enabled, get_exe_path, add_to_startup, remove_from_startup
from utils.logger import get_logger

routes_logger = get_logger('Routes')
bp = Blueprint('health', __name__)


@bp.route('/health', methods=['GET'])
@swag_from({
    'tags': ['系统'],
    'summary': '健康检查',
    'responses': {200: {'description': '服务正常'}}
})
def health_check():
    """健康检查接口"""
    return jsonify({
        'status': 'ok',
        'service': Config.APP_NAME,
        'startup_enabled': is_startup_enabled()
    }), 200


@bp.route('/startup', methods=['GET', 'POST', 'DELETE'])
@swag_from({
    'tags': ['系统'],
    'summary': '管理开机自启动',
    'parameters': [],
    'responses': {
        200: {'description': '成功'},
        500: {'description': '操作失败'}
    }
})
def manage_startup():
    """管理开机自启动：GET 查询状态，POST 启用，DELETE 禁用"""
    try:
        if request.method == 'GET':
            enabled = is_startup_enabled()
            return jsonify({
                'success': True,
                'startup_enabled': enabled,
                'exe_path': get_exe_path()
            }), 200
        elif request.method == 'POST':
            if add_to_startup():
                return jsonify({
                    'success': True,
                    'message': '已启用开机自启动',
                    'startup_enabled': True
                }), 200
            else:
                return jsonify({
                    'success': False,
                    'error': '启用开机自启动失败'
                }), 500
        elif request.method == 'DELETE':
            if remove_from_startup():
                return jsonify({
                    'success': True,
                    'message': '已禁用开机自启动',
                    'startup_enabled': False
                }), 200
            else:
                return jsonify({
                    'success': False,
                    'error': '禁用开机自启动失败'
                }), 500
    except Exception as e:
        routes_logger.error(f"管理启动项异常: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'服务器内部错误: {str(e)}'
        }), 500
