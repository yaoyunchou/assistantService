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
                    return data
            except Exception as e:
                logger.warning("从种子文件初始化 tasks.json 失败: %s", e)
        return {"tasks": []}
    try:
        with open(TASKS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("读取任务配置失败: %s", e)
        return {"tasks": []}


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
