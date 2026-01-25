"""
JNSpider HTTP服务主入口
提供快递物流信息查询API服务
"""
import sys
import signal
import atexit

# 在导入其他模块前查找浏览器路径
from utils.browser_path import CHROME_EXECUTABLE_PATH, find_chrome_executable

# 初始化浏览器路径
find_chrome_executable()

# 打印调试信息
if CHROME_EXECUTABLE_PATH:
    print(f"[JNSpider] 已找到浏览器驱动: {CHROME_EXECUTABLE_PATH}")
else:
    print("[JNSpider] 警告: 未找到浏览器驱动，将使用 Playwright 默认路径")

# 现在导入其他模块（此时 CHROME_EXECUTABLE_PATH 已经设置）
from flask import Flask
from spider.query_manager import BrowserPool
from config import Config
from utils.startup import is_startup_enabled, add_to_startup
from api.routes import register_routes

# 创建Flask应用
app = Flask(__name__)

# 全局浏览器池实例
browser_pool = None


def init_browser_pool():
    """初始化浏览器池"""
    global browser_pool
    if browser_pool is None:
        print("正在创建浏览器池...")
        try:
            browser_pool = BrowserPool(headless=Config.HEADLESS)
            print("浏览器池创建完成（使用上下文管理器模式）")
        except Exception as e:
            error_msg = str(e)
            if "Executable doesn't exist" in error_msg or "playwright" in error_msg.lower():
                print("\n" + "="*60)
                print("错误：Playwright 浏览器驱动未安装")
                print("="*60)
                print("请运行以下命令安装浏览器驱动：")
                print("  venv\\Scripts\\python.exe -m playwright install chromium")
                print("或者：")
                print("  playwright install chromium")
                print("="*60 + "\n")
            raise


def close_browser_pool():
    """关闭浏览器池"""
    global browser_pool
    if browser_pool is not None:
        print("正在关闭浏览器池...")
        browser_pool.close()
        browser_pool = None
        print("浏览器池已关闭")


def signal_handler(signum, frame):
    """信号处理器，用于优雅关闭"""
    print("\n收到关闭信号，正在关闭服务...")
    close_browser_pool()
    sys.exit(0)


# 注册信号处理器
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# 注册退出时的清理函数
atexit.register(close_browser_pool)


def main():
    """主函数"""
    try:
        # 检查并添加到开机启动（如果还没有）
        if not is_startup_enabled():
            print("检测到未设置开机自启动，正在自动添加...")
            add_to_startup()
        else:
            print("开机自启动已启用")
        
        # 在服务启动前初始化浏览器池
        print("正在初始化浏览器池（2个专用页面：JD页面和百度页面）...")
        print(f"headless={Config.HEADLESS} (True=后台运行，False=显示浏览器窗口，调试时使用False)")
        
        # 确保浏览器路径已找到（在打包后的exe中，可能需要重新查找）
        global CHROME_EXECUTABLE_PATH
        if not CHROME_EXECUTABLE_PATH:
            print("重新查找浏览器驱动路径...")
            find_chrome_executable()
            if CHROME_EXECUTABLE_PATH:
                print(f"找到浏览器驱动: {CHROME_EXECUTABLE_PATH}")
            else:
                print("警告: 未找到浏览器驱动，将使用 Playwright 默认路径")
        
        global browser_pool
        try:
            browser_pool = BrowserPool(headless=Config.HEADLESS)
            print("浏览器池创建完成（使用上下文管理器模式）")
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
            raise  # 重新抛出异常，让外层异常处理捕获并统一暂停
        
        # 重新注册路由（此时 browser_pool 已初始化）
        register_routes(app, browser_pool)
        
        # 启动Flask服务
        print(f"\nJNSpider服务启动中...")
        print(f"服务地址: http://{Config.HOST}:{Config.PORT}")
        print(f"健康检查: http://{Config.HOST}:{Config.PORT}/health")
        print(f"单个查询: GET http://{Config.HOST}:{Config.PORT}/query?waybill=单号")
        print(f"批量查询: POST http://{Config.HOST}:{Config.PORT}/batch")
        print(f"自启动管理: GET/POST/DELETE http://{Config.HOST}:{Config.PORT}/startup")
        print("按 Ctrl+C 停止服务\n")
        
        app.run(
            host=Config.HOST,
            port=Config.PORT,
            debug=False,
            threaded=False  # 禁用多线程，避免Playwright线程切换问题
        )
    except KeyboardInterrupt:
        print("\n收到中断信号，正在关闭服务...")
    except Exception as e:
        print(f"\n{'='*60}")
        print("服务启动失败！")
        print(f"{'='*60}")
        print(f"错误信息: {e}")
        print(f"{'='*60}")
        import traceback
        traceback.print_exc()
        print(f"{'='*60}")
    finally:
        close_browser_pool()
        # 确保程序退出前暂停，让用户能看到错误信息
        print("\n按回车键关闭程序...")
        try:
            input()
        except:
            pass


if __name__ == '__main__':
    main()
