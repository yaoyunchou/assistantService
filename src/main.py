"""
桌面应用主程序入口
整合系统托盘、Flask服务和工具管理
"""
import sys
import signal
import atexit
import threading
import time
import logging
from pathlib import Path
import requests
from requests.exceptions import ConnectionError, RequestException

# 首先初始化日志系统
from utils.logger import init_logging, get_logger
from config import Config

# 将字符串日志级别转换为logging常量
LOG_LEVEL_MAP = {
    'DEBUG': logging.DEBUG,
    'INFO': logging.INFO,
    'WARNING': logging.WARNING,
    'ERROR': logging.ERROR,
    'CRITICAL': logging.CRITICAL
}
log_level = LOG_LEVEL_MAP.get(Config.LOG_LEVEL.upper(), logging.INFO)

# 初始化日志系统
init_logging(log_dir=Config.LOG_DIR, level=log_level)
logger = get_logger('Main')

# 在导入其他模块前查找浏览器路径
from utils.browser_path import CHROME_EXECUTABLE_PATH, find_chrome_executable

# 初始化浏览器路径
find_chrome_executable()

# 记录浏览器路径信息
if CHROME_EXECUTABLE_PATH:
    logger.info(f"已找到浏览器驱动: {CHROME_EXECUTABLE_PATH}")
else:
    logger.warning("未找到浏览器驱动，将使用 Playwright 默认路径")

# 现在导入其他模块
from flask import Flask
from app import create_app, init_browser_pool, init_tools, setup_app
from tray.tray_icon import TrayIcon
from utils.startup import is_startup_enabled, add_to_startup

# 全局变量
app: Flask = None  # Flask应用实例（在Flask线程中创建）
browser_pool = None
tool_manager = None
tray_icon: TrayIcon = None
flask_thread = None
shutdown_event = threading.Event()


# 全局窗口变量
webview_window = None
_window_created = False
_window_lock = threading.Lock()

# 服务就绪标志
_flask_ready = threading.Event()

def wait_for_server_ready(timeout=60, check_interval=0.5):
    """
    等待Flask服务就绪（直到看到 "Running on..." 消息）
    
    Args:
        timeout: 超时时间（秒）
        check_interval: 检查间隔（秒）
    
    Returns:
        bool: 服务是否就绪
    """
    url = f"http://{Config.HOST}:{Config.PORT}"
    start_time = time.time()
    
    logger.info(f"等待Flask服务就绪: {url}")
    logger.info(f"等待服务显示 'Running on {url}' 消息...")
    
    # 先等待一小段时间，让Flask开始启动
    time.sleep(0.5)
    
    while time.time() - start_time < timeout:
        try:
            # 尝试访问根路径，确保服务完全启动并能响应请求
            # 这比只检查连接更可靠，因为可以确认服务已经可以处理请求
            response = requests.get(url, timeout=2)
            # 200表示成功，404表示服务已启动但路径不存在（也可以接受）
            # 500表示服务启动但可能有错误，我们也认为服务已就绪
            if response.status_code in [200, 404, 500]:
                # 再等待一小段时间，确保Flask完全初始化完成
                time.sleep(0.3)
                # 再次检查，确保服务稳定
                try:
                    test_response = requests.get(url, timeout=1)
                    elapsed = time.time() - start_time
                    logger.info(f"✓ Flask服务已就绪（耗时 {elapsed:.2f} 秒）")
                    logger.info(f"服务地址: {url}")
                    return True
                except:
                    # 如果第二次检查失败，继续等待
                    pass
        except ConnectionError:
            # 连接被拒绝，服务还未启动
            pass
        except RequestException as e:
            # 其他请求异常，可能是服务还在启动中
            pass
        except Exception as e:
            # 其他异常，记录但不中断
            logger.debug(f"等待服务就绪时出现异常: {e}")
        
        time.sleep(check_interval)
    
    elapsed = time.time() - start_time
    logger.warning(f"✗ Flask服务启动超时（{elapsed:.2f} 秒）")
    return False


