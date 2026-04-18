"""
库存映射配置：商品信息 → 商品名称（库存信息表）的手动映射关系。

映射优先于 AI 匹配；映射值为 ["空"] 时表示该商品不参与库存扣减。
默认 JSON 位于 ``config/inventory_product_mapping.json``（打包时随 exe 分发）；
可写路径下的同名文件与之合并，后者覆盖同名键（见 ``load_mappings``）。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from utils.logger import get_logger
from utils.path_helper import get_bundled_data_root, get_project_root, get_safe_data_path

logger = get_logger('InventoryMapping')

TZ_SH = timezone(timedelta(hours=8))

MAPPING_FILE_REL = 'config/inventory_product_mapping.json'

SKIP_PLACEHOLDER = '空'


def _get_mapping_path() -> Path:
    return get_safe_data_path(MAPPING_FILE_REL)


def _read_mapping_file(path: Path) -> Dict[str, List[str]]:
    if not path.exists():
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        raw = data.get('mappings', {})
        return raw if isinstance(raw, dict) else {}
    except Exception as e:
        logger.warning('加载库存映射失败 %s: %s', path, e)
        return {}


def load_mappings() -> Dict[str, List[str]]:
    """加载映射：先读打包/项目内嵌的默认文件，再与可写路径合并（后者覆盖同名键）。

    PyInstaller 6 onedir 模式下 datas 在 ``_internal/`` 下，
    因此默认文件用 ``get_bundled_data_root()`` 定位；
    exe 旁（get_project_root）仍作为回退，兼容手动放置的场景。
    """
    bundled_path = get_bundled_data_root() / MAPPING_FILE_REL
    project_path = get_project_root() / MAPPING_FILE_REL
    user_path = _get_mapping_path()

    base = _read_mapping_file(bundled_path)
    if not base and bundled_path != project_path:
        base = _read_mapping_file(project_path)

    resolved_paths = set()
    for p in (bundled_path, project_path):
        try:
            resolved_paths.add(p.resolve())
        except OSError:
            pass
    try:
        user_is_same = user_path.resolve() in resolved_paths
    except OSError:
        user_is_same = False

    if user_is_same:
        return base
    override = _read_mapping_file(user_path)
    return {**base, **override}


def save_mappings(mappings: Dict[str, List[str]]) -> bool:
    path = _get_mapping_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = {
            'mappings': mappings,
            'updated_at': datetime.now(tz=TZ_SH).isoformat(),
        }
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info('库存映射已保存，共 %d 条', len(mappings))
        return True
    except Exception as e:
        logger.exception('保存库存映射失败: %s', e)
        return False


def get_mapping_for_product_info(
    product_info: str,
    mappings: Optional[Dict[str, List[str]]] = None,
) -> Optional[List[str]]:
    """查询某个商品信息的映射。

    Returns:
        - None: 未配置映射，应走 AI 匹配
        - ["空"]: 已配置为跳过
        - ["名称1", "名称2"]: 已配置的库存商品名称列表
    """
    if mappings is None:
        mappings = load_mappings()
    return mappings.get(product_info.strip()) if product_info else None
