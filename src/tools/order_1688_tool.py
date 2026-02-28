"""
1688 订单提取工具
"""
from typing import Dict, Any, Optional
from .base import BaseTool
from utils.logger import get_logger

logger = get_logger("Order1688Tool")


class Order1688Tool(BaseTool):
    """1688 订单提取工具"""

    def __init__(self):
        super().__init__(
            name="order_1688",
            display_name="1688 订单提取",
            description="从 1688 待收货订单列表提取订单信息（含收货人、物流号等），支持同步到飞书多维表格",
        )
        self.browser_pool = None

    def get_info(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "icon": "📦",
            "template": self.get_template_name(),
            "api_prefix": self.get_api_prefix(),
        }

    def initialize(self, **kwargs) -> bool:
        self.browser_pool = kwargs.get("browser_pool")
        if not self.browser_pool:
            logger.warning("order_1688: browser_pool 未提供")
        return True

    def cleanup(self):
        self.browser_pool = None
