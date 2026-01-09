"""
配置文件
"""
import os


class Config:
    """应用配置类"""
    # HTTP服务配置
    HOST = '127.0.0.1'
    PORT = 8889
    
    # 浏览器配置
    HEADLESS = True  # 是否使用无头模式
    
    # 查询配置
    MAX_RETRY = 3  # 最大重试次数
    
    # Web界面配置
    APP_NAME = '蕉内工具箱'
    APP_VERSION = '1.0.2'
    AUTO_OPEN_BROWSER = True  # 启动时自动打开浏览器（已废弃，使用 USE_NATIVE_WINDOW）
    USE_NATIVE_WINDOW = True  # 使用原生窗口（True）还是浏览器（False）
    
    # 原生窗口配置
    WINDOW_TITLE = '蕉内工具箱'  # 窗口标题
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