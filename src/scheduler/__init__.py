"""
定时任务模块

任务配置存 scheduler/tasks.toml（id=uuid, name, type, data, cron），按 type 执行对应 handler。
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
    get_task_type_schemas,
    pause_task,
    resume_task,
    get_task_status,
    get_task_log_lines,
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
    "get_task_type_schemas",
    "pause_task",
    "resume_task",
    "get_task_status",
    "get_task_log_lines",
]
