"""
工具管理器
负责工具的注册、加载和管理
"""
from typing import Dict, List, Optional, Type
from .base import BaseTool


class ToolManager:
    """工具管理器，单例模式"""
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self._tools: Dict[str, BaseTool] = {}
            self._initialized = True
    
    def register_tool(self, tool: BaseTool):
        """
        注册工具
        
        Args:
            tool: 工具实例
        """
        if not isinstance(tool, BaseTool):
            raise ValueError("工具必须继承自BaseTool")
        
        if tool.name in self._tools:
            raise ValueError(f"工具 {tool.name} 已注册")
        
        self._tools[tool.name] = tool
        print(f"[ToolManager] 已注册工具: {tool.display_name} ({tool.name})")
    
    def get_tool(self, name: str) -> Optional[BaseTool]:
        """
        获取工具
        
        Args:
            name: 工具名称
            
        Returns:
            工具实例，如果不存在返回None
        """
        return self._tools.get(name)
    
    def get_all_tools(self) -> List[BaseTool]:
        """
        获取所有工具
        
        Returns:
            工具列表
        """
        return list(self._tools.values())
    
    def get_tools_info(self) -> List[Dict]:
        """
        获取所有工具的信息
        
        Returns:
            工具信息列表
        """
        return [tool.get_info() for tool in self._tools.values()]
    
    def initialize_all(self, **kwargs) -> Dict[str, bool]:
        """
        初始化所有工具
        
        Args:
            **kwargs: 初始化参数
            
        Returns:
            初始化结果字典 {工具名: 是否成功}
        """
        results = {}
        for name, tool in self._tools.items():
            try:
                results[name] = tool.initialize(**kwargs)
                if results[name]:
                    print(f"[ToolManager] 工具 {name} 初始化成功")
                else:
                    print(f"[ToolManager] 工具 {name} 初始化失败")
            except Exception as e:
                print(f"[ToolManager] 工具 {name} 初始化异常: {e}")
                results[name] = False
        return results
    
    def cleanup_all(self):
        """清理所有工具资源"""
        for name, tool in self._tools.items():
            try:
                tool.cleanup()
                print(f"[ToolManager] 工具 {name} 清理完成")
            except Exception as e:
                print(f"[ToolManager] 工具 {name} 清理异常: {e}")
