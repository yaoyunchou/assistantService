"""
浏览器池管理模块
提供线程安全的浏览器实例池，支持动态扩展和自动清理
"""
from playwright.sync_api import sync_playwright, BrowserContext, Page, Playwright
from typing import List, Dict, Optional
from pathlib import Path
from utils.path_helper import get_safe_data_path
import random
import time
import sys
import os
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime


class BrowserTimeoutError(Exception):
    """浏览器操作超时异常"""
    pass

# 获取 chrome.exe 路径（从 utils.browser_path 模块获取）
def get_chrome_executable_path():
    """获取 chrome.exe 可执行文件路径"""
    try:
        # 方法1：直接从 utils.browser_path 模块获取（推荐，线程安全）
        try:
            from utils.browser_path import CHROME_EXECUTABLE_PATH
            if CHROME_EXECUTABLE_PATH:
                return CHROME_EXECUTABLE_PATH
        except ImportError:
            pass
        
        # 方法2：尝试从环境变量获取（如果设置了）
        env_path = os.environ.get('PLAYWRIGHT_CHROME_EXECUTABLE_PATH')
        if env_path and Path(env_path).exists():
            return env_path
        
        # 方法3：尝试从 __main__ 模块获取（打包后的exe，如果设置了）
        if '__main__' in sys.modules:
            main_module = sys.modules['__main__']
            if hasattr(main_module, 'CHROME_EXECUTABLE_PATH'):
                path = main_module.CHROME_EXECUTABLE_PATH
                if path:
                    return path
                    
    except Exception as e:
        print(f"[BrowserPool] 获取浏览器路径时出错: {e}")
        import traceback
        traceback.print_exc()
        return None
    
    return None


@dataclass
class BrowserInstance:
    """浏览器实例"""
    playwright: Playwright
    context: BrowserContext
    page: Page
    is_busy: bool = False
    last_used_time: datetime = None
    thread_id: int = None
    timeout_timer: threading.Timer = None  # 超时定时器
    is_timeout: bool = False  # 是否超时
    should_close: bool = False  # 是否应该关闭（由清理线程标记）
    
    def __post_init__(self):
        if self.last_used_time is None:
            self.last_used_time = datetime.now()


