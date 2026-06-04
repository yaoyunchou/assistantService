"""
飞书消息与事件订阅 API
"""
import json
from flask import Blueprint, request, jsonify
from flasgger import swag_from
from config import Config
from api.routes.context import get_browser_executor
from utils.logger import get_logger

routes_logger = get_logger('Routes')
bp = Blueprint('feishu', __name__, url_prefix='/api/feishu')


def _handle_feishu_message_event(payload: dict):
    """在后台线程处理 im.message.receive_v1：解析用户消息并回复。"""
    try:
        event = payload.get("event") or {}
        message = event.get("message") or {}
        message_id = message.get("message_id")
        content_str = message.get("content") or "{}"
        if not message_id:
            routes_logger.warning("飞书事件缺少 message_id，跳过回复")
            return
        try:
            content = json.loads(content_str)
            user_text = (content.get("text") or "").strip()
        except Exception:
            user_text = content_str
        from tools.feishu.feishu_client import FeishuClient
        client = FeishuClient()
        if not client.is_configured():
            routes_logger.warning("飞书未配置，无法回复消息")
            return
        reply_text = f"收到：{user_text[:200]}" if user_text else "收到一条消息。"
        client.reply_to_message(message_id, reply_text)
    except Exception as e:
        routes_logger.error(f"处理飞书消息事件异常: {e}", exc_info=True)


@bp.route('/event', methods=['POST'])
@swag_from({
    'tags': ['飞书'],
    'summary': '飞书事件订阅回调（接收用户消息并回复）',
    'parameters': [{
        'in': 'body',
        'name': 'body',
        'description': '飞书推送的 challenge 或 2.0 事件',
        'schema': {'type': 'object'}
    }],
    'responses': {200: {'description': '成功（含 challenge 或空'}}
})
def feishu_event():
    """飞书事件订阅回调。请求地址配置为: https://你的公网域名/api/feishu/event"""
    try:
        body = request.get_json(silent=True) or {}
        if "challenge" in body:
            return jsonify({"challenge": body["challenge"]}), 200
        if body.get("schema") == "2.0":
            header = body.get("header") or {}
            event_type = header.get("event_type")
            if event_type == "im.message.receive_v1":
                get_browser_executor().submit(_handle_feishu_message_event, body)
        return "", 200
    except Exception as e:
        routes_logger.error(f"飞书事件回调异常: {e}", exc_info=True)
        return "", 200


@bp.route('/status', methods=['GET'])
@swag_from({
    'tags': ['飞书'],
    'summary': '获取飞书消息发送器状态',
    'responses': {200: {'description': '状态'}, 500: {'description': '异常'}}
})
def feishu_status():
    """获取飞书消息发送器状态"""
    try:
        from tools.feishu.message_sender import get_message_sender
        sender = get_message_sender()
        return jsonify({
            'success': True,
            'feishu_enabled': Config.FEISHU_ENABLED,
            'client_configured': sender.client.is_configured(),
            'default_user_id': sender.default_user_id,
            'is_available': sender.is_available()
        }), 200
    except Exception as e:
        routes_logger.error(f"获取飞书状态异常: {e}", exc_info=True)
        return jsonify({'success': False, 'error': f'服务器内部错误: {str(e)}'}), 500


@bp.route('/test/login-alert', methods=['POST'])
@swag_from({
    'tags': ['飞书'],
    'summary': '测试发送拼多多登录提醒',
    'parameters': [{'in': 'body', 'name': 'body', 'schema': {'type': 'object', 'properties': {'user_id': {'type': 'string'}}}}],
    'responses': {200: {'description': '成功'}, 500: {'description': '发送失败'}}
})
def feishu_test_login_alert():
    """测试发送拼多多登录提醒"""
    try:
        from notify import login_alert
        data = request.get_json() or {}
        user_id = data.get('user_id')
        success = login_alert("pinduoduo", user_id=user_id)
        if success:
            return jsonify({'success': True, 'message': '登录提醒消息已成功发送'}), 200
        return jsonify({'success': False, 'message': '消息发送失败，请检查配置和日志'}), 500
    except Exception as e:
        routes_logger.error(f"测试发送登录提醒异常: {e}", exc_info=True)
        return jsonify({'success': False, 'error': f'服务器内部错误: {str(e)}'}), 500


