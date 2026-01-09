"""
日志工具模块
支持按天生成独立的日志文件
"""
import logging
import os
from pathlib import Path
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler


class DailyRotatingFileHandler(TimedRotatingFileHandler):
    """
    按天轮转的日志处理器
    每天生成一个新的日志文件
    """
    def __init__(self, filename, when='midnight', interval=1, backupCount=0, encoding='utf-8', delay=False, utc=False):
        """
        初始化按天轮转的日志处理器
        
        Args:
            filename: 日志文件路径
            when: 轮转时间，'midnight'表示每天午夜
            interval: 轮转间隔（天）
            backupCount: 保留的日志文件数量，0表示不删除旧文件
            encoding: 文件编码
            delay: 是否延迟打开文件
            utc: 是否使用UTC时间
        """
        # 确保日志目录存在
        log_dir = Path(filename).parent
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            # 如果权限不足，使用用户目录
            user_log_dir = Path(os.getenv('LOCALAPPDATA', os.path.expanduser('~'))) / 'JNTools' / 'logs'
            user_log_dir.mkdir(parents=True, exist_ok=True)
            filename = str(user_log_dir / Path(filename).name)
            log_dir = user_log_dir
        
        super().__init__(
            filename=filename,
            when=when,
            interval=interval,
            backupCount=backupCount,
            encoding=encoding,
            delay=delay,
            utc=utc
        )


def _get_safe_log_dir(default_log_dir: Path) -> Path:
    """
    获取安全的日志目录（如果默认目录需要管理员权限，则使用用户目录）
    
    Args:
        default_log_dir: 默认日志目录
        
    Returns:
        安全的日志目录路径
    """
    # 检查是否在 Program Files 目录下
    try:
        default_str = str(default_log_dir.resolve())
        program_files_paths = [
            os.path.expandvars(r'%ProgramFiles%'),
            os.path.expandvars(r'%ProgramFiles(x86)%'),
            r'C:\Program Files',
            r'C:\Program Files (x86)'
        ]
        
        # 检查默认目录是否在 Program Files 下
        is_in_program_files = any(
            default_str.lower().startswith(pf.lower()) 
            for pf in program_files_paths 
            if pf
        )
        
        # 如果不在 Program Files 下，尝试使用默认目录
        if not is_in_program_files:
            try:
                # 尝试创建目录以测试权限
                default_log_dir.mkdir(parents=True, exist_ok=True)
                # 尝试创建一个测试文件
                test_file = default_log_dir / '.test_write'
                try:
                    test_file.write_text('test')
                    test_file.unlink()
                    return default_log_dir
                except (PermissionError, OSError):
                    # 无法写入，使用用户目录
                    pass
            except (PermissionError, OSError):
                # 无法创建目录，使用用户目录
                pass
        else:
            # 在 Program Files 下，直接使用用户目录
            pass
    except Exception:
        # 任何异常都使用用户目录
        pass
    
    # 使用用户目录（LOCALAPPDATA）
    user_log_dir = Path(os.getenv('LOCALAPPDATA', os.path.expanduser('~'))) / 'JNTools' / 'logs'
    user_log_dir.mkdir(parents=True, exist_ok=True)
    return user_log_dir


def setup_logger(name: str = None, log_dir: str = None, level: int = logging.INFO) -> logging.Logger:
    """
    设置日志记录器
    
    Args:
        name: 日志记录器名称，默认为根记录器
        log_dir: 日志文件目录，默认为项目根目录下的logs文件夹
        level: 日志级别，默认为INFO
    
    Returns:
        配置好的日志记录器
    """
    # 获取根日志记录器（用于配置全局处理器）
    root_logger = logging.getLogger()
    
    # 如果根记录器已经有处理器，说明已经初始化过，直接返回请求的logger
    if root_logger.handlers:
        return logging.getLogger(name) if name else root_logger
    
    # 确定日志目录
    if log_dir is None:
        # 获取项目根目录（src的父目录）
        current_file = Path(__file__)
        project_root = current_file.parent.parent.parent
        default_log_dir = project_root / 'logs'
    else:
        default_log_dir = Path(log_dir)
    
    # 获取安全的日志目录（自动处理权限问题）
    log_dir = _get_safe_log_dir(default_log_dir)
    
    # 日志文件名格式：app_YYYY-MM-DD.log
    log_filename = log_dir / f"app_{datetime.now().strftime('%Y-%m-%d')}.log"
    
    # 创建文件处理器（按天轮转）
    file_handler = DailyRotatingFileHandler(
        filename=str(log_filename),
        when='midnight',
        interval=1,
        backupCount=0,  # 不自动删除旧日志，保留所有历史日志
        encoding='utf-8'
    )
    file_handler.setLevel(level)
    
    # 文件日志格式：[时间] [级别] [模块] 消息
    file_formatter = logging.Formatter(
        '[%(asctime)s] [%(levelname)-8s] [%(name)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    
    # 创建控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    
    # 控制台日志格式：[模块] 消息（简化格式，便于阅读）
    console_formatter = logging.Formatter(
        '[%(name)s] %(message)s'
    )
    console_handler.setFormatter(console_formatter)
    
    # 只给根记录器添加处理器，子记录器会自动继承
    root_logger.setLevel(level)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    
    # 返回请求的日志记录器
    return logging.getLogger(name) if name else root_logger


def get_logger(name: str = None) -> logging.Logger:
    """
    获取日志记录器（如果已配置则返回，否则创建新的）
    
    Args:
        name: 日志记录器名称
    
    Returns:
        日志记录器
    """
    # 检查根记录器是否已初始化
    root_logger = logging.getLogger()
    if not root_logger.handlers:
        # 如果根记录器没有处理器，进行初始化
        setup_logger()
    
    # 返回请求的日志记录器（会自动继承根记录器的配置）
    return logging.getLogger(name) if name else root_logger


# 默认日志记录器
_default_logger = None


def init_logging(log_dir: str = None, level: int = logging.INFO):
    """
    初始化全局日志系统
    
    Args:
        log_dir: 日志文件目录
        level: 日志级别
    """
    global _default_logger
    _default_logger = setup_logger(log_dir=log_dir, level=level)
    return _default_logger


def get_default_logger() -> logging.Logger:
    """
    获取默认日志记录器
    
    Returns:
        默认日志记录器
    """
    global _default_logger
    if _default_logger is None:
        _default_logger = setup_logger()
    return _default_logger
