"""
闲鱼商品管理工具
"""
from typing import Dict, Any
from .base import BaseTool
from utils.logger import get_logger

logger = get_logger('GoofishTool')


class GoofishTool(BaseTool):
    """闲鱼卖家工作台自动化：商品发布与商品管理"""

    def __init__(self):
        super().__init__(
            name='goofish',
            display_name='闲鱼商品',
            description='Playwright 自动化闲鱼卖家工作台：本地队列发布、在线商品上下架/编辑/删除',
        )
        self.browser_pool = None

    def get_info(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'display_name': self.display_name,
            'description': self.description,
            'icon': '🐟',
            'template': self.get_template_name(),
            'api_prefix': '/api/goofish',
        }

    def initialize(self, **kwargs) -> bool:
        self.browser_pool = kwargs.get('browser_pool')
        if not self.browser_pool:
            logger.warning('goofish: browser_pool 未提供')
        return True

    def cleanup(self):
        self.browser_pool = None