def on_window_closing():
    """窗口关闭事件处理：隐藏窗口到托盘而不是真正关闭"""
    global webview_window
    
    try:
        logger.info("窗口关闭按钮被点击，隐藏窗口到系统托盘...")
        
        # 隐藏窗口而不是关闭（隐藏后任务栏图标会消失，只保留托盘图标）
        if webview_window:
            try:
                # 使用 hide() 隐藏窗口，这样任务栏图标会消失
                # 窗口仍然存在，可以通过托盘图标恢复
                webview_window.hide()
                logger.info("窗口已隐藏，应用继续在后台运行（任务栏图标已移除）")
                logger.info("可以通过系统托盘图标恢复窗口")
                return False  # 返回 False 表示取消关闭操作
            except Exception as e:
                logger.warning(f"隐藏窗口失败: {e}，尝试最小化窗口")
                # 如果隐藏失败，尝试最小化（作为备选方案）
                try:
                    webview_window.minimize()
                    logger.warning("窗口已最小化到任务栏（备选方案）")
                    return False
                except Exception as minimize_error:
                    logger.error(f"最小化窗口也失败: {minimize_error}")
                    # 如果都失败，允许关闭
                    return True
        else:
            # 如果窗口对象不存在，允许关闭
            return True
    except Exception as e:
        logger.error(f"处理窗口关闭事件时出错: {e}")
        return True  # 出错时允许关闭


def show_native_window():
    """显示原生窗口（如果已创建）或创建新窗口
    
    优化：使用最直接的方法快速恢复窗口，避免慢操作
    """
    global webview_window, _window_created
    
    try:
        import webview
        
        # 检查窗口是否存在
        if not _window_created or not webview_window:
            logger.warning("窗口不存在，无法从托盘创建新窗口（webview.start() 必须在主线程）")
            return create_native_window_in_thread()
        
        # 窗口已存在，使用最直接的方法快速恢复
        try:
            # 对于隐藏的窗口，使用 show() 显示窗口
            # 对于最小化的窗口，使用 restore() 恢复
            try:
                webview_window.show()
                logger.info("窗口已从隐藏状态显示")
            except (AttributeError, Exception) as show_error:
                # 如果 show() 不支持或失败，尝试 restore()
                try:
                    webview_window.restore()
                    logger.info("窗口已从最小化状态恢复")
                except (AttributeError, Exception) as restore_error:
                    logger.warning(f"恢复窗口失败: show()={show_error}, restore()={restore_error}")
            
            # 尝试将窗口置于前台（可选，可能在某些平台不支持）
            try:
                webview_window.bring_to_front()
            except (AttributeError, Exception):
                # 某些平台可能不支持 bring_to_front，忽略错误
                pass
            
            return True
            
        except Exception as e:
            logger.warning(f"restore() 方法失败: {e}，尝试 show() 方法")
            # 如果 restore() 失败，尝试 show()（可能窗口被隐藏了）
            try:
                webview_window.show()
                logger.info("窗口已显示")
                
                # 再次尝试 restore()
                try:
                    webview_window.restore()
                    logger.info("窗口已恢复")
                except:
                    pass
                
                return True
            except Exception as show_error:
                logger.error(f"显示窗口失败: {show_error}")
                # 如果都失败，回退到浏览器模式
                logger.warning("窗口对象可能已失效，无法恢复窗口")
                return create_native_window_in_thread()
            
    except ImportError:
        logger.warning("pywebview 未安装")
        return False
    except Exception as e:
        logger.error(f"显示窗口时出错: {e}", exc_info=True)
        return False


