"""
浏览器池状态 API
"""
from flask import Blueprint, jsonify
from flasgger import swag_from
from api.routes.context import get_browser_pool
from utils.logger import get_logger

routes_logger = get_logger('Routes')
bp = Blueprint('browser', __name__, url_prefix='/api/browser')


@bp.route('/pool/status', methods=['GET'])
@swag_from({
    'tags': ['浏览器'],
    'summary': '获取浏览器池状态',
    'responses': {200: {'description': '状态信息（可能未初始化）'}}
})
def browser_pool_status():
    """获取浏览器池状态信息"""
    try:
        pool = get_browser_pool()
        if not pool:
            return jsonify({
                'success': True,
                'data': {'status': 'not_initialized', 'message': '浏览器池未初始化'}
            }), 200
        status = pool.get_pool_status()
        return jsonify({
            'success': True,
            'data': {'status': 'active', **status}
        }), 200
    except Exception as e:
        routes_logger.error(f"获取浏览器池状态异常: {e}", exc_info=True)
        return jsonify({'success': False, 'error': f'服务器内部错误: {str(e)}'}), 500
