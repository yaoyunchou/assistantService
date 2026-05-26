# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller打包配置文件
用于打包桌面应用主程序
"""

import sys
import shutil
from pathlib import Path

# 打包后的应用名称（exe 文件名与 dist 下文件夹名）
APP_NAME = '如意助手'

# 项目根目录
project_root = Path(SPECPATH)

# 源代码目录
src_dir = project_root / 'src'

# 打包前清理：删除 dist 文件夹
def force_remove(path):
    """强制删除文件或文件夹（处理文件被占用的情况）"""
    import os
    import stat
    import time
    
    if not path.exists():
        return True
    
    # 如果是文件，直接删除
    if path.is_file():
        try:
            # 尝试修改文件属性为可写
            os.chmod(str(path), stat.S_IWRITE)
            path.unlink()
            return True
        except Exception as e:
            print(f"  警告: 无法删除文件 {path}: {e}")
            return False
    
    # 如果是文件夹，递归删除
    try:
        # 先修改所有文件的权限
        for root, dirs, files in os.walk(str(path)):
            for d in dirs:
                try:
                    os.chmod(os.path.join(root, d), stat.S_IWRITE | stat.S_IREAD | stat.S_IEXEC)
                except:
                    pass
            for f in files:
                try:
                    file_path = os.path.join(root, f)
                    os.chmod(file_path, stat.S_IWRITE)
                except:
                    pass
        
        # 尝试删除
        shutil.rmtree(str(path), ignore_errors=False)
        return True
    except PermissionError:
        # 如果权限错误，等待一小段时间后重试
        print(f"  文件可能被占用，等待后重试...")
        time.sleep(0.5)
        try:
            shutil.rmtree(str(path), ignore_errors=True)
            # 再次尝试，如果还是失败，使用更强制的方式
            if path.exists():
                import subprocess
                if sys.platform == 'win32':
                    # Windows: 使用 rmdir /s /q 强制删除
                    subprocess.run(['cmd', '/c', 'rmdir', '/s', '/q', str(path)], 
                                 shell=False, capture_output=True)
                else:
                    # Linux/Mac: 使用 rm -rf
                    subprocess.run(['rm', '-rf', str(path)], 
                                 shell=False, capture_output=True)
            return not path.exists()
        except Exception as e:
            print(f"  强制删除失败: {e}")
            return False
    except Exception as e:
        print(f"  删除失败: {e}")
        return False

def clean_dist_folder():
    """清理 dist 文件夹（强制删除，包括被占用的文件）"""
    dist_dir = project_root / 'dist'
    if dist_dir.exists():
        print("\n" + "="*60)
        print("正在清理 dist 文件夹...")
        print("="*60)
        
        # 特别处理 logs 文件夹（可能被日志文件占用）
        logs_dir = dist_dir / APP_NAME / 'logs'
        if logs_dir.exists():
            print(f"正在强制删除 logs 文件夹: {logs_dir}")
            if force_remove(logs_dir):
                print(f"✓ 已删除 logs 文件夹")
            else:
                print(f"✗ 删除 logs 文件夹失败，但继续清理其他文件")
        
        # 删除整个 dist 文件夹
        print(f"正在删除 dist 文件夹: {dist_dir}")
        if force_remove(dist_dir):
            print(f"✓ 已删除 dist 文件夹: {dist_dir}")
            print("="*60 + "\n")
            return True
        else:
            print(f"✗ 删除 dist 文件夹失败，但继续打包流程")
            print("="*60 + "\n")
            return False
    else:
        print("\n" + "="*60)
        print("dist 文件夹不存在，无需清理")
        print("="*60 + "\n")
        return True

# 执行清理
clean_dist_folder()

a = Analysis(
    [str(src_dir / 'main.py')],
    pathex=[str(src_dir)],
    binaries=[],
    datas=[
        # config 包通过路径动态加载同级 config.py，需显式打入包（否则打包后找不到）
        (str(src_dir / 'config.py'), '.'),
        # 模块开关（需浏览器）；缺省时用代码内 DEFAULT_MODULE_CONFIG，但打入文件便于用户修改
        (str(project_root / 'module_config.toml'), '.'),
        # 库存商品信息→商品名称映射（库存同步 / 映射页）；与 exe 同目录 config/ 可继续编辑
        (str(project_root / 'config' / 'inventory_product_mapping.json'), 'config'),
        # 定时任务默认列表（与仓库 scheduler/tasks.toml 一致；运行时可继续改 exe 旁 scheduler/tasks.toml）
        (str(project_root / 'scheduler' / 'tasks.toml'), 'scheduler'),
        # Playwright 注入脚本（erp_order_sync / order_address_sync 通过 __file__ 引用）
        (str(src_dir / 'spider' / 'pinduoduo' / 'scripts'), 'spider/pinduoduo/scripts'),
        # playwright-stealth 运行时读取的 JS 资源文件（打包时必须包含，否则启动报 FileNotFoundError）
        (str(project_root / '.venv' / 'Lib' / 'site-packages' / 'playwright_stealth' / 'js'), 'playwright_stealth/js'),
        # Web模板文件
        (str(src_dir / 'web' / 'templates'), 'web/templates'),
        # 静态资源文件
        (str(src_dir / 'static'), 'static'),
    ],
    hiddenimports=[
        'pystray',
        'PIL',
        'PIL._tkinter_finder',
        'pystray._win32',
        'pystray._darwin',
        'pystray._x11',
        'flask',
        'playwright',
        'playwright.sync_api',
        'playwright_stealth',
        'playwright_stealth.stealth',
        'spider.logistics_query',
        'spider.query_manager',
        'spider.waybill_extractor',
        'tools.base',
        'tools.manager',
        'tools.spider_tool',
        'tray.tray_icon',
        'utils.browser_path',
        'utils.startup',
        'web.routes',
        'webview',
        'webview.platforms',
        'webview.platforms.winforms',
        'webview.platforms.edgechromium',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

# 应用图标路径（优先使用logo_default.jpg，如果不存在则使用默认）
# PyInstaller支持直接使用JPG/PNG格式，会自动转换为ICO格式
icon_path = None
possible_icon_paths = [
    project_root / 'src' / 'static' / 'images' / 'log_default.png',
    project_root / 'src' / 'static' / 'images' / 'logo_default.jpg',
    project_root / 'src' / 'static' / 'images' / 'icon.ico',
    project_root / 'src' / 'static' / 'images' / 'icon.png',
]

for path in possible_icon_paths:
    if path.exists():
        icon_path = str(path)
        print(f"使用应用图标: {icon_path}")
        break

exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # 不显示控制台窗口（打包后的exe不显示控制台）
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_path,  # 应用图标
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=APP_NAME,
)


def copy_app_config_production_to_dist():
    """将 app_config.production.toml 复制为 dist/<APP_NAME>/app_config.toml（与 exe 同目录），发布即用生产 Nest 等配置。"""
    dist_dir = project_root / 'dist' / APP_NAME
    src = project_root / 'app_config.production.toml'
    dst = dist_dir / 'app_config.toml'
    print("\n" + "=" * 60)
    if not src.is_file():
        print("提示: 项目根无 app_config.production.toml，未写入生产 app_config.toml。")
        print(f"  可自行在 exe 同目录放置 app_config.toml: {dist_dir}")
        print("=" * 60 + "\n")
        return
    if not dist_dir.is_dir():
        print(f"警告: 打包输出目录不存在，跳过复制 app_config: {dist_dir}")
        print("=" * 60 + "\n")
        return
    try:
        shutil.copy2(src, dst)
        print(f"已复制生产配置为 app_config.toml（exe 同目录）: {dst}")
        print("=" * 60 + "\n")
    except Exception as e:
        print(f"复制 app_config.production.toml 失败: {e}")
        print("=" * 60 + "\n")


def copy_dotenv_to_dist():
    """若项目根存在 .env，复制到 dist/<APP_NAME>/，与 exe 同目录，避免打包后读不到 AI/飞书等配置。"""
    dist_dir = project_root / 'dist' / APP_NAME
    src = project_root / '.env'
    dst = dist_dir / '.env'
    print("\n" + "=" * 60)
    if not src.is_file():
        print("提示: 项目根目录无 .env 文件，未自动复制。")
        print(f"  若需 AI/飞书密钥，请将 .env 放到 exe 同目录: {dist_dir}")
        print("=" * 60 + "\n")
        return
    if not dist_dir.is_dir():
        print(f"警告: 打包输出目录不存在，跳过复制 .env: {dist_dir}")
        print("=" * 60 + "\n")
        return
    try:
        shutil.copy2(src, dst)
        print(f"已复制 .env 到打包目录（exe 同目录）: {dst}")
        print("=" * 60 + "\n")
    except Exception as e:
        print(f"复制 .env 失败: {e}")
        print("=" * 60 + "\n")


# 打包后处理：自动复制浏览器驱动
def _get_expected_chromium_revision():
    """从 playwright 包的 browsers.json 获取当前版本期望的 Chromium revision"""
    try:
        import json as _json
        browsers_json = project_root / '.venv' / 'Lib' / 'site-packages' / 'playwright' / 'driver' / 'package' / 'browsers.json'
        if browsers_json.exists():
            data = _json.loads(browsers_json.read_text(encoding='utf-8'))
            for b in data.get('browsers', []):
                if b.get('name') == 'chromium':
                    return str(b['revision'])
    except Exception:
        pass
    return None


def _pick_best_chromium(search_dirs):
    """
    从多个候选目录中选出与 playwright 期望 revision 最匹配的 chromium 目录。
    优先：精确匹配 revision；其次：revision 号最大。
    """
    expected = _get_expected_chromium_revision()
    if expected:
        print(f"playwright 期望 Chromium revision: {expected}")

    candidates = []
    for base in search_dirs:
        if not base.exists():
            continue
        for d in base.glob('chromium-*'):
            candidates.append(d)

    if not candidates:
        return None

    if expected:
        exact = [d for d in candidates if d.name == f'chromium-{expected}']
        if exact:
            return exact[0]

    # 取 revision 号最大的
    def _rev(p):
        try:
            return int(p.name.split('-', 1)[1])
        except (IndexError, ValueError):
            return 0

    best = max(candidates, key=_rev)
    if expected:
        print(f"[警告] 未找到 chromium-{expected}，使用 {best.name}（版本不匹配可能导致崩溃）")
    return best


def copy_playwright_drivers():
    """复制 Playwright 浏览器驱动到打包目录"""
    print("\n" + "="*60)
    print("正在复制 Playwright 浏览器驱动...")
    print("="*60)

    dist_dir = project_root / 'dist' / APP_NAME
    playwright_drivers_dir = dist_dir / 'playwright_drivers'

    # 搜索顺序：项目 playwright_drivers 优先，其次系统目录，最后 venv 内
    search_dirs = [
        project_root / 'playwright_drivers',
        Path.home() / 'AppData' / 'Local' / 'ms-playwright',
        project_root / 'venv' / 'Lib' / 'site-packages' / 'playwright' / 'driver' / 'package' / '.local-browsers',
        project_root / '.venv' / 'Lib' / 'site-packages' / 'playwright' / 'driver' / 'package' / '.local-browsers',
    ]

    for d in search_dirs:
        if d.exists():
            print(f"搜索目录: {d}")

    source_dir = _pick_best_chromium(search_dirs)
    if not source_dir:
        print("未找到 Playwright 浏览器驱动")
        print("请先运行: .venv\\Scripts\\playwright install chromium")
        print("="*60 + "\n")
        return False

    target_dir = playwright_drivers_dir / source_dir.name
    try:
        playwright_drivers_dir.mkdir(parents=True, exist_ok=True)
        if target_dir.exists():
            print(f"删除已存在的目录: {target_dir}")
            shutil.rmtree(target_dir)
        print(f"正在复制: {source_dir} -> {target_dir}")
        shutil.copytree(source_dir, target_dir)
        print(f"浏览器驱动复制成功: {source_dir.name}")
        print("="*60 + "\n")
        return True
    except Exception as e:
        print(f"复制浏览器驱动失败: {e}")
        print("="*60 + "\n")
        return False

# 执行后处理
copy_app_config_production_to_dist()
copy_dotenv_to_dist()
if not copy_playwright_drivers():
        print(f"警告: 浏览器驱动未复制，请手动复制到 dist/{APP_NAME}/playwright_drivers/ 目录")
