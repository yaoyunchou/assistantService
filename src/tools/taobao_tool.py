"""
淘宝商品上架工具
"""
from typing import Dict, Any
from .base import BaseTool
from utils.logger import get_logger

logger = get_logger('TaobaoTool')


class TaobaoTool(BaseTool):
    """淘宝以图发品自动上架"""

    def __init__(self):
        super().__init__(
            name='taobao',
            display_name='淘宝商品上架',
            description='Playwright 以图发品：本地上传、主图审计、类目确认、发布填表、提交与 Excel 回填',
        )
        self.browser_pool = None

    def get_info(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'display_name': self.display_name,
            'description': self.description,
            'icon': '🛍️',
            'template': self.get_template_name(),
            'api_prefix': '/api/taobao',
        }

    def initialize(self, **kwargs) -> bool:
        self.browser_pool = kwargs.get('browser_pool')
        if not self.browser_pool:
            logger.warning('taobao: browser_pool 未提供')
        return True

    def cleanup(self):
        self.browser_pool = None