@bp.route('/test/custom-message', methods=['POST'])
@swag_from({
    'tags': ['飞书'],
    'summary': '测试发送自定义消息',
    'parameters': [{
        'in': 'body',
        'name': 'body',
        'required': True,
        'schema': {
            'type': 'object',
            'properties': {'message': {'type': 'string'}, 'user_id': {'type': 'string'}},
            'required': ['message']
        }
    }],
    'responses': {200: {'description': '成功'}, 400: {'description': '消息为空'}, 500: {'description': '发送失败'}}
})
def feishu_test_custom_message():
    """测试发送自定义消息"""
    try:
        from notify import custom as _notify_custom
        data = request.get_json() or {}
        message = data.get('message')
        user_id = data.get('user_id')
        if not message:
            return jsonify({'success': False, 'error': '消息内容不能为空'}), 400
        success = _notify_custom(message, source="api", user_id=user_id)
        if success:
            return jsonify({'success': True, 'message': '自定义消息已成功发送'}), 200
        return jsonify({'success': False, 'message': '消息发送失败，请检查配置和日志'}), 500
    except Exception as e:
        routes_logger.error(f"测试发送自定义消息异常: {e}", exc_info=True)
        return jsonify({'success': False, 'error': f'服务器内部错误: {str(e)}'}), 500


@bp.route('/compare_orders', methods=['POST'])
@swag_from({
    'tags': ['飞书'],
    'summary': '飞书两表按快递单号对比并更新关联',
    'description': '用表B的快递单号匹配表A，匹配到的表A记录：是否关联改为「关联正常」，关联订单号填为表B的订单号。表A=tblpx3szhgwxAxDa，表B=tblpV1RrhyUAzfSy。',
    'responses': {200: {'description': '返回 success/updated_count/message 等'}}
})
def feishu_compare_orders():
    """按快递单号对比两个飞书表，更新表A的是否关联与关联订单号。"""
    try:
        from api.service.feishu_compare import run_feishu_order_compare
        result = run_feishu_order_compare()
        status = 200 if result.get('success') else 500
        return jsonify(result), status
    except Exception as e:
        routes_logger.error(f"飞书订单对比异常: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'message': str(e),
            'updated_count': 0,
            'matched_express_nos': [],
            'error': str(e)
        }), 500


