"""
Windows：部分环境「已安装」VC++ 运行库但 System32 未落盘 msvcp140.dll 等，
导致 greenlet / Playwright 原生扩展加载失败。在导入这些扩展前补充 DLL 搜索路径。
彻底修复仍应在「程序和功能」中对 Microsoft Visual C++ x64 运行库执行修复或重装（管理员）。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def add_dll_search_paths_if_needed() -> None:
    if sys.platform != "win32":
        return
    add_dll = getattr(os, "add_dll_directory", None)
    if add_dll is None:
        return
    system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    if (system_root / "System32" / "msvcp140.dll").is_file():
        return
    # 与系统其他组件同版本的 CRT，常见于此目录（随 Edge WebView 部署）
    edge_crt = system_root / "System32" / "Microsoft-Edge-WebView"
    if edge_crt.is_dir() and any(edge_crt.glob("msvcp140.dll")):
        add_dll(str(edge_crt))
