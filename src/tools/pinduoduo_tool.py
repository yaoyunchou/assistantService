"""
拼多多工具实现
将拼多多自动化功能封装为工具
"""
from typing import Dict, Any, Optional
from .base import BaseTool
from utils.logger import get_logger

logger = get_logger('PinduoduoTool')


class PinduoduoTool(BaseTool):
    """拼多多助手工具"""
    
    def __init__(self):
        super().__init__(
            name="pinduoduo",
            display_name="拼多多助手",
            description="拼多多商家后台自动化工具，支持登录管理和自动化操作"
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
        """
        初始化工具
        
        Args:
            **kwargs: 可选参数，包括 browser_pool
            
        Returns:
            是否初始化成功
        """
        self.browser_pool = kwargs.get('browser_pool')
        if not self.browser_pool:
            logger.warning("browser_pool 未提供")
        return True
    
    def cleanup(self):
        """清理工具资源"""
        self.browser_pool = None
    
    def execute_with_client(self, callback, timeout: float = 60.0):
        """
        使用 PinduoduoClient 执行操作（上下文管理器模式）
        
        Args:
            callback: 回调函数，接收 PinduoduoClient 实例作为参数
            timeout: 超时时间（秒），默认60秒
            
        Returns:
            回调函数的返回值
        """
        if not self.browser_pool:
            logger.error("BrowserPool 未设置")
            raise RuntimeError("BrowserPool 未设置，请先初始化工具")
        
        try:
            # 使用上下文管理器获取页面
            logger.info(f"开始执行操作，超时限制: {timeout} 秒")
            with self.browser_pool.get_page(timeout=timeout) as page:
                # 创建 PinduoduoClient
                from spider.pinduoduo.client import PinduoduoClient
                client = PinduoduoClient(page=page)
                logger.info("PinduoduoClient 创建成功")
                
                # 执行回调
                result = callback(client)
                
                logger.info("操作执行完成")
                return result
                
        except Exception as e:
            logger.error(f"执行操作失败: {e}", exc_info=True)
            raise
