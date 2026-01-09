"""
功能模块管理器
"""
from typing import Dict, Any, List, Optional, Set
from config import load_module_config, save_module_config
from config.modules import validate_module_config, get_default_module_config


class ModuleManager:
    """功能模块管理器"""
    
    def __init__(self):
        """初始化模块管理器"""
        self._config: Dict[str, Dict[str, Any]] = {}
        self._loaded_modules: Set[str] = set()
        self._module_instances: Dict[str, Any] = {}
        self._load_config()
    
    def _load_config(self):
        """加载模块配置"""
        self._config = load_module_config()
    
    def reload_config(self) -> bool:
        """
        重新加载模块配置
        
        Returns:
            是否成功
        """
        try:
            self._load_config()
            return True
        except Exception as e:
            print(f"[ModuleManager] 重新加载配置失败: {e}")
            return False
    
    def get_config(self) -> Dict[str, Dict[str, Any]]:
        """
        获取所有模块配置
        
        Returns:
            模块配置字典
        """
        return self._config.copy()
    
    def get_module_config(self, module_name: str) -> Optional[Dict[str, Any]]:
        """
        获取单个模块配置
        
        Args:
            module_name: 模块名称
            
        Returns:
            模块配置字典，如果不存在返回None
        """
        return self._config.get(module_name)
    
    def get_enabled_modules(self) -> List[str]:
        """
        获取启用的模块列表
        
        Returns:
            启用的模块名称列表
        """
        return [name for name, config in self._config.items() if config.get('enabled', False)]
    
    def get_startup_modules(self) -> List[str]:
        """
        获取启动时初始化的模块列表
        
        Returns:
            启动时初始化的模块名称列表
        """
        return [
            name for name, config in self._config.items()
            if config.get('enabled', False) and config.get('init_on_startup', False)
        ]
    
    def get_modules_requiring_browser(self) -> List[str]:
        """
        获取需要浏览器的模块列表
        
        Returns:
            需要浏览器的模块名称列表
        """
        return [
            name for name, config in self._config.items()
            if config.get('enabled', False) and config.get('requires_browser', False)
        ]
    
    def is_module_enabled(self, module_name: str) -> bool:
        """
        检查模块是否启用
        
        Args:
            module_name: 模块名称
            
        Returns:
            是否启用
        """
        config = self._config.get(module_name)
        return config is not None and config.get('enabled', False)
    
    def is_module_loaded(self, module_name: str) -> bool:
        """
        检查模块是否已加载
        
        Args:
            module_name: 模块名称
            
        Returns:
            是否已加载
        """
        return module_name in self._loaded_modules
    
    def get_module_status(self, module_name: str) -> Dict[str, Any]:
        """
        获取模块状态
        
        Args:
            module_name: 模块名称
            
        Returns:
            模块状态字典
        """
        config = self._config.get(module_name)
        if config is None:
            return {
                'exists': False,
                'enabled': False,
                'loaded': False,
                'init_on_startup': False,
                'requires_browser': False
            }
        
        return {
            'exists': True,
            'enabled': config.get('enabled', False),
            'loaded': module_name in self._loaded_modules,
            'init_on_startup': config.get('init_on_startup', False),
            'requires_browser': config.get('requires_browser', False),
            'memory_mb': config.get('memory_mb', 0),
            'description': config.get('description', ''),
            'display_name': config.get('display_name', module_name),
            'icon': config.get('icon', '🔧'),
            'category': config.get('category', 'tools')
        }
    
    def get_all_modules_status(self) -> Dict[str, Dict[str, Any]]:
        """
        获取所有模块状态
        
        Returns:
            所有模块状态字典
        """
        return {
            name: self.get_module_status(name)
            for name in self._config.keys()
        }
    
    def enable_module(self, module_name: str) -> bool:
        """
        启用模块
        
        Args:
            module_name: 模块名称
            
        Returns:
            是否成功
        """
        if module_name not in self._config:
            return False
        
        self._config[module_name]['enabled'] = True
        return self._save_config()
    
    def disable_module(self, module_name: str) -> bool:
        """
        禁用模块
        
        Args:
            module_name: 模块名称
            
        Returns:
            是否成功
        """
        if module_name not in self._config:
            return False
        
        self._config[module_name]['enabled'] = False
        return self._save_config()
    
    def set_startup_init(self, module_name: str, init_on_startup: bool) -> bool:
        """
        设置模块是否在启动时初始化
        
        Args:
            module_name: 模块名称
            init_on_startup: 是否在启动时初始化
            
        Returns:
            是否成功
        """
        if module_name not in self._config:
            return False
        
        self._config[module_name]['init_on_startup'] = init_on_startup
        return self._save_config()
    
    def register_module_instance(self, module_name: str, instance: Any):
        """
        注册模块实例
        
        Args:
            module_name: 模块名称
            instance: 模块实例
        """
        self._module_instances[module_name] = instance
        self._loaded_modules.add(module_name)
    
    def unregister_module_instance(self, module_name: str):
        """
        注销模块实例
        
        Args:
            module_name: 模块名称
        """
        if module_name in self._module_instances:
            del self._module_instances[module_name]
        self._loaded_modules.discard(module_name)
    
    def get_module_instance(self, module_name: str) -> Optional[Any]:
        """
        获取模块实例
        
        Args:
            module_name: 模块名称
            
        Returns:
            模块实例，如果不存在返回None
        """
        return self._module_instances.get(module_name)
    
    def check_module_dependencies(self, module_name: str) -> List[str]:
        """
        检查模块依赖
        
        Args:
            module_name: 模块名称
            
        Returns:
            缺失的依赖列表
        """
        config = self._config.get(module_name)
        if config is None:
            return []
        
        missing_deps = []
        
        # 检查浏览器依赖
        if config.get('requires_browser', False):
            # 这里可以添加浏览器可用性检查
            pass
        
        # 可以添加其他依赖检查
        
        return missing_deps
    
    def _save_config(self) -> bool:
        """
        保存配置到文件
        
        Returns:
            是否成功
        """
        try:
            # 只保存用户修改的配置（与默认配置不同的部分）
            default_config = get_default_module_config()
            user_config = {}
            
            for name, config in self._config.items():
                default = default_config.get(name, {})
                # 找出与默认配置不同的部分
                diff = {}
                for key, value in config.items():
                    if key not in default or default[key] != value:
                        diff[key] = value
                
                if diff:
                    user_config[name] = diff
            
            return save_module_config(user_config)
        except Exception as e:
            print(f"[ModuleManager] 保存配置失败: {e}")
            return False
    
    def update_module_config(self, module_name: str, config_updates: Dict[str, Any]) -> bool:
        """
        更新模块配置
        
        Args:
            module_name: 模块名称
            config_updates: 配置更新字典
            
        Returns:
            是否成功
        """
        if module_name not in self._config:
            return False
        
        # 验证配置
        test_config = self._config[module_name].copy()
        test_config.update(config_updates)
        if not validate_module_config(test_config):
            return False
        
        # 更新配置
        self._config[module_name].update(config_updates)
        return self._save_config()


# 全局模块管理器实例
_module_manager: Optional[ModuleManager] = None


def get_module_manager() -> ModuleManager:
    """
    获取全局模块管理器实例
    
    Returns:
        模块管理器实例
    """
    global _module_manager
    if _module_manager is None:
        _module_manager = ModuleManager()
    return _module_manager
