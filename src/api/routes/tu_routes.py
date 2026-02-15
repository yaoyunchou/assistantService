"""
途强(TU) 助手 API
"""
from flask import Blueprint, jsonify
from flasgger import swag_from
from api.routes.context import get_browser_pool
from utils.logger import get_logger

routes_logger = get_logger('Routes')
bp = Blueprint('tu', __name__, url_prefix='/api/tu')


@bp.route('/status', methods=['GET'])
@swag_from({
    'tags': ['途强'],
    'summary': '获取途强最后执行状态',
    'responses': {200: {'description': '状态'}, 500: {'description': '异常'}}
})
def tu_get_status():
    """获取途强最后执行状态（只读本地状态文件）"""
    try:
        from spider.tu.client import TuClient
        client = TuClient(page=None)
        status_data = client.get_last_execution_status()
        return jsonify({'success': True, **status_data}), 200
    except Exception as e:
        routes_logger.error(f"获取途强状态异常: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/login', methods=['POST'])
@swag_from({
    'tags': ['途强'],
    'summary': '打开浏览器窗口等待手动登录（自动登录失败时使用）',
    'responses': {200: {'description': '登录结果'}, 500: {'description': '异常'}}
})
def tu_manual_login():
    """打开浏览器窗口，等待用户手动登录途强"""
    try:
        routes_logger.info("[TuLogin] 开始手动登录流程")
        pool = get_browser_pool()
        if not pool:
            return jsonify({'success': False, 'error': '浏览器池未初始化'}), 500

        from spider.tu.client import TuClient
        result = pool.execute(
            lambda page: TuClient(page=page).wait_for_manual_login(timeout=300),
            timeout=310
        )
        return jsonify(result), 200
    except Exception as e:
        routes_logger.error(f"途强手动登录异常: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/execute', methods=['POST'])
@swag_from({
    'tags': ['途强'],
    'summary': '执行途强自动化（自动登录并获取最近30天记录）',
    'responses': {200: {'description': '执行结果'}, 500: {'description': '浏览器池未初始化或超时'}}
})
def tu_execute():
    """执行途强自动化：通过 pool.execute 在浏览器线程执行"""
    try:
        routes_logger.info("[TuExecute] 开始处理执行请求")
        pool = get_browser_pool()
        if not pool:
            return jsonify({'success': False, 'error': '浏览器池未初始化'}), 500

        from spider.tu.client import TuClient
        result = pool.execute(
            lambda page: TuClient(page=page).execute_automation(),
            timeout=120
        )
        return jsonify(result), 200
    except Exception as e:
        routes_logger.error(f"途强自动化执行异常: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/logout', methods=['POST'])
@swag_from({
    'tags': ['途强'],
    'summary': '途强不管理Cookie，仅返回成功',
    'responses': {200: {'description': '成功'}}
})
def tu_logout():
    """途强不管理 Cookie，仅返回成功（兼容前端按钮）"""
    try:
        return jsonify({'success': True, 'message': '途强不管理 Cookie，无需清除'}), 200
    except Exception as e:
        routes_logger.error(f"途强 logout 异常: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500
