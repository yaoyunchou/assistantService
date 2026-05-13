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


@bp.route('/inventory-mapping/data', methods=['GET'])
@swag_from({
    'tags': ['拼多多'],
    'summary': '获取库存映射配置数据（商品信息列表 + 商品名称列表 + 已保存映射）',
    'responses': {200: {'description': '映射数据'}},
})
def pinduoduo_inventory_mapping_data():
    """从飞书扣减日志表读去重的商品信息，从库存信息表读商品名称，加载已保存的映射。"""
    try:
        from config import Config
        from tools.feishu.feishu_table_client import FeishuTableClient
        from spider.pinduoduo.feishutable import feishu_field_to_text
        from spider.pinduoduo.inventory_mapping import load_mappings

        app_token = (Config.PINDUODUO_FEISHU_APP_TOKEN or '').strip()
        log_table = (Config.PINDUODUO_FEISHU_INVENTORY_LOG_TABLE_ID or '').strip()
        inv_table = (Config.PINDUODUO_FEISHU_INVENTORY_INFO_TABLE_ID or '').strip()
        inv_name_field = (Config.PINDUODUO_INVENTORY_PRODUCT_NAME_FIELD or '商品名称').strip()

        if not app_token or not log_table or not inv_table:
            return jsonify({
                'success': False,
                'message': '缺少飞书配置（app_token / log_table / inv_table）',
            }), 200

        log_client = FeishuTableClient(app_token, log_table)
        inv_client = FeishuTableClient(app_token, inv_table)

        log_records = log_client.get_all_records()
        inv_records = inv_client.get_all_records()

        product_infos_seen = set()
        product_infos = []
        for rec in log_records:
            f = rec.get('fields') or {}
            info = feishu_field_to_text(f.get('商品信息')).strip()
            if info and info not in product_infos_seen:
                product_infos_seen.add(info)
                product_infos.append(info)

        product_names_seen = set()
        product_names = []
        for rec in inv_records:
            f = rec.get('fields') or {}
            name = feishu_field_to_text(f.get(inv_name_field)).strip()
            if name and name not in product_names_seen:
                product_names_seen.add(name)
                product_names.append(name)

        mappings = load_mappings()

        return jsonify({
            'success': True,
            'product_infos': sorted(product_infos),
            'product_names': sorted(product_names),
            'mappings': mappings,
        }), 200
    except Exception as e:
        routes_logger.error('获取库存映射数据异常: %s', e, exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500


@bp.route('/inventory-mapping/save', methods=['POST'])
@swag_from({
    'tags': ['拼多多'],
    'summary': '保存库存映射配置',
    'parameters': [{
        'in': 'body', 'name': 'body',
        'schema': {
            'type': 'object',
            'properties': {
                'mappings': {
                    'type': 'object',
                    'description': '商品信息→商品名称列表 的映射字典',
                },
            },
        },
    }],
    'responses': {200: {'description': '保存结果'}},
})
def pinduoduo_inventory_mapping_save():
    """保存库存映射配置到本地文件。"""
    try:
        from spider.pinduoduo.inventory_mapping import save_mappings

        body = request.get_json(silent=True) or {}
        mappings = body.get('mappings')
        if not isinstance(mappings, dict):
            return jsonify({'success': False, 'message': 'mappings 字段必须是对象'}), 400

        ok = save_mappings(mappings)
        return jsonify({
            'success': ok,
            'message': f'已保存 {len(mappings)} 条映射' if ok else '保存失败',
        }), 200
    except Exception as e:
        routes_logger.error('保存库存映射异常: %s', e, exc_info=True)
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


@bp.route('/erp-audit/pending', methods=['POST'])
@swag_from({
    'tags': ['拼多多'],
    'summary': 'ERP 待审核订单列表（抓取商品明细）',
    'responses': {200: {'description': '执行结果'}, 500: {'description': '异常'}},
})
def pinduoduo_erp_audit_pending():
    """打开审核页并执行采集脚本。"""
    try:
        pool = get_browser_pool()
        if not pool:
            return jsonify({'success': False, 'error': '浏览器池未初始化'}), 500

        body = request.get_json(silent=True) or {}
        sms = body.get('scroll_max_steps')
        spm = body.get('scroll_pause_ms')
        try:
            sms = int(sms) if sms is not None else None
        except (TypeError, ValueError):
            sms = None
        try:
            spm = int(spm) if spm is not None else None
        except (TypeError, ValueError):
            spm = None

        from spider.pinduoduo import erp_audit

        result = pool.execute(
            lambda page: erp_audit.fetch_pending_audit_rows(
                page,
                scroll_max_steps=sms,
                scroll_pause_ms=spm,
            ),
            timeout=620,
        )
        return jsonify(result if isinstance(result, dict) else {'success': False, 'message': str(result)}), 200
    except Exception as e:
        routes_logger.error('ERP 待审核列表异常: %s', e, exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500


@bp.route('/erp-audit/submit', methods=['POST'])
@swag_from({
    'tags': ['拼多多'],
    'summary': '勾选并提交审核指定订单号',
    'parameters': [{
        'in': 'body',
        'name': 'body',
        'schema': {
            'type': 'object',
            'properties': {
                'order_nos': {
                    'type': 'array',
                    'items': {'type': 'string'},
                    'description': '平台订单号列表（与 pending 返回的 orderNo 一致）；与 orderNos 二选一',
                },
                'orderNos': {
                    'type': 'array',
                    'items': {'type': 'string'},
                    'description': '同 order_nos',
                },
                'scroll_max_steps': {'type': 'integer'},
                'scroll_pause_ms': {'type': 'integer'},
            },
        },
    }],
    'responses': {200: {'description': '执行结果'}, 400: {'description': '参数错误'}, 500: {'description': '异常'}},
})
def pinduoduo_erp_audit_submit():
    """审核选中订单；成功后写入 SQLite 并尝试同步飞书。"""
    try:
        pool = get_browser_pool()
        if not pool:
            return jsonify({'success': False, 'error': '浏览器池未初始化'}), 500

        body = request.get_json(silent=True) or {}
        order_nos = body.get('order_nos') or body.get('orderNos') or []
        if not isinstance(order_nos, list):
            return jsonify({'success': False, 'message': 'order_nos 须为数组'}), 400

        sms = body.get('scroll_max_steps')
        spm = body.get('scroll_pause_ms')
        try:
            sms = int(sms) if sms is not None else None
        except (TypeError, ValueError):
            sms = None
        try:
            spm = int(spm) if spm is not None else None
        except (TypeError, ValueError):
            spm = None

        from spider.pinduoduo import erp_audit

        result = pool.execute(
            lambda page: erp_audit.submit_audit_orders(
                page,
                order_nos,
                scroll_max_steps=sms,
                scroll_pause_ms=spm,
            ),
            timeout=620,
        )
        if not isinstance(result, dict):
            return jsonify({'success': False, 'message': str(result)}), 200

        out = dict(result)
        feishu_sync = None
        if result.get('success') and result.get('rows'):
            from spider.pinduoduo import audit_store
            from spider.pinduoduo.feishutable import sync_audit_events_to_feishu
            from config import Config

            chk = result.get('check_result') or []
            ok_set = {c.get('orderNo') for c in chk if c.get('ok')}
            rows_src = result['rows']
            if ok_set:
                rows_store = [
                    r for r in rows_src
                    if (r.get('orderNo') or '').strip() in ok_set
                ]
            else:
                rows_store = rows_src

            inserted = audit_store.insert_batch_from_submit_rows(rows_store)
            out['sqlite_inserted'] = len(inserted)
            tbl = (Config.PINDUODUO_ERP_AUDIT_FEISHU_TABLE_ID or '').strip()
            if inserted and tbl:
                routes_logger.info(
                    'ERP 审核：本地新增 %d 条，开始同步飞书 table=%s',
                    len(inserted), tbl,
                )
                feishu_sync = sync_audit_events_to_feishu(inserted)
                out['feishu_sync'] = feishu_sync
                routes_logger.info(
                    'ERP 审核飞书同步结果: 成功 %s / 失败 %s / 总 %s',
                    feishu_sync.get('success_count'),
                    feishu_sync.get('fail_count'),
                    feishu_sync.get('total_count'),
                )
                pairs = feishu_sync.get('record_pairs') or []
                if pairs:
                    local_ids = [p[0] for p in pairs if p[0] is not None]
                    fr_ids = [p[1] for p in pairs if p[0] is not None]
                    audit_store.mark_synced(local_ids, fr_ids)
            else:
                if inserted and not tbl:
                    routes_logger.warning(
                        'ERP 审核：本地新增 %d 条，但 PINDUODUO_ERP_AUDIT_FEISHU_TABLE_ID 未配置，跳过飞书同步',
                        len(inserted),
                    )
                out['feishu_sync'] = None

        return jsonify(out), 200
    except Exception as e:
        routes_logger.error('ERP 审核提交异常: %s', e, exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500


@bp.route('/erp-delivering/pending-list', methods=['POST'])
@swag_from({
    'tags': ['拼多多'],
    'summary': '待发货页：仅抓取当前列表（实时，不入库）',
    'responses': {200: {'description': 'rows 为页面当前可见订单'}},
})
def pinduoduo_erp_delivering_pending_list():
    try:
        pool = get_browser_pool()
        if not pool:
            return jsonify({'success': False, 'error': '浏览器池未初始化'}), 500

        from spider.pinduoduo import erp_audit

        result = pool.execute(
            lambda page: erp_audit.run_delivering_list_query(page),
            timeout=200,
        )
        return jsonify(result if isinstance(result, dict) else {'success': False, 'message': str(result)}), 200
    except Exception as e:
        routes_logger.error('待发货列表查询异常: %s', e, exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500


@bp.route('/erp-delivering/print-ship', methods=['POST'])
@swag_from({
    'tags': ['拼多多'],
    'summary': '待发货页：全选并打印快递单、打印并发货',
    'responses': {200: {'description': '执行结果'}, 500: {'description': '异常'}},
})
def pinduoduo_erp_delivering_print_ship():
    try:
        pool = get_browser_pool()
        if not pool:
            return jsonify({'success': False, 'error': '浏览器池未初始化'}), 500

        from spider.pinduoduo import erp_audit

        result = pool.execute(
            lambda page: erp_audit.run_delivering_print_ship(page),
            timeout=180,
        )
        return jsonify(result if isinstance(result, dict) else {'success': False, 'message': str(result)}), 200
    except Exception as e:
        routes_logger.error('待发货打印异常: %s', e, exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500


@bp.route('/erp-delivered/today-printed-query', methods=['POST'])
@swag_from({
    'tags': ['拼多多'],
    'summary': '已发货页：今日已打印快递单列表（表格抓取）',
    'parameters': [{
        'in': 'body',
        'name': 'body',
        'schema': {
            'type': 'object',
            'properties': {
                'filter_print_status': {
                    'type': 'string',
                    'description': '默认「已打印快递单」；传 __ALL__/all/* 表示不筛选；空串与缺省相同',
                },
                'time_type': {'type': 'string'},
                'date_shortcut': {'type': 'string'},
                'auto_scroll': {'type': 'boolean'},
                'scroll_max_steps': {'type': 'integer'},
                'scroll_pause_ms': {'type': 'integer'},
            },
        },
    }],
    'responses': {200: {'description': '执行结果'}, 500: {'description': '异常'}},
})
def pinduoduo_erp_delivered_today_printed_query():
    """
    打开 ERP 已发货页，按脚本筛选「发货时间 / 今天 / 已打印快递单」并滚动抓取订单行。
    完成后向拼多多渠道飞书 Webhook 推送摘要。
    """
    try:
        pool = get_browser_pool()
        if not pool:
            return jsonify({'success': False, 'error': '浏览器池未初始化'}), 500

        body = request.get_json(silent=True) or {}
        # 与脚本 SCHEMA_PLACEHOLDER 一致，避免 Swagger 把类型名 "string" 当字段值提交
        _schema_bad = frozenset(
            {'string', 'number', 'integer', 'boolean', 'object', 'array', 'null'}
        )

        def _clean_text_opt(v):
            """无或空或 schema 占位符 → None（由页内脚本用默认：今天 / 发货时间等）。"""
            if v is None or not isinstance(v, str):
                return None
            s = v.strip()
            if not s or s.lower() in _schema_bad:
                return None
            return s

        if 'filter_print_status' in body:
            v = body['filter_print_status']
            if v is not None and not isinstance(v, str):
                fps = None
            elif isinstance(v, str):
                s = v.strip()
                if s.lower() in _schema_bad:
                    fps = None
                elif not s:
                    fps = None
                elif s.lower() in ('__all__', 'all', '*'):
                    fps = '__ALL__'
                else:
                    fps = s
            else:
                fps = None
        else:
            fps = None

        tt = _clean_text_opt(body.get('time_type'))
        ds = _clean_text_opt(body.get('date_shortcut'))

        auto_scroll = body.get('auto_scroll')
        if auto_scroll is not None:
            auto_scroll = bool(auto_scroll)

        sms = body.get('scroll_max_steps')
        spm = body.get('scroll_pause_ms')
        try:
            sms = int(sms) if sms is not None else None
        except (TypeError, ValueError):
            sms = None
        try:
            spm = int(spm) if spm is not None else None
        except (TypeError, ValueError):
            spm = None

        from spider.pinduoduo import erp_audit

        result = pool.execute(
            lambda page: erp_audit.fetch_delivered_today_printed_rows(
                page,
                filter_print_status=fps,
                time_type=tt,
                date_shortcut=ds,
                auto_scroll=auto_scroll,
                scroll_max_steps=sms,
                scroll_pause_ms=spm,
            ),
            timeout=620,
        )
        return jsonify(result if isinstance(result, dict) else {'success': False, 'message': str(result)}), 200
    except Exception as e:
        routes_logger.error('已发货今日打印单查询异常: %s', e, exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500


@bp.route('/erp-audit/today', methods=['GET'])
@swag_from({
    'tags': ['拼多多'],
    'summary': '今日已审核订单（本地 SQLite）',
    'parameters': [{
        'name': 'unprinted',
        'in': 'query',
        'type': 'boolean',
        'required': False,
        'description': '为 true/1 时仅返回尚未被「打印并发货」标记的记录（printed_at 为空）',
    }],
    'responses': {200: {'description': '列表'}},
})
def pinduoduo_erp_audit_today():
    try:
        from spider.pinduoduo import audit_store

        raw = (request.args.get('unprinted') or '').strip().lower()
        only_unprinted = raw in ('1', 'true', 'yes', 'on')
        rows = audit_store.list_today_local(only_unprinted=only_unprinted)
        return jsonify({
            'success': True,
            'rows': rows,
            'count': len(rows),
            'filter_unprinted': only_unprinted,
        }), 200
    except Exception as e:
        routes_logger.error('读取今日审核记录异常: %s', e, exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500


@bp.route('/erp-audit/sync-feishu', methods=['POST'])
@swag_from({
    'tags': ['拼多多'],
    'summary': '将未同步的本地审核记录推送到飞书',
    'responses': {200: {'description': '同步结果'}},
})
def pinduoduo_erp_audit_sync_feishu():
    try:
        from spider.pinduoduo import audit_store
        from spider.pinduoduo.feishutable import sync_audit_events_to_feishu
        from config import Config

        body = request.get_json(silent=True) or {}
        limit = body.get('limit', 200)
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = 200
        limit = max(1, min(limit, 500))

        if not (Config.PINDUODUO_ERP_AUDIT_FEISHU_TABLE_ID or '').strip():
            return jsonify({
                'success': False,
                'message': '未配置 PINDUODUO_ERP_AUDIT_FEISHU_TABLE_ID',
            }), 200

        unsynced = audit_store.list_unsynced_for_feishu(limit=limit)
        fs = sync_audit_events_to_feishu(unsynced)
        pairs = fs.get('record_pairs') or []
        if pairs:
            local_ids = [p[0] for p in pairs if p[0] is not None]
            fr_ids = [p[1] for p in pairs if p[0] is not None]
            audit_store.mark_synced(local_ids, fr_ids)
        return jsonify({'success': True, **fs}), 200
    except Exception as e:
        routes_logger.error('审核记录同步飞书异常: %s', e, exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500
