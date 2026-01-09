"""
功能模块配置定义
"""
from typing import Dict, Any

# 默认模块配置
DEFAULT_MODULE_CONFIG: Dict[str, Dict[str, Any]] = {
    'logistics': {
        'enabled': False,  # 是否启用
        'init_on_startup': False,  # 启动时初始化
        'requires_browser': True,  # 需要浏览器
        'memory_mb': 150,  # 预估内存占用（MB）
        'description': '快递查询工具',
        'display_name': '快递查询',
        'icon': '📦',
        'category': 'tools'
    },
    'script_executor': {
        'enabled': True,
        'init_on_startup': True,  # 脚本执行器轻量，启动时初始化
        'requires_browser': False,
        'memory_mb': 20,
        'description': 'Python脚本执行器',
        'display_name': '脚本执行',
        'icon': '🐍',
        'category': 'tools'
    },
    'resource_monitor': {
        'enabled': True,
        'init_on_startup': True,
        'requires_browser': False,
        'memory_mb': 10,
        'description': '资源监控',
        'display_name': '资源监控',
        'icon': '📊',
        'category': 'system'
    }
}


def get_default_module_config() -> Dict[str, Dict[str, Any]]:
    """
    获取默认模块配置
    
    Returns:
        默认模块配置字典
    """
    return DEFAULT_MODULE_CONFIG.copy()


def validate_module_config(config: Dict[str, Any]) -> bool:
    """
    验证模块配置是否有效
    
    Args:
        config: 模块配置字典
        
    Returns:
        是否有效
    """
    required_fields = ['enabled', 'init_on_startup', 'requires_browser', 'memory_mb']
    for field in required_fields:
        if field not in config:
            return False
    
    # 验证类型
    if not isinstance(config['enabled'], bool):
        return False
    if not isinstance(config['init_on_startup'], bool):
        return False
    if not isinstance(config['requires_browser'], bool):
        return False
    if not isinstance(config['memory_mb'], (int, float)) or config['memory_mb'] < 0:
        return False
    
    return True