def _get_window_icon_path():
    """
    获取窗口图标路径
    
    Returns:
        图标文件路径（ICO格式），如果不存在则返回None
    """
    try:
        from pathlib import Path
        from PIL import Image
        
        # 获取当前文件所在目录
        current_dir = Path(__file__).parent
        
        # 优先使用logo_default.jpg，转换为ICO格式
        logo_path = current_dir / 'static' / 'images' / 'logo_default.jpg'
        icon_path = current_dir / 'static' / 'images' / 'window_icon.ico'
        
        if logo_path.exists():
            try:
                # 如果ICO文件不存在或比JPG文件旧，则重新生成
                if not icon_path.exists() or logo_path.stat().st_mtime > icon_path.stat().st_mtime:
                    img = Image.open(logo_path)
                    # 转换为RGBA模式
                    if img.mode != 'RGBA':
                        img = img.convert('RGBA')
                    # 调整大小（Windows窗口图标通常需要256x256）
                    if img.size[0] != 256 or img.size[1] != 256:
                        img = img.resize((256, 256), Image.Resampling.LANCZOS)
                    # 保存为ICO格式
                    img.save(icon_path, format='ICO')
                    logger.info(f"已生成窗口图标: {icon_path}")
                return str(icon_path)
            except Exception as e:
                logger.warning(f"转换窗口图标失败: {e}，尝试使用现有ICO文件")
        
        # 尝试使用现有的ICO文件
        possible_icon_paths = [
            current_dir / 'static' / 'images' / 'icon.ico',
            current_dir / 'static' / 'images' / 'favicon.ico',
        ]
        
        for path in possible_icon_paths:
            if path.exists():
                return str(path)
        
        return None
    except Exception as e:
        logger.warning(f"获取窗口图标路径失败: {e}")
        return None


def create_native_window_in_thread():
    """在后台线程中创建原生窗口（非阻塞）
    
    注意：这个方法只能用于从托盘图标打开窗口的情况
    因为 webview.start() 必须在主线程中调用
    """
    try:
        import webbrowser
        # 如果窗口无法显示，回退到浏览器模式
        url = f"http://{Config.HOST}:{Config.PORT}"
        logger.info(f"无法显示原生窗口，使用浏览器打开: {url}")
        webbrowser.open(url)
        return True
    except Exception as e:
        logger.error(f"打开浏览器失败: {e}")
        return False


def create_native_window():
    """创建原生窗口显示Web界面（在主线程中调用，会阻塞直到窗口关闭）
    
    注意：调用此函数前应确保服务已就绪（通过 wait_for_server_ready()）
    """
    global webview_window, _window_created
    
    try:
        import webview
        
        url = f"http://{Config.HOST}:{Config.PORT}"
        logger.info(f"正在创建原生窗口: {url}")
        logger.info(f"窗口标题: {Config.WINDOW_TITLE}")
        logger.info(f"窗口大小: {Config.WINDOW_WIDTH}x{Config.WINDOW_HEIGHT}")
        
        with _window_lock:
            if not _window_created:
                # 获取窗口图标路径
                icon_path = _get_window_icon_path()
                
                # 创建原生窗口
                # 注意：pywebview 的 debug 参数在 webview.start() 中设置，不在 create_window() 中
                # Windows上窗口图标通常从exe文件获取，但也可以通过webview.start()的icon参数设置
                webview_window = webview.create_window(
                    title=Config.WINDOW_TITLE,
                    url=url,
                    width=Config.WINDOW_WIDTH,
                    height=Config.WINDOW_HEIGHT,
                    min_size=(Config.WINDOW_MIN_WIDTH, Config.WINDOW_MIN_HEIGHT),
                    resizable=Config.WINDOW_RESIZABLE,
                    on_top=False
                )
                
                # 设置窗口关闭事件处理
                # pywebview 使用 events.closing 事件
                try:
                    if hasattr(webview_window, 'events') and hasattr(webview_window.events, 'closing'):
                        webview_window.events.closing += on_window_closing
                        logger.info("已设置窗口关闭事件处理（最小化到托盘）")
                    else:
                        logger.warning("无法设置窗口关闭事件，窗口关闭将直接退出应用")
                except Exception as e:
                    logger.error(f"设置窗口关闭事件失败: {e}，将使用默认行为")
                
                _window_created = True
                logger.info("原生窗口已创建")
                logger.info("提示: 点击窗口关闭按钮将隐藏窗口到系统托盘（任务栏图标会消失）")
                logger.info("窗口将阻塞主线程，直到应用退出...")
                
                # webview.start() 必须在主线程中调用，并且会阻塞直到窗口关闭
                # 由于我们拦截了关闭事件，窗口关闭时会最小化而不是真正关闭
                # 所以 webview.start() 会一直运行，直到应用退出
                # 注意：即使窗口被最小化，webview.start() 也会继续运行
                # debug参数：控制是否默认显示开发者工具
                # False=不默认显示，但F12快捷键仍可用（如果浏览器支持）
                # icon参数：设置窗口图标（Windows上可能不生效，图标主要从exe文件获取）
                if icon_path:
                    try:
                        webview.start(debug=Config.ENABLE_DEVTOOLS, icon=icon_path)
                    except Exception as e:
                        logger.warning(f"设置窗口图标失败: {e}，使用默认图标")
                        webview.start(debug=Config.ENABLE_DEVTOOLS)
                else:
                    webview.start(debug=Config.ENABLE_DEVTOOLS)
                
                # 如果执行到这里，说明窗口真正关闭了（可能是应用退出）
                logger.info("原生窗口已关闭")
                shutdown_event.set()
            else:
                # 窗口已存在，尝试显示它
                show_native_window()
    except ImportError:
        logger.warning("pywebview 未安装，回退到浏览器模式")
        # 注意：服务就绪检查应在调用此函数前完成
        import webbrowser
        url = f"http://{Config.HOST}:{Config.PORT}"
        webbrowser.open(url)
    except Exception as e:
        logger.error(f"创建原生窗口失败: {e}", exc_info=True)
        # 回退到浏览器模式
        try:
            import webbrowser
            url = f"http://{Config.HOST}:{Config.PORT}"
            webbrowser.open(url)
        except Exception as browser_error:
            logger.error(f"回退到浏览器模式也失败: {browser_error}")

