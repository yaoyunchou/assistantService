"""
查询管理器模块 - 重试机制和浏览器实例管理（单线程顺序处理）
"""
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page
from typing import List, Dict, Optional
from spider.logistics_query import get_logistics_info
from config import Config
from pathlib import Path
import random
import time
import sys
import os
import threading
from config import Config

# 获取 chrome.exe 路径（从 utils.browser_path 模块获取）
def get_chrome_executable_path():
    """获取 chrome.exe 可执行文件路径"""
    try:
        # 方法1：直接从 utils.browser_path 模块获取（推荐，线程安全）
        # 这个模块在主线程中已经初始化了 CHROME_EXECUTABLE_PATH
        try:
            from utils.browser_path import CHROME_EXECUTABLE_PATH
            if CHROME_EXECUTABLE_PATH:
                print(f"[BrowserPool] 使用浏览器路径（utils.browser_path）: {CHROME_EXECUTABLE_PATH}")
                return CHROME_EXECUTABLE_PATH
        except ImportError:
            pass
        
        # 方法2：尝试从环境变量获取（如果设置了）
        env_path = os.environ.get('PLAYWRIGHT_CHROME_EXECUTABLE_PATH')
        if env_path and Path(env_path).exists():
            print(f"[BrowserPool] 使用环境变量指定的浏览器路径: {env_path}")
            return env_path
        
        # 方法3：尝试从 __main__ 模块获取（打包后的exe，如果设置了）
        if '__main__' in sys.modules:
            main_module = sys.modules['__main__']
            if hasattr(main_module, 'CHROME_EXECUTABLE_PATH'):
                path = main_module.CHROME_EXECUTABLE_PATH
                if path:
                    print(f"[BrowserPool] 使用指定的浏览器路径（__main__）: {path}")
                    return path
                    
    except Exception as e:
        print(f"[BrowserPool] 获取浏览器路径时出错: {e}")
        import traceback
        traceback.print_exc()
    
    print("[BrowserPool] 警告: 未找到指定的浏览器路径，将使用 Playwright 默认路径")
    return None


