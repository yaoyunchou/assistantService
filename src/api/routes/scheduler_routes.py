"""
定时任务 API：列表、新增、删除、触发、任务类型
"""
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
    """列出可用的任务类型（type, name），用于新增任务时的下拉。"""
    try:
        from scheduler import get_task_types
        types = get_task_types()
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
    立即执行指定任务。执行方式 = 向该任务 type 对应的业务 API 发一条 HTTP 请求（与定时到点一致）。
    见 docs/定时任务对接说明.md。
    """
    routes_logger.info("收到立即执行请求: task_id=%s", task_id)
    try:
        from scheduler import run_task_by_id
        success, result_data, message = run_task_by_id(task_id)
        if not success:
            routes_logger.warning("立即执行失败: task_id=%s error=%s", task_id, message)
            return jsonify({"success": False, "error": message}), 404 if "不存在" in message else 500
        routes_logger.info("立即执行完成: task_id=%s message=%s", task_id, message)
        return jsonify({
            "success": True,
            "job_id": task_id,
            "filled_count": result_data if isinstance(result_data, int) else None,
            "message": message,
        }), 200
    except Exception as e:
        routes_logger.error("手动触发任务异常: task_id=%s error=%s", task_id, e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500