@bp.route('/test/card-message', methods=['POST'])
@swag_from({
    'tags': ['飞书'],
    'summary': '测试发送卡片消息',
    'parameters': [{
        'in': 'body',
        'name': 'body',
        'required': True,
        'schema': {
            'type': 'object',
            'properties': {'card': {'type': 'object'}, 'user_id': {'type': 'string'}},
            'required': ['card']
        }
    }],
    'responses': {200: {'description': '成功'}, 400: {'description': '卡片为空'}, 500: {'description': '发送失败'}}
})
def feishu_test_card_message():
    """测试发送卡片消息"""
    try:
        from tools.feishu.message_sender import get_message_sender
        data = request.get_json() or {}
        card = data.get('card')
        user_id = data.get('user_id')
        if card is None:
            return jsonify({'success': False, 'error': '卡片内容不能为空'}), 400
        sender = get_message_sender()
        success = sender.send_card_message(card=card, user_id=user_id)
        if success:
            return jsonify({'success': True, 'message': '卡片消息已成功发送'}), 200
        return jsonify({
            'success': False,
            'message': '卡片发送失败。若填写了接收用户ID，请使用飞书 open_id（ou_xxx）或较长用户ID，勿填工号等短数字；或留空使用默认用户。'
        }), 500
    except Exception as e:
        routes_logger.error(f"测试发送卡片消息异常: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


def _handle_feishu_message_event(payload: dict):
    """在后台线程处理 im.message.receive_v1：解析用户消息并回复。"""
    try:
        event = payload.get("event") or {}
        message = event.get("message") or {}
        message_id = message.get("message_id")
        content_str = message.get("content") or "{}"
        if not message_id:
            routes_logger.warning("飞书事件缺少 message_id，跳过回复")
            return
        try:
            content = json.loads(content_str)
            user_text = (content.get("text") or "").strip()
        except Exception:
            user_text = content_str
        from tools.feishu.feishu_client import FeishuClient
        client = FeishuClient()
        if not client.is_configured():
            routes_logger.warning("飞书未配置，无法回复消息")
            return
        reply_text = f"收到：{user_text[:200]}" if user_text else "收到一条消息。"
        client.reply_to_message(message_id, reply_text)
    except Exception as e:
        routes_logger.error(f"处理飞书消息事件异常: {e}", exc_info=True)


@bp.route('/event', methods=['POST'])
@swag_from({
    'tags': ['飞书'],
    'summary': '飞书事件订阅回调（接收用户消息并回复）',
    'parameters': [{
        'in': 'body',
        'name': 'body',
        'description': '飞书推送的 challenge 或 2.0 事件',
        'schema': {'type': 'object'}
    }],
    'responses': {200: {'description': '成功（含 challenge 或空'}}
})
def feishu_event():
    """飞书事件订阅回调。请求地址配置为: https://你的公网域名/api/feishu/event"""
    try:
        body = request.get_json(silent=True) or {}
        if "challenge" in body:
            return jsonify({"challenge": body["challenge"]}), 200
        if body.get("schema") == "2.0":
            header = body.get("header") or {}
            event_type = header.get("event_type")
            if event_type == "im.message.receive_v1":
                get_browser_executor().submit(_handle_feishu_message_event, body)
        return "", 200
    except Exception as e:
        routes_logger.error(f"飞书事件回调异常: {e}", exc_info=True)
        return "", 200


@bp.route('/status', methods=['GET'])
@swag_from({
    'tags': ['飞书'],
    'summary': '获取飞书消息发送器状态',
    'responses': {200: {'description': '状态'}, 500: {'description': '异常'}}
})
def feishu_status():
    """获取飞书消息发送器状态"""
    try:
        from tools.feishu.message_sender import get_message_sender
        sender = get_message_sender()
        return jsonify({
            'success': True,
            'feishu_enabled': Config.FEISHU_ENABLED,
            'client_configured': sender.client.is_configured(),
            'default_user_id': sender.default_user_id,
            'is_available': sender.is_available()
        }), 200
    except Exception as e:
        routes_logger.error(f"获取飞书状态异常: {e}", exc_info=True)
        return jsonify({'success': False, 'error': f'服务器内部错误: {str(e)}'}), 500


@bp.route('/test/login-alert', methods=['POST'])
@swag_from({
    'tags': ['飞书'],
    'summary': '测试发送拼多多登录提醒',
    'parameters': [{'in': 'body', 'name': 'body', 'schema': {'type': 'object', 'properties': {'user_id': {'type': 'string'}}}}],
    'responses': {200: {'description': '成功'}, 500: {'description': '发送失败'}}
})
def feishu_test_login_alert():
    """测试发送拼多多登录提醒"""
    try:
        from tools.feishu.message_sender import get_message_sender
        data = request.get_json() or {}
        user_id = data.get('user_id')
        sender = get_message_sender()
        success = sender.send_pinduoduo_login_alert(user_id=user_id)
        if success:
            return jsonify({'success': True, 'message': '登录提醒消息已成功发送'}), 200
        return jsonify({'success': False, 'message': '消息发送失败，请检查配置和日志'}), 500
    except Exception as e:
        routes_logger.error(f"测试发送登录提醒异常: {e}", exc_info=True)
        return jsonify({'success': False, 'error': f'服务器内部错误: {str(e)}'}), 500


@bp.route('/test/custom-message', methods=['POST'])
@swag_from({
    'tags': ['飞书'],
    'summary': '测试发送自定义消息',
    'parameters': [{
        'in': 'body',
        'name': 'body',
        'required': True,
        'schema': {
            'type': 'object',
            'properties': {'message': {'type': 'string'}, 'user_id': {'type': 'string'}},
            'required': ['message']
        }
    }],
    'responses': {200: {'description': '成功'}, 400: {'description': '消息为空'}, 500: {'description': '发送失败'}}
})
def feishu_test_custom_message():
    """测试发送自定义消息"""
    try:
        from tools.feishu.message_sender import get_message_sender
        data = request.get_json() or {}
        message = data.get('message')
        user_id = data.get('user_id')
        if not message:
            return jsonify({'success': False, 'error': '消息内容不能为空'}), 400
        sender = get_message_sender()
        success = sender.send_custom_message(message=message, user_id=user_id)
        if success:
            return jsonify({'success': True, 'message': '自定义消息已成功发送'}), 200
        return jsonify({'success': False, 'message': '消息发送失败，请检查配置和日志'}), 500
    except Exception as e:
        routes_logger.error(f"测试发送自定义消息异常: {e}", exc_info=True)
        return jsonify({'success': False, 'error': f'服务器内部错误: {str(e)}'}), 500


@bp.route('/compare_orders', methods=['POST'])
@swag_from({
    'tags': ['飞书'],
    'summary': '飞书两表按快递单号对比并更新关联',
    'description': '用表B的快递单号匹配表A，匹配到的表A记录：是否关联改为「关联正常」，关联订单号填为表B的订单号。表A=tblpx3szhgwxAxDa，表B=tblpV1RrhyUAzfSy。',
    'responses': {200: {'description': '返回 success/updated_count/message 等'}}
})
def feishu_compare_orders():
    """按快递单号对比两个飞书表，更新表A的是否关联与关联订单号。"""
    try:
        from api.service.feishu_compare import run_feishu_order_compare
        result = run_feishu_order_compare()
        status = 200 if result.get('success') else 500
        return jsonify(result), status
    except Exception as e:
        routes_logger.error(f"飞书订单对比异常: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'message': str(e),
            'updated_count': 0,
            'matched_express_nos': [],
            'error': str(e)
        }), 500


