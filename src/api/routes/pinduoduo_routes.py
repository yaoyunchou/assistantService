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
        from config import Config
        app_token = body.get('app_token') or Config.PINDUODUO_FEISHU_APP_TOKEN
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


@bp.route('/feishu/cleanup-empty-order-sn', methods=['POST'])
@swag_from({
    'tags': ['拼多多'],
    'summary': '删除飞书表中无「订单号」的记录',
    'parameters': [{
        'in': 'body', 'name': 'body',
        'schema': {
            'type': 'object',
            'properties': {
                'app_token': {'type': 'string'},
                'table_id': {'type': 'string'},
            }
        }
    }],
    'responses': {200: {'description': '删除结果'}}
})
def pinduoduo_feishu_cleanup_empty_order_sn():
    """调用飞书接口批量删除「订单号」为空的行。"""
    try:
        from config import Config
        from spider.pinduoduo.feishutable import delete_feishu_rows_without_order_sn
        body = request.get_json(silent=True) or {}
        app_token = body.get('app_token') or Config.PINDUODUO_FEISHU_APP_TOKEN
        table_id = body.get('table_id') or Config.PINDUODUO_FEISHU_TABLE_ID
        result = delete_feishu_rows_without_order_sn(app_token, table_id)
        return jsonify(result), 200
    except Exception as e:
        routes_logger.error(f"清理飞书无订单号记录异常: {e}", exc_info=True)
        return jsonify({'success': False, 'message': str(e), 'deleted_count': 0}), 500


