"""
自动化构建脚本
用法:
    python build.py              # 只执行 PyInstaller 打包
    python build.py --installer  # 打包 + 编译 Inno Setup 安装包
    python build.py --version    # 只显示当前版本号
    python build.py --sync-only  # 只同步版本到 setup.iss（不打包）
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
CONFIG_PY = SRC_DIR / "config.py"
SETUP_ISS = PROJECT_ROOT / "setup.iss"
MAIN_SPEC = PROJECT_ROOT / "main.spec"


def read_version_from_config() -> tuple[str, str]:
    """从 config.py 读取 APP_NAME 和 APP_VERSION（唯一来源）"""
    text = CONFIG_PY.read_text(encoding="utf-8")

    m_name = re.search(r"APP_NAME\s*=\s*['\"](.+?)['\"]", text)
    m_ver = re.search(r"APP_VERSION\s*=\s*['\"](.+?)['\"]", text)

    if not m_name or not m_ver:
        print("ERROR: 无法从 config.py 读取 APP_NAME / APP_VERSION")
        sys.exit(1)

    return m_name.group(1), m_ver.group(1)


def sync_setup_iss(app_name: str, version: str) -> bool:
    """将版本号和应用名同步到 setup.iss，返回是否有变更"""
    if not SETUP_ISS.exists():
        print(f"WARNING: {SETUP_ISS} 不存在，跳过同步")
        return False

    original = SETUP_ISS.read_text(encoding="utf-8")
    text = original

    replacements = {
        r"(AppName=).*": rf"\g<1>{app_name}",
        r"(AppVersion=).*": rf"\g<1>{version}",
        r"(AppPublisher=).*": rf"\g<1>{app_name}",
        r"(OutputBaseFilename=).*": rf"\g<1>{app_name}_Setup_v{version}",
        r"(DefaultGroupName=).*": rf"\g<1>{app_name}",
        r"(UninstallDisplayName=).*": rf"\g<1>{app_name}",
    }

    for pattern, repl in replacements.items():
        text = re.sub(pattern, repl, text)

    changed = text != original
    if changed:
        SETUP_ISS.write_text(text, encoding="utf-8")
        print(f"  ✓ setup.iss 已同步: {app_name} v{version}")
    else:
        print(f"  - setup.iss 已是最新: {app_name} v{version}")

    return changed


def run_pyinstaller():
    """运行 PyInstaller 打包"""
    print("\n" + "=" * 60)
    print("开始 PyInstaller 打包...")
    print("=" * 60)

    cmd = [sys.executable, "-m", "PyInstaller", str(MAIN_SPEC), "--noconfirm"]
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))

    if result.returncode != 0:
        print("\nERROR: PyInstaller 打包失败")
        sys.exit(result.returncode)

    print("\n✓ PyInstaller 打包完成")


def run_inno_setup(app_name: str, version: str):
    """编译 Inno Setup 安装包"""
    print("\n" + "=" * 60)
    print("开始编译 Inno Setup 安装包...")
    print("=" * 60)

    iscc_paths = [
        Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
        Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
    ]

    iscc = None
    for p in iscc_paths:
        if p.exists():
            iscc = p
            break

    if not iscc:
        print("WARNING: 未找到 Inno Setup (ISCC.exe)，跳过安装包编译")
        print("  请安装 Inno Setup 6: https://jrsoftware.org/isinfo.php")
        return

    cmd = [str(iscc), str(SETUP_ISS)]
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))

    if result.returncode != 0:
        print("\nERROR: Inno Setup 编译失败")
        sys.exit(result.returncode)

    output_file = PROJECT_ROOT / f"{app_name}_Setup_v{version}.exe"
    print(f"\n✓ 安装包编译完成: {output_file}")


def main():
    parser = argparse.ArgumentParser(description="如意助手自动化构建工具")
    parser.add_argument("--installer", action="store_true",
                        help="打包后编译 Inno Setup 安装包")
    parser.add_argument("--version", action="store_true",
                        help="只显示当前版本号")
    parser.add_argument("--sync-only", action="store_true",
                        help="只同步版本到 setup.iss（不打包）")
    args = parser.parse_args()

    app_name, version = read_version_from_config()

    if args.version:
        print(f"{app_name} v{version}")
        return

    print("=" * 60)
    print(f"构建 {app_name} v{version}")
    print("=" * 60)

    print("\n[1/3] 同步版本号到 setup.iss ...")
    sync_setup_iss(app_name, version)

    if args.sync_only:
        print("\n✓ 同步完成 (--sync-only)")
        return

    print("\n[2/3] PyInstaller 打包 ...")
    run_pyinstaller()

    if args.installer:
        print("\n[3/3] Inno Setup 安装包 ...")
        run_inno_setup(app_name, version)
    else:
        print("\n[3/3] 跳过安装包编译 (添加 --installer 参数以启用)")

    print("\n" + "=" * 60)
    print(f"✓ 构建完成: {app_name} v{version}")
    print("=" * 60)


if __name__ == "__main__":
    main()
