"""
API 路由包：按功能拆分的 Blueprint 与 Swagger 文档整合
"""
from flask import jsonify
from flasgger import Swagger

from .context import set_browser_pool
from .health import bp as health_bp
from .script_routes import bp as script_bp
from .settings_routes import bp as settings_bp
from .browser_routes import bp as browser_bp
from .pinduoduo_routes import bp as pinduoduo_bp
from .tu_routes import bp as tu_bp
from .feishu_routes import bp as feishu_bp
from .order_1688_routes import bp as order_1688_bp
from .websocket_routes import bp as websocket_bp
from .scheduler_routes import bp as scheduler_bp
from .taobao_routes import bp as taobao_bp
from .goofish_routes import bp as goofish_bp
from .antexiadan_routes import bp as antexiadan_bp
from .ai_routes import bp as ai_bp

from utils.logger import get_logger

routes_logger = get_logger('Routes')

# Swagger 文档配置
SWAGGER_TEMPLATE = {
    'info': {
        'title': '如意助手 API',
        'description': '如意助手 RESTful API 文档',
        'version': '1.0.0',
    },
    'tags': [
        {'name': '系统', 'description': '健康检查、开机自启'},
        {'name': '脚本', 'description': '脚本执行与管理'},
        {'name': '配置', 'description': '模块配置、应用配置'},
        {'name': '浏览器', 'description': '浏览器池状态'},
        {'name': '拼多多', 'description': '拼多多助手'},
        {'name': '途强', 'description': '途强物联网平台助手'},
        {'name': '飞书', 'description': '飞书消息与事件'},
        {'name': '1688订单', 'description': '1688 订单提取与飞书同步'},
        {'name': 'WebSocket', 'description': 'Socket.IO 客户端连接与配置'},
        {'name': '定时任务', 'description': '定时任务列表与手动触发'},
        {'name': '淘宝', 'description': '淘宝商品采集与 Playwright 自动上架'},
        {'name': '闲鱼', 'description': '闲鱼卖家工作台：商品发布与在线商品管理'},
        {'name': '安特', 'description': '安特 PC 商城限时秒杀'},
        {'name': 'AI', 'description': 'AI 大脑：LLM 问答与 Cursor SDK Agent'},
    ],
}
SWAGGER_CONFIG = {
    'headers': [],
    'specs': [{'endpoint': 'apispec', 'route': '/apispec.json', 'rule_filter': lambda rule: True, 'model_filter': lambda tag: True}],
    'static_url_path': '/flasgger_static',
    'swagger_ui': True,
    'specs_route': '/api/docs',  # Swagger UI 页面地址
}


def register_routes(app, browser_pool):
    """
    注册所有 API 路由与 Swagger 文档。

    Args:
        app: Flask 应用实例
        browser_pool: 浏览器池实例（可为 None）
    """
    set_browser_pool(browser_pool)

    if browser_pool:
        routes_logger.info(f"注册路由时，browser_pool 对象ID: {id(browser_pool)}")
        routes_logger.info(f"注册路由时，browser_pool._initialized: {getattr(browser_pool, '_initialized', 'N/A')}")
        try:
            from tools.manager import get_tool_manager
            tool_manager = get_tool_manager()
            for tool in tool_manager.get_all_tools():
                if hasattr(tool, 'browser_pool'):
                    tool.browser_pool = browser_pool
                    routes_logger.info(f"已设置工具 {tool.name} 的浏览器池引用")
        except Exception as e:
            routes_logger.warning(f"更新工具浏览器池引用失败: {e}")
    else:
        routes_logger.info("注册路由时，browser_pool 为 None（将在需要时懒加载创建）")

    # 注册各功能 Blueprint
    app.register_blueprint(health_bp)
    app.register_blueprint(script_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(browser_bp)
    app.register_blueprint(pinduoduo_bp)
    app.register_blueprint(tu_bp)
    app.register_blueprint(feishu_bp)
    app.register_blueprint(order_1688_bp)
    app.register_blueprint(websocket_bp)
    app.register_blueprint(scheduler_bp)
    app.register_blueprint(taobao_bp)
    app.register_blueprint(goofish_bp)
    app.register_blueprint(antexiadan_bp)
    app.register_blueprint(ai_bp)

    # 全局错误处理（注册在 app 上）
    @app.errorhandler(404)
    def not_found(error):
        return jsonify({'success': False, 'error': '接口不存在'}), 404

    @app.errorhandler(500)
    def internal_error(error):
        return jsonify({'success': False, 'error': '服务器内部错误'}), 500

    # Swagger 文档（访问 /api/docs 查看）
    Swagger(app, config=SWAGGER_CONFIG, template=SWAGGER_TEMPLATE)
