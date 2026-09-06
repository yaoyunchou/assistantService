"""
Web 控制版入口 — Flask + 系统浏览器，无托盘 / pywebview。

适用于 macOS、Linux 及不需要 Windows 桌面壳的场景。
启动后访问 http://127.0.0.1:{PORT}（默认 8887，可由 PORT 或 app_config.toml 覆盖）。

与 main.py 的区别：
  - 不启用系统托盘、原生窗口、单实例锁、注册表开机自启
  - 服务就绪后用系统默认浏览器打开 Web UI
"""
import os
import sys

os.environ.setdefault('APP_ENV', 'production')

from utils.win32_msvc_runtime import add_dll_search_paths_if_needed

add_dll_search_paths_if_needed()

import signal
import atexit
import threading
import time
import logging
import webbrowser
import requests
from requests.exceptions import ConnectionError, RequestException

from utils.logger import init_logging, get_logger
from config import Config

# Web 控制版默认：纯浏览器 UI
Config.TRAY_ENABLED = False
Config.USE_NATIVE_WINDOW = False
Config.AUTO_OPEN_BROWSER = True

LOG_LEVEL_MAP = {
    'DEBUG': logging.DEBUG,
    'INFO': logging.INFO,
    'WARNING': logging.WARNING,
    'ERROR': logging.ERROR,
    'CRITICAL': logging.CRITICAL,
}
log_level = LOG_LEVEL_MAP.get(Config.LOG_LEVEL.upper(), logging.INFO)
init_logging(log_dir=Config.LOG_DIR, level=log_level)
logger = get_logger('WebMode')

from utils.browser_path import CHROME_EXECUTABLE_PATH, find_chrome_executable

find_chrome_executable()
if CHROME_EXECUTABLE_PATH:
    logger.info(f"已找到浏览器驱动: {CHROME_EXECUTABLE_PATH}")
else:
    logger.warning("未找到浏览器驱动，将使用 Playwright 默认路径（请运行: playwright install chromium）")

app = None
browser_pool = None
tool_manager = None
flask_thread = None
shutdown_event = threading.Event()


def _warn_optional_data_dirs() -> None:
    """非 Windows 上提示配置淘宝/闲鱼数据目录。"""
    if sys.platform == 'win32':
        return
    try:
        from spider.taobao.config import TAOBAO_DATA_DIR
        from spider.goofish.config import GOOFISH_DATA_DIR
    except Exception:
        return
    for name, path in (
        ('TAOBAO_DATA_DIR', TAOBAO_DATA_DIR),
        ('GOOFISH_DATA_DIR', GOOFISH_DATA_DIR),
    ):
        if not str(path):
            logger.warning('%s 未配置，淘宝/闲鱼模块可能不可用', name)
        elif not path.exists():
            logger.warning('%s 指向的目录不存在: %s', name, path)


def wait_for_server_ready(timeout=60, check_interval=0.5):
    """等待 Flask 服务就绪"""
    url = f"http://{Config.HOST}:{Config.PORT}"
    start_time = time.time()
    logger.info(f"等待 Flask 服务就绪: {url}")
    time.sleep(0.5)

    while time.time() - start_time < timeout:
        try:
            response = requests.get(url, timeout=2)
            if response.status_code in (200, 404, 500):
                time.sleep(0.3)
                try:
                    requests.get(url, timeout=1)
                    elapsed = time.time() - start_time
                    logger.info(f"Flask 服务已就绪（耗时 {elapsed:.2f} 秒）")
                    return True
                except RequestException:
                    pass
        except ConnectionError:
            pass
        except RequestException:
            pass
        except Exception as e:
            logger.debug(f"等待服务就绪时出现异常: {e}")
        time.sleep(check_interval)

    logger.warning(f"Flask 服务启动超时（{timeout} 秒）")
    return False


