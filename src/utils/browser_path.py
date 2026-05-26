"""
浏览器路径查找工具模块
"""
import sys
import os
import json
from pathlib import Path

# 全局变量：存储 chrome.exe 路径
CHROME_EXECUTABLE_PATH = None


def _get_playwright_expected_revision() -> str | None:
    """从 playwright 包的 browsers.json 获取当前版本期望的 Chromium revision 号"""
    try:
        import playwright
        pkg_dir = Path(playwright.__file__).parent
        browsers_json = pkg_dir / 'driver' / 'package' / 'browsers.json'
        if browsers_json.exists():
            data = json.loads(browsers_json.read_text(encoding='utf-8'))
            for browser in data.get('browsers', []):
                if browser.get('name') == 'chromium':
                    return str(browser['revision'])
    except Exception:
        pass
    return None


def _find_chrome_in_dir(chromium_dir: Path) -> str | None:
    """在指定 chromium 目录中查找 chrome.exe，返回路径字符串或 None"""
    candidates = [
        chromium_dir / 'chrome-win64' / 'chrome.exe',
        chromium_dir / 'chrome-win' / 'chrome.exe',
        chromium_dir / 'chrome-headless-shell-win64' / 'chrome-headless-shell.exe',
    ]
    for p in candidates:
        if p.exists():
            return str(p.resolve())
    return None


def _search_chromium_in(base_dir: Path, expected_revision: str | None) -> str | None:
    """
    在 base_dir 中按优先级查找 Chromium：
    1. 与 playwright 期望 revision 精确匹配的目录
    2. revision 最新的目录（数字最大）
    3. 扁平布局（chrome-win64/chrome.exe）
    返回找到的 chrome.exe 路径，同时设置 PLAYWRIGHT_BROWSERS_PATH。
    """
    if not base_dir.exists():
        return None

    chromium_dirs = sorted(base_dir.glob('chromium-*'), key=lambda p: p.name)

    # 优先精确匹配 playwright 期望版本
    if expected_revision and chromium_dirs:
        exact = base_dir / f'chromium-{expected_revision}'
        if exact in chromium_dirs or exact.exists():
            exe = _find_chrome_in_dir(exact)
            if exe:
                os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(base_dir.resolve())
                return exe

    # 其次取 revision 号最大的目录
    if chromium_dirs:
        def _rev_num(p: Path) -> int:
            try:
                return int(p.name.split('-', 1)[1])
            except (IndexError, ValueError):
                return 0
        chromium_dirs_sorted = sorted(chromium_dirs, key=_rev_num, reverse=True)
        for chromium_dir in chromium_dirs_sorted:
            exe = _find_chrome_in_dir(chromium_dir)
            if exe:
                rev = chromium_dir.name
                if expected_revision and f'-{expected_revision}' not in chromium_dir.name:
                    print(f"[BrowserPath] ⚠ 版本不匹配（期望 chromium-{expected_revision}，实际使用 {rev}）")
                os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(base_dir.resolve())
                return exe

    # 扁平布局：playwright_drivers/chrome-win64/chrome.exe
    for dirname in ('chrome-win64', 'chrome-win'):
        flat = base_dir / dirname / 'chrome.exe'
        if flat.is_file():
            os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(base_dir.resolve())
            return str(flat.resolve())  

    return None


def find_chrome_executable():
    """查找 chrome.exe 路径，优先从 exe 同目录的 playwright_drivers 查找"""
    global CHROME_EXECUTABLE_PATH

    if getattr(sys, 'frozen', False):
        exe_dir = Path(sys.executable).parent
        print(f"[BrowserPath] 打包环境，exe目录: {exe_dir}")
    else:
        exe_dir = Path(__file__).parent.parent.parent
        print(f"[BrowserPath] 开发环境，项目根目录: {exe_dir}")

    expected_revision = _get_playwright_expected_revision()
    if expected_revision:
        print(f"[BrowserPath] playwright 期望 Chromium revision: {expected_revision}")

    # 1. 优先查找项目/打包目录下的 playwright_drivers
    playwright_drivers_dir = exe_dir / 'playwright_drivers'
    print(f"[BrowserPath] 查找 playwright_drivers 目录: {playwright_drivers_dir}")
    exe = _search_chromium_in(playwright_drivers_dir, expected_revision)
    if exe:
        CHROME_EXECUTABLE_PATH = exe
        print(f"[BrowserPath] [OK] 找到浏览器驱动: {CHROME_EXECUTABLE_PATH}")
        print(f"[BrowserPath] [OK] PLAYWRIGHT_BROWSERS_PATH: {os.environ.get('PLAYWRIGHT_BROWSERS_PATH')}")
        return CHROME_EXECUTABLE_PATH

    # 2. 回退到系统 ms-playwright 目录
    system_playwright = Path.home() / 'AppData' / 'Local' / 'ms-playwright'
    print(f"[BrowserPath] 尝试系统 Playwright 目录: {system_playwright}")
    exe = _search_chromium_in(system_playwright, expected_revision)
    if exe:
        CHROME_EXECUTABLE_PATH = exe
        print(f"[BrowserPath] [OK] 使用系统安装的浏览器驱动: {CHROME_EXECUTABLE_PATH}")
        print(f"[BrowserPath] [OK] PLAYWRIGHT_BROWSERS_PATH: {os.environ.get('PLAYWRIGHT_BROWSERS_PATH')}")
        return CHROME_EXECUTABLE_PATH

    print(f"[BrowserPath] ✗ 未找到浏览器驱动")
    print(f"[BrowserPath] 请运行: playwright install chromium")
    return None
