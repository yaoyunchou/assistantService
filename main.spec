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
def copy_playwright_drivers():
    """复制 Playwright 浏览器驱动到打包目录"""
    print("\n" + "="*60)
    print("正在复制 Playwright 浏览器驱动...")
    print("="*60)
    
    # 打包输出目录
    dist_dir = project_root / 'dist' / APP_NAME
    playwright_drivers_dir = dist_dir / 'playwright_drivers'
    
    # 查找浏览器驱动源位置
    sources = []
    
    # 方法1：查找系统安装的 Playwright 浏览器驱动
    user_home = Path.home()
    system_playwright = user_home / 'AppData' / 'Local' / 'ms-playwright'
    if system_playwright.exists():
        chromium_dirs = list(system_playwright.glob('chromium-*'))
        if chromium_dirs:
            sources.append(chromium_dirs[0])
            print(f"找到系统浏览器驱动: {chromium_dirs[0]}")
    
    # 方法2：查找项目目录下的 playwright_drivers
    project_playwright = project_root / 'playwright_drivers'
    if project_playwright.exists():
        chromium_dirs = list(project_playwright.glob('chromium-*'))
        if chromium_dirs:
            sources.append(chromium_dirs[0])
            print(f"找到项目浏览器驱动: {chromium_dirs[0]}")
    
    # 方法3：查找虚拟环境中的 Playwright 浏览器驱动
    venv_playwright = project_root / 'venv' / 'Lib' / 'site-packages' / 'playwright' / 'driver' / 'package' / '.local-browsers'
    if venv_playwright.exists():
        chromium_dirs = list(venv_playwright.glob('chromium-*'))
        if chromium_dirs:
            sources.append(chromium_dirs[0])
            print(f"找到虚拟环境浏览器驱动: {chromium_dirs[0]}")
    
    # 复制浏览器驱动
    if sources:
        source_dir = sources[0]  # 使用第一个找到的
        target_dir = playwright_drivers_dir / source_dir.name
        
        try:
            # 创建目标目录
            playwright_drivers_dir.mkdir(parents=True, exist_ok=True)
            
            # 如果目标目录已存在，先删除
            if target_dir.exists():
                print(f"删除已存在的目录: {target_dir}")
                shutil.rmtree(target_dir)
            
            # 复制整个 chromium 目录
            print(f"正在复制: {source_dir} -> {target_dir}")
            shutil.copytree(source_dir, target_dir)
            
            print(f"✓ 浏览器驱动复制成功！")
            print(f"  源目录: {source_dir}")
            print(f"  目标目录: {target_dir}")
            print("="*60 + "\n")
            return True
        except Exception as e:
            print(f"✗ 复制浏览器驱动失败: {e}")
            print("="*60 + "\n")
            return False
    else:
        print("✗ 未找到 Playwright 浏览器驱动")
        print("请先运行: venv\\Scripts\\python.exe -m playwright install chromium")
        print("="*60 + "\n")
        return False

# 执行后处理
copy_dotenv_to_dist()
if not copy_playwright_drivers():
        print(f"警告: 浏览器驱动未复制，请手动复制到 dist/{APP_NAME}/playwright_drivers/ 目录")
