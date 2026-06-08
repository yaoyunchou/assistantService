"""
开发调试模式入口
简化版本，只启动Flask服务，支持热重载

不启动系统托盘、原生窗口等桌面应用功能

与生产模式 (main.py) 的区别：
  - 端口：开发 DEV_PORT(8886)  vs  生产 PORT(8887)
  - 热重载：开发 use_reloader=True  vs  生产 use_reloader=False
  - 页面标题：带「开发」标识
  - 日志级别：开发默认 DEBUG
"""
import os
import sys

# 在任何其他导入之前标记开发环境
os.environ.setdefault('APP_ENV', 'development')

from utils.win32_msvc_runtime import add_dll_search_paths_if_needed

add_dll_search_paths_if_needed()

import logging
from pathlib import Path

# 首先初始化日志系统
from utils.logger import init_logging, get_logger
from config import Config

# 设置开发环境
Config.APP_ENV = 'development'
Config.PORT = Config.DEV_PORT

# 将字符串日志级别转换为logging常量
LOG_LEVEL_MAP = {
    'DEBUG': logging.DEBUG,
    'INFO': logging.INFO,
    'WARNING': logging.WARNING,
    'ERROR': logging.ERROR,
    'CRITICAL': logging.CRITICAL
}
log_level = LOG_LEVEL_MAP.get(Config.LOG_LEVEL.upper(), logging.DEBUG)

# 初始化日志系统
init_logging(log_dir=Config.LOG_DIR, level=log_level)
logger = get_logger('DevMode')

# 在导入其他模块前查找浏览器路径
from utils.browser_path import CHROME_EXECUTABLE_PATH, find_chrome_executable

# 初始化浏览器路径
find_chrome_executable()

# 记录浏览器路径信息
if CHROME_EXECUTABLE_PATH:
    logger.info(f"已找到浏览器驱动: {CHROME_EXECUTABLE_PATH}")
else:
    logger.warning("未找到浏览器驱动，将使用 Playwright 默认路径")

# 导入Flask相关模块
from app import create_app, init_browser_pool, init_tools, setup_app


def main():
    """开发模式主函数"""
    logger.info("="*60)
    logger.info("开发调试模式启动")
    logger.info("支持文件修改热重载")
    logger.info("="*60)
    
    try:
        # 创建Flask应用
        logger.info("正在创建Flask应用...")
        app = create_app()
        
        # 初始化浏览器池
        logger.info("正在初始化浏览器池...")
        browser_pool = init_browser_pool()
        if browser_pool:
            logger.info("浏览器池初始化成功")
        else:
            logger.info("浏览器池未初始化（没有启用的模块需要浏览器）")
        
        # 初始化工具管理器
        logger.info("正在初始化工具管理器...")
        tool_manager = init_tools(browser_pool)
        
        # 注册路由
        setup_app(app, browser_pool, tool_manager)
        
        # 启动定时任务调度器
        # use_reloader=True 时 Flask 会启动两个进程，
        # WERKZEUG_RUN_MAIN='true' 只在实际服务的子进程中设置，
        # 调度器只在子进程中启动，避免重复执行。
        if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
            try:
                from scheduler import start_scheduler
                if start_scheduler():
                    logger.info("定时任务调度器已启动")
            except Exception as e:
                logger.warning(f"启动定时任务调度器失败: {e}")
            # 与 main 生产模式一致：开发服子进程内自动连接 Socket.IO 客户端
            try:
                from utils.websocket_client import get_websocket_client
                ws_result = get_websocket_client().start_if_enabled()
                if ws_result.get('skipped'):
                    logger.info('WebSocket 客户端未启用: %s', ws_result.get('reason', ''))
                elif ws_result.get('success'):
                    logger.info('WebSocket 客户端已启动: %s', ws_result.get('url', ''))
                else:
                    logger.warning('WebSocket 客户端启动失败: %s', ws_result.get('error', ''))
            except Exception as e:
                logger.warning('WebSocket 客户端启动异常: %s', e)

        logger.info("="*60)
        logger.info(f"服务地址: http://{Config.HOST}:{Config.PORT}")
        logger.info("按 Ctrl+C 停止服务")
        logger.info("="*60)
        
        # 启动Flask开发服务器（支持热重载）
        
        app.run(
            host=Config.HOST,
            port=Config.PORT,
            debug=True,           # 启用调试模式
            use_reloader=True,    # 启用热重载
            threaded=False        # 禁用多线程，避免Playwright跨线程问题
        )
        
    except KeyboardInterrupt:
        logger.info("\n收到中断信号，正在关闭...")
    except Exception as e:
        logger.error("="*60)
        logger.error("应用启动失败！", exc_info=True)
        logger.error("="*60)
    finally:
        # 关闭定时任务调度器
        try:
            from scheduler import shutdown_scheduler
            shutdown_scheduler()
        except Exception:
            pass
        # 清理资源
        if 'browser_pool' in locals() and browser_pool:
            logger.info("正在关闭浏览器池...")
            browser_pool.close()
        if 'tool_manager' in locals() and tool_manager:
            logger.info("正在清理工具...")
            tool_manager.cleanup_all()
        logger.info("开发模式已退出")


if __name__ == '__main__':
    main()
