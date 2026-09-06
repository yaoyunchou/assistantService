"""
开机自启动管理工具模块

Windows：通过注册表 HKCU\\...\\Run 管理。
非 Windows：提供 no-op stub，避免 import winreg 导致 Flask 无法启动。
"""
import sys
from pathlib import Path

STARTUP_REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
STARTUP_APP_NAME = "RuyiAssistant"  # 如意助手

_IS_WINDOWS = sys.platform == 'win32'


def get_exe_path():
    """获取当前 exe 或入口脚本路径（供 /startup API 展示）。"""
    if getattr(sys, 'frozen', False):
        return sys.executable
    src_dir = Path(__file__).parent.parent
    for name in ('web.py', 'main.py'):
        candidate = src_dir / name
        if candidate.is_file():
            return str(candidate.absolute())
    return str((src_dir / 'main.py').absolute())


if _IS_WINDOWS:
    import winreg

    def is_startup_enabled():
        """检查是否已添加到开机启动"""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                STARTUP_REG_KEY,
                0,
                winreg.KEY_READ,
            )
            try:
                winreg.QueryValueEx(key, STARTUP_APP_NAME)
                winreg.CloseKey(key)
                return True
            except FileNotFoundError:
                winreg.CloseKey(key)
                return False
        except Exception as e:
            print(f"检查启动项失败: {e}")
            return False

    def add_to_startup():
        """添加到开机启动"""
        try:
            exe_path = get_exe_path()
            exe_path_quoted = f'"{exe_path}"'

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                STARTUP_REG_KEY,
                0,
                winreg.KEY_WRITE,
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
                winreg.KEY_WRITE,
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

else:

    def is_startup_enabled():
        return False

    def add_to_startup():
        print("当前平台不支持注册表开机自启动（仅 Windows）")
        return False

    def remove_from_startup():
        print("当前平台不支持注册表开机自启动（仅 Windows）")
        return False
