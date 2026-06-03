"""
路径辅助工具
提供安全的数据目录获取功能，避免权限问题
"""
import os
import sys
from pathlib import Path
from typing import Optional


def get_user_data_dir(app_name: str = '如意助手') -> Path:
    """
    获取用户数据目录

    Windows: %LOCALAPPDATA%\如意助手
    Linux/Mac: ~/.local/share/如意助手 或 ~/如意助手

    Args:
        app_name: 应用名称，默认为 '如意助手'
        
    Returns:
        用户数据目录路径
    """
    if sys.platform == 'win32':
        # Windows: 使用 LOCALAPPDATA
        base_dir = Path(os.getenv('LOCALAPPDATA', os.path.expanduser('~')))
        user_dir = base_dir / app_name
    else:
        # Linux/Mac: 使用 .local/share 或直接用户目录
        base_dir = Path(os.path.expanduser('~'))
        local_share = base_dir / '.local' / 'share'
        if local_share.exists() or not (base_dir / app_name).exists():
            user_dir = local_share / app_name
        else:
            user_dir = base_dir / app_name
    
    # 确保目录存在
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir


def get_browser_data_dir(app_name: str = '如意助手') -> Path:
    """
    获取浏览器用户数据目录（固定持久化缓存）。

    生产与开发使用不同子目录，避免 dev.py 与 main/打包版同时运行时
    争抢同一 Chromium profile（SingletonLock 导致互踢、登录态错乱）。

    - production: browser_data
    - development: browser_data_dev

    Windows:
      生产 %LOCALAPPDATA%\\如意助手\\browser_data
      开发 %LOCALAPPDATA%\\如意助手\\browser_data_dev

    Args:
        app_name: 应用名称，默认为 '如意助手'

    Returns:
        浏览器数据目录路径
    """
    env = (os.getenv('APP_ENV') or 'production').strip().lower()
    subdir = 'browser_data_dev' if env == 'development' else 'browser_data'
    browser_dir = get_user_data_dir(app_name) / subdir
    browser_dir.mkdir(parents=True, exist_ok=True)
    return browser_dir


def get_safe_data_path(relative_path: str, app_name: str = '如意助手') -> Path:
    """
    获取安全的数据文件路径
    
    优先尝试使用项目目录，如果没有写入权限（如安装在Program Files），
    则使用用户数据目录。
    
    Args:
        relative_path: 相对路径，如 'cookies/pinduoduo_cookies.json'
        app_name: 应用名称
        
    Returns:
        安全的绝对路径
    """
    # 获取项目根目录
    if getattr(sys, 'frozen', False):
        # 打包后的exe环境
        project_root = Path(sys.executable).parent
    else:
        # 开发环境
        project_root = Path(__file__).parent.parent.parent
    
    # 尝试使用项目目录
    project_path = project_root / relative_path
    
    # 检查是否在 Program Files 下或者没有写入权限
    try:
        project_str = str(project_root.resolve())
        program_files_paths = [
            os.path.expandvars(r'%ProgramFiles%'),
            os.path.expandvars(r'%ProgramFiles(x86)%'),
            r'C:\Program Files',
            r'C:\Program Files (x86)'
        ]
        
        # 检查是否在 Program Files 下
        is_in_program_files = any(
            project_str.lower().startswith(pf.lower()) 
            for pf in program_files_paths 
            if pf
        )
        
        # 如果不在 Program Files 下，尝试测试写入权限
        if not is_in_program_files:
            # 确保父目录存在
            project_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 测试写入权限
            test_file = project_path.parent / '.test_write'
            try:
                test_file.write_text('test')
                test_file.unlink()
                # 有写入权限，使用项目目录
                return project_path
            except (PermissionError, OSError):
                pass
    
    except Exception:
        pass
    
    # 使用用户数据目录
    user_dir = get_user_data_dir(app_name)
    return user_dir / relative_path


def get_project_root() -> Path:
    """
    获取项目根目录
    
    Returns:
        项目根目录路径
    """
    if getattr(sys, 'frozen', False):
        # 打包后的exe环境
        return Path(sys.executable).parent
    else:
        # 开发环境
        return Path(__file__).parent.parent.parent


def get_bundled_data_root() -> Path:
    """获取 PyInstaller 打包时通过 datas 嵌入的只读资源根目录。

    PyInstaller 6 onedir 模式下 datas 放在 ``exe_dir/_internal/``；
    开发环境等价于项目根目录。
    """
    if getattr(sys, 'frozen', False):
        exe_dir = Path(sys.executable).parent
        internal = exe_dir / '_internal'
        if internal.is_dir():
            return internal
        return exe_dir
    return Path(__file__).parent.parent.parent