@bp.route('/sync-order-addresses', methods=['POST'])
@swag_from({
    'tags': ['拼多多'],
    'summary': '检查飞书前几条缺手机号则打开订单列表并执行地址补全脚本',
    'parameters': [{
        'in': 'body', 'name': 'body',
        'schema': {
            'type': 'object',
            'properties': {
                'app_token': {'type': 'string'},
                'table_id': {'type': 'string'},
                'view_id': {'type': 'string', 'description': '与多维表格 URL 中 view= 一致'},
                'top_n': {'type': 'integer', 'default': 3},
            }
        }
    }],
    'responses': {200: {'description': '执行结果'}, 500: {'description': '浏览器池异常'}}
})
def pinduoduo_sync_order_addresses():
    """在飞书表中翻页查找最多 N 条「有订单号且无手机号」的记录，再进入订单列表补全地址。"""
    try:
        from config import Config
        from spider.pinduoduo.order_address_sync import sync_order_addresses_from_feishu_top_records
        pool = get_browser_pool()
        if not pool:
            return jsonify({'success': False, 'error': '浏览器池未初始化'}), 500
        body = request.get_json(silent=True) or {}
        app_token = body.get('app_token') or Config.PINDUODUO_FEISHU_APP_TOKEN
        table_id = body.get('table_id') or Config.PINDUODUO_FEISHU_TABLE_ID
        top_n = body.get('top_n')
        if top_n is None:
            top_n = 3
        try:
            top_n = int(top_n)
        except (TypeError, ValueError):
            top_n = 3
        top_n = max(1, min(top_n, 50))
        view_id = body.get('view_id')
        if view_id is not None and view_id == '':
            view_id = None

        result = pool.execute(
            lambda page: sync_order_addresses_from_feishu_top_records(
                page,
                app_token=app_token,
                table_id=table_id,
                top_n=top_n,
                view_id=view_id,
            ),
            timeout=300,
        )
        return jsonify(result if isinstance(result, dict) else {'success': False, 'message': str(result)}), 200
    except Exception as e:
        routes_logger.error(f"同步 PDD 订单地址异常: {e}", exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500


@bp.route('/sync-erp-orders', methods=['POST'])
@swag_from({
    'tags': ['拼多多'],
    'summary': 'ERP 全部订单表抓取并同步到飞书（平台订单号去重）',
    'parameters': [{
        'in': 'body',
        'name': 'body',
        'schema': {
            'type': 'object',
            'properties': {
                'app_token': {'type': 'string'},
                'table_id': {'type': 'string'},
                'scroll_max_steps': {'type': 'integer'},
                'scroll_pause_ms': {'type': 'integer'},
            },
        },
    }],
    'responses': {200: {'description': '执行结果'}, 500: {'description': '浏览器池异常'}},
})
def pinduoduo_sync_erp_orders():
    """打开 mms ERP 全部订单页，执行 pdd-erp-order-all-table.js，写入 Config 指定的 ERP 飞书表。"""
    try:
        from config import Config
        from spider.pinduoduo.erp_order_sync import sync_erp_orders_to_feishu

        pool = get_browser_pool()
        if not pool:
            return jsonify({'success': False, 'error': '浏览器池未初始化'}), 500

        body = request.get_json(silent=True) or {}
        app_token = body.get('app_token') or Config.PINDUODUO_FEISHU_APP_TOKEN
        table_id = body.get('table_id') or Config.PINDUODUO_ERP_FEISHU_TABLE_ID
        scroll_max_steps = body.get('scroll_max_steps')
        scroll_pause_ms = body.get('scroll_pause_ms')
        if scroll_max_steps is not None:
            try:
                scroll_max_steps = int(scroll_max_steps)
            except (TypeError, ValueError):
                scroll_max_steps = None
        if scroll_pause_ms is not None:
            try:
                scroll_pause_ms = int(scroll_pause_ms)
            except (TypeError, ValueError):
                scroll_pause_ms = None

        result = pool.execute(
            lambda page: sync_erp_orders_to_feishu(
                page,
                app_token=app_token,
                table_id=table_id,
                scroll_max_steps=scroll_max_steps,
                scroll_pause_ms=scroll_pause_ms,
            ),
            timeout=720,
        )
        return jsonify(result if isinstance(result, dict) else {'success': False, 'message': str(result)}), 200
    except Exception as e:
        routes_logger.error(f'同步 ERP 订单异常: {e}', exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500


@bp.route('/inventory-sync-from-erp-feishu', methods=['POST'])
@swag_from({
    'tags': ['拼多多'],
    'summary': '定时逻辑：读飞书 ERP 全部店铺表，写库存信息表与扣减日志表（无需浏览器）',
    'parameters': [{
        'in': 'body',
        'name': 'body',
        'schema': {
            'type': 'object',
            'properties': {
                'app_token': {'type': 'string'},
                'erp_table_id': {'type': 'string'},
                'erp_view_id': {'type': 'string'},
                'inventory_info_table_id': {'type': 'string'},
                'inventory_log_table_id': {'type': 'string'},
                'pay_after_date': {'type': 'string'},
                'require_express': {'type': 'boolean'},
                'return_keywords': {'type': 'array', 'items': {'type': 'string'}},
                'inventory_product_name_field': {'type': 'string'},
                'stock_link_score_weights': {
                    'type': 'object',
                    'description': '库存关联分项权重：weight_char_cover / weight_symmetric_jaccard / weight_power / weight_kind',
                },
                'stock_link_match_min_score': {'type': 'integer', 'description': '0–100，≥ 则库存关联写商品名称原文，默认 80'},
            },
        },
    }],
    'responses': {200: {'description': '执行结果'}},
})
def pinduoduo_inventory_sync_from_erp_feishu():
    """读飞书多维表（ERP 订单 → 库存信息 + 扣减日志），详见 spider.pinduoduo.inventory_sync_job。"""
    try:
        from spider.pinduoduo.inventory_sync_job import run_inventory_sync_job

        body = request.get_json(silent=True) or {}
        result = run_inventory_sync_job(body if isinstance(body, dict) else {})
        code = 200 if result.get('success') else 400
        return jsonify(result if isinstance(result, dict) else {'success': False, 'message': str(result)}), code
    except Exception as e:
        routes_logger.error('库存飞书同步任务异常: %s', e, exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500
