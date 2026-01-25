"""
Flask应用整合
整合API路由和Web界面路由
"""
import sys
from pathlib import Path
from typing import Optional
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
from tools.script_tool import ScriptTool
from utils.module_manager import get_module_manager


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


def init_browser_pool() -> Optional[BrowserPool]:
    """
    初始化浏览器池（按需初始化）
    
    Returns:
        浏览器池实例，如果不需要则返回None
    """
    # 检查是否有模块需要浏览器
    module_manager = get_module_manager()
    modules_requiring_browser = module_manager.get_modules_requiring_browser()
    
    if not modules_requiring_browser:
        print("[App] 没有启用的模块需要浏览器，跳过浏览器池初始化")
        return None
    
    print(f"[App] 以下模块需要浏览器: {', '.join(modules_requiring_browser)}")
    print("正在初始化浏览器池...")
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
        browser_pool = BrowserPool(
            headless=Config.HEADLESS,
            idle_timeout=600,      # 10分钟空闲后关闭
            max_instances=5        # 最多5个浏览器实例（渐进式扩展）
        )
        print("浏览器池创建完成（使用上下文管理器模式，每次调用时才创建浏览器）")
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


def init_tools(browser_pool: Optional[BrowserPool] = None) -> ToolManager:
    """
    初始化工具管理器并注册工具（根据模块配置）
    
    Args:
        browser_pool: 浏览器池实例（可选）
        
    Returns:
        工具管理器实例
    """
    tool_manager = ToolManager()
    module_manager = get_module_manager()
    
    # 获取启动时需要初始化的模块
    startup_modules = module_manager.get_startup_modules()
    print(f"[App] 启动时需要初始化的模块: {startup_modules if startup_modules else '无'}")
    
    # 根据模块配置注册工具
    # 脚本执行工具（script_executor模块）
    if module_manager.is_module_enabled('script_executor'):
        try:
            script_tool = ScriptTool()
            tool_manager.register_tool(script_tool)
            module_manager.register_module_instance('script_executor', script_tool)
            print(f"[App] 已注册工具: {script_tool.display_name}")
        except Exception as e:
            print(f"[App] 注册脚本执行工具失败: {e}")
    
    # 拼多多工具（pinduoduo模块）
    # 默认启用，不需要检查模块配置（因为配置文件中可能还没有这个模块）
    try:
        from tools.pinduoduo_tool import PinduoduoTool
        pinduoduo_tool = PinduoduoTool()
        tool_manager.register_tool(pinduoduo_tool)
        print(f"[App] 已注册工具: {pinduoduo_tool.display_name}")
        
        # 初始化拼多多工具（传递浏览器池）
        if pinduoduo_tool.initialize(browser_pool=browser_pool):
            print(f"[App] 工具 pinduoduo 初始化成功")
        else:
            print(f"[App] 工具 pinduoduo 初始化失败")
    except Exception as e:
        print(f"[App] 注册拼多多工具失败: {e}")
        import traceback
        traceback.print_exc()
    
    # 只初始化启动时需要初始化的工具
    tools_to_init = []
    
    if 'script_executor' in startup_modules:
        script_tool = tool_manager.get_tool('script_executor')
        if script_tool:
            tools_to_init.append(('script_executor', script_tool))
    
    # 初始化工具
    init_results = {}
    for tool_name, tool in tools_to_init:
        try:
            # 如果工具需要浏览器，确保浏览器池已初始化
            if tool_name == 'spider' and browser_pool is None:
                print(f"[App] 工具 {tool_name} 需要浏览器，但浏览器池未初始化，跳过初始化")
                init_results[tool_name] = False
                continue
            
            init_results[tool_name] = tool.initialize(browser_pool=browser_pool)
            if init_results[tool_name]:
                print(f"[App] 工具 {tool_name} 初始化成功")
            else:
                print(f"[App] 工具 {tool_name} 初始化失败")
        except Exception as e:
            print(f"[App] 工具 {tool_name} 初始化异常: {e}")
            init_results[tool_name] = False
    
    # 检查初始化结果
    failed_tools = [name for name, success in init_results.items() if not success]
    if failed_tools:
        print(f"[App] 警告: 以下工具初始化失败: {', '.join(failed_tools)}")
    else:
        print("[App] 启动时工具初始化完成")
    
    return tool_manager


def setup_app(app: Flask, browser_pool: Optional[BrowserPool], tool_manager: ToolManager):
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