def open_browser():
    """打开浏览器访问Web界面（兼容旧代码，已等待服务就绪）"""
    if Config.USE_NATIVE_WINDOW:
        # 原生窗口在主线程中创建，这里只记录日志
        logger.info("将使用原生窗口模式")
    else:
        import webbrowser
        url = f"http://{Config.HOST}:{Config.PORT}"
        logger.info(f"正在打开浏览器: {url}")
        try:
            webbrowser.open(url)
        except Exception as e:
            logger.error(f"打开浏览器失败: {e}")


def run_flask_app():
    """在单独线程中运行Flask应用"""
    global app, browser_pool, tool_manager
    flask_logger = get_logger('Flask')
    try:
        flask_logger.info("="*60)
        flask_logger.info("Flask线程启动中...")
        flask_logger.info(f"当前线程: {threading.current_thread().name}")
        
        # 重要：在Flask线程中先查找浏览器路径（如果还没找到）
        from utils.browser_path import CHROME_EXECUTABLE_PATH, find_chrome_executable
        if not CHROME_EXECUTABLE_PATH:
            flask_logger.info("Flask线程中重新查找浏览器路径...")
            find_chrome_executable()
            if CHROME_EXECUTABLE_PATH:
                flask_logger.info(f"Flask线程中找到浏览器驱动: {CHROME_EXECUTABLE_PATH}")
            else:
                flask_logger.warning("Flask线程中未找到浏览器驱动，将使用 Playwright 默认路径")
        
        # 在Flask线程中创建Flask应用（确保所有Flask相关操作在同一线程）
        flask_logger.info("正在Flask线程中创建Flask应用...")
        from app import create_app
        app = create_app()
        
        # 重要：在Flask线程中初始化BrowserPool，确保Playwright操作在同一线程
        flask_logger.info("正在Flask线程中初始化浏览器池...")
        from app import init_browser_pool, init_tools
        browser_pool = init_browser_pool()
        flask_logger.info(f"浏览器池对象ID: {id(browser_pool)}")
        flask_logger.info(f"浏览器池._initialized: {getattr(browser_pool, '_initialized', 'N/A')}")
        
        # 在Flask线程中初始化工具管理器
        flask_logger.info("正在Flask线程中初始化工具管理器...")
        tool_manager = init_tools(browser_pool)
        
        # 注册Flask应用的路由（使用新初始化的browser_pool和tool_manager）
        from app import setup_app
        flask_logger.info(f"注册路由前，browser_pool对象ID: {id(browser_pool)}")
        flask_logger.info(f"注册路由前，browser_pool._initialized: {getattr(browser_pool, '_initialized', 'N/A')}")
        setup_app(app, browser_pool, tool_manager)
        flask_logger.info(f"注册路由后，browser_pool对象ID: {id(browser_pool)}")
        flask_logger.info(f"注册路由后，browser_pool._initialized: {getattr(browser_pool, '_initialized', 'N/A')}")
        
        flask_logger.info("Flask服务启动中...")
        flask_logger.info(f"服务地址: http://{Config.HOST}:{Config.PORT}")
        flask_logger.info(f"Flask应用对象: {app}")
        flask_logger.info(f"Flask应用名称: {app.name}")
        flask_logger.info("Flask路由列表:")
        for rule in app.url_map.iter_rules():
            flask_logger.info(f"  {rule.methods} {rule.rule}")
        flask_logger.info("="*60)
        
        # 配置Flask的werkzeug日志，使用我们的日志系统
        werkzeug_logger = logging.getLogger('werkzeug')
        werkzeug_logger.setLevel(logging.INFO)
        # 移除werkzeug的默认处理器，使用我们的日志系统
        werkzeug_logger.handlers = []
        werkzeug_logger.addHandler(logging.NullHandler())  # 避免重复输出
        
        # 标记服务准备启动
        flask_logger.info("Flask服务即将启动...")
        
        app.run(
            host=Config.HOST,
            port=Config.PORT,
            debug=False,
            threaded=False,  # 禁用多线程，避免Playwright线程切换问题
            use_reloader=False  # 禁用自动重载
        )
        
        # 服务关闭时，设置就绪标志为False（虽然通常不会执行到这里）
        _flask_ready.clear()
    except Exception as e:
        flask_logger.error("="*60)
        flask_logger.error(f"Flask服务运行异常: {e}", exc_info=True)
        flask_logger.error("="*60)


