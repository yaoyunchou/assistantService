"""
浏览器代理模块（单线程 + 持久化 context + 复用 page）

设计原则：
- 一个专用后台线程拥有 playwright、持久化 context 和一个长驻 page
- 所有浏览器操作通过 execute(fn) 提交到该线程串行执行
- 使用固定 browser_data 目录，Cookie/localStorage 跨次运行持久化
- 复用同一个 page，sessionStorage / JS 内存中的登录态在 page 存活期间保持
- context 或 page 失效时自动重建，调用方无感

为什么复用 page？
- 有些网站（如 iot.tqiot.com）把登录凭证存在 sessionStorage 或 JS 内存中
- 关闭 page 就丢失，必须复用同一个 page 才能保持登录
- 就像你平时用浏览器一样：始终在同一个标签页操作
"""
from playwright.sync_api import sync_playwright, BrowserContext, Page, Playwright
from typing import Dict, Optional, Callable, TypeVar, Any
from pathlib import Path
from utils.path_helper import get_browser_data_dir
from concurrent.futures import ThreadPoolExecutor
import random
import sys
import os
import threading
from contextlib import contextmanager
from datetime import datetime

T = TypeVar('T')


class BrowserTimeoutError(Exception):
    """浏览器操作超时异常"""
    pass


def get_chrome_executable_path():
    """获取 chrome.exe 可执行文件路径"""
    try:
        try:
            from utils.browser_path import CHROME_EXECUTABLE_PATH
            if CHROME_EXECUTABLE_PATH:
                return CHROME_EXECUTABLE_PATH
        except ImportError:
            pass
        env_path = os.environ.get('PLAYWRIGHT_CHROME_EXECUTABLE_PATH')
        if env_path and Path(env_path).exists():
            return env_path
        if '__main__' in sys.modules:
            main_module = sys.modules['__main__']
            if hasattr(main_module, 'CHROME_EXECUTABLE_PATH'):
                path = main_module.CHROME_EXECUTABLE_PATH
                if path:
                    return path
    except Exception as e:
        print(f"[BrowserPool] 获取浏览器路径时出错: {e}")
    return None


