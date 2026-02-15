"""
途强物联网平台工具实现
将途强自动化功能封装为工具（自动登录 + 获取最近 30 天记录）
"""
from typing import Dict, Any, Optional
from .base import BaseTool
from utils.logger import get_logger

logger = get_logger('TuTool')


class TuTool(BaseTool):
    """途强物联网平台助手工具"""

    def __init__(self):
        super().__init__(
            name="tu",
            display_name="途强助手",
            description="途强智能设备管理平台自动化，支持自动登录与最近 30 天记录获取"
        )
        self.browser_pool = None

    def get_info(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "icon": "📡",
            "template": self.get_template_name(),
            "api_prefix": self.get_api_prefix(),
        }

    def initialize(self, **kwargs) -> bool:
        self.browser_pool = kwargs.get("browser_pool")
        if not self.browser_pool:
            logger.warning("browser_pool 未提供")
        return True

    def cleanup(self):
        self.browser_pool = None

    def execute_with_client(self, callback, timeout: float = 120.0):
        """
        使用 TuClient 执行操作（通过 pool.execute 在浏览器线程执行）

        Args:
            callback: 回调函数，接收 TuClient 实例作为参数
            timeout: 超时时间（秒）
        """
        if not self.browser_pool:
            raise RuntimeError("BrowserPool 未设置，请先初始化工具")
        try:
            from spider.tu.client import TuClient

            def _run(page):
                client = TuClient(page=page)
                return callback(client)

            return self.browser_pool.execute(_run, timeout=timeout)
        except Exception as e:
            logger.error(f"执行操作失败: {e}", exc_info=True)
            raise
