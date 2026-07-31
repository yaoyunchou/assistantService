"""
定时任务配置：持久化任务列表（id=uuid, name, type, data, cron），及按 type 执行。
配置文件格式为 TOML。
"""
import json
import uuid
from pathlib import Path
from typing import List, Dict, Any, Optional

from utils.logger import get_logger
from utils.path_helper import get_project_root, get_safe_data_path
from utils.toml_helper import load_toml, dump_toml, migrate_json_to_toml

logger = get_logger("Scheduler")

CONFIG_DIR = get_safe_data_path("scheduler")
TASKS_FILE = CONFIG_DIR / "tasks.toml"
# task_last_success 纯内部数据，保持 JSON（无需注释）
LAST_SUCCESS_FILE = CONFIG_DIR / "task_last_success.json"

_TASKS_HEADER = """\
===== 定时任务配置 =====
每个 [[tasks]] 块为一条任务，字段说明：
  id   = 任务唯一标识（UUID 或自定义）
  name = 显示名称
  type = 任务类型（http_request / python_script / pdd_erp_order_sync / pdd_inventory_sync / order_1688_fill_detail）
  cron = cron 表达式（分 时 日 月 周）
  enabled = 是否启用（默认 true）
  catch_up_on_start = 启动时补跑漏执行的任务（可选）
  [tasks.data] = 任务参数（按类型不同）"""

# 种子：优先仓库根目录 scheduler/tasks.toml（与 PyInstaller datas、用户编辑处一致）；兼容旧路径 src/scheduler/
_SRC_DIR = Path(__file__).resolve().parent
_SEED_TASKS_JSON = _SRC_DIR / "tasks.json"  # 旧版种子，仅做迁移兼容


def _seed_tasks_file() -> Path:
    root_seed = get_project_root() / "scheduler" / "tasks.toml"
    if root_seed.is_file():
        return root_seed
    return _SRC_DIR / "tasks.toml"

_SCHEDULER_SEED_MERGE_VERSION = "2"
_SEED_MERGE_MARKER = CONFIG_DIR / ".scheduler_seed_merge_version"


