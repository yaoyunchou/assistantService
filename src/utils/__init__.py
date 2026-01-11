"""
工具模块
"""
from .browser_path import CHROME_EXECUTABLE_PATH, find_chrome_executable
from .startup import get_exe_path, is_startup_enabled, add_to_startup, remove_from_startup
from .logger import setup_logger, get_logger, init_logging, get_default_logger
from .module_manager import ModuleManager, get_module_manager
from .config_manager import ConfigManager, get_config_manager

__all__ = [
    'CHROME_EXECUTABLE_PATH',
    'find_chrome_executable',
    'get_exe_path',
    'is_startup_enabled',
    'add_to_startup',
    'remove_from_startup',
    'setup_logger',
    'get_logger',
    'init_logging',
    'get_default_logger',
    'ModuleManager',
    'get_module_manager',
    'ConfigManager',
    'get_config_manager',
]