class BrowserPool:
    """浏览器实例池（维护2个专用页面：JD和百度）"""
    
    def __init__(self, headless: bool = True):
        self.headless = headless
        self.playwright = None
        self.browser = None
        self.context = None
        self.jd_page = None  # JD 运单号专用页面（快递100）
        self.baidu_page = None  # 其他运单号专用页面（百度搜索）
        self._initialized = False
        self._baidu_page_initialized = False  # 百度页面是否已初始化（是否已访问过搜索页面）
        self._last_used_time = None  # 最后使用时间
        self._idle_timer = None  # 空闲定时器
        self._idle_timeout = getattr(Config, 'BROWSER_IDLE_TIMEOUT', 300)  # 空闲超时时间（秒）
        self._lock = threading.Lock()  # 线程锁
    
    def initialize(self):
        """初始化浏览器和2个专用页面"""
        if self._initialized:
            return
        
        self.playwright = sync_playwright().start()
        
        # 获取 chrome.exe 路径
        chrome_executable_path = get_chrome_executable_path()
        
        # 准备 launch 参数
        launch_args = {
            'headless': self.headless,
            'args': [
                '--disable-blink-features=AutomationControlled',  # 隐藏自动化特征
                '--disable-dev-shm-usage',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-web-security',  # 禁用CORS检查，解决跨域资源加载问题
                '--disable-features=VizDisplayCompositor',  # 禁用某些可能导致问题的特性
                '--disable-site-isolation-trials',  # 禁用站点隔离，允许跨域资源加载
                '--disable-infobars',  # 禁用信息栏
                '--disable-notifications',  # 禁用通知
                '--disable-popup-blocking',  # 禁用弹窗阻止
                '--start-maximized',  # 启动时最大化
            ]
        }
        
        # 如果指定了 chrome.exe 路径，使用它
        if chrome_executable_path:
            from pathlib import Path
            chrome_path = Path(chrome_executable_path)
            if chrome_path.exists():
                launch_args['executable_path'] = str(chrome_path.absolute())
                print(f"[BrowserPool] 启动浏览器，使用路径: {launch_args['executable_path']}")
            else:
                print(f"[BrowserPool] 警告: 指定的浏览器路径不存在: {chrome_executable_path}")
                print(f"[BrowserPool] 将使用 Playwright 默认路径")
        else:
            print("[BrowserPool] 未指定浏览器路径，使用 Playwright 默认路径")
        
        # 只创建1个浏览器和1个上下文
        self.browser = self.playwright.chromium.launch(**launch_args)
        
        # 随机化 viewport 尺寸（模拟不同屏幕）
        viewport_widths = [1920, 1366, 1440, 1536, 1600]
        viewport_heights = [1080, 768, 900, 864, 1024]
        viewport_width = random.choice(viewport_widths)
        viewport_height = random.choice(viewport_heights)
        
        # 使用更新的 User-Agent（Chrome 最新版本）
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36',
        ]
        user_agent = random.choice(user_agents)
        
        # 创建上下文时设置更真实的浏览器指纹
        self.context = self.browser.new_context(
            viewport={'width': viewport_width, 'height': viewport_height},
            user_agent=user_agent,
            locale='zh-CN',
            timezone_id='Asia/Shanghai',
            # 添加更多浏览器特征
            permissions=['geolocation', 'notifications'],
            geolocation={'latitude': 39.9042 + random.uniform(-0.1, 0.1), 'longitude': 116.4074 + random.uniform(-0.1, 0.1)},  # 北京坐标（稍微随机化）
            color_scheme='light',
            # 忽略 HTTPS 错误
            ignore_https_errors=True,
            # 添加额外的 HTTP 头
            extra_http_headers={
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                'Accept-Language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
                'Accept-Encoding': 'gzip, deflate, br, zstd',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1',
                'Cache-Control': 'max-age=0',
            },
        )
        
        # 反爬虫措施: 注入脚本隐藏 webdriver 特征和增强浏览器指纹
        self.context.add_init_script("""
            // 1. 隐藏 webdriver 特征
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            
            // 2. 覆盖 plugins 属性（模拟真实浏览器插件）
            Object.defineProperty(navigator, 'plugins', {
                get: () => {
                    return [
                        {name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer'},
                        {name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai'},
                        {name: 'Native Client', filename: 'internal-nacl-plugin'}
                    ];
                }
            });
            
            // 3. 覆盖 languages 属性
            Object.defineProperty(navigator, 'languages', {
                get: () => ['zh-CN', 'zh', 'en-US', 'en']
            });
            
            // 4. 覆盖 chrome 属性（完整的 Chrome 对象）
            window.chrome = {
                runtime: {},
                loadTimes: function() {},
                csi: function() {},
                app: {}
            };
            
            // 5. 覆盖 permissions 属性
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
            
            // 6. 覆盖 platform 属性
            Object.defineProperty(navigator, 'platform', {
                get: () => 'Win32'
            });
            
            // 7. 覆盖 hardwareConcurrency（CPU核心数）
            Object.defineProperty(navigator, 'hardwareConcurrency', {
                get: () => 8
            });
            
            // 8. 覆盖 deviceMemory（内存大小，GB）
            Object.defineProperty(navigator, 'deviceMemory', {
                get: () => 8
            });
            
            // 9. 覆盖 connection（网络连接信息）
            Object.defineProperty(navigator, 'connection', {
                get: () => ({
                    effectiveType: '4g',
                    rtt: 50,
                    downlink: 10,
                    saveData: false
                })
            });
            
            // 10. 覆盖 getBattery（电池信息，桌面浏览器返回 null）
            navigator.getBattery = () => Promise.resolve({
                charging: true,
                chargingTime: 0,
                dischargingTime: Infinity,
                level: 1
            });
            
            // 11. 覆盖 vendor 和 vendorSub
            Object.defineProperty(navigator, 'vendor', {
                get: () => 'Google Inc.'
            });
            
            // 12. 确保 XMLHttpRequest 和 fetch 正常工作
            const OriginalXHR = window.XMLHttpRequest;
            window.XMLHttpRequest = function() {
                const xhr = new OriginalXHR();
                return xhr;
            };
            
            const OriginalFetch = window.fetch;
            window.fetch = function(...args) {
                return OriginalFetch.apply(this, args);
            };
            
            // 13. 覆盖 toString 方法，防止检测
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {
                if (parameter === 37445) {
                    return 'Intel Inc.';
                }
                if (parameter === 37446) {
                    return 'Intel Iris OpenGL Engine';
                }
                return getParameter.call(this, parameter);
            };
            
            // 14. 覆盖 canvas 指纹
            const toBlob = HTMLCanvasElement.prototype.toBlob;
            const toDataURL = HTMLCanvasElement.prototype.toDataURL;
            const getImageData = CanvasRenderingContext2D.prototype.getImageData;
            
            // 15. 忽略 CORS 错误和字体加载错误（在控制台）
            const originalError = console.error;
            const originalWarn = console.warn;
            const originalLog = console.log;
            
            console.error = function(...args) {
                const msg = args[0] ? String(args[0]).toLowerCase() : '';
                if (msg.includes('cors') || 
                    msg.includes('blocked by cors policy') ||
                    msg.includes('font') ||
                    msg.includes('ttf') ||
                    msg.includes('woff') ||
                    msg.includes('preflight') ||
                    msg.includes('automation') ||
                    msg.includes('webdriver')) {
                    return;
                }
                originalError.apply(console, args);
            };
            
            console.warn = function(...args) {
                const msg = args[0] ? String(args[0]).toLowerCase() : '';
                if (msg.includes('cors') || 
                    msg.includes('font') ||
                    msg.includes('ttf') ||
                    msg.includes('woff') ||
                    msg.includes('automation') ||
                    msg.includes('webdriver')) {
                    return;
                }
                originalWarn.apply(console, args);
            };
            
            // 16. 覆盖 Notification 权限
            if (window.Notification) {
                Object.defineProperty(Notification, 'permission', {
                    get: () => 'default'
                });
            }
            
            // 17. 添加真实的浏览器特征
            Object.defineProperty(navigator, 'maxTouchPoints', {
                get: () => 0
            });
            
            // 18. 覆盖 screen 属性
            Object.defineProperty(screen, 'availWidth', {
                get: () => window.innerWidth || 1920
            });
            Object.defineProperty(screen, 'availHeight', {
                get: () => window.innerHeight || 1080
            });
        """)
        
        # 浏览器和上下文已创建成功，立即标记为已初始化
        # 这样即使后续步骤失败，浏览器池仍然可以使用
        self._initialized = True
        self._update_last_used_time()
        self._start_idle_timer()
        print("浏览器和上下文已创建，浏览器池已初始化")
        
        # 创建2个专用页面
        try:
            self.jd_page = self._create_page_with_listeners()
            self.baidu_page = self._create_page_with_listeners()
            print("已创建2个专用页面（JD页面和百度页面）")
        except Exception as e:
            print(f"创建页面时出错: {e}")
            import traceback
            traceback.print_exc()
            print("警告: 页面创建失败，但浏览器池已初始化，可以尝试创建新页面")
            return
        
        # 初始化百度页面（访问首页和搜索页面，建立会话）
        print("正在初始化百度页面（访问首页和搜索页面）...")
        try:
            self._initialize_baidu_page()
        except Exception as e:
            print(f"初始化百度页面时出错: {e}")
            import traceback
            traceback.print_exc()
            print("警告: 百度页面初始化失败，但浏览器池已初始化，可以尝试使用")
        
        print("浏览器池初始化完成")
    
    def _initialize_baidu_page(self):
        """初始化百度页面：访问首页和搜索页面，建立会话"""
        if not self.baidu_page:
            return
        
        try:
            # 反爬虫措施1: 设置更真实的浏览器指纹
            # 添加额外的 HTTP 头，模拟真实浏览器
            self.baidu_page.set_extra_http_headers({
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            })
            
            # 反爬虫措施2: 先访问百度首页，建立会话（更真实的访问流程）
            print(f"[百度查询] 正在访问百度首页建立会话...")
            try:
                self.baidu_page.goto('https://www.baidu.com', wait_until='domcontentloaded', timeout=2000)
                # 模拟鼠标移动和点击（更真实的交互）
                try:
                    # 随机移动鼠标
                    for _ in range(random.randint(1, 2)):
                        x = random.randint(100, 800)
                        y = random.randint(100, 600)
                        self.baidu_page.mouse.move(x, y)
                        time.sleep(random.uniform(0.2, 0.5))
                    
                    # 模拟点击搜索框（但不输入）
                    try:
                        search_box = self.baidu_page.locator('#kw').first
                        if search_box.count() > 0:
                            search_box.hover()
                            time.sleep(random.uniform(0.3, 0.6))
                    except:
                        pass
                except:
                    pass
                    
            except Exception as e:
                print(f"[百度查询] 首页加载警告: {e}，尝试继续...")
                time.sleep(random.uniform(2, 3))
            
            
            # 构建百度搜索URL（不包含订单号，只访问搜索页面）
            base_url = "https://www.baidu.com/s?ie=utf-8&f=8&rsv_bp=1&rsv_idx=1&tn=baidu&wd=百度快递查詢"
            
            # 打开搜索页面（使用更真实的导航方式）
            print(f"[百度查询] 正在打开搜索页面...")
            
            # 先检查是否有 hitAntibot 拦截
            try:
                response = self.baidu_page.goto(base_url, wait_until='domcontentloaded', timeout=30000)
                
                # 检查响应内容是否包含 hitAntibot
                try:
                    content = self.baidu_page.content()
                    if 'hitAntibot' in content or '"hitAntibot":"1"' in content:
                        print(f"[百度查询] 检测到反爬虫拦截，等待更长时间后重试...")
                        time.sleep(random.uniform(1, 2))  # 等待更长时间
                        
                        # 尝试刷新页面
                        self.baidu_page.reload(wait_until='domcontentloaded', timeout=20000)
                        time.sleep(random.uniform(1, 2))
                        
                        # 再次检查
                        content = self.baidu_page.content()
                        if 'hitAntibot' in content or '"hitAntibot":"1"' in content:
                            print(f"[百度查询] 仍然被拦截，初始化失败")
                            return
                except:
                    pass
                    
                print(f"[百度查询] 搜索页面加载完成")
            except Exception as e:
                print(f"[百度查询] 页面加载警告: {e}，尝试继续...")
                time.sleep(random.uniform(2, 3))
            
            # 等待页面 JavaScript 执行完成（增加延迟）
            print(f"[百度查询] 等待页面 JavaScript 初始化...")
            time.sleep(random.uniform(3, 5))  # 增加延迟，让页面完全加载
            
            # 模拟真实用户行为：滚动和鼠标移动
            try:
                # 缓慢滚动页面
                for scroll_pos in [200, 400, 600, 300, 0]:
                    self.baidu_page.evaluate(f'window.scrollTo(0, {scroll_pos})')
                    time.sleep(random.uniform(0.3, 0.6))
                
                # 随机鼠标移动
                for _ in range(random.randint(2, 4)):
                    x = random.randint(200, 1000)
                    y = random.randint(200, 700)
                    self.baidu_page.mouse.move(x, y)
                    time.sleep(random.uniform(0.2, 0.4))
            except:
                pass
            
            time.sleep(random.uniform(1, 2))  # 额外延迟
            
            # 标记百度页面已初始化
            self._baidu_page_initialized = True
            print("[百度查询] 百度页面初始化完成")
            
        except Exception as e:
            print(f"[百度查询] 初始化过程中出现错误: {e}")
            import traceback
            traceback.print_exc()
    
    def _create_page_with_listeners(self) -> Page:
        """创建页面并设置监听器"""
        page = self.context.new_page()
        
        # 监听控制台消息，过滤 CORS 错误、字体加载错误和资源加载失败
        def handle_console(msg):
            msg_text = msg.text.lower()
            if any(keyword in msg_text for keyword in [
                'cors', 
                'blocked by cors policy',
                'font',
                'ttf',
                'woff',
                'preflight request',
                'access control check',
                'net::err_failed',
                'failed to load resource',
                'all_async_search',
                'bdstatic.com',
                'pss.bdstatic.com'
            ]):
                return
        
        page.on('console', handle_console)
        
        # 监听页面错误
        def handle_page_error(error):
            error_text = error.message.lower() if hasattr(error, 'message') else str(error).lower()
            if any(keyword in error_text for keyword in [
                'cors',
                'blocked by cors policy',
                'font',
                'ttf',
                'woff',
                'preflight',
                'net::err_failed',
                'failed to load',
                'bdstatic.com'
            ]):
                return
        
        page.on('pageerror', handle_page_error)
        
        # 监听请求失败事件
        def handle_request_failed(request):
            url = request.url.lower()
            if 'all_async_search' in url or 'search' in url:
                print(f"[警告] 关键资源加载失败: {request.url}，可能会影响搜索功能")
        
        page.on('requestfailed', handle_request_failed)
        
        return page
    
    def get_page_for_waybill(self, waybill_number: str) -> tuple[Optional[Page], bool]:
        """
        根据运单号类型返回对应的页面实例和是否首次使用标志
        
        Args:
            waybill_number: 运单号
            
        Returns:
            (页面实例, 是否首次使用)，SF运单号返回(None, False)
            注意：百度页面已在初始化时完成初始化，所以 is_first_time 始终为 False
        """
        if not self._initialized:
            # 尝试延迟初始化
            if not self.ensure_initialized():
                return None, False
        
        # 更新最后使用时间
        self._update_last_used_time()
        
        waybill_upper = waybill_number.upper()
        
        if 'SF' in waybill_upper:
            # SF 不需要查询
            return None, False
        elif waybill_upper.startswith('JD'):
            # JD 运单号使用快递100页面
            return self.jd_page, False
        else:
            # 其他运单号使用百度搜索页面
            # 百度页面已在初始化时完成初始化，所以 is_first_time 始终为 False
            return self.baidu_page, False
    
    def get_page(self) -> Optional[Page]:
        """
        从池中获取一个页面实例（轮询方式）
        保留此方法以保持向后兼容，但建议使用 get_page_for_waybill
        """
        if not self._initialized:
            return None
        
        # 默认返回百度页面（向后兼容）
        return self.baidu_page
    
    def _update_last_used_time(self):
        """更新最后使用时间"""
        with self._lock:
            self._last_used_time = time.time()
    
    def _start_idle_timer(self):
        """启动空闲定时器"""
        self._stop_idle_timer()
        
        def check_idle():
            with self._lock:
                if not self._initialized:
                    return
                
                if self._last_used_time is None:
                    return
                
                idle_time = time.time() - self._last_used_time
                if idle_time >= self._idle_timeout:
                    print(f"[BrowserPool] 浏览器空闲超过 {self._idle_timeout} 秒，自动关闭")
                    self.close()
                else:
                    # 继续检查
                    self._idle_timer = threading.Timer(60.0, check_idle)  # 每60秒检查一次
                    self._idle_timer.daemon = True
                    self._idle_timer.start()
        
        self._idle_timer = threading.Timer(60.0, check_idle)
        self._idle_timer.daemon = True
        self._idle_timer.start()
    
    def _stop_idle_timer(self):
        """停止空闲定时器"""
        if self._idle_timer:
            self._idle_timer.cancel()
            self._idle_timer = None
    
    def ensure_initialized(self):
        """
        确保浏览器已初始化（延迟初始化）
        
        Returns:
            是否成功初始化
        """
        if self._initialized:
            self._update_last_used_time()
            return True
        
        try:
            self.initialize()
            return True
        except Exception as e:
            print(f"[BrowserPool] 延迟初始化失败: {e}")
            return False
    
    def close(self):
        """关闭浏览器实例"""
        self._stop_idle_timer()
        
        if self.browser:
            try:
                self.browser.close()
            except:
                pass
        
        if self.playwright:
            try:
                self.playwright.stop()
            except:
                pass
        
        self._initialized = False
        self.jd_page = None
        self.baidu_page = None
        self._last_used_time = None
        print("已关闭浏览器实例和所有页面")


