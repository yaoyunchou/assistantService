"""
定时任务 API：列表、新增、删除、触发、任务类型
"""
import threading
from flask import Blueprint, jsonify, request
from api.routes.context import get_browser_pool
from utils.logger import get_logger

routes_logger = get_logger("Routes")
bp = Blueprint("scheduler", __name__, url_prefix="/api/scheduler")


@bp.route("/jobs", methods=["GET"])
def list_scheduler_jobs():
    """列出所有任务（id, name, type, data, cron, next_run_time）。"""
    try:
        from scheduler import list_jobs
        jobs = list_jobs()
        return jsonify({"success": True, "jobs": jobs}), 200
    except Exception as e:
        routes_logger.error("列出定时任务异常: %s", e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/types", methods=["GET"])
def list_task_types():
    """列出可用的任务类型。?detail=1 时返回每个类型的字段 schema（用于新增表单动态渲染）。"""
    try:
        from scheduler import get_task_types, get_task_type_schemas
        types = get_task_types()
        detail = request.args.get("detail", "0")
        if detail == "1":
            schemas = get_task_type_schemas()
            for t in types:
                s = schemas.get(t["type"], {})
                t["description"] = s.get("description", "")
                t["fields"] = s.get("fields", [])
        return jsonify({"success": True, "types": types}), 200
    except Exception as e:
        routes_logger.error("列出任务类型异常: %s", e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/tasks", methods=["POST"])
def add_scheduler_task():
    """
    新增任务。body: { "name": "任务名", "type": "order_1688_fill_detail", "data": {}, "cron": "0 * * * *" }。
    id 自动生成 UUID。
    """
    try:
        body = request.get_json() or {}
        name = (body.get("name") or "").strip()
        task_type = (body.get("type") or "").strip()
        data = body.get("data")
        if data is not None and not isinstance(data, dict):
            data = {}
        cron = (body.get("cron") or "0 * * * *").strip()
        if not name:
            return jsonify({"success": False, "error": "name 不能为空"}), 400
        if not task_type:
            return jsonify({"success": False, "error": "type 不能为空"}), 400
        from scheduler import add_task_and_register, get_task_types
        allowed = [t["type"] for t in get_task_types()]
        if task_type not in allowed:
            return jsonify({"success": False, "error": f"不支持的 type，可选: {allowed}"}), 400
        task = add_task_and_register(name=name, task_type=task_type, data=data, cron=cron)
        return jsonify({"success": True, "task": task}), 200
    except Exception as e:
        routes_logger.error("新增定时任务异常: %s", e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/tasks/<task_id>", methods=["DELETE"])
def delete_scheduler_task(task_id):
    """删除指定任务（按 UUID）。"""
    try:
        from scheduler import remove_task_and_unregister
        if remove_task_and_unregister(task_id):
            return jsonify({"success": True, "message": "已删除"}), 200
        return jsonify({"success": False, "error": "任务不存在"}), 404
    except Exception as e:
        routes_logger.error("删除定时任务异常: %s", e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/trigger/<task_id>", methods=["POST"])
def trigger_job(task_id):
    """
    立即执行指定任务（异步）。

    Flask 单线程模式下，任务 handler 会回调本机 API（如 sync-erp-orders），
    若同步等待会造成死锁。因此将任务放到后台线程执行，本接口立即返回。
    执行状态与结果通过 ``/tasks/<task_id>/status`` 和 ``/tasks/<task_id>/logs`` 查询。
    """
    routes_logger.info("收到立即执行请求: task_id=%s", task_id)
    try:
        from scheduler.task_config import get_task
        task = get_task(task_id)
        if not task:
            return jsonify({"success": False, "error": "任务不存在"}), 404

        from scheduler.manager import get_task_status
        status = get_task_status(task_id)
        if status.get("running"):
            return jsonify({"success": False, "error": "任务正在执行中，请勿重复触发"}), 409

        def _bg():
            from scheduler import run_task_by_id
            run_task_by_id(task_id)

        t = threading.Thread(target=_bg, daemon=True, name=f"trigger-{task_id}")
        t.start()

        routes_logger.info("任务已提交后台执行: task_id=%s", task_id)
        return jsonify({
            "success": True,
            "job_id": task_id,
            "message": "任务已提交执行，请通过状态接口查询结果",
        }), 202
    except Exception as e:
        routes_logger.error("手动触发任务异常: task_id=%s error=%s", task_id, e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/tasks/<task_id>/pause", methods=["POST"])
def pause_scheduler_task(task_id):
    """暂停任务（停止定时触发，但保留配置）。"""
    try:
        from scheduler import pause_task
        pause_task(task_id)
        return jsonify({"success": True, "message": "已暂停"}), 200
    except Exception as e:
        routes_logger.error("暂停任务异常: %s", e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/tasks/<task_id>/resume", methods=["POST"])
def resume_scheduler_task(task_id):
    """恢复任务（重新注册到调度器）。"""
    try:
        from scheduler import resume_task
        resume_task(task_id)
        return jsonify({"success": True, "message": "已恢复"}), 200
    except Exception as e:
        routes_logger.error("恢复任务异常: %s", e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/tasks/<task_id>/status", methods=["GET"])
def get_task_exec_status(task_id):
    """获取任务执行状态（running、last_run、last_success、last_message）。"""
    try:
        from scheduler import get_task_status
        status = get_task_status(task_id)
        return jsonify({"success": True, "status": status}), 200
    except Exception as e:
        routes_logger.error("获取任务状态异常: %s", e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/tasks/<task_id>/logs", methods=["GET"])
def get_task_logs(task_id):
    """获取指定任务最近的执行日志行（内存缓存）。?n=50 控制返回行数。"""
    try:
        from scheduler import get_task_log_lines
        n = request.args.get("n", 50, type=int)
        lines = get_task_log_lines(task_id, last_n=min(n, 500))
        return jsonify({"success": True, "lines": lines}), 200
    except Exception as e:
        routes_logger.error("获取任务日志异常: %s", e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/logs", methods=["GET"])
def get_global_task_log():
    """读取当天 task_*.log 文件最后 N 行。?n=100 控制行数。"""
    try:
        from utils.logger import get_task_log_path
        n = request.args.get("n", 100, type=int)
        log_path = get_task_log_path()
        if not log_path.exists():
            return jsonify({"success": True, "lines": [], "file": str(log_path)}), 200
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
        tail = [l.rstrip("\n\r") for l in all_lines[-min(n, 2000):]]
        return jsonify({"success": True, "lines": tail, "file": str(log_path)}), 200
    except Exception as e:
        routes_logger.error("读取任务日志文件异常: %s", e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500