def run_flask_app():
    """在单独线程中运行 Flask 应用"""
    global app, browser_pool, tool_manager
    flask_logger = get_logger('Flask')
    try:
        from utils.browser_path import find_chrome_executable as _find_chrome
        if not CHROME_EXECUTABLE_PATH:
            _find_chrome()

        from app import create_app, init_browser_pool, init_tools, setup_app

        flask_logger.info("正在创建 Flask 应用...")
        app = create_app()

        flask_logger.info("正在初始化浏览器池...")
        browser_pool = init_browser_pool()
        tool_manager = init_tools(browser_pool)
        setup_app(app, browser_pool, tool_manager)

        try:
            from scheduler import start_scheduler
            if start_scheduler():
                flask_logger.info("定时任务调度器已启动")
        except Exception as e:
            flask_logger.warning(f"启动定时任务调度器失败: {e}")

        try:
            from utils.websocket_client import get_websocket_client
            ws_result = get_websocket_client().start_if_enabled()
            if ws_result.get('skipped'):
                flask_logger.info(f"WebSocket 客户端未启用: {ws_result.get('reason', '')}")
            elif ws_result.get('success'):
                flask_logger.info(f"WebSocket 客户端已启动: {ws_result.get('url', '')}")
            else:
                flask_logger.warning(f"WebSocket 客户端启动失败: {ws_result.get('error', '')}")
        except Exception as e:
            flask_logger.warning(f"WebSocket 客户端启动异常: {e}")

        flask_logger.info(f"Flask 服务启动: http://{Config.HOST}:{Config.PORT}")

        werkzeug_logger = logging.getLogger('werkzeug')
        werkzeug_logger.setLevel(logging.INFO)
        werkzeug_logger.handlers = []
        werkzeug_logger.addHandler(logging.NullHandler())

        app.run(
            host=Config.HOST,
            port=Config.PORT,
            debug=False,
            threaded=False,
            use_reloader=False,
        )
    except Exception as e:
        flask_logger.error(f"Flask 服务运行异常: {e}", exc_info=True)


def cleanup():
    """清理资源"""
    global browser_pool, tool_manager
    logger.info("正在清理资源...")

    try:
        from utils.websocket_client import get_websocket_client
        get_websocket_client().disconnect()
    except Exception as e:
        logger.debug(f"断开 WebSocket 客户端时: {e}")

    if tool_manager:
        tool_manager.cleanup_all()

    try:
        from scheduler import shutdown_scheduler
        shutdown_scheduler()
    except Exception as e:
        logger.debug(f"关闭定时任务调度器时: {e}")

    if browser_pool:
        browser_pool.close()

    logger.info("资源清理完成")


def signal_handler(signum, frame):
    logger.info("收到关闭信号，正在关闭应用...")
    shutdown_event.set()
    cleanup()
    sys.exit(0)


def open_browser():
    url = f"http://{Config.HOST}:{Config.PORT}"
    logger.info(f"正在打开浏览器: {url}")
    try:
        webbrowser.open(url)
    except Exception as e:
        logger.error(f"打开浏览器失败: {e}")


def main():
    global flask_thread

    _warn_optional_data_dirs()

    try:
        flask_thread = threading.Thread(target=run_flask_app, daemon=True)
        flask_thread.start()

        logger.info("=" * 60)
        logger.info(f"{Config.APP_NAME} Web 控制版正在启动...")
        logger.info(f"平台: {sys.platform}")
        logger.info(f"服务地址: http://{Config.HOST}:{Config.PORT}")
        logger.info("=" * 60)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        atexit.register(cleanup)

        if not wait_for_server_ready():
            logger.warning("服务启动超时，但仍将尝试打开浏览器")

        if Config.AUTO_OPEN_BROWSER:
            open_browser()

        logger.info("按 Ctrl+C 退出应用")

        while not shutdown_event.is_set():
            time.sleep(1)

    except KeyboardInterrupt:
        logger.info("收到中断信号，正在关闭应用...")
        shutdown_event.set()
    except Exception:
        logger.error("应用启动失败！", exc_info=True)
    finally:
        cleanup()


if __name__ == '__main__':
    main()
