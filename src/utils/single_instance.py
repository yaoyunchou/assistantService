"""
Windows 单实例互斥锁。

通过命名 Mutex 保证同一时刻只有一个应用实例在运行。
若检测到已有实例，自动尝试激活已有窗口后退出。

用法::

    from utils.single_instance import ensure_single_instance
    ensure_single_instance('如意助手')  # 若已有实例则本进程退出
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import sys
from typing import Optional

# Windows API 常量
_ERROR_ALREADY_EXISTS = 0xB7
_SW_SHOW = 5
_SW_RESTORE = 9
_HWND_TOPMOST = -1
_HWND_NOTOPMOST = -2
_SWP_NOMOVE = 0x0002
_SWP_NOSIZE = 0x0001
_GW_OWNER = 4

_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32


def _find_and_activate_window(title: str) -> bool:
    """通过窗口标题查找已有窗口并激活到前台。"""
    hwnd = _user32.FindWindowW(None, title)
    if not hwnd:
        return False

    if _user32.IsIconic(hwnd):
        _user32.ShowWindow(hwnd, _SW_RESTORE)

    _user32.ShowWindow(hwnd, _SW_SHOW)

    # SetForegroundWindow 在 Windows 中有限制（调用进程必须是前台进程），
    # 先短暂置顶再取消，确保窗口可见
    _user32.SetWindowPos(
        hwnd, _HWND_TOPMOST, 0, 0, 0, 0,
        _SWP_NOMOVE | _SWP_NOSIZE,
    )
    _user32.SetWindowPos(
        hwnd, _HWND_NOTOPMOST, 0, 0, 0, 0,
        _SWP_NOMOVE | _SWP_NOSIZE,
    )
    _user32.SetForegroundWindow(hwnd)
    return True


class SingleInstance:
    """
    Windows 命名 Mutex 单实例锁。

    同一个 ``mutex_name`` 全局唯一——第二次创建时
    ``GetLastError() == ERROR_ALREADY_EXISTS``。
    """

    def __init__(self, mutex_name: str):
        self._name = mutex_name
        self._handle: Optional[int] = None
        self._already_running = False

        self._handle = _kernel32.CreateMutexW(None, False, self._name)
        if _kernel32.GetLastError() == _ERROR_ALREADY_EXISTS:
            self._already_running = True
            if self._handle:
                _kernel32.CloseHandle(self._handle)
                self._handle = None

    @property
    def already_running(self) -> bool:
        return self._already_running

    def release(self) -> None:
        if self._handle:
            _kernel32.ReleaseMutex(self._handle)
            _kernel32.CloseHandle(self._handle)
            self._handle = None

    def __del__(self):
        self.release()


def ensure_single_instance(
    window_title: str,
    mutex_name: Optional[str] = None,
) -> SingleInstance:
    """
    确保当前进程为唯一实例；若已有实例在运行则激活其窗口并退出。

    Args:
        window_title: 用于查找已有窗口的标题（需与 pywebview 窗口标题一致）。
        mutex_name: 自定义 Mutex 名称；默认由 window_title 派生。

    Returns:
        ``SingleInstance`` 对象（调用方应持有引用，防止 GC 释放 Mutex）。
    """
    if mutex_name is None:
        mutex_name = f'Global\\{window_title}_SingleInstance'

    instance = SingleInstance(mutex_name)

    if instance.already_running:
        _find_and_activate_window(window_title)
        sys.exit(0)

    return instance
