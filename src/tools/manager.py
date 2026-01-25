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
            self._lazy_tools: Dict[str, callable] = {}  # 延迟加载的工具工厂函数
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
    
    def register_lazy_tool(self, name: str, factory: callable):
        """
        注册延迟加载工具
        
        Args:
            name: 工具名称
            factory: 工具工厂函数，返回工具实例
        """
        self._lazy_tools[name] = factory
        print(f"[ToolManager] 已注册延迟加载工具: {name}")
    
    def load_lazy_tool(self, name: str, **kwargs) -> Optional[BaseTool]:
        """
        加载延迟工具
        
        Args:
            name: 工具名称
            **kwargs: 初始化参数
            
        Returns:
            工具实例，如果不存在或加载失败返回None
        """
        if name in self._tools:
            return self._tools[name]
        
        if name not in self._lazy_tools:
            return None
        
        try:
            factory = self._lazy_tools[name]
            tool = factory()
            if tool:
                self._tools[name] = tool
                # 尝试初始化
                if hasattr(tool, 'initialize'):
                    tool.initialize(**kwargs)
                print(f"[ToolManager] 延迟加载工具 {name} 成功")
                return tool
        except Exception as e:
            print(f"[ToolManager] 延迟加载工具 {name} 失败: {e}")
        
        return None
    
    def unregister_tool(self, name: str) -> bool:
        """
        注销工具
        
        Args:
            name: 工具名称
            
        Returns:
            是否成功
        """
        if name in self._tools:
            tool = self._tools[name]
            try:
                if hasattr(tool, 'cleanup'):
                    tool.cleanup()
            except Exception as e:
                print(f"[ToolManager] 清理工具 {name} 时出错: {e}")
            del self._tools[name]
            print(f"[ToolManager] 已注销工具: {name}")
            return True
        return False
    
    def cleanup_all(self):
        """清理所有工具资源"""
        for name, tool in self._tools.items():
            try:
                tool.cleanup()
                print(f"[ToolManager] 工具 {name} 清理完成")
            except Exception as e:
                print(f"[ToolManager] 工具 {name} 清理异常: {e}")


# 全局单例访问函数
_tool_manager_instance = None


def get_tool_manager() -> ToolManager:
    """
    获取工具管理器单例实例
    
    Returns:
        ToolManager实例
    """
    global _tool_manager_instance
    if _tool_manager_instance is None:
        _tool_manager_instance = ToolManager()
    return _tool_manager_instance
