"""
配置管理 API：模块配置、应用配置、重置、重载
"""
from flask import Blueprint, request, jsonify
from flasgger import swag_from
from utils.config_manager import get_config_manager
from utils.logger import get_logger

routes_logger = get_logger('Routes')
bp = Blueprint('settings', __name__, url_prefix='/api/settings')
config_manager = get_config_manager()


@bp.route('/modules', methods=['GET', 'POST'])
@swag_from({
    'tags': ['配置'],
    'summary': '管理模块配置',
    'responses': {200: {'description': '成功'}, 400: {'description': '请求体为空或格式无效'}}
})
def manage_module_config():
    """GET: 获取模块配置；POST: 保存模块配置"""
    try:
        from utils.module_manager import get_module_manager
        from config import save_module_config
        module_manager = get_module_manager()
        if request.method == 'GET':
            config = module_manager.get_config()
            return jsonify({'success': True, 'data': config}), 200
        elif request.method == 'POST':
            data = request.get_json()
            if not data:
                return jsonify({'success': False, 'error': '请求体不能为空'}), 400
            from config.modules import validate_module_config
            for module_name, module_config in data.items():
                if not validate_module_config(module_config):
                    return jsonify({'success': False, 'error': f'模块 {module_name} 的配置格式无效'}), 400
            if save_module_config(data):
                module_manager.reload_config()
                return jsonify({'success': True, 'message': '模块配置已保存'}), 200
            return jsonify({'success': False, 'error': '保存模块配置失败'}), 500
    except Exception as e:
        routes_logger.error(f"管理模块配置异常: {e}", exc_info=True)
        return jsonify({'success': False, 'error': f'服务器内部错误: {str(e)}'}), 500


@bp.route('/reset', methods=['POST'])
@swag_from({
    'tags': ['配置'],
    'summary': '重置配置为默认值',
    'responses': {200: {'description': '成功'}, 500: {'description': '重置失败'}}
})
def reset_settings():
    """重置配置为默认值"""
    try:
        from config.modules import get_default_module_config
        from config import save_module_config
        from utils.module_manager import get_module_manager
        default_config = get_default_module_config()
        if save_module_config(default_config):
            module_manager = get_module_manager()
            module_manager.reload_config()
            return jsonify({'success': True, 'message': '配置已重置为默认值'}), 200
        return jsonify({'success': False, 'error': '重置配置失败'}), 500
    except Exception as e:
        routes_logger.error(f"重置配置异常: {e}", exc_info=True)
        return jsonify({'success': False, 'error': f'服务器内部错误: {str(e)}'}), 500


@bp.route('/app', methods=['GET', 'POST'])
@swag_from({
    'tags': ['配置'],
    'summary': '管理应用配置',
    'parameters': [{
        'in': 'body',
        'name': 'body',
        'schema': {
            'type': 'object',
            'properties': {'port': {'type': 'integer'}, 'host': {'type': 'string'}}
        }
    }],
    'responses': {200: {'description': '成功'}, 400: {'description': '验证失败'}}
})
def manage_app_config():
    """GET: 获取当前配置；POST: 保存和应用配置"""
    try:
        if request.method == 'GET':
            config = config_manager.get_config()
            return jsonify({'success': True, 'data': config}), 200
        elif request.method == 'POST':
            data = request.get_json()
            if not data:
                return jsonify({'success': False, 'error': '请求体不能为空'}), 400
            if 'port' in data:
                port = int(data['port'])
                if port < 1024 or port > 65535:
                    return jsonify({'success': False, 'error': f'端口号必须在1024-65535之间，当前值: {port}'}), 400
            if not config_manager.save_config(data):
                return jsonify({'success': False, 'error': '保存配置失败'}), 500
            result = config_manager.apply_config(data)
            response_data = {
                'success': True,
                'message': '配置已保存',
                'applied': result['applied'],
                'need_restart': result['need_restart'],
                'require_restart': result['require_restart']
            }
            if result['require_restart']:
                response_data['message'] = '配置已保存，但需要重启应用才能生效（端口或主机配置已更改）'
            else:
                response_data['message'] = '配置已保存并应用（无需重启）'
            return jsonify(response_data), 200
    except ValueError as e:
        return jsonify({'success': False, 'error': f'配置验证失败: {str(e)}'}), 400
    except Exception as e:
        routes_logger.error(f"管理应用配置异常: {e}", exc_info=True)
        return jsonify({'success': False, 'error': f'服务器内部错误: {str(e)}'}), 500


@bp.route('/headless', methods=['GET', 'POST'])
@swag_from({
    'tags': ['配置'],
    'summary': '快捷开关：浏览器无头模式（修改后即时生效）',
    'responses': {200: {'description': '当前/已更新的状态'}, 400: {'description': '参数错误'}}
})
def quick_toggle_headless():
    """
    GET: 返回当前 headless 状态
    POST: body = { "headless": bool }；
          - 持久化到 app_config.toml（合并保存）
          - 更新 Config.HEADLESS 与 BrowserPool.headless
          - 软重启浏览器 context（如非空且未占用），下次任务以新模式启动
    """
    try:
        from config import Config
        from api.routes.context import get_browser_pool

        if request.method == 'GET':
            pool = get_browser_pool()
            return jsonify({
                'success': True,
                'headless': bool(Config.HEADLESS),
                'pool_headless': bool(pool.headless) if pool else None,
                'pool_busy': bool(pool._busy) if pool else False,
            }), 200

        data = request.get_json(silent=True) or {}
        if 'headless' not in data:
            return jsonify({'success': False, 'error': '缺少 headless 字段'}), 400
        new_val = bool(data['headless'])
        old_val = bool(Config.HEADLESS)

        config_manager.save_config({'headless': new_val})
        Config.HEADLESS = new_val

        restarted = False
        restart_msg = ''
        pool = get_browser_pool()
        if pool is not None:
            pool.headless = new_val
            if old_val != new_val:
                if pool._busy:
                    restart_msg = '当前有浏览器任务在跑，软重启已排队，任务结束后立即生效'
                else:
                    restart_msg = '已立即重启浏览器'
                restarted = pool.restart_browser_context()

        return jsonify({
            'success': True,
            'headless': new_val,
            'changed': old_val != new_val,
            'restarted': restarted,
            'message': restart_msg or ('headless 已切换为 ' + str(new_val)),
        }), 200
    except Exception as e:
        routes_logger.error(f"切换 headless 异常: {e}", exc_info=True)
        return jsonify({'success': False, 'error': f'服务器内部错误: {str(e)}'}), 500


@bp.route('/reload', methods=['POST'])
@swag_from({
    'tags': ['配置'],
    'summary': '重新加载配置文件',
    'responses': {200: {'description': '重载结果'}}
})
def reload_config():
    """重新加载配置文件"""
    try:
        from utils.module_manager import get_module_manager
        module_manager = get_module_manager()
        module_reload_success = module_manager.reload_config()
        app_reload_success = config_manager.reload_from_file()
        return jsonify({
            'success': module_reload_success or app_reload_success,
            'module_reloaded': module_reload_success,
            'app_reloaded': app_reload_success,
            'message': '配置已重新加载'
        }), 200
    except Exception as e:
        routes_logger.error(f"重新加载配置异常: {e}", exc_info=True)
        return jsonify({'success': False, 'error': f'服务器内部错误: {str(e)}'}), 500
