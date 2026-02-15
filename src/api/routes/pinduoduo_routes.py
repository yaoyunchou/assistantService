"""
拼多多助手 API
"""
import json
from flask import Blueprint, request, jsonify
from flasgger import swag_from
from api.routes.context import get_browser_pool
from utils.logger import get_logger

routes_logger = get_logger('Routes')
bp = Blueprint('pinduoduo', __name__, url_prefix='/api/pinduoduo')


@bp.route('/status', methods=['GET'])
@swag_from({
    'tags': ['拼多多'],
    'summary': '获取拼多多最后执行状态',
    'responses': {200: {'description': '状态'}, 500: {'description': '浏览器池未初始化'}}
})
def pinduoduo_get_status():
    """获取拼多多最后执行状态"""
    try:
        pool = get_browser_pool()
        if not pool:
            return jsonify({'success': False, 'error': '浏览器池未初始化'}), 500
        from spider.pinduoduo.client import PinduoduoClient
        status_data = pool.execute(
            lambda page: PinduoduoClient(page=page).get_last_execution_status(),
            timeout=30
        )
        return jsonify({'success': True, **status_data}), 200
    except Exception as e:
        routes_logger.error(f"获取拼多多状态异常: {e}", exc_info=True)
        return jsonify({'success': False, 'error': f'服务器内部错误: {str(e)}'}), 500


@bp.route('/login', methods=['POST'])
@swag_from({
    'tags': ['拼多多'],
    'summary': '启动拼多多登录，返回二维码',
    'responses': {200: {'description': '二维码或已登录'}, 500: {'description': '失败'}}
})
def pinduoduo_start_login():
    """启动拼多多登录流程，返回二维码"""
    try:
        routes_logger.info("[PinduoduoLogin] 开始处理登录请求")
        pool = get_browser_pool()
        if not pool:
            routes_logger.error("[PinduoduoLogin] 浏览器池未初始化")
            return jsonify({'success': False, 'error': '浏览器池未初始化'}), 500
        from spider.pinduoduo.client import PinduoduoClient
        routes_logger.info("[PinduoduoLogin] 获取浏览器页面...")
        qrcode_data = pool.execute(
            lambda page: PinduoduoClient(page=page).show_login_qrcode(),
            timeout=60
        )
        if qrcode_data == "ALREADY_LOGGED_IN":
            return jsonify({'success': True, 'already_logged_in': True, 'message': '已经登录，无需扫码'}), 200
        if not qrcode_data:
            return jsonify({'success': False, 'error': '获取二维码失败，请检查网络连接或页面加载'}), 500
        return jsonify({
            'success': True,
            'already_logged_in': False,
            'qrcode': qrcode_data,
            'message': '请使用拼多多APP扫描二维码'
        }), 200
    except Exception as e:
        error_msg = str(e)
        error_type = type(e).__name__
        routes_logger.error(f"[PinduoduoLogin] 启动拼多多登录异常: {error_type}: {error_msg}", exc_info=True)
        return jsonify({'success': False, 'error': f'服务器内部错误: {error_type}: {error_msg}'}), 500


@bp.route('/check_login_complete', methods=['GET'])
@swag_from({
    'tags': ['拼多多'],
    'summary': '检查拼多多登录是否完成',
    'responses': {200: {'description': '登录状态'}, 500: {'description': '浏览器池未初始化'}}
})
def pinduoduo_check_login():
    """检查拼多多登录是否完成"""
    try:
        pool = get_browser_pool()
        if not pool:
            return jsonify({'success': False, 'error': '浏览器池未初始化'}), 500
        from spider.pinduoduo.client import PinduoduoClient
        logged_in = pool.execute(
            lambda page: PinduoduoClient(page=page).check_login_complete(timeout=0),
            timeout=30
        )
        routes_logger.info(f"[PinduoduoCheckLogin] 登录状态检查结果: {logged_in}")
        return jsonify({
            'success': True,
            'logged_in': logged_in,
            'message': '登录成功' if logged_in else '等待扫码'
        }), 200
    except Exception as e:
        routes_logger.error(f"检查拼多多登录状态异常: {e}", exc_info=True)
        return jsonify({'success': False, 'error': f'服务器内部错误: {str(e)}'}), 500


