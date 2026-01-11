"""
Web界面路由
"""
from flask import render_template, jsonify, request, send_from_directory
from tools.manager import ToolManager
from config import Config
from utils.logger import get_logger
import os
import sys

# 获取logger
routes_logger = get_logger('WebRoutes')


def register_web_routes(app, tool_manager: ToolManager):
    """
    注册Web界面路由
    
    Args:
        app: Flask应用实例
        tool_manager: 工具管理器实例
    """
    
    @app.route('/favicon.ico')
    def favicon():
        """Favicon图标路由"""
        return send_from_directory(
            os.path.join(app.static_folder, 'images'),
            'favicon.ico',
            mimetype='image/vnd.microsoft.icon'
        )
    
    @app.route('/')
    def index():
        """主页"""
        try:
            tools_info = tool_manager.get_tools_info()
            routes_logger.info(f"主页访问，工具数量: {len(tools_info)}")
            routes_logger.info(f"工具列表: {[t.get('name', 'unknown') for t in tools_info]}")
            routes_logger.info("尝试渲染模板: index.html")
            routes_logger.debug(f"工具信息类型: {type(tools_info)}")
            # 避免打印包含emoji的内容，使用logger的debug级别
            # 如果需要查看详细信息，可以单独打印不包含emoji的字段
            result = render_template('index.html', tools=tools_info, config=Config)
            routes_logger.info(f"模板渲染成功，返回内容长度: {len(result)}")
            return result
        except Exception as e:
            routes_logger.error(f"主页渲染错误: {e}", exc_info=True)
            import traceback
            return f"<h1>页面渲染错误</h1><pre>{str(e)}</pre><pre>{traceback.format_exc()}</pre>", 500
    
    @app.errorhandler(404)
    def not_found(error):
        """404错误处理"""
        tools_info = tool_manager.get_tools_info()
        return render_template('error.html', message='页面不存在', tools=tools_info, config=Config), 404
    
    @app.route('/tools/<tool_name>')
    def tool_page(tool_name):
        """工具页面"""
        tool = tool_manager.get_tool(tool_name)
        if tool is None:
            return render_template('error.html', message=f'工具 {tool_name} 不存在', tools=tool_manager.get_tools_info(), config=Config), 404
        
        tool_info = tool.get_info()
        tools_info = tool_manager.get_tools_info()
        return render_template(tool.get_template_name(), tool=tool_info, tools=tools_info, config=Config)
    
    @app.route('/api/tools')
    def get_tools():
        """获取所有工具信息（API）"""
        tools_info = tool_manager.get_tools_info()
        return jsonify({
            'success': True,
            'tools': tools_info
        })
    
    @app.route('/api/tools/<tool_name>')
    def get_tool_info(tool_name):
        """获取指定工具信息（API）"""
        tool = tool_manager.get_tool(tool_name)
        if tool is None:
            return jsonify({
                'success': False,
                'error': f'工具 {tool_name} 不存在'
            }), 404
        
        return jsonify({
            'success': True,
            'tool': tool.get_info()
        })
    
    @app.route('/test')
    def test():
        """测试路由"""
        tools_info = tool_manager.get_tools_info()
        return f"""
        <h1>测试页面</h1>
        <p>工具数量: {len(tools_info)}</p>
        <p>工具列表: {[t.get('name', 'unknown') for t in tools_info]}</p>
        <p>配置: {Config.APP_NAME}</p>
        <a href="/">返回首页</a>
        """
    
    @app.route('/hello')
    def hello():
        """最简单的测试路由"""
        routes_logger.info("/hello 路由被访问")
        return "<h1>Hello World! Flask 正常工作！</h1><a href='/'>返回首页</a>"
    
    @app.route('/settings')
    def settings():
        """配置页面"""
        try:
            tools_info = tool_manager.get_tools_info()
            routes_logger.info("配置页面访问")
            return render_template('settings.html', tools=tools_info, config=Config)
        except Exception as e:
            routes_logger.error(f"配置页面渲染错误: {e}", exc_info=True)
            return render_template('error.html', message='配置页面加载失败', tools=tool_manager.get_tools_info(), config=Config), 500
    
    @app.before_request
    def log_request_info():
        """记录每个请求"""
        routes_logger.debug(f"收到请求: {request.method} {request.path}")
    
    @app.after_request
    def log_response_info(response):
        """记录每个响应"""
        routes_logger.debug(f"响应: {request.method} {request.path} -> {response.status_code}")
        return response