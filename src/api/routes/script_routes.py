"""
脚本执行与管理 API
"""
import uuid
from flask import Blueprint, request, jsonify
from flasgger import swag_from
from utils.script_manager import get_script_manager
from tools.script_tool import ScriptTool
from utils.logger import get_logger

routes_logger = get_logger('Routes')
bp = Blueprint('script', __name__, url_prefix='/api/script')

script_tool = ScriptTool()
script_manager = get_script_manager()


@bp.route('/execute', methods=['POST'])
@swag_from({
    'tags': ['脚本'],
    'summary': '执行Python脚本',
    'parameters': [{
        'in': 'body',
        'name': 'body',
        'required': True,
        'schema': {
            'type': 'object',
            'properties': {
                'code': {'type': 'string', 'description': 'Python 代码'},
                'timeout': {'type': 'integer', 'default': 30},
                'args': {'type': 'object'},
                'sandbox': {'type': 'boolean', 'default': True},
                'script_id': {'type': 'string', 'description': '可选，用于记录历史'}
            },
            'required': ['code']
        }
    }],
    'responses': {200: {'description': '执行结果'}, 400: {'description': '参数错误'}}
})
def execute_script():
    """执行 Python 脚本"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': '请求体不能为空'}), 400
        code = data.get('code', '')
        if not code:
            return jsonify({'success': False, 'error': '缺少必需参数: code'}), 400
        timeout = data.get('timeout', 30)
        args = data.get('args', {})
        sandbox = data.get('sandbox', True)
        script_id = data.get('script_id')
        result = script_tool.execute_script(code=code, timeout=timeout, args=args, sandbox=sandbox)
        if script_id:
            script_manager.add_execution_history(
                script_id=script_id,
                success=result['success'],
                output=result.get('output', ''),
                error=str(result.get('error', {}).get('message', '')) if result.get('error') else None,
                elapsed_time=result.get('elapsed_time', 0)
            )
        return jsonify({'success': True, 'data': result}), 200
    except Exception as e:
        routes_logger.error(f"执行脚本异常: {e}", exc_info=True)
        return jsonify({'success': False, 'error': f'服务器内部错误: {str(e)}'}), 500


@bp.route('/list', methods=['GET'])
@swag_from({
    'tags': ['脚本'],
    'summary': '获取脚本列表',
    'parameters': [{'in': 'query', 'name': 'category', 'type': 'string', 'description': '分类过滤'}],
    'responses': {200: {'description': '脚本列表'}}
})
def list_scripts():
    """获取脚本列表"""
    try:
        category = request.args.get('category')
        scripts = script_manager.list_scripts(category=category)
        return jsonify({'success': True, 'data': scripts}), 200
    except Exception as e:
        routes_logger.error(f"获取脚本列表异常: {e}", exc_info=True)
        return jsonify({'success': False, 'error': f'服务器内部错误: {str(e)}'}), 500


@bp.route('/save', methods=['POST'])
@swag_from({
    'tags': ['脚本'],
    'summary': '保存脚本',
    'parameters': [{
        'in': 'body',
        'name': 'body',
        'required': True,
        'schema': {
            'type': 'object',
            'properties': {
                'script_id': {'type': 'string'},
                'code': {'type': 'string'},
                'name': {'type': 'string'},
                'category': {'type': 'string'},
                'description': {'type': 'string'}
            },
            'required': ['code']
        }
    }],
    'responses': {200: {'description': '保存成功'}, 400: {'description': '参数错误'}}
})
def save_script():
    """保存脚本"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': '请求体不能为空'}), 400
        code = data.get('code', '')
        if not code:
            return jsonify({'success': False, 'error': '缺少必需参数: code'}), 400
        script_id = data.get('script_id') or str(uuid.uuid4())
        name = data.get('name', script_id)
        category = data.get('category', 'default')
        description = data.get('description', '')
        if script_manager.save_script(script_id=script_id, code=code, name=name, category=category, description=description):
            return jsonify({'success': True, 'data': {'script_id': script_id, 'name': name}}), 200
        return jsonify({'success': False, 'error': '保存脚本失败'}), 500
    except Exception as e:
        routes_logger.error(f"保存脚本异常: {e}", exc_info=True)
        return jsonify({'success': False, 'error': f'服务器内部错误: {str(e)}'}), 500


@bp.route('/<script_id>', methods=['GET', 'DELETE'])
@swag_from({
    'tags': ['脚本'],
    'summary': '获取或删除脚本',
    'parameters': [{'in': 'path', 'name': 'script_id', 'type': 'string', 'required': True}],
    'responses': {200: {'description': '成功'}, 404: {'description': '脚本不存在'}}
})
def manage_script(script_id):
    """GET: 获取脚本；DELETE: 删除脚本"""
    try:
        if request.method == 'GET':
            code = script_manager.load_script(script_id)
            if code is None:
                return jsonify({'success': False, 'error': '脚本不存在'}), 404
            info = script_manager.get_script_info(script_id)
            return jsonify({'success': True, 'data': {'script_id': script_id, 'code': code, 'info': info}}), 200
        elif request.method == 'DELETE':
            if script_manager.delete_script(script_id):
                return jsonify({'success': True, 'message': '脚本已删除'}), 200
            return jsonify({'success': False, 'error': '删除脚本失败'}), 500
    except Exception as e:
        routes_logger.error(f"管理脚本异常: {e}", exc_info=True)
        return jsonify({'success': False, 'error': f'服务器内部错误: {str(e)}'}), 500


@bp.route('/<script_id>/history', methods=['GET'])
@swag_from({
    'tags': ['脚本'],
    'summary': '获取脚本执行历史',
    'parameters': [
        {'in': 'path', 'name': 'script_id', 'type': 'string', 'required': True},
        {'in': 'query', 'name': 'limit', 'type': 'integer', 'default': 20}
    ],
    'responses': {200: {'description': '执行历史列表'}}
})
def get_script_history(script_id):
    """获取脚本执行历史"""
    try:
        limit = int(request.args.get('limit', 20))
        history = script_manager.get_execution_history(script_id, limit=limit)
        return jsonify({'success': True, 'data': history}), 200
    except Exception as e:
        routes_logger.error(f"获取执行历史异常: {e}", exc_info=True)
        return jsonify({'success': False, 'error': f'服务器内部错误: {str(e)}'}), 500


@bp.route('/categories', methods=['GET'])
@swag_from({
    'tags': ['脚本'],
    'summary': '获取所有脚本分类',
    'responses': {200: {'description': '分类列表'}}
})
def get_script_categories():
    """获取所有脚本分类"""
    try:
        categories = script_manager.get_categories()
        return jsonify({'success': True, 'data': categories}), 200
    except Exception as e:
        routes_logger.error(f"获取分类异常: {e}", exc_info=True)
        return jsonify({'success': False, 'error': f'服务器内部错误: {str(e)}'}), 500