def cleanup():
    """清理资源"""
    global browser_pool, tool_manager, tray_icon
    
    logger.info("正在清理资源...")
    
    # 停止系统托盘
    if tray_icon:
        tray_icon.stop()
    
    # 清理工具
    if tool_manager:
        tool_manager.cleanup_all()
    
    # 关闭浏览器池
    if browser_pool:
        browser_pool.close()
    
    logger.info("资源清理完成")


def signal_handler(signum, frame):
    """信号处理器，用于优雅关闭"""
    logger.info("\n收到关闭信号，正在关闭应用...")
    shutdown_event.set()
    cleanup()
    sys.exit(0)


def on_tray_open():
    """托盘图标打开界面回调（优化：快速响应）"""
    if Config.USE_NATIVE_WINDOW:
        # 尝试显示已存在的窗口（快速操作，不记录过多日志）
        try:
            if not show_native_window():
                # 如果显示失败，尝试重新创建
                create_native_window_in_thread()
        except Exception as e:
            logger.error(f"打开窗口失败: {e}")
            # 回退到浏览器模式
            try:
                import webbrowser
                url = f"http://{Config.HOST}:{Config.PORT}"
                webbrowser.open(url)
            except:
                pass
    else:
        import webbrowser
        url = f"http://{Config.HOST}:{Config.PORT}"
        webbrowser.open(url)


def on_tray_quit():
    """托盘图标退出回调"""
    logger.info("用户选择退出应用")
    shutdown_event.set()
    
    # 清理资源
    cleanup()
    
    # 停止托盘图标（在清理之后，避免资源冲突）
    global tray_icon
    if tray_icon:
        try:
            tray_icon.stop()
        except Exception as e:
            logger.warning(f"停止托盘图标时出错: {e}")
    
    # 使用 os._exit() 直接退出，避免 SystemExit 异常被 pystray 捕获并记录为错误
    # os._exit() 会立即终止进程，不会抛出异常
    import os
    os._exit(0)


