"""
配置模块包
"""
# 从父级 config.py 导入 Config 类和函数
# 使用动态导入避免循环导入问题
import sys
from pathlib import Path

# 获取 config.py 的路径
# PyInstaller onedir 模式下数据文件在 sys._MEIPASS（即 _internal/）；
# 开发环境下在 src/ 的上级目录（config/__init__.py → config/ → src/）
if getattr(sys, 'frozen', False):
    _config_py_path = Path(sys._MEIPASS) / 'config.py'
else:
    _parent_dir = Path(__file__).parent.parent
    _config_py_path = _parent_dir / 'config.py'

# 动态导入 config.py 中的内容
if _config_py_path.exists():
    import importlib.util
    _spec = importlib.util.spec_from_file_location("_config_py_module", _config_py_path)
    _config_py_module = importlib.util.module_from_spec(_spec)
    # 使用一个唯一的模块名避免冲突
    _module_name = f"_config_py_{id(_config_py_module)}"
    sys.modules[_module_name] = _config_py_module
    _spec.loader.exec_module(_config_py_module)
    
    # 导出 Config 类和函数
    Config = _config_py_module.Config
    get_module_config_file_path = _config_py_module.get_module_config_file_path
    load_module_config = _config_py_module.load_module_config
    save_module_config = _config_py_module.save_module_config
    
    __all__ = ['Config', 'get_module_config_file_path', 'load_module_config', 'save_module_config']
else:
    raise ImportError(f"config.py not found at {_config_py_path}")