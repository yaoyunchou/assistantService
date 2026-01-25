"""
配置文件
"""
import os
import json
import sys
from pathlib import Path
from typing import Dict, Any, Optional

# 加载环境变量
try:
    from dotenv import load_dotenv
    # 获取项目根目录
    if getattr(sys, 'frozen', False):
        # 打包后的exe环境
        root_dir = Path(sys.executable).parent
    else:
        # 开发环境
        root_dir = Path(__file__).parent.parent
    
    # 加载.env文件
    env_file = root_dir / '.env'
    if env_file.exists():
        load_dotenv(env_file)
        print(f"[Config] 已加载环境变量文件: {env_file}")
    else:
        print(f"[Config] 未找到.env文件: {env_file}")
except ImportError:
    print("[Config] python-dotenv 未安装，跳过环境变量加载")
except Exception as e:
    print(f"[Config] 加载环境变量失败: {e}")


class Config:
    """应用配置类"""
    # HTTP服务配置
    HOST = '127.0.0.1'
    PORT = 8887  # 端口范围：1024-65535
    
    # 浏览器配置
    # HEADLESS = True  # 是否使用无头模式
    HEADLESS = False  # 是否使用无头模式

    
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
    
    # 拼多多配置
    # Cookie和状态文件将保存在用户数据目录，避免权限问题
    PINDUODUO_COOKIE_PATH = None  # None表示使用默认的用户数据目录
    PINDUODUO_STATUS_PATH = None  # None表示使用默认的用户数据目录
    # PINDUODUO_TARGET_URL = 'https://mms.pinduoduo.com/home'
    PINDUODUO_TARGET_URL = 'https://www.doubao.com/chat/28899721294850?open_from_ext=1'

    
    # 飞书配置
    FEISHU_ENABLED = True  # 是否启用飞书通知


# 在Config类定义后，尝试从配置文件加载配置
def _load_config_from_file():
    """从配置文件加载配置（如果存在）"""
    try:
        # 延迟导入避免循环导入
        from utils.config_manager import get_config_manager
        config_manager = get_config_manager()
        saved_config = config_manager.load_config()
        
        # 应用已保存的配置
        if saved_config:
            if 'host' in saved_config:
                Config.HOST = str(saved_config['host'])
            if 'port' in saved_config:
                port = int(saved_config['port'])
                if 1024 <= port <= 65535:
                    Config.PORT = port
            if 'headless' in saved_config:
                Config.HEADLESS = bool(saved_config['headless'])
            if 'window_width' in saved_config:
                Config.WINDOW_WIDTH = int(saved_config['window_width'])
            if 'window_height' in saved_config:
                Config.WINDOW_HEIGHT = int(saved_config['window_height'])
            if 'tray_enabled' in saved_config:
                Config.TRAY_ENABLED = bool(saved_config['tray_enabled'])
            if 'use_native_window' in saved_config:
                Config.USE_NATIVE_WINDOW = bool(saved_config['use_native_window'])
            if 'log_level' in saved_config:
                Config.LOG_LEVEL = str(saved_config['log_level'])
            if 'browser_lazy_init' in saved_config:
                Config.BROWSER_LAZY_INIT = bool(saved_config['browser_lazy_init'])
            if 'browser_idle_timeout' in saved_config:
                Config.BROWSER_IDLE_TIMEOUT = int(saved_config['browser_idle_timeout'])
            if 'enable_resource_monitor' in saved_config:
                Config.ENABLE_RESOURCE_MONITOR = bool(saved_config['enable_resource_monitor'])
            if 'max_memory_mb' in saved_config:
                Config.MAX_MEMORY_MB = int(saved_config['max_memory_mb'])
    except Exception:
        # 如果加载失败，使用默认配置
        pass

# 延迟加载，避免循环导入
try:
    _load_config_from_file()
except:
    pass


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
    # 延迟导入避免循环导入
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