def main():
    """主函数"""
    global app, browser_pool, tool_manager, tray_icon, flask_thread
    
    try:
        # 检查并添加到开机启动（如果还没有）
        if not is_startup_enabled():
            logger.info("检测到未设置开机自启动，正在自动添加...")
            add_to_startup()
        else:
            logger.info("开机自启动已启用")
        
        # 注意：Flask应用、BrowserPool 和 ToolManager 都将在 Flask 线程中初始化
        # 这样可以确保 Playwright 操作在同一线程中执行，避免线程切换错误
        # app 将在 run_flask_app() 函数中创建
        
        # 启动系统托盘
        if Config.TRAY_ENABLED:
            logger.info("正在启动系统托盘...")
            tray_icon = TrayIcon(on_open=on_tray_open, on_quit=on_tray_quit)
            tray_icon.start()
        
        # 在单独线程中启动Flask服务
        flask_thread = threading.Thread(target=run_flask_app, daemon=True)
        flask_thread.start()
        
        logger.info("="*60)
        logger.info(f"{Config.APP_NAME} 正在启动...")
        logger.info("="*60)
        logger.info(f"服务地址: http://{Config.HOST}:{Config.PORT}")
        logger.info("="*60)
        
        # 注册信号处理器
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # 注册退出时的清理函数
        atexit.register(cleanup)
        
        # 根据配置选择界面模式
        if Config.AUTO_OPEN_BROWSER:
            # 无论是原生窗口还是浏览器模式，都需要先等待服务就绪
            logger.info("等待Flask服务就绪...")
            if not wait_for_server_ready():
                logger.warning("服务启动超时，但仍将尝试打开界面")
            else:
                logger.info("Flask服务已就绪，现在可以安全打开界面")
            
            if Config.USE_NATIVE_WINDOW:
                # 使用原生窗口模式
                try:
                    create_native_window()  # 这会阻塞直到窗口关闭
                except Exception as e:
                    logger.error(f"原生窗口模式失败: {e}", exc_info=True)
                    # 回退到等待模式
                    try:
                        while not shutdown_event.is_set():
                            time.sleep(1)
                    except KeyboardInterrupt:
                        logger.info("\n收到中断信号")
                        shutdown_event.set()
            else:
                # 浏览器模式
                try:
                    open_browser()
                except Exception as e:
                    logger.error(f"打开浏览器失败: {e}", exc_info=True)
                
                logger.info("按 Ctrl+C 或通过系统托盘退出应用")
                
                # 主线程等待，直到收到关闭信号
                try:
                    while not shutdown_event.is_set():
                        time.sleep(1)
                except KeyboardInterrupt:
                    logger.info("\n收到中断信号")
                    shutdown_event.set()
        else:
            # 禁用自动打开，只等待服务启动
            logger.info("等待Flask服务就绪...")
            if wait_for_server_ready():
                logger.info("Flask服务已就绪，应用正在后台运行")
            else:
                logger.warning("服务启动超时")
            
            logger.info("按 Ctrl+C 或通过系统托盘退出应用")
            
            # 主线程等待，直到收到关闭信号
            try:
                while not shutdown_event.is_set():
                    time.sleep(1)
            except KeyboardInterrupt:
                logger.info("\n收到中断信号")
                shutdown_event.set()
        
    except KeyboardInterrupt:
        logger.info("\n收到中断信号，正在关闭应用...")
    except Exception as e:
        logger.error("="*60)
        logger.error("应用启动失败！", exc_info=True)
        logger.error("="*60)
    finally:
        cleanup()
        # 确保程序退出前暂停，让用户能看到错误信息
        if not shutdown_event.is_set():
            logger.info("\n按回车键关闭程序...")
            try:
                input()
            except:
                pass


if __name__ == '__main__':
    main()