def _load_seed() -> Dict[str, Any]:
    """加载种子文件（优先 TOML，兼容旧 JSON）。"""
    seed_toml = _seed_tasks_file()
    if seed_toml.exists():
        try:
            return load_toml(seed_toml)
        except Exception as e:
            logger.warning("读取种子 tasks.toml 失败: %s", e)
    if _SEED_TASKS_JSON.exists():
        try:
            with open(_SEED_TASKS_JSON, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("读取种子 tasks.json 失败: %s", e)
    return {}


def _merge_missing_tasks_from_seed_inplace(data: Dict[str, Any]) -> bool:
    """
    当本地版本落后时，将种子中缺失的任务 id 追加到本地。
    """
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        applied = _SEED_MERGE_MARKER.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        applied = ""
    if applied == _SCHEDULER_SEED_MERGE_VERSION:
        return False
    seed = _load_seed()
    seed_tasks = seed.get("tasks") if isinstance(seed.get("tasks"), list) else []
    if not seed_tasks:
        try:
            _SEED_MERGE_MARKER.write_text(_SCHEDULER_SEED_MERGE_VERSION, encoding="utf-8")
        except OSError:
            pass
        return False
    tasks = list(data.get("tasks") or [])
    ids = {t.get("id") for t in tasks if t.get("id")}
    changed = False
    for st in seed_tasks:
        tid = st.get("id")
        if tid and tid not in ids:
            tasks.append(st)
            ids.add(tid)
            changed = True
    if changed:
        data["tasks"] = tasks
        logger.info(
            "已从种子文件合并缺失的定时任务（合并版本 %s）",
            _SCHEDULER_SEED_MERGE_VERSION,
        )
    try:
        _SEED_MERGE_MARKER.write_text(_SCHEDULER_SEED_MERGE_VERSION, encoding="utf-8")
    except OSError as e:
        logger.warning("写入种子合并标记失败: %s", e)
    return changed


def _merge_seed_fields_for_existing_tasks_inplace(data: Dict[str, Any]) -> bool:
    """
    从种子为已存在任务补全顶层字段（如 catch_up_on_start），
    仅当本地任务缺少该键时写入。
    """
    seed = _load_seed()
    seed_tasks = seed.get("tasks") if isinstance(seed.get("tasks"), list) else []
    if not seed_tasks:
        return False
    by_id = {t.get("id"): t for t in seed_tasks if t.get("id")}
    changed = False
    for t in data.get("tasks") or []:
        tid = t.get("id")
        if not tid or tid not in by_id:
            continue
        st = by_id[tid]
        if "catch_up_on_start" in st and "catch_up_on_start" not in t:
            t["catch_up_on_start"] = st["catch_up_on_start"]
            changed = True
    return changed


def _load_raw() -> Dict[str, Any]:
    # 首次升级：自动把旧 JSON 迁移为 TOML
    migrate_json_to_toml(CONFIG_DIR / "tasks.json", TASKS_FILE, header=_TASKS_HEADER)

    if not TASKS_FILE.exists():
        seed = _load_seed()
        if isinstance(seed.get("tasks"), list):
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            dump_toml(seed, TASKS_FILE, header=_TASKS_HEADER)
            logger.info("已从种子文件初始化 tasks.toml")
            try:
                _SEED_MERGE_MARKER.write_text(
                    _SCHEDULER_SEED_MERGE_VERSION, encoding="utf-8"
                )
            except OSError:
                pass
            return seed
        return {"tasks": []}
    try:
        data = load_toml(TASKS_FILE)
    except Exception as e:
        logger.warning("读取任务配置失败: %s", e)
        return {"tasks": []}
    if not isinstance(data.get("tasks"), list):
        data["tasks"] = []
    if _merge_missing_tasks_from_seed_inplace(data):
        _save_raw(data)
    if _merge_seed_fields_for_existing_tasks_inplace(data):
        _save_raw(data)
    return data


def _save_raw(data: Dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    dump_toml(data, TASKS_FILE, header=_TASKS_HEADER)


def list_tasks() -> List[Dict[str, Any]]:
    """返回所有任务配置（id, name, type, data, cron）。"""
    return list(_load_raw().get("tasks", []))


def get_task(task_id: str) -> Optional[Dict[str, Any]]:
    """按 id 获取一条任务。"""
    for t in list_tasks():
        if t.get("id") == task_id:
            return t
    return None


def add_task(
    name: str,
    task_type: str,
    data: Optional[Dict[str, Any]] = None,
    cron: str = "0 * * * *",
    *,
    run_at: Any = None,
) -> Dict[str, Any]:
    """
    新增任务，id 为 UUID。返回完整任务项。
    run_at: 可选，一次性触发时间（unix 秒 / ISO 字符串）；有则优先于 cron。
    """
    data = data if data is not None else {}
    task_id = str(uuid.uuid4())
    task = {"id": task_id, "name": name, "type": task_type, "data": data, "cron": cron.strip() or "0 * * * *"}
    if run_at is not None and run_at != "":
        task["run_at"] = run_at
    raw = _load_raw()
    raw.setdefault("tasks", []).append(task)
    _save_raw(raw)
    logger.info(
        "新增定时任务: id=%s name=%s type=%s cron=%s run_at=%s",
        task_id, name, task_type, task["cron"], task.get("run_at"),
    )
    return task


def remove_task(task_id: str) -> bool:
    """删除任务，返回是否找到并删除。"""
    raw = _load_raw()
    tasks = raw.get("tasks", [])
    new_tasks = [t for t in tasks if t.get("id") != task_id]
    if len(new_tasks) == len(tasks):
        return False
    raw["tasks"] = new_tasks
    _save_raw(raw)
    logger.info("删除定时任务: id=%s", task_id)
    return True


def update_task_field(task_id: str, field: str, value: Any) -> bool:
    """更新指定任务的某个字段（如 enabled）。"""
    raw = _load_raw()
    for t in raw.get("tasks", []):
        if t.get("id") == task_id:
            t[field] = value
            _save_raw(raw)
            logger.info("更新任务字段: id=%s %s=%s", task_id, field, value)
            return True
    return False