@bp.route('/logout', methods=['POST'])
@swag_from({
    'tags': ['拼多多'],
    'summary': '拼多多不提供自动清除，缓存问题请手动处理',
    'responses': {200: {'description': '成功'}}
})
def pinduoduo_logout():
    """拼多多登录态由浏览器缓存管理，不自动清除；如有缓存问题请手动处理 browser_data 目录"""
    try:
        return jsonify({'success': True, 'message': '拼多多不自动清除缓存，如有需要请手动处理'}), 200
    except Exception as e:
        routes_logger.error(f"拼多多 logout 异常: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/execute', methods=['POST'])
@swag_from({
    'tags': ['拼多多'],
    'summary': '执行拼多多自动化操作',
    'responses': {200: {'description': '执行结果'}, 500: {'description': '浏览器池未初始化'}}
})
def pinduoduo_execute():
    """执行拼多多自动化操作"""
    try:
        routes_logger.info("[PinduoduoExecute] 开始处理执行请求")
        pool = get_browser_pool()
        if not pool:
            return jsonify({'success': False, 'error': '浏览器池未初始化'}), 500
        from spider.pinduoduo.client import PinduoduoClient
        result = pool.execute(
            lambda page: PinduoduoClient(page=page).execute_automation(),
            timeout=120
        )
        return jsonify(result), 200
    except Exception as e:
        routes_logger.error(f"执行拼多多自动化异常: {e}", exc_info=True)
        return jsonify({'success': False, 'error': f'服务器内部错误: {str(e)}'}), 500


@bp.route('/sync-to-feishu', methods=['POST'])
@swag_from({
    'tags': ['拼多多'],
    'summary': '将本地缓存的订单数据同步到飞书多维表格',
    'parameters': [{
        'in': 'body',
        'name': 'body',
        'schema': {
            'type': 'object',
            'properties': {'app_token': {'type': 'string'}, 'table_id': {'type': 'string'}}
        }
    }],
    'responses': {200: {'description': '同步结果'}, 500: {'description': '异常'}}
})
def pinduoduo_sync_to_feishu():
    """将本地缓存的订单数据同步到飞书多维表格"""
    try:
        from utils.path_helper import get_safe_data_path
        from spider.pinduoduo.feishutable import sync_orders_to_feishu
        cache_path = get_safe_data_path('cache/pinduoduo_orders_recent.json')
        if not cache_path.exists():
            return jsonify({
                'success': False,
                'message': '本地暂无订单缓存，请先点击「同步订单」获取数据'
            }), 200
        with open(cache_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        orders = data.get('data', {}).get('result', {}).get('pageItems', [])
        if not orders:
            return jsonify({
                'success': True,
                'message': '缓存中无订单数据',
                'success_count': 0, 'fail_count': 0, 'create_count': 0, 'update_count': 0, 'total_count': 0
            }), 200
        body = request.get_json(silent=True) or {}
        app_token = body.get('app_token') or 'ORSHbpajoaANQ4sFg25c917jnTc'
        table_id = body.get('table_id') or 'tblpV1RrhyUAzfSy'
        result = sync_orders_to_feishu(orders, app_token=app_token, table_id=table_id)
        return jsonify({
            'success': result.get('success', False),
            'message': result.get('message', ''),
            'success_count': result.get('success_count', 0),
            'fail_count': result.get('fail_count', 0),
            'create_count': result.get('create_count', 0),
            'update_count': result.get('update_count', 0),
            'total_count': result.get('total_count', 0)
        }), 200
    except Exception as e:
        routes_logger.error(f"同步订单到飞书异常: {e}", exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500
