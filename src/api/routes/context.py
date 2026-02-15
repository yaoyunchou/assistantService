"""
API 路由公共上下文：浏览器池等，供各 Blueprint 使用。
"""
import threading

# 全局浏览器池引用（由 register_routes 设置）
_browser_pool_ref = None

# 通用后台线程池（飞书消息等非浏览器异步任务使用）
_bg_executor_lock = threading.Lock()
_bg_executor = None


def _get_bg_executor():
    """获取通用后台线程池（懒初始化）"""
    global _bg_executor
    if _bg_executor is None:
        with _bg_executor_lock:
            if _bg_executor is None:
                from concurrent.futures import ThreadPoolExecutor
                _bg_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="bg_task")
    return _bg_executor


def get_browser_pool():
    return _browser_pool_ref


def get_browser_executor():
    """兼容旧代码：返回通用后台线程池（非浏览器操作用）"""
    return _get_bg_executor()


def set_browser_pool(pool):
    global _browser_pool_ref
    _browser_pool_ref = pool
