"""
定时任务模块

任务配置存 scheduler/tasks.json（id=uuid, name, type, data, cron），按 type 执行对应 handler。
"""
from .manager import (
    get_scheduler,
    start_scheduler,
    shutdown_scheduler,
    list_jobs,
    run_task_by_id,
    add_task_and_register,
    remove_task_and_unregister,
    get_task_types,
)

__all__ = [
    "get_scheduler",
    "start_scheduler",
    "shutdown_scheduler",
    "list_jobs",
    "run_task_by_id",
    "add_task_and_register",
    "remove_task_and_unregister",
    "get_task_types",
]