def query_with_retry(
    waybill_number: str,
    browser_pool: Optional[BrowserPool] = None,
    max_retry: int = 3
) -> Optional[Dict]:
    """
    带重试机制的物流信息查询（单线程版本）
    
    Args:
        waybill_number: 运单号
        browser_pool: 浏览器实例池
        max_retry: 最大重试次数
        
    Returns:
        物流信息字典，失败返回 None
    """
    # 如果包含SF就是顺丰的单， SF的单不用查询，没有办法查，直接返回空
    if 'SF' in waybill_number.upper():
        return {
            'success': True,
            'data': []
        }
    
    # 根据运单号类型获取对应的页面实例
    if browser_pool is None:
        return {
            'success': False,
            'error': '需要浏览器实例池（所有运单号都需要通过浏览器实例进行AJAX请求）'
        }
    
    page, is_first_time = browser_pool.get_page_for_waybill(waybill_number)
    if page is None:
        # SF 运单号会返回 None，这是正常的
        if 'SF' in waybill_number.upper():
            return {
                'success': True,
                'data': []
            }
        return {
            'success': False,
            'error': '无法获取浏览器实例'
        }
    
    # 重试查询
    for attempt in range(max_retry):
        try:
            # 获取物流信息
            result = get_logistics_info(page, waybill_number, is_first_time=is_first_time)
            # 第一次查询后，后续查询不再需要初始化
            is_first_time = False
            
            if result and result.get('success'):
                return result
            
            # 如果失败但不是最后一次尝试，继续重试
            if attempt < max_retry - 1:
                print(f"运单号 {waybill_number} 第 {attempt + 1} 次查询失败，重试中...")
                continue
            else:
                # 最后一次尝试失败
                return result
                
        except Exception as e:
            print(f"运单号 {waybill_number} 查询异常: {e}")
            if attempt < max_retry - 1:
                continue
            else:
                return {
                    'success': False,
                    'error': f'查询异常：{str(e)}'
                }
    
    return None


