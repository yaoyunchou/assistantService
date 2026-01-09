"""
开机自启动管理工具模块
"""
import sys
import os
import winreg
from pathlib import Path

# 启动项注册表键名
STARTUP_REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
STARTUP_APP_NAME = "RuyiAssistant"  # 如意助手


def get_exe_path():
    """获取当前exe文件的完整路径"""
    if getattr(sys, 'frozen', False):
        # 如果是打包后的exe
        return sys.executable
    else:
        # 如果是开发环境，返回 main.py 的路径
        # utils -> src -> main.py
        main_path = Path(__file__).parent.parent / 'main.py'
        return str(main_path.absolute())


def is_startup_enabled():
    """检查是否已添加到开机启动"""
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            STARTUP_REG_KEY,
            0,
            winreg.KEY_READ
        )
        try:
            value, _ = winreg.QueryValueEx(key, STARTUP_APP_NAME)
            winreg.CloseKey(key)
            return True
        except FileNotFoundError:
            winreg.CloseKey(key)
            return False
    except Exception as e:
        # 使用logger而不是print，但这里可能logger还没初始化，所以保持print
        print(f"检查启动项失败: {e}")
        return False


def add_to_startup():
    """添加到开机启动"""
    try:
        exe_path = get_exe_path()
        # 确保路径用引号包裹，以处理路径中的空格
        exe_path_quoted = f'"{exe_path}"'
        
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            STARTUP_REG_KEY,
            0,
            winreg.KEY_WRITE
        )
        winreg.SetValueEx(key, STARTUP_APP_NAME, 0, winreg.REG_SZ, exe_path_quoted)
        winreg.CloseKey(key)
        print(f"已添加到开机启动: {exe_path_quoted}")
        return True
    except Exception as e:
        print(f"添加到启动项失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def remove_from_startup():
    """从开机启动中移除"""
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            STARTUP_REG_KEY,
            0,
            winreg.KEY_WRITE
        )
        try:
            winreg.DeleteValue(key, STARTUP_APP_NAME)
            winreg.CloseKey(key)
            print("已从开机启动中移除")
            return True
        except FileNotFoundError:
            winreg.CloseKey(key)
            print("启动项不存在，无需移除")
            return True
    except Exception as e:
        print(f"从启动项移除失败: {e}")
        import traceback
        traceback.print_exc()
        return False
