"""
工具基类
定义所有工具的统一接口
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class BaseTool(ABC):
    """工具基类，所有工具都应继承此类"""
    
    def __init__(self, name: str, display_name: str, description: str = ""):
        """
        初始化工具
        
        Args:
            name: 工具唯一标识符（英文，用于URL和内部引用）
            display_name: 工具显示名称（中文，用于界面显示）
            description: 工具描述
        """
        self.name = name
        self.display_name = display_name
        self.description = description
    
    @abstractmethod
    def get_info(self) -> Dict[str, Any]:
        """
        获取工具信息
        
        Returns:
            包含工具信息的字典，至少包含：
            - name: 工具标识符
            - display_name: 显示名称
            - description: 描述
            - icon: 图标路径（可选）
        """
        pass
    
    @abstractmethod
    def initialize(self, **kwargs) -> bool:
        """
        初始化工具
        
        Args:
            **kwargs: 初始化参数
            
        Returns:
            是否初始化成功
        """
        pass
    
    @abstractmethod
    def cleanup(self):
        """清理工具资源"""
        pass
    
    def get_template_name(self) -> str:
        """
        获取工具对应的HTML模板名称
        
        Returns:
            模板文件名，默认返回 tools/{name}.html
        """
        return f"tools/{self.name}.html"
    
    def get_api_prefix(self) -> str:
        """
        获取工具的API前缀
        
        Returns:
            API前缀，默认返回 /api/tools/{name}
        """
        return f"/api/tools/{self.name}"