def batch_query_waybill_numbers(
    waybill_numbers: List[str],
    browser_pool: Optional[BrowserPool] = None,
    max_retry: int = 3
) -> Dict[str, Optional[Dict]]:
    """
    批量查询物流信息（顺序处理，使用浏览器实例池）
    
    Args:
        waybill_numbers: 运单号列表
        browser_pool: 浏览器实例池
        max_retry: 最大重试次数
        
    Returns:
        字典：{运单号: 物流信息}
    """
    results = {}
    
    # 初始化浏览器池（如果需要）
    if browser_pool and not browser_pool._initialized:
        browser_pool.initialize()
    
    # 顺序处理每个运单号
    total = len(waybill_numbers)
    for idx, waybill_number in enumerate(waybill_numbers, 1):
        try:
            #  查询物流信息
            result = query_with_retry(waybill_number, browser_pool, max_retry)
            # 将结果保存到字典中
            results[waybill_number] = result
            
            # 显示进度
            if idx % 10 == 0 or idx == total:
                success_count = sum(1 for r in results.values() if r and r.get('success'))
                print(f"进度: {idx}/{total}，成功: {success_count}")
                
        except Exception as e:
            print(f"运单号 {waybill_number} 查询失败: {e}")
            import traceback
            traceback.print_exc()
            results[waybill_number] = {
                'success': False,
                'error': f'查询异常：{str(e)}'
            }
    
    return results