@bp.route('/test/card-message', methods=['POST'])
@swag_from({
    'tags': ['飞书'],
    'summary': '测试发送卡片消息',
    'parameters': [{
        'in': 'body',
        'name': 'body',
        'required': True,
        'schema': {
            'type': 'object',
            'properties': {'card': {'type': 'object'}, 'user_id': {'type': 'string'}},
            'required': ['card']
        }
    }],
    'responses': {200: {'description': '成功'}, 400: {'description': '卡片为空'}, 500: {'description': '发送失败'}}
})
def feishu_test_card_message():
    """测试发送卡片消息"""
    try:
        from tools.feishu.message_sender import get_message_sender
        data = request.get_json() or {}
        card = data.get('card')
        user_id = data.get('user_id')
        if card is None:
            return jsonify({'success': False, 'error': '卡片内容不能为空'}), 400
        sender = get_message_sender()
        success = sender.send_card_message(card=card, user_id=user_id)
        if success:
            return jsonify({'success': True, 'message': '卡片消息已成功发送'}), 200
        return jsonify({
            'success': False,
            'message': '卡片发送失败。若填写了接收用户ID，请使用飞书 open_id（ou_xxx）或较长用户ID，勿填工号等短数字；或留空使用默认用户。'
        }), 500
    except Exception as e:
        routes_logger.error(f"测试发送卡片消息异常: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500
