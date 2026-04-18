"""
TOML 读写工具

兼容 Python 3.8-3.10（tomli + tomli_w）和 3.11+（内置 tomllib + tomli_w）。
所有配置文件统一使用 TOML 格式，支持注释。
"""
import json
from pathlib import Path
from typing import Any, Dict, Optional


def _get_reader():
    """获取 TOML 读取模块（优先内置 tomllib）"""
    try:
        import tomllib
        return tomllib
    except ImportError:
        import tomli
        return tomli


def load_toml(path: Path) -> Dict[str, Any]:
    """
    读取 TOML 文件并返回字典。

    Args:
        path: TOML 文件路径

    Returns:
        解析后的字典，文件不存在则返回空字典
    """
    if not path.exists():
        return {}
    reader = _get_reader()
    with open(path, "rb") as f:
        return reader.load(f)


def dump_toml(data: Dict[str, Any], path: Path, header: str = "") -> None:
    """
    将字典写入 TOML 文件。

    Args:
        data: 要写入的字典
        path: 目标文件路径
        header: 可选的文件头注释（每行自动加 # 前缀）
    """
    import tomli_w

    path.parent.mkdir(parents=True, exist_ok=True)
    raw = tomli_w.dumps(data)

    with open(path, "w", encoding="utf-8") as f:
        if header:
            for line in header.strip().splitlines():
                f.write(f"# {line}\n")
            f.write("\n")
        f.write(raw)


def migrate_json_to_toml(json_path: Path, toml_path: Path, header: str = "") -> bool:
    """
    将 JSON 配置文件迁移为 TOML（迁移后删除旧 JSON）。

    仅当 TOML 文件不存在 且 JSON 文件存在 时执行迁移。

    Args:
        json_path: 旧 JSON 文件路径
        toml_path: 新 TOML 文件路径
        header: TOML 文件头注释

    Returns:
        是否执行了迁移
    """
    if toml_path.exists() or not json_path.exists():
        return False
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        dump_toml(data, toml_path, header=header)
        json_path.unlink()
        return True
    except Exception as e:
        print(f"[TOML] 迁移 {json_path.name} → {toml_path.name} 失败: {e}")
        return False
