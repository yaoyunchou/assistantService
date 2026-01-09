"""
配置文件
"""
import os
import json
from pathlib import Path
from typing import Dict, Any, Optional


class Config:
    """应用配置类"""
    # HTTP服务配置
    HOST = '127.0.0.1'
    PORT = 888888
    
    # 浏览器配置
    HEADLESS = True  # 是否使用无头模式
    
    # 查询配置
    MAX_RETRY = 3  # 最大重试次数
    
    # Web界面配置
    APP_NAME = '如意助手'
    APP_VERSION = '2.0.0'
    AUTO_OPEN_BROWSER = True  # 启动时自动打开浏览器（已废弃，使用 USE_NATIVE_WINDOW）
    USE_NATIVE_WINDOW = True  # 使用原生窗口（True）还是浏览器（False）
    
    # 原生窗口配置
    WINDOW_TITLE = '如意助手'  # 窗口标题
    WINDOW_WIDTH = 1200  # 窗口宽度
    WINDOW_HEIGHT = 800  # 窗口高度
    WINDOW_MIN_WIDTH = 800  # 最小宽度
    WINDOW_MIN_HEIGHT = 600  # 最小高度
    WINDOW_RESIZABLE = True  # 是否可调整大小
    
    # 系统托盘配置
    TRAY_ENABLED = True  # 是否启用系统托盘
    TRAY_ICON_PATH = None  # 托盘图标路径，None则使用默认图标（优先使用logo_default.jpg）
    
    # 日志配置
    LOG_DIR = None  # 日志文件目录，None则使用项目根目录下的logs文件夹
    LOG_LEVEL = 'INFO'  # 日志级别：DEBUG, INFO, WARNING, ERROR, CRITICAL
    
    # 窗口调试配置
    SHOW_CONSOLE = False  # 是否显示控制台窗口（开发时可用，打包后建议False）
    ENABLE_DEVTOOLS = False  # 是否启用开发者工具（F12调试窗口）
    
    # 模块配置
    MODULE_CONFIG_FILE = None  # 模块配置文件路径，None则使用默认配置
    BROWSER_LAZY_INIT = True  # 延迟初始化浏览器
    BROWSER_IDLE_TIMEOUT = 300  # 浏览器空闲超时（秒）
    ENABLE_RESOURCE_MONITOR = True  # 启用资源监控
    MAX_MEMORY_MB = 200  # 最大内存限制（MB）


def get_module_config_file_path() -> Path:
    """
    获取模块配置文件路径
    
    Returns:
        配置文件路径
    """
    if Config.MODULE_CONFIG_FILE:
        return Path(Config.MODULE_CONFIG_FILE)
    
    # 默认路径：项目根目录或exe同目录
    if getattr(__import__('sys'), 'frozen', False):
        # 打包后的exe环境
        exe_dir = Path(__import__('sys').executable).parent
        return exe_dir / 'module_config.json'
    else:
        # 开发环境
        current_dir = Path(__file__).parent.parent
        return current_dir / 'module_config.json'


def load_module_config() -> Dict[str, Dict[str, Any]]:
    """
    加载模块配置
    
    Returns:
        模块配置字典
    """
    from config.modules import get_default_module_config
    
    # 获取默认配置
    config = get_default_module_config()
    
    # 尝试从文件加载用户配置
    config_file = get_module_config_file_path()
    if config_file.exists():
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                user_config = json.load(f)
            
            # 合并用户配置到默认配置
            for module_name, module_config in user_config.items():
                if module_name in config:
                    # 只更新用户提供的字段
                    config[module_name].update(module_config)
                else:
                    # 新模块，直接添加
                    config[module_name] = module_config
        except Exception as e:
            print(f"[Config] 加载模块配置文件失败: {e}")
    
    return config


def save_module_config(config: Dict[str, Dict[str, Any]]) -> bool:
    """
    保存模块配置到文件
    
    Args:
        config: 模块配置字典
        
    Returns:
        是否保存成功
    """
    config_file = get_module_config_file_path()
    try:
        # 确保目录存在
        config_file.parent.mkdir(parents=True, exist_ok=True)
        
        # 保存配置
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        
        return True
    except Exception as e:
        print(f"[Config] 保存模块配置文件失败: {e}")
        return False