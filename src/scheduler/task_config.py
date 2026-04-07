"""
定时任务配置：持久化任务列表（id=uuid, name, type, data, cron），及按 type 执行。
"""
import json
import uuid
from pathlib import Path
from typing import List, Dict, Any, Optional

from utils.logger import get_logger
from utils.path_helper import get_safe_data_path

logger = get_logger("Scheduler")

CONFIG_DIR = get_safe_data_path("scheduler")
TASKS_FILE = CONFIG_DIR / "tasks.json"

# 规范种子文件：与 task_config.py 同目录的 tasks.json，运行时若本地无配置则按此初始化
_SEED_TASKS_FILE = Path(__file__).resolve().parent / "tasks.json"
# 种子合并版本：在种子中新增「内置任务 id」后递增，老用户启动时会自动把缺失 id 追加进本地 tasks.json
_SCHEDULER_SEED_MERGE_VERSION = "1"
_SEED_MERGE_MARKER = CONFIG_DIR / ".scheduler_seed_merge_version"


def _merge_missing_tasks_from_seed_inplace(data: Dict[str, Any]) -> bool:
    """
    当本地 `.scheduler_seed_merge_version` 落后于代码中的版本时，
    将种子 tasks.json 里存在、而本地 tasks 列表中缺少的 **任务 id** 整段追加。

    说明：页面与调度器读的是 get_safe_data_path('scheduler')/tasks.json（开发环境多为项目根目录
    scheduler/tasks.json），与仓库里的 src/scheduler/tasks.json 不是同一个文件；改种子后需提版本号才能合并到已有环境。
    """
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        applied = _SEED_MERGE_MARKER.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        applied = ""
    if applied == _SCHEDULER_SEED_MERGE_VERSION:
        return False
    if not _SEED_TASKS_FILE.exists():
        try:
            _SEED_MERGE_MARKER.write_text(_SCHEDULER_SEED_MERGE_VERSION, encoding="utf-8")
        except OSError:
            pass
        return False
    try:
        with open(_SEED_TASKS_FILE, "r", encoding="utf-8") as f:
            seed = json.load(f)
    except Exception as e:
        logger.warning("读取种子 tasks.json 失败: %s", e)
        return False
    seed_tasks = seed.get("tasks") if isinstance(seed.get("tasks"), list) else []
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
            "已从 src/scheduler/tasks.json 合并缺失的定时任务（合并版本 %s）",
            _SCHEDULER_SEED_MERGE_VERSION,
        )
    try:
        _SEED_MERGE_MARKER.write_text(_SCHEDULER_SEED_MERGE_VERSION, encoding="utf-8")
    except OSError as e:
        logger.warning("写入种子合并标记失败: %s", e)
    return changed


def _load_raw() -> Dict[str, Any]:
    if not TASKS_FILE.exists():
        if _SEED_TASKS_FILE.exists():
            try:
                with open(_SEED_TASKS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data.get("tasks"), list):
                    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
                    with open(TASKS_FILE, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    logger.info("已按规范从种子文件初始化 tasks.json")
                    try:
                        _SEED_MERGE_MARKER.write_text(
                            _SCHEDULER_SEED_MERGE_VERSION, encoding="utf-8"
                        )
                    except OSError:
                        pass
                    return data
            except Exception as e:
                logger.warning("从种子文件初始化 tasks.json 失败: %s", e)
        return {"tasks": []}
    try:
        with open(TASKS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.warning("读取任务配置失败: %s", e)
        return {"tasks": []}
    if not isinstance(data.get("tasks"), list):
        data["tasks"] = []
    if _merge_missing_tasks_from_seed_inplace(data):
        _save_raw(data)
    return data


def _save_raw(data: Dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(TASKS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def list_tasks() -> List[Dict[str, Any]]:
    """返回所有任务配置（id, name, type, data, cron）。"""
    return list(_load_raw().get("tasks", []))


def get_task(task_id: str) -> Optional[Dict[str, Any]]:
    """按 id 获取一条任务。"""
    for t in list_tasks():
        if t.get("id") == task_id:
            return t
    return None


def add_task(name: str, task_type: str, data: Optional[Dict[str, Any]] = None, cron: str = "0 * * * *") -> Dict[str, Any]:
    """
    新增任务，id 为 UUID。返回完整任务项。
    """
    data = data if data is not None else {}
    task_id = str(uuid.uuid4())
    task = {"id": task_id, "name": name, "type": task_type, "data": data, "cron": cron.strip() or "0 * * * *"}
    raw = _load_raw()
    raw.setdefault("tasks", []).append(task)
    _save_raw(raw)
    logger.info("新增定时任务: id=%s name=%s type=%s cron=%s", task_id, name, task_type, task["cron"])
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