class BrowserPool:
    """
    浏览器实例池（智能复用模式）
    
    特性：
    - 浏览器使用完后标记为空闲状态，可被其他请求复用
    - 空闲超过10分钟的浏览器自动关闭释放资源
    - 所有浏览器共享同一个持久化用户数据目录，确保登录状态共享
    - 线程安全，支持并发访问
    """
    
    def __init__(self, headless: bool = True, idle_timeout: int = 600, max_instances: int = 5):
        """
        初始化浏览器池
        
        Args:
            headless: 是否使用无头模式
            idle_timeout: 空闲超时时间（秒），默认600秒（10分钟）
            max_instances: 最大浏览器实例数，默认5个
        """
        self.headless = headless
        self.idle_timeout = idle_timeout
        self.max_instances = max_instances
        
        # 渐进式扩展阈值配置
        # 格式：{实例数: 触发阈值}
        self.scale_thresholds = {
            2: 5,    # 排队 > 5 个，扩展到2个实例
            3: 20,   # 排队 > 20 个，扩展到3个实例
            4: 30,   # 排队 > 30 个，扩展到4个实例
            5: 40    # 排队 > 40 个，扩展到5个实例
        }
        
        # 共享的用户数据目录（所有浏览器使用同一个目录，确保登录状态共享）
        self._shared_user_data_dir = get_safe_data_path('browser_data', app_name='JNTools')
        
        # 浏览器实例池
        self._instances: List[BrowserInstance] = []
        
        # 池锁（保护实例列表）
        self._pool_lock = threading.Lock()
        
        # 用户数据目录锁（确保同一时间只有一个浏览器在创建）
        # Playwright 不允许多个实例同时使用同一个用户数据目录
        self._user_data_dir_lock = threading.Lock()
        
        # 等待队列计数（用于动态扩展决策）
        self._waiting_count = 0
        
        # 启动清理线程
        self._cleanup_thread = None
        self._cleanup_running = False
        self._start_cleanup_thread()
    
    @property
    def _initialized(self):
        """兼容性属性：浏览器池始终处于"已初始化"状态"""
        return True
    
    def _start_cleanup_thread(self):
        """启动后台清理线程"""
        if self._cleanup_thread is None or not self._cleanup_thread.is_alive():
            self._cleanup_running = True
            self._cleanup_thread = threading.Thread(
                target=self._cleanup_idle_browsers,
                name="BrowserPoolCleanup",
                daemon=True
            )
            self._cleanup_thread.start()
            print("[BrowserPool] 清理线程已启动")
    
    def _cleanup_idle_browsers(self):
        """后台清理空闲超时的浏览器（只标记，不直接关闭）"""
        while self._cleanup_running:
            try:
                time.sleep(30)  # 每30秒检查一次
                
                now = datetime.now()
                marked_count = 0
                
                with self._pool_lock:
                    for instance in self._instances:
                        # 检查是否空闲且超时
                        if not instance.is_busy and not instance.should_close:
                            idle_time = (now - instance.last_used_time).total_seconds()
                            if idle_time > self.idle_timeout:
                                # 只标记为待关闭，不直接关闭（避免跨线程问题）
                                instance.should_close = True
                                marked_count += 1
                                print(f"[BrowserPool] 标记浏览器实例待关闭（空闲 {idle_time:.1f} 秒，线程ID: {instance.thread_id}）")
                
                if marked_count > 0:
                    print(f"[BrowserPool] 已标记 {marked_count} 个浏览器实例待关闭（将在下次使用时由创建线程关闭）")
                    
            except Exception as e:
                print(f"[BrowserPool] 清理线程异常: {e}")
                import traceback
                traceback.print_exc()
    
    def _close_instance(self, instance: BrowserInstance):
        """关闭单个浏览器实例"""
        try:
            if instance.context:
                instance.context.close()
                print("[BrowserPool] 浏览器上下文已关闭")
            if instance.playwright:
                instance.playwright.stop()
                print("[BrowserPool] Playwright 已停止")
        except Exception as e:
            print(f"[BrowserPool] 关闭浏览器实例时出错: {e}")
    
    def _create_new_instance(self) -> BrowserInstance:
        """创建新的浏览器实例"""
        thread_name = threading.current_thread().name
        print(f"[BrowserPool] 线程 {thread_name} 创建新的浏览器实例...")
        
        # 使用锁确保同一时间只有一个线程在创建浏览器
        with self._user_data_dir_lock:
            # 启动 Playwright
            playwright = sync_playwright().start()
            
            # 获取 chrome.exe 路径
            chrome_executable_path = get_chrome_executable_path()
            
            # 使用共享的用户数据目录
            user_data_dir = self._shared_user_data_dir
            user_data_dir.mkdir(parents=True, exist_ok=True)
            
            # 随机化 viewport 尺寸（模拟不同屏幕）
            viewport_widths = [1920, 1366, 1440, 1536, 1600]
            viewport_heights = [1080, 768, 900, 864, 1024]
            viewport_width = random.choice(viewport_widths)
            viewport_height = random.choice(viewport_heights)
            
            # 使用更新的 User-Agent
            user_agents = [
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36',
            ]
            user_agent = random.choice(user_agents)
            
            # 准备持久化上下文参数
            context_args = {
                'user_data_dir': str(user_data_dir),
                'headless': self.headless,
                'viewport': {'width': viewport_width, 'height': viewport_height},
                'user_agent': user_agent,
                'locale': 'zh-CN',
                'timezone_id': 'Asia/Shanghai',
                'permissions': ['geolocation', 'notifications'],
                'geolocation': {'latitude': 39.9042 + random.uniform(-0.1, 0.1), 'longitude': 116.4074 + random.uniform(-0.1, 0.1)},
                'color_scheme': 'light',
                'ignore_https_errors': True,
                'extra_http_headers': {
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
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
                ]
            }
            
            # 如果指定了 chrome.exe 路径，使用它
            if chrome_executable_path:
                chrome_path = Path(chrome_executable_path)
                if chrome_path.exists() and chrome_path.is_file():
                    context_args['executable_path'] = str(chrome_path.absolute())
            
            # 创建持久化上下文（会自动保存和恢复登录状态）
            context = playwright.chromium.launch_persistent_context(**context_args)
            
            # 注入反爬虫脚本
            context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                window.chrome = { runtime: {}, loadTimes: function() {}, csi: function() {}, app: {} };
            """)
            
            # 创建新页面
            page = context.new_page()
            
            print(f"[BrowserPool] 线程 {thread_name} 浏览器实例创建成功")
            
            return BrowserInstance(
                playwright=playwright,
                context=context,
                page=page,
                is_busy=False,
                last_used_time=datetime.now(),
                thread_id=threading.get_ident()
            )
    
    def _get_or_create_instance(self) -> BrowserInstance:
        """
        获取或创建浏览器实例（支持动态扩展）
        
        策略：
        1. 优先复用当前线程的空闲实例
        2. 如果没有，尝试复用其他线程的空闲实例（如果等待队列不长）
        3. 如果等待队列过长或实例数未达上限，创建新实例
        4. 最多创建 max_instances 个实例
        
        注意：由于 Playwright 同步 API 不支持跨线程使用，
        复用其他线程的实例时需要重新创建 Page
        """
        current_thread_id = threading.get_ident()
        
        # 先清理当前线程中被标记为待关闭的实例
        self._cleanup_marked_instances(current_thread_id)
        
        with self._pool_lock:
            # 增加等待计数
            self._waiting_count += 1
            waiting = self._waiting_count
            total_instances = len(self._instances)
            idle_instances = sum(1 for i in self._instances if not i.is_busy and not i.should_close)
            
            print(f"[BrowserPool] 请求到达：等待队列 {waiting}，总实例 {total_instances}，空闲 {idle_instances}")
            
            # 策略1：优先复用当前线程的空闲实例
            for instance in self._instances:
                if not instance.is_busy and instance.thread_id == current_thread_id and not instance.should_close:
                    instance.is_busy = True
                    instance.last_used_time = datetime.now()
                    self._waiting_count -= 1
                    print(f"[BrowserPool] ✓ 复用当前线程的空闲实例")
                    return instance
            
            # 策略2：如果有其他线程的空闲实例，复用它们
            # 注意：复用时需要转移所有权到当前线程
            if idle_instances > 0:
                for instance in self._instances:
                    if not instance.is_busy and not instance.should_close:
                        instance.is_busy = True
                        instance.last_used_time = datetime.now()
                        instance.thread_id = current_thread_id  # 转移所有权到当前线程
                        self._waiting_count -= 1
                        print(f"[BrowserPool] ✓ 复用其他线程的空闲实例（转移所有权到当前线程）")
                        return instance
            
            # 策略3：渐进式动态扩展
            # 根据等待队列长度，决定需要的实例数
            should_create_new = False
            target_instances = self._calculate_target_instances(waiting)
            
            if total_instances < target_instances and total_instances < self.max_instances:
                print(f"[BrowserPool] ⚡ 渐进式扩展触发：等待队列 {waiting}，当前实例 {total_instances}，目标实例 {target_instances}")
                should_create_new = True
            elif total_instances == 0:
                # 如果池中没有任何实例，创建第一个
                print(f"[BrowserPool] 创建首个浏览器实例")
                should_create_new = True
            elif total_instances >= self.max_instances:
                # 已达上限，必须等待
                print(f"[BrowserPool] ⚠️ 已达最大实例数限制（{self.max_instances}），等待空闲实例...")
                should_create_new = False
                self._waiting_count -= 1
            else:
                # 有实例但都在忙，等待空闲
                print(f"[BrowserPool] 所有实例繁忙，等待空闲实例...")
                should_create_new = False
                self._waiting_count -= 1
        
        # 在锁外创建实例（避免长时间持锁）
        if should_create_new:
            try:
                instance = self._create_new_instance()
                instance.is_busy = True
                instance.thread_id = current_thread_id
                
                # 添加到池中
                with self._pool_lock:
                    self._instances.append(instance)
                    self._waiting_count -= 1
                    print(f"[BrowserPool] ✓ 新浏览器已加入池（池中共 {len(self._instances)} 个实例）")
                
                return instance
            except Exception as e:
                with self._pool_lock:
                    self._waiting_count -= 1
                raise
        else:
            # 需要等待，递归重试（简单实现）
            time.sleep(0.5)  # 等待500ms
            return self._get_or_create_instance()
    
    def _calculate_target_instances(self, waiting_count: int) -> int:
        """
        根据等待队列长度计算目标实例数（渐进式扩展）
        
        扩展策略：
        - 排队 > 5 个：需要 2 个实例
        - 排队 > 20 个：需要 3 个实例
        - 排队 > 30 个：需要 4 个实例
        - 排队 > 40 个：需要 5 个实例
        
        Args:
            waiting_count: 等待队列长度
            
        Returns:
            目标实例数
        """
        # 按照阈值从大到小检查
        for instances, threshold in sorted(self.scale_thresholds.items(), reverse=True):
            if waiting_count > threshold:
                return min(instances, self.max_instances)
        
        # 如果都不满足，返回1个实例
        return 1
    
    def _cleanup_marked_instances(self, thread_id: int):
        """
        清理当前线程中被标记为待关闭的实例
        这个方法由创建实例的线程调用，避免跨线程关闭问题
        
        Args:
            thread_id: 当前线程ID
        """
        instances_to_close = []
        
        with self._pool_lock:
            # 查找当前线程中被标记为待关闭的实例
            for instance in self._instances[:]:
                if instance.thread_id == thread_id and instance.should_close and not instance.is_busy:
                    instances_to_close.append(instance)
                    self._instances.remove(instance)
        
        # 在锁外关闭（由当前线程关闭自己创建的实例）
        for instance in instances_to_close:
            thread_name = threading.current_thread().name
            print(f"[BrowserPool] 线程 {thread_name} 关闭自己创建的空闲浏览器实例")
            self._close_instance(instance)
    
    def _release_instance(self, instance: BrowserInstance, timeout_occurred: bool = False):
        """
        释放浏览器实例（标记为空闲，或关闭如果被标记为待关闭）
        
        Args:
            instance: 浏览器实例
            timeout_occurred: 是否因超时释放
        """
        # 取消超时定时器（如果存在）
        if instance.timeout_timer:
            instance.timeout_timer.cancel()
            instance.timeout_timer = None
        
        # 重置超时标志
        instance.is_timeout = False
        
        # 检查是否被标记为待关闭
        if instance.should_close:
            # 需要关闭此实例
            with self._pool_lock:
                if instance in self._instances:
                    self._instances.remove(instance)
            
            # 关闭实例（在当前线程中，即创建它的线程）
            thread_name = threading.current_thread().name
            print(f"[BrowserPool] 线程 {thread_name} 关闭被标记的浏览器实例")
            self._close_instance(instance)
        else:
            # 标记为空闲，可被复用
            with self._pool_lock:
                instance.is_busy = False
                instance.last_used_time = datetime.now()
                
                if timeout_occurred:
                    print(f"[BrowserPool] 浏览器实例因超时被释放（池中共 {len(self._instances)} 个实例）")
                else:
                    print(f"[BrowserPool] 浏览器实例已标记为空闲（池中共 {len(self._instances)} 个实例）")
    
    def _on_timeout(self, instance: BrowserInstance, timeout_seconds: float):
        """
        超时回调函数
        
        Args:
            instance: 浏览器实例
            timeout_seconds: 超时时间（秒）
        """
        thread_name = threading.current_thread().name
        print(f"[BrowserPool] ⚠️ 警告：线程 {thread_name} 的浏览器操作超时（超过 {timeout_seconds} 秒）")
        
        # 标记为超时状态
        instance.is_timeout = True
        
        # 注意：不在这里释放实例，而是在 finally 块中检查超时标志后释放
        # 这样可以确保调用者的代码能够正确退出
    
    @contextmanager
    def get_page(self, timeout: float = 60.0):
        """
        获取一个浏览器页面（上下文管理器）
        
        使用方法：
            with browser_pool.get_page(timeout=30) as page:
                page.goto('https://example.com')
                # 使用 page 进行操作
            # 离开 with 块后，浏览器标记为空闲，可被其他请求复用
        
        Args:
            timeout: 超时时间（秒），默认60秒。超时后会记录日志并强制释放浏览器
        
        Yields:
            Page 对象
            
        Raises:
            BrowserTimeoutError: 如果操作超时
        """
        instance = None
        timeout_occurred = False
        start_time = time.time()
        
        try:
            # 获取或创建浏览器实例
            instance = self._get_or_create_instance()
            
            # 启动超时定时器
            if timeout > 0:
                instance.timeout_timer = threading.Timer(
                    timeout, 
                    self._on_timeout, 
                    args=(instance, timeout)
                )
                instance.timeout_timer.daemon = True
                instance.timeout_timer.start()
                print(f"[BrowserPool] 启动超时定时器，超时时间: {timeout} 秒")
            
            # yield page 给调用者使用
            yield instance.page
            
            # 检查是否超时
            if instance.is_timeout:
                timeout_occurred = True
                elapsed = time.time() - start_time
                thread_name = threading.current_thread().name
                print(f"[BrowserPool] ❌ 线程 {thread_name} 的浏览器操作已超时（耗时 {elapsed:.2f} 秒，超时限制 {timeout} 秒）")
                raise BrowserTimeoutError(f"浏览器操作超时（超过 {timeout} 秒）")
            
        except BrowserTimeoutError:
            # 超时异常，直接抛出
            timeout_occurred = True
            raise
            
        except Exception as e:
            thread_name = threading.current_thread().name
            elapsed = time.time() - start_time
            
            # 检查是否是因为超时导致的其他异常
            if instance and instance.is_timeout:
                timeout_occurred = True
                print(f"[BrowserPool] ❌ 线程 {thread_name} 因超时导致异常（耗时 {elapsed:.2f} 秒）: {e}")
                raise BrowserTimeoutError(f"浏览器操作超时导致异常: {e}") from e
            else:
                print(f"[BrowserPool] 线程 {thread_name} 使用浏览器异常（耗时 {elapsed:.2f} 秒）: {e}")
                import traceback
                traceback.print_exc()
                raise
        
        finally:
            # 无论成功、失败还是超时，都要释放实例
            if instance:
                elapsed = time.time() - start_time
                print(f"[BrowserPool] 浏览器操作完成，耗时 {elapsed:.2f} 秒")
                self._release_instance(instance, timeout_occurred=timeout_occurred)
    
    def close(self):
        """关闭浏览器池，清理所有资源"""
        print("[BrowserPool] 开始关闭浏览器池...")
        
        # 停止清理线程
        self._cleanup_running = False
        if self._cleanup_thread and self._cleanup_thread.is_alive():
            self._cleanup_thread.join(timeout=5)
        
        # 关闭所有浏览器实例
        with self._pool_lock:
            instances_to_close = self._instances[:]
            self._instances.clear()
        
        for instance in instances_to_close:
            self._close_instance(instance)
        
        print(f"[BrowserPool] 浏览器池已关闭，共关闭 {len(instances_to_close)} 个实例")
    
    def get_pool_status(self) -> Dict:
        """获取浏览器池状态信息"""
        with self._pool_lock:
            total = len(self._instances)
            busy = sum(1 for i in self._instances if i.is_busy)
            idle = total - busy
            
            instances_info = []
            for idx, instance in enumerate(self._instances):
                idle_time = (datetime.now() - instance.last_used_time).total_seconds()
                instances_info.append({
                    'index': idx,
                    'is_busy': instance.is_busy,
                    'idle_seconds': idle_time,
                    'thread_id': instance.thread_id,
                    'should_close': instance.should_close
                })
            
            return {
                'total': total,
                'busy': busy,
                'idle': idle,
                'waiting': self._waiting_count,
                'max_instances': self.max_instances,
                'scale_thresholds': self.scale_thresholds,  # 渐进式扩展阈值
                'instances': instances_info,
                'idle_timeout': self.idle_timeout
            }


