"""
Flask应用整合
整合API路由和Web界面路由
"""
import sys
from pathlib import Path
from flask import Flask

# 在导入其他模块前查找浏览器路径
from utils.browser_path import CHROME_EXECUTABLE_PATH, find_chrome_executable

# 初始化浏览器路径
find_chrome_executable()

# 打印调试信息
if CHROME_EXECUTABLE_PATH:
    print(f"[App] 已找到浏览器驱动: {CHROME_EXECUTABLE_PATH}")
else:
    print("[App] 警告: 未找到浏览器驱动，将使用 Playwright 默认路径")

# 现在导入其他模块
from spider.query_manager import BrowserPool
from config import Config
from api.routes import register_routes as register_api_routes
from tools.manager import ToolManager
from tools.spider_tool import SpiderTool


def create_app() -> Flask:
    """
    创建Flask应用实例
    
    Returns:
        Flask应用实例
    """
    # 获取当前文件所在目录
    current_dir = Path(__file__).parent
    
    # 确定模板和静态文件路径
    # 如果是打包后的exe，路径在 _internal 目录（onedir模式）或 exe 同目录
    # 如果是开发环境，路径在src目录
    if getattr(sys, 'frozen', False):
        # 打包后的exe环境
        exe_dir = Path(sys.executable).parent
        
        # PyInstaller onedir 模式下，datas 文件会被复制到 _internal 目录
        # 先尝试 _internal 目录，如果不存在则尝试 exe 同目录
        internal_path = exe_dir / '_internal'
        if internal_path.exists():
            # onedir 模式：文件在 _internal 目录
            base_path = internal_path
        else:
            # onefile 模式或其他：文件在 exe 同目录
            base_path = exe_dir
        
        template_folder = str(base_path / 'web' / 'templates')
        static_folder = str(base_path / 'static')
    else:
        # 开发环境
        template_folder = str(current_dir / 'web' / 'templates')
        static_folder = str(current_dir / 'static')
    
    # 创建Flask应用
    print(f"[App] 模板文件夹路径: {template_folder}")
    print(f"[App] 静态文件夹路径: {static_folder}")
    
    # 检查路径是否存在
    template_path = Path(template_folder)
    static_path = Path(static_folder)
    print(f"[App] 模板文件夹存在: {template_path.exists()}")
    print(f"[App] 静态文件夹存在: {static_path.exists()}")
    if template_path.exists():
        print(f"[App] 模板文件列表: {list(template_path.glob('*.html'))}")
    
    app = Flask(
        __name__,
        template_folder=template_folder,
        static_folder=static_folder,
        static_url_path='/static'
    )
    
    # 配置
    app.config['SECRET_KEY'] = 'your-secret-key-here'  # 可以改为从环境变量读取
    
    return app


def init_browser_pool() -> BrowserPool:
    """
    初始化浏览器池
    
    Returns:
        浏览器池实例
    """
    print("正在初始化浏览器池（2个专用页面：JD页面和百度页面）...")
    print(f"headless={Config.HEADLESS} (True=后台运行，False=显示浏览器窗口，调试时使用False)")
    
    # 确保浏览器路径已找到
    global CHROME_EXECUTABLE_PATH
    if not CHROME_EXECUTABLE_PATH:
        print("重新查找浏览器驱动路径...")
        find_chrome_executable()
        if CHROME_EXECUTABLE_PATH:
            print(f"找到浏览器驱动: {CHROME_EXECUTABLE_PATH}")
        else:
            print("警告: 未找到浏览器驱动，将使用 Playwright 默认路径")
            print("提示: 如果应用无法正常工作，请确保 playwright_drivers 目录已正确复制到打包目录")
            print("      或者运行: playwright install chromium 安装系统级浏览器驱动")
    
    try:
        browser_pool = BrowserPool(headless=Config.HEADLESS)
        browser_pool.initialize()
        print("浏览器池初始化完成")
        return browser_pool
    except Exception as e:
        error_msg = str(e)
        print(f"\n{'='*60}")
        print("浏览器池初始化失败！")
        print(f"{'='*60}")
        if "Executable doesn't exist" in error_msg or "playwright" in error_msg.lower():
            print("错误：Playwright 浏览器驱动未安装")
            print("\n请运行以下命令安装浏览器驱动：")
            print("  venv\\Scripts\\python.exe -m playwright install chromium")
            print("或者：")
            print("  playwright install chromium")
        else:
            print(f"错误信息: {e}")
        print(f"{'='*60}")
        import traceback
        traceback.print_exc()
        print(f"{'='*60}")
        raise


def init_tools(browser_pool: BrowserPool) -> ToolManager:
    """
    初始化工具管理器并注册工具
    
    Args:
        browser_pool: 浏览器池实例
        
    Returns:
        工具管理器实例
    """
    tool_manager = ToolManager()
    
    # 注册爬虫工具
    spider_tool = SpiderTool()
    tool_manager.register_tool(spider_tool)
    
    # 初始化所有工具
    init_results = tool_manager.initialize_all(browser_pool=browser_pool)
    
    # 检查初始化结果
    failed_tools = [name for name, success in init_results.items() if not success]
    if failed_tools:
        print(f"[App] 警告: 以下工具初始化失败: {', '.join(failed_tools)}")
    else:
        print("[App] 所有工具初始化成功")
    
    return tool_manager


def setup_app(app: Flask, browser_pool: BrowserPool, tool_manager: ToolManager):
    """
    设置Flask应用（注册路由等）
    
    Args:
        app: Flask应用实例
        browser_pool: 浏览器池实例
        tool_manager: 工具管理器实例
    """
    # 注册API路由
    register_api_routes(app, browser_pool)
    
    # 注册Web界面路由（稍后创建）
    from web.routes import register_web_routes
    register_web_routes(app, tool_manager)
    
    print("[App] 路由注册完成")
