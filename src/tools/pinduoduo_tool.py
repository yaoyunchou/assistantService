"""
拼多多工具实现
将拼多多自动化功能封装为工具
"""
from typing import Dict, Any, Optional
from .base import BaseTool
from utils.logger import get_logger

logger = get_logger('PinduoduoTool')


class PinduoduoTool(BaseTool):
    """订单助手工具"""

    def __init__(self):
        super().__init__(
            name="pinduoduo",
            display_name="订单助手",
            description="订单后台自动化工具，支持登录管理和自动化操作"
        )
        self.browser_pool = None

    def get_info(self) -> Dict[str, Any]:
        """获取工具信息"""
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "icon": "🛒",
            "template": self.get_template_name(),
            "api_prefix": self.get_api_prefix()
        }

    def initialize(self, **kwargs) -> bool:
        """初始化工具"""
        self.browser_pool = kwargs.get('browser_pool')
        if not self.browser_pool:
            logger.warning("browser_pool 未提供")
        return True

    def cleanup(self):
        """清理工具资源"""
        self.browser_pool = None

    def execute_with_client(self, callback, timeout: float = 60.0):
        """
        使用 PinduoduoClient 执行操作（通过 pool.execute 在浏览器线程执行）

        Args:
            callback: 回调函数，接收 PinduoduoClient 实例作为参数
            timeout: 超时时间（秒），默认60秒
        """
        if not self.browser_pool:
            logger.error("BrowserPool 未设置")
            raise RuntimeError("BrowserPool 未设置，请先初始化工具")

        try:
            from spider.pinduoduo.client import PinduoduoClient
            logger.info(f"开始执行操作，超时限制: {timeout} 秒")

            def _run(page):
                client = PinduoduoClient(page=page)
                logger.info("PinduoduoClient 创建成功")
                result = callback(client)
                logger.info("操作执行完成")
                return result

            return self.browser_pool.execute(_run, timeout=timeout)
        except Exception as e:
            logger.error(f"执行操作失败: {e}", exc_info=True)
            raise