class BrowserPool:
    """
    浏览器代理（单线程 + 持久化 context + 复用 page）

    用法：
        # 推荐：execute() —— 提交任务，拿结果，不用管线程
        result = pool.execute(lambda page: my_function(page), timeout=60)

        # 兼容：get_page() —— 仅在浏览器线程内使用
        with pool.get_page() as page:
            page.goto(...)
    """

    def __init__(self, headless: bool = True, idle_timeout: int = 600, max_instances: int = 5):
        self.headless = headless
        self._shared_user_data_dir = get_browser_data_dir(app_name='JNTools')
        print(f"[BrowserPool] 浏览器缓存目录（持久化）: {self._shared_user_data_dir.resolve()}")

        # 专用线程（max_workers=1 保证所有 playwright 操作在同一线程）
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="playwright")

        # 以下变量只在 _executor 线程上操作，无需额外锁
        self._playwright: Optional[Playwright] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None  # 长驻复用的 page
        self._busy: bool = False  # 是否正在执行任务

    @property
    def _initialized(self):
        return True

    # ─── 浏览器生命周期（只在 playwright 线程上调用） ─────────────

    def _build_context_args(self) -> dict:
        chrome_executable_path = get_chrome_executable_path()
        user_data_dir = self._shared_user_data_dir
        user_data_dir.mkdir(parents=True, exist_ok=True)
        args = {
            'user_data_dir': str(user_data_dir),
            'headless': self.headless,
            'viewport': {'width': 1920, 'height': 1080},
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'locale': 'zh-CN',
            'timezone_id': 'Asia/Shanghai',
            'permissions': ['geolocation', 'notifications'],
            'geolocation': {
                'latitude': 39.9042 + random.uniform(-0.1, 0.1),
                'longitude': 116.4074 + random.uniform(-0.1, 0.1),
            },
            'color_scheme': 'light',
            'ignore_https_errors': True,
            'extra_http_headers': {
                'Accept-Language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
                'Accept-Encoding': 'gzip, deflate, br, zstd',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            },
            'args': [
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-web-security',
                '--disable-features=VizDisplayCompositor',
                '--disable-site-isolation-trials',
                '--disable-infobars',
                '--disable-notifications',
                '--disable-popup-blocking',
                '--start-maximized',
            ],
        }
        if chrome_executable_path:
            chrome_path = Path(chrome_executable_path)
            if chrome_path.exists() and chrome_path.is_file():
                args['executable_path'] = str(chrome_path.absolute())
        return args

    def _setup_context(self, context: BrowserContext) -> None:
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = { runtime: {}, loadTimes: function() {}, csi: function() {}, app: {} };
        """)

    def _is_context_alive(self) -> bool:
        if self._context is None:
            return False
        try:
            _ = self._context.pages
            return True
        except Exception:
            return False

    def _is_page_alive(self) -> bool:
        """检查长驻 page 是否可用"""
        if self._page is None:
            return False
        try:
            return not self._page.is_closed()
        except Exception:
            return False

    def _ensure_browser(self) -> None:
        """确保 playwright + context 可用"""
        if self._playwright is None:
            self._playwright = sync_playwright().start()
            print("[BrowserPool] Playwright 已启动")

        if not self._is_context_alive():
            if self._context is not None:
                try:
                    self._context.close()
                except Exception:
                    pass
                self._context = None
                self._page = None  # context 没了，page 也没了

            try:
                context = self._playwright.chromium.launch_persistent_context(**self._build_context_args())
            except Exception as e:
                print(f"[BrowserPool] 创建 context 失败（{e}），完全重建 playwright...")
                try:
                    self._playwright.stop()
                except Exception:
                    pass
                self._playwright = None
                self._playwright = sync_playwright().start()
                context = self._playwright.chromium.launch_persistent_context(**self._build_context_args())

            self._setup_context(context)
            self._context = context
            print("[BrowserPool] 持久化 context 已就绪（登录态与缓存共享）")

    def _ensure_page(self) -> Page:
        """确保有一个可用的 page（复用长驻 page）"""
        self._ensure_browser()
        if self._is_page_alive():
            return self._page

        # 创建新 page（首次 / 旧 page 已损坏 / 浏览器被手动关闭）
        try:
            self._page = self._context.new_page()
        except Exception as e:
            # new_page 失败说明 context 也坏了（浏览器被关闭），需要整个重建
            print(f"[BrowserPool] new_page 失败（{e}），重建 context...")
            self._page = None
            self._context = None
            self._ensure_browser()
            self._page = self._context.new_page()

        print("[BrowserPool] 已创建页面（长驻复用，登录态在页面存活期间保持）")
        return self._page

    # ─── 核心 API ──────────────────────────────────────────────

    def _is_page_error(self, e: Exception) -> bool:
        """判断异常是否是 page/context/browser 已关闭的错误"""
        err_str = str(e).lower()
        return (
            'has been closed' in err_str
            or 'target closed' in err_str
            or 'browser has been closed' in err_str
            or 'navigation failed because page was closed' in err_str
            or 'session closed' in err_str
            or isinstance(e, type) and 'TargetClosedError' in type(e).__name__
        )

    def _reset_all(self):
        """清除 page 和 context 引用，下次 _ensure_* 会重建"""
        self._page = None
        self._context = None

    def execute(self, fn: Callable[[Page], T], timeout: float = 60.0) -> T:
        """
        在浏览器专用线程上执行操作（推荐方式）。

        page 会被复用，不会每次创建/销毁。登录态（包括 sessionStorage）
        在 page 存活期间保持，只需登录一次。

        如果 page/context/浏览器 在任何环节失效（如手动关闭了浏览器窗口），
        会自动重建并重试一次，保证稳定性。

        Args:
            fn: 接收 Page 参数的函数
            timeout: 超时时间（秒）
        Returns:
            fn 的返回值
        Raises:
            BrowserTimeoutError: 超时
        """
        def _task():
            self._busy = True
            try:
                # 尝试获取 page 并执行
                page = self._ensure_page()
                return fn(page)
            except Exception as e:
                if not self._is_page_error(e):
                    raise  # 非浏览器关闭类错误，直接抛出

                # ── 浏览器/page/context 失效 → 全部重建并重试一次 ──
                print(f"[BrowserPool] 检测到浏览器失效（{type(e).__name__}），正在自动重建...")
                self._reset_all()
                try:
                    page = self._ensure_page()
                    print("[BrowserPool] 重建成功，正在重试任务...")
                    return fn(page)
                except Exception as retry_err:
                    print(f"[BrowserPool] 重试也失败了: {retry_err}")
                    if self._is_page_error(retry_err):
                        self._reset_all()
                    raise
            finally:
                self._busy = False

        try:
            future = self._executor.submit(_task)
            return future.result(timeout=timeout)
        except BrowserTimeoutError:
            raise
        except TimeoutError:
            raise BrowserTimeoutError(f"浏览器操作超时（{timeout}秒）")

    @contextmanager
    def get_page(self, timeout: float = 60.0):
        """
        获取页面（向后兼容，复用长驻 page）。
        仅应在浏览器线程内调用。
        如果 page 失效会自动重建（但不会自动重试调用方的逻辑）。
        """
        page = self._ensure_page()
        self._busy = True
        try:
            yield page
        except Exception as e:
            if self._is_page_error(e):
                print(f"[BrowserPool] get_page 中浏览器失效，已标记重建")
                self._reset_all()
            raise
        finally:
            self._busy = False

    # ─── 关闭与状态 ────────────────────────────────────────────

    def close(self):
        """关闭浏览器，释放所有资源"""
        print("[BrowserPool] 开始关闭...")

        def _close():
            self._page = None
            if self._context is not None:
                try:
                    self._context.close()
                except Exception:
                    pass
                self._context = None
            if self._playwright is not None:
                try:
                    self._playwright.stop()
                except Exception:
                    pass
                self._playwright = None

        try:
            self._executor.submit(_close).result(timeout=10)
        except Exception as e:
            print(f"[BrowserPool] 关闭时出错（已忽略）: {e}")

        self._executor.shutdown(wait=False)
        print("[BrowserPool] 已关闭")

    def get_pool_status(self) -> Dict:
        has_context = self._context is not None
        has_page = self._is_page_alive()
        return {
            'total': 1 if has_context else 0,
            'busy': 1 if self._busy else 0,
            'idle': 1 if has_context and not self._busy else 0,
            'waiting': 0,
            'max_instances': 1,
            'page_alive': has_page,
            'instances': [{
                'index': 0,
                'is_busy': self._busy,
                'idle_seconds': 0,
                'thread_id': None,
                'should_close': False,
            }] if has_context else [],
            'idle_timeout': 0,
        }
