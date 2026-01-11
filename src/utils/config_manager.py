"""
配置管理器
支持配置的保存、加载和热重载
"""
import json
import sys
from pathlib import Path
from typing import Dict, Any, Optional
from config import Config


class ConfigManager:
    """配置管理器"""
    
    def __init__(self, config_file: Optional[str] = None):
        """
        初始化配置管理器
        
        Args:
            config_file: 配置文件路径，None则使用默认路径
        """
        if config_file:
            self.config_file = Path(config_file)
        else:
            # 默认路径：项目根目录或exe同目录下的app_config.json
            if getattr(sys, 'frozen', False):
                exe_dir = Path(sys.executable).parent
                self.config_file = exe_dir / 'app_config.json'
            else:
                current_dir = Path(__file__).parent.parent.parent
                self.config_file = current_dir / 'app_config.json'
        
        # 确保目录存在
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
    
    def get_config(self) -> Dict[str, Any]:
        """
        获取当前配置
        
        Returns:
            配置字典
        """
        return {
            'host': Config.HOST,
            'port': Config.PORT,
            'headless': Config.HEADLESS,
            'window_width': Config.WINDOW_WIDTH,
            'window_height': Config.WINDOW_HEIGHT,
            'window_min_width': Config.WINDOW_MIN_WIDTH,
            'window_min_height': Config.WINDOW_MIN_HEIGHT,
            'window_resizable': Config.WINDOW_RESIZABLE,
            'tray_enabled': Config.TRAY_ENABLED,
            'use_native_window': Config.USE_NATIVE_WINDOW,
            'log_level': Config.LOG_LEVEL,
            'enable_devtools': Config.ENABLE_DEVTOOLS,
            'browser_lazy_init': Config.BROWSER_LAZY_INIT,
            'browser_idle_timeout': Config.BROWSER_IDLE_TIMEOUT,
            'enable_resource_monitor': Config.ENABLE_RESOURCE_MONITOR,
            'max_memory_mb': Config.MAX_MEMORY_MB
        }
    
    def load_config(self) -> Dict[str, Any]:
        """
        从文件加载配置
        
        Returns:
            配置字典，如果文件不存在返回空字典
        """
        if not self.config_file.exists():
            return {}
        
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[ConfigManager] 加载配置文件失败: {e}")
            return {}
    
    def save_config(self, config: Dict[str, Any]) -> bool:
        """
        保存配置到文件
        
        Args:
            config: 配置字典
            
        Returns:
            是否保存成功
        """
        try:
            # 验证端口号
            if 'port' in config:
                port = int(config['port'])
                if port < 1024 or port > 65535:
                    raise ValueError(f"端口号必须在1024-65535之间，当前值: {port}")
                config['port'] = port
            
            # 保存配置
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            
            return True
        except Exception as e:
            print(f"[ConfigManager] 保存配置文件失败: {e}")
            return False
    
    def apply_config(self, config: Dict[str, Any], require_restart: bool = False) -> Dict[str, Any]:
        """
        应用配置（热重载或标记需要重启）
        
        Args:
            config: 配置字典
            require_restart: 是否标记需要重启
            
        Returns:
            应用结果字典，包含哪些配置已应用，哪些需要重启
        """
        applied = {}
        need_restart = {}
        
        # 需要重启的配置
        restart_required = ['port', 'host']
        
        for key, value in config.items():
            if key in restart_required:
                # 这些配置需要重启才能生效
                need_restart[key] = value
            else:
                # 可以热重载的配置
                try:
                    self._apply_single_config(key, value)
                    applied[key] = value
                except Exception as e:
                    print(f"[ConfigManager] 应用配置 {key} 失败: {e}")
        
        return {
            'applied': applied,
            'need_restart': need_restart,
            'require_restart': len(need_restart) > 0 or require_restart
        }
    
    def _apply_single_config(self, key: str, value: Any):
        """
        应用单个配置项
        
        Args:
            key: 配置键
            value: 配置值
        """
        # 可以热重载的配置
        if key == 'headless':
            Config.HEADLESS = bool(value)
        elif key == 'window_width':
            Config.WINDOW_WIDTH = int(value)
        elif key == 'window_height':
            Config.WINDOW_HEIGHT = int(value)
        elif key == 'window_min_width':
            Config.WINDOW_MIN_WIDTH = int(value)
        elif key == 'window_min_height':
            Config.WINDOW_MIN_HEIGHT = int(value)
        elif key == 'window_resizable':
            Config.WINDOW_RESIZABLE = bool(value)
        elif key == 'tray_enabled':
            Config.TRAY_ENABLED = bool(value)
        elif key == 'use_native_window':
            Config.USE_NATIVE_WINDOW = bool(value)
        elif key == 'log_level':
            Config.LOG_LEVEL = str(value)
        elif key == 'enable_devtools':
            Config.ENABLE_DEVTOOLS = bool(value)
        elif key == 'browser_lazy_init':
            Config.BROWSER_LAZY_INIT = bool(value)
        elif key == 'browser_idle_timeout':
            Config.BROWSER_IDLE_TIMEOUT = int(value)
        elif key == 'enable_resource_monitor':
            Config.ENABLE_RESOURCE_MONITOR = bool(value)
        elif key == 'max_memory_mb':
            Config.MAX_MEMORY_MB = int(value)
        # 注意：host 和 port 需要重启，不在这里处理
    
    def reload_from_file(self) -> bool:
        """
        从文件重新加载配置并应用
        
        Returns:
            是否成功
        """
        config = self.load_config()
        if not config:
            return False
        
        result = self.apply_config(config)
        return len(result['applied']) > 0


# 全局配置管理器实例
_config_manager: Optional[ConfigManager] = None


def get_config_manager() -> ConfigManager:
    """
    获取全局配置管理器实例
    
    Returns:
        配置管理器实例
    """
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager
