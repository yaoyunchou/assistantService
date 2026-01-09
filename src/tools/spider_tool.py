"""
爬虫工具实现
将现有的爬虫功能封装为工具
"""
from typing import Dict, Any, Optional
from .base import BaseTool
from spider.query_manager import BrowserPool
from config import Config


class SpiderTool(BaseTool):
    """爬虫工具"""
    
    def __init__(self):
        super().__init__(
            name="spider",
            display_name="快递查询",
            description="快递物流信息查询工具，支持单个和批量查询"
        )
        self.browser_pool: Optional[BrowserPool] = None
    
    def get_info(self) -> Dict[str, Any]:
        """获取工具信息"""
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "icon": "📦",
            "template": self.get_template_name(),
            "api_prefix": self.get_api_prefix()
        }
    
    def initialize(self, browser_pool: Optional[BrowserPool] = None, **kwargs) -> bool:
        """
        初始化工具
        
        Args:
            browser_pool: 浏览器池实例（如果提供则使用，否则创建新的）
            **kwargs: 其他参数
            
        Returns:
            是否初始化成功
        """
        try:
            if browser_pool is not None:
                self.browser_pool = browser_pool
            else:
                # 如果没有提供浏览器池，创建一个新的
                self.browser_pool = BrowserPool(headless=Config.HEADLESS)
                self.browser_pool.initialize()
            
            return True
        except Exception as e:
            print(f"[SpiderTool] 初始化失败: {e}")
            return False
    
    def cleanup(self):
        """清理工具资源"""
        # 注意：如果browser_pool是从外部传入的，不应该在这里关闭
        # 这里只清理工具自己的资源
        pass
    
    def get_browser_pool(self) -> Optional[BrowserPool]:
        """获取浏览器池实例"""
        return self.browser_pool
