"""
浏览器路径查找工具模块
"""
import sys
import os
from pathlib import Path

# 全局变量：存储 chrome.exe 路径
CHROME_EXECUTABLE_PATH = None


def find_chrome_executable():
    """查找 chrome.exe 路径，优先从 exe 同目录查找"""
    global CHROME_EXECUTABLE_PATH
    
    if getattr(sys, 'frozen', False):
        # 如果是打包后的exe，从exe同目录查找
        # 注意：PyInstaller onedir 模式下，exe 在 dist/如意助手/ 目录
        exe_dir = Path(sys.executable).parent
        
        # 如果是 onedir 模式，exe 在 dist/如意助手/，playwright_drivers 也在 dist/如意助手/playwright_drivers/
        # 我们需要在 exe 同目录下查找 playwright_drivers
        print(f"[BrowserPath] 打包环境，exe目录: {exe_dir}")
    else:
        # 开发环境，从项目根目录查找（utils -> src -> 项目根目录）
        exe_dir = Path(__file__).parent.parent.parent
        print(f"[BrowserPath] 开发环境，项目根目录: {exe_dir}")
    
    # 查找 playwright_drivers 目录（在 exe 同目录）
    playwright_drivers_dir = exe_dir / 'playwright_drivers'
    print(f"[BrowserPath] 查找 playwright_drivers 目录: {playwright_drivers_dir}")
    print(f"[BrowserPath] 目录存在: {playwright_drivers_dir.exists()}")
    
    if playwright_drivers_dir.exists():
        # 查找 chromium 目录
        chromium_dirs = list(playwright_drivers_dir.glob('chromium-*'))
        if not chromium_dirs:
            chromium_dirs = list(playwright_drivers_dir.glob('chromium_headless_shell-*'))
        
        print(f"[BrowserPath] 找到 chromium 目录数量: {len(chromium_dirs)}")
        
        if chromium_dirs:
            chromium_dir = chromium_dirs[0]
            print(f"[BrowserPath] 使用 chromium 目录: {chromium_dir}")
            
            # 查找 chrome.exe
            # 可能的路径：chromium-XXXX/chrome-win/chrome.exe 或 chromium-XXXX/chrome-win64/chrome.exe
            # 或 chromium_headless_shell-XXXX/chrome-headless-shell-win64/chrome-headless-shell.exe
            chrome_paths = [
                chromium_dir / 'chrome-win' / 'chrome.exe',
                chromium_dir / 'chrome-win64' / 'chrome.exe',
                chromium_dir / 'chrome-headless-shell-win64' / 'chrome-headless-shell.exe',
            ]
            
            for chrome_path in chrome_paths:
                if chrome_path.exists():
                    CHROME_EXECUTABLE_PATH = str(chrome_path.absolute())
                    print(f"[BrowserPath] ✓ 找到浏览器驱动: {CHROME_EXECUTABLE_PATH}")
                    
                    # 重要：设置环境变量，让 Playwright 知道浏览器位置
                    # PLAYWRIGHT_BROWSERS_PATH 应该指向包含 chromium-* 目录的父目录
                    browsers_path = str(playwright_drivers_dir.absolute())
                    os.environ['PLAYWRIGHT_BROWSERS_PATH'] = browsers_path
                    print(f"[BrowserPath] ✓ 设置 PLAYWRIGHT_BROWSERS_PATH: {browsers_path}")
                    
                    # 同时设置 PLAYWRIGHT_DRIVER_PATH（如果需要）
                    # 这个环境变量告诉 Playwright 驱动的位置
                    return CHROME_EXECUTABLE_PATH
            else:
                print(f"[BrowserPath] ✗ 在 {chromium_dir} 中未找到 chrome.exe")
                print(f"[BrowserPath] 尝试的路径:")
                for cp in chrome_paths:
                    print(f"  - {cp} (存在: {cp.exists()})")

        # 手工解压 chrome-win64.zip 常见布局：直接放在 playwright_drivers/chrome-win64/，无 chromium-* 包一层
        for dirname in ('chrome-win64', 'chrome-win'):
            flat = playwright_drivers_dir / dirname / 'chrome.exe'
            if flat.is_file():
                CHROME_EXECUTABLE_PATH = str(flat.resolve())
                browsers_path = str(playwright_drivers_dir.resolve())
                os.environ['PLAYWRIGHT_BROWSERS_PATH'] = browsers_path
                print(f"[BrowserPath] ✓ 找到浏览器驱动（playwright_drivers/{dirname}）: {CHROME_EXECUTABLE_PATH}")
                print(f"[BrowserPath] ✓ 设置 PLAYWRIGHT_BROWSERS_PATH: {browsers_path}")
                return CHROME_EXECUTABLE_PATH
    
    # 如果没找到，尝试使用系统安装的
    user_home = Path.home()
    system_playwright = user_home / 'AppData' / 'Local' / 'ms-playwright'
    print(f"[BrowserPath] 尝试系统 Playwright 目录: {system_playwright}")
    print(f"[BrowserPath] 系统目录存在: {system_playwright.exists()}")
    
    if system_playwright.exists():
        chromium_dirs = list(system_playwright.glob('chromium-*'))
        if not chromium_dirs:
            chromium_dirs = list(system_playwright.glob('chromium_headless_shell-*'))
        
        if chromium_dirs:
            chromium_dir = chromium_dirs[0]
            print(f"[BrowserPath] 找到系统 chromium 目录: {chromium_dir}")
            chrome_paths = [
                chromium_dir / 'chrome-win' / 'chrome.exe',
                chromium_dir / 'chrome-win64' / 'chrome.exe',
                chromium_dir / 'chrome-headless-shell-win64' / 'chrome-headless-shell.exe',
            ]
            
            for chrome_path in chrome_paths:
                if chrome_path.exists():
                    CHROME_EXECUTABLE_PATH = str(chrome_path)
                    print(f"[BrowserPath] ✓ 使用系统安装的浏览器驱动: {CHROME_EXECUTABLE_PATH}")
                    
                    # 设置环境变量
                    browsers_path = str(system_playwright.absolute())
                    os.environ['PLAYWRIGHT_BROWSERS_PATH'] = browsers_path
                    print(f"[BrowserPath] ✓ 设置 PLAYWRIGHT_BROWSERS_PATH: {browsers_path}")
                    return CHROME_EXECUTABLE_PATH
    
    print(f"[BrowserPath] ✗ 未找到浏览器驱动")
    print(f"[BrowserPath] 请确保 playwright_drivers 目录存在于: {exe_dir / 'playwright_drivers'}")
    print(f"[BrowserPath] 或者运行: playwright install chromium")
    return None
