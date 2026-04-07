"""
定时任务管理器：基于 APScheduler，任务配置存 JSON（id=uuid, name, type, data, cron），按 type 执行对应 handler。

日志分离：
  - logger（Scheduler）→ app_*.log  调度器基础设施日志（启动、注册、配置）
  - tlog （TaskExec） → task_*.log  任务执行日志（开始、结果、异常）
"""
import collections
import threading
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

from utils.logger import get_logger, get_task_logger

logger = get_logger("Scheduler")
tlog = get_task_logger("TaskExec")

_scheduler = None

# 任务执行状态追踪（内存中）
_task_status: Dict[str, Dict[str, Any]] = {}
_task_status_lock = threading.Lock()

# 每个任务最近 N 条执行日志行（内存缓冲，供页面查看）
_MAX_LOG_LINES_PER_TASK = 200
_task_log_lines: Dict[str, collections.deque] = {}
_task_log_lines_lock = threading.Lock()


def _task_log(task_id: str, level: str, msg: str, *args) -> None:
    """同时写入任务日志文件 + 缓存到内存。"""
    formatted = msg % args if args else msg
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] [{level}] {formatted}"
    getattr(tlog, level.lower(), tlog.info)(formatted)
    with _task_log_lines_lock:
        if task_id not in _task_log_lines:
            _task_log_lines[task_id] = collections.deque(maxlen=_MAX_LOG_LINES_PER_TASK)
        _task_log_lines[task_id].append(line)


def get_task_log_lines(task_id: str, last_n: int = 50) -> List[str]:
    """获取指定任务最近 N 条执行日志行。"""
    with _task_log_lines_lock:
        buf = _task_log_lines.get(task_id)
        if not buf:
            return []
        lines = list(buf)
        return lines[-last_n:]


def _set_task_running(task_id: str) -> None:
    with _task_status_lock:
        _task_status.setdefault(task_id, {})
        _task_status[task_id]["running"] = True
        _task_status[task_id]["started_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _set_task_finished(task_id: str, success: bool, message: str) -> None:
    with _task_status_lock:
        _task_status.setdefault(task_id, {})
        s = _task_status[task_id]
        s["running"] = False
        s["last_run"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        s["last_success"] = success
        s["last_message"] = message[:500] if message else ""
        s["started_at"] = None


def get_task_status(task_id: str) -> Dict[str, Any]:
    with _task_status_lock:
        return dict(_task_status.get(task_id, {}))


def get_all_task_status() -> Dict[str, Dict[str, Any]]:
    with _task_status_lock:
        return {k: dict(v) for k, v in _task_status.items()}


def _run_order_1688_fill_detail(data: Dict[str, Any], _tid: str = "") -> Tuple[int, str]:
    """
    定时器只负责调用业务 API，不执行业务逻辑。
    _tid 为内部传入的 task_id，用于关联日志行。
    """
    from config import Config
    import requests
    data = data or {}
    url = (data.get("url") or "").strip()
    if url and url.startswith("http"):
        _task_log(_tid, "INFO", "使用任务配置 URL: %s", url)
    else:
        url = f"http://{Config.HOST}:{Config.PORT}/api/order_1688/fill_detail"
        _task_log(_tid, "INFO", "任务未配置 url，使用默认: %s", url)
    body = data.get("data") if isinstance(data.get("data"), dict) else {}
    _task_log(_tid, "INFO", "调用业务 API: POST %s", url)
    try:
        r = requests.post(url, json=body, timeout=300)
        resp_body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        if not resp_body.get("success"):
            err = resp_body.get("error") or resp_body.get("message") or r.text or str(r.status_code)
            _task_log(_tid, "WARNING", "业务 API 返回失败: %s", err)
            return 0, err
        filled = int(resp_body.get("filled_count", 0) or 0)
        msg = str(resp_body.get("message") or "已执行")
        _task_log(_tid, "INFO", "业务 API 返回成功: filled_count=%s message=%s", filled, msg)
        return filled, msg
    except Exception as e:
        _task_log(_tid, "WARNING", "调用 1688 补详情 API 失败: %s", e)
        return 0, str(e)


def _scheduler_api_base_url() -> str:
    """本机回环调用 Flask API；HOST 为 0.0.0.0 时改用 127.0.0.1。"""
    from config import Config

    h = (Config.HOST or "").strip()
    if h in ("0.0.0.0", "::", ""):
        h = "127.0.0.1"
    return f"http://{h}:{Config.PORT}"


def _format_pdd_erp_sync_summary(resp: Dict[str, Any]) -> str:
    """将 sync-erp-orders 的 JSON 整理为可读多行文本（用于日志与飞书）。"""
    lines = [
        f"成功: {'是' if resp.get('success') else '否'}",
        f"说明: {resp.get('message') or resp.get('error') or '-'}",
    ]
    if resp.get("intercepted"):
        lines.append("登录拦截: 是（需在助手内扫码后再跑）")
    if resp.get("page_url"):
        lines.append(f"页面: {resp['page_url']}")
    if resp.get("row_count") is not None:
        lines.append(f"抓取行数: {resp['row_count']}")
    fs = resp.get("feishu_sync")
    if isinstance(fs, dict):
        lines.append(
            f"飞书: {fs.get('message') or '-'} "
            f"(新建 {fs.get('create_count', '-')}, 更新 {fs.get('update_count', '-')}, "
            f"失败 {fs.get('fail_count', '-')})"
        )
        if fs.get("update_skipped_no_delta"):
            lines.append(f"已存在无增量跳过: {fs['update_skipped_no_delta']}")
    return "\n".join(lines)


def _notify_pdd_erp_sync_result(
    ok: bool,
    summary: str,
    raw: Optional[Dict[str, Any]] = None,
    feishu_user_id: Optional[str] = None,
) -> None:
    """执行结束后发飞书私聊（默认 FEISHU_USER_ID；可在任务 data.feishu_user_id 覆盖）。"""
    title = "【订单同步 ERP】定时执行完成" if ok else "【订单同步 ERP】定时执行异常"
    when = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    body = f"时间: {when}\n{summary}"
    if raw is not None:
        tlog.debug("ERP 定时同步原始响应: %s", raw)
    try:
        from config import Config
        from tools.feishu.message_sender import get_message_sender

        sender = get_message_sender()
        if not Config.FEISHU_ENABLED or not sender.client.is_configured():
            tlog.info("飞书未配置或未启用，跳过 ERP 同步结果通知")
            return
        if not (feishu_user_id or "").strip() and not sender.default_user_id:
            tlog.info("未配置 FEISHU_USER_ID 且任务未指定 feishu_user_id，跳过 ERP 同步结果通知")
            return
        text = f"{title}\n{body}"
        if len(text) > 4500:
            text = text[:4497] + "..."
        if sender.send_custom_message(text, user_id=feishu_user_id):
            tlog.info("已发送 ERP 同步结果飞书通知")
        else:
            tlog.warning("ERP 同步结果飞书通知发送返回失败")
    except Exception as e:
        tlog.warning("发送 ERP 同步结果飞书通知异常: %s", e, exc_info=True)


def _run_pdd_erp_order_sync(data: Dict[str, Any], _tid: str = "") -> Tuple[int, str]:
    """
    定时触发拼多多 ERP 全部订单 → 飞书同步（与页面「开始同步」同源 API）。
    _tid 为内部传入的 task_id，用于关联日志行。
    """
    import requests

    data = data or {}
    url = (data.get("url") or "").strip()
    if not url.startswith("http"):
        url = f"{_scheduler_api_base_url()}/api/pinduoduo/sync-erp-orders"
    body = data.get("data") if isinstance(data.get("data"), dict) else {}
    try:
        timeout = float(data.get("timeout", 780))
    except (TypeError, ValueError):
        timeout = 780.0

    _task_log(_tid, "INFO", "定时 ERP 订单同步: POST %s timeout=%s", url, timeout)
    try:
        r = requests.post(url, json=body, timeout=timeout)
        ct = (r.headers.get("content-type") or "").lower()
        if "application/json" in ct:
            resp = r.json()
        else:
            resp = {"success": False, "message": r.text[:2000] or f"HTTP {r.status_code}"}

        summary = _format_pdd_erp_sync_summary(resp if isinstance(resp, dict) else {})
        ok = bool(isinstance(resp, dict) and resp.get("success")) and r.status_code == 200
        if isinstance(resp, dict) and resp.get("intercepted"):
            ok = False

        uid = (data.get("feishu_user_id") or "").strip() or None
        _notify_pdd_erp_sync_result(
            ok, summary, resp if isinstance(resp, dict) else None, feishu_user_id=uid
        )

        if not ok:
            err = (
                (resp.get("message") or resp.get("error") if isinstance(resp, dict) else None)
                or r.text
                or str(r.status_code)
            )
            _task_log(_tid, "WARNING", "ERP 同步 API 未成功: %s", err)
            return 0, summary

        _task_log(_tid, "INFO", "ERP 同步定时任务完成:\n%s", summary)
        return int(resp.get("row_count") or 0), summary
    except Exception as e:
        summary = f"请求异常: {e}"
        uid = (data.get("feishu_user_id") or "").strip() or None
        _notify_pdd_erp_sync_result(False, summary, None, feishu_user_id=uid)
        _task_log(_tid, "ERROR", "调用 ERP 同步 API 失败: %s", e)
        return 0, summary


def _run_http_request(data: Dict[str, Any], _tid: str = "") -> Tuple[int, str]:
    """通用 HTTP 定时请求：支持 GET/POST/PUT/DELETE，可配置 headers、body、timeout。"""
    import requests as req_lib

    data = data or {}
    url = (data.get("url") or "").strip()
    if not url:
        _task_log(_tid, "ERROR", "未配置请求 URL")
        return 0, "未配置请求 URL"
    method = (data.get("method") or "GET").upper()
    headers = data.get("headers") if isinstance(data.get("headers"), dict) else {}
    body = data.get("body") if isinstance(data.get("body"), dict) else None
    try:
        timeout = float(data.get("timeout", 30))
    except (TypeError, ValueError):
        timeout = 30.0

    _task_log(_tid, "INFO", "HTTP 请求: %s %s  timeout=%s", method, url, timeout)
    try:
        if method in ("POST", "PUT", "PATCH"):
            r = req_lib.request(method, url, json=body, headers=headers, timeout=timeout)
        else:
            r = req_lib.request(method, url, headers=headers, timeout=timeout)
        status = r.status_code
        ct = (r.headers.get("content-type") or "").lower()
        if "application/json" in ct:
            try:
                resp_text = str(r.json())[:1000]
            except Exception:
                resp_text = r.text[:1000]
        else:
            resp_text = r.text[:1000]
        ok = 200 <= status < 400
        level = "INFO" if ok else "WARNING"
        _task_log(_tid, level, "HTTP %s → %s\n%s", status, url, resp_text)
        return (1 if ok else 0), f"HTTP {status}: {resp_text[:300]}"
    except Exception as e:
        _task_log(_tid, "ERROR", "HTTP 请求失败: %s", e)
        return 0, str(e)


def _run_python_script(data: Dict[str, Any], _tid: str = "") -> Tuple[int, str]:
    """执行 Python 脚本（data.script 为脚本内容，或 data.script_path 为文件路径）。"""
    import subprocess
    import tempfile

    data = data or {}
    script = (data.get("script") or "").strip()
    script_path = (data.get("script_path") or "").strip()
    try:
        timeout = float(data.get("timeout", 60))
    except (TypeError, ValueError):
        timeout = 60.0

    if not script and not script_path:
        _task_log(_tid, "ERROR", "未配置脚本内容或脚本路径")
        return 0, "未配置脚本内容或脚本路径"

    use_tmp = False
    if script:
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8")
        tmp.write(script)
        tmp.close()
        exec_path = tmp.name
        use_tmp = True
        _task_log(_tid, "INFO", "执行内联脚本 (%d 字符), timeout=%s", len(script), timeout)
    else:
        import os
        if not os.path.isfile(script_path):
            _task_log(_tid, "ERROR", "脚本文件不存在: %s", script_path)
            return 0, f"脚本文件不存在: {script_path}"
        exec_path = script_path
        _task_log(_tid, "INFO", "执行脚本文件: %s  timeout=%s", script_path, timeout)

    import sys as _sys
    python = _sys.executable or "python"
    try:
        result = subprocess.run(
            [python, exec_path],
            capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace",
        )
        stdout = (result.stdout or "").strip()
        stderr = (result.stderr or "").strip()
        code = result.returncode
        output_lines = []
        if stdout:
            output_lines.append(stdout[-2000:])
        if stderr:
            output_lines.append(f"[stderr] {stderr[-1000:]}")
        output = "\n".join(output_lines) or "(无输出)"
        if code == 0:
            _task_log(_tid, "INFO", "脚本执行成功 (exit 0):\n%s", output[:500])
            return 1, output[:500]
        else:
            _task_log(_tid, "WARNING", "脚本退出码 %s:\n%s", code, output[:500])
            return 0, f"exit {code}: {output[:500]}"
    except subprocess.TimeoutExpired:
        _task_log(_tid, "ERROR", "脚本执行超时 (%s秒)", timeout)
        return 0, f"脚本执行超时 ({timeout}秒)"
    except Exception as e:
        _task_log(_tid, "ERROR", "执行脚本异常: %s", e)
        return 0, str(e)
    finally:
        if use_tmp:
            try:
                import os
                os.unlink(exec_path)
            except OSError:
                pass


def get_task_handlers() -> Dict[str, Dict[str, Any]]:
    """任务类型 -> { name, run(data) -> (code, message) or raise。"""
    return {
        "http_request": {
            "name": "HTTP 定时请求",
            "run": _run_http_request,
        },
        "python_script": {
            "name": "Python 脚本",
            "run": _run_python_script,
        },
        "order_1688_fill_detail": {
            "name": "1688 订单补详情",
            "run": _run_order_1688_fill_detail,
        },
        "pdd_erp_order_sync": {
            "name": "拼多多 ERP 订单同步",
            "run": _run_pdd_erp_order_sync,
        },
    }


def get_task_type_schemas() -> Dict[str, Dict[str, Any]]:
    """返回每种任务类型的表单 schema（供前端动态渲染新增表单）。"""
    handlers = get_task_handlers()
    schemas = {
        "http_request": {
            "name": handlers["http_request"]["name"],
            "description": "定时发送 HTTP 请求到指定 URL，适用于调用任意 API、Webhook 等场景",
            "fields": [
                {"key": "url", "label": "请求 URL", "type": "text", "required": True, "placeholder": "https://example.com/api/xxx"},
                {"key": "method", "label": "请求方法", "type": "select", "options": ["GET", "POST", "PUT", "DELETE"], "default": "GET"},
                {"key": "headers", "label": "请求头 (JSON)", "type": "json", "placeholder": '{"Authorization": "Bearer xxx"}'},
                {"key": "body", "label": "请求体 (JSON, POST/PUT 时有效)", "type": "json", "placeholder": '{"key": "value"}'},
                {"key": "timeout", "label": "超时时间 (秒)", "type": "number", "default": 30, "min": 1, "max": 600},
            ],
        },
        "python_script": {
            "name": handlers["python_script"]["name"],
            "description": "定时执行 Python 脚本，可以写内联代码或指定脚本文件路径",
            "fields": [
                {"key": "script", "label": "脚本内容 (与脚本路径二选一)", "type": "code", "placeholder": "print('Hello from scheduled task')"},
                {"key": "script_path", "label": "脚本文件路径 (与脚本内容二选一)", "type": "text", "placeholder": "C:/scripts/my_task.py"},
                {"key": "timeout", "label": "超时时间 (秒)", "type": "number", "default": 60, "min": 1, "max": 3600},
            ],
        },
        "order_1688_fill_detail": {
            "name": handlers["order_1688_fill_detail"]["name"],
            "description": "调用本机 API 补充 1688 订单详情信息",
            "fields": [
                {"key": "url", "label": "API URL (可选，留空使用默认)", "type": "text", "placeholder": "留空使用默认地址"},
            ],
        },
        "pdd_erp_order_sync": {
            "name": handlers["pdd_erp_order_sync"]["name"],
            "description": "同步拼多多 ERP 全部订单到飞书多维表格",
            "fields": [
                {"key": "url", "label": "API URL (可选，留空使用默认)", "type": "text", "placeholder": "留空使用默认地址"},
                {"key": "timeout", "label": "超时时间 (秒)", "type": "number", "default": 780, "min": 60, "max": 3600},
                {"key": "feishu_user_id", "label": "飞书通知用户 ID (可选)", "type": "text", "placeholder": "留空使用默认配置"},
            ],
        },
    }
    return schemas


def _run_task_by_id(task_id: str) -> None:
    """供 APScheduler 定时调用：按 id 执行任务（只执行，不返回）。"""
    try:
        from scheduler.task_config import get_task
        task = get_task(task_id)
        if not task:
            _task_log(task_id, "WARNING", "定时执行时未找到任务: id=%s", task_id)
            return
        _task_log(task_id, "INFO", "========== 定时触发 ==========")
        _task_log(task_id, "INFO", "任务: %s  类型: %s  id: %s", task.get("name"), task.get("type"), task_id)
        handlers = get_task_handlers()
        handler_info = handlers.get(task.get("type"))
        if not handler_info:
            _task_log(task_id, "WARNING", "未知任务类型: type=%s", task.get("type"))
            _set_task_finished(task_id, False, f"未知任务类型: {task.get('type')}")
            return
        _set_task_running(task_id)
        data = task.get("data") or {}
        result = handler_info["run"](data, _tid=task_id)
        if isinstance(result, (list, tuple)) and len(result) >= 2:
            _task_log(task_id, "INFO", "定时任务执行完成: %s", result[1])
            _set_task_finished(task_id, True, str(result[1]))
        else:
            _task_log(task_id, "INFO", "定时任务执行完成")
            _set_task_finished(task_id, True, "已执行")
    except Exception as e:
        _task_log(task_id, "ERROR", "定时任务执行异常: %s", e)
        _set_task_finished(task_id, False, str(e))


def run_task_by_id(task_id: str) -> Tuple[bool, Any, str]:
    """
    立即执行指定任务（手动触发 / 页面点「执行」）。
    返回 (success, result_data, message)。
    """
    from scheduler.task_config import get_task
    task = get_task(task_id)
    if not task:
        _task_log(task_id, "WARNING", "执行任务失败: 任务不存在 id=%s", task_id)
        return False, None, "任务不存在"
    handlers = get_task_handlers()
    handler_info = handlers.get(task.get("type"))
    if not handler_info:
        _task_log(task_id, "WARNING", "执行任务失败: 未知类型 id=%s type=%s", task_id, task.get("type"))
        return False, None, "未知任务类型: " + (task.get("type") or "")
    _task_log(task_id, "INFO", "========== 手动触发 ==========")
    _task_log(task_id, "INFO", "任务: %s  类型: %s  id: %s", task.get("name"), task.get("type"), task_id)
    _set_task_running(task_id)
    try:
        data = task.get("data") or {}
        result = handler_info["run"](data, _tid=task_id)
        if isinstance(result, (list, tuple)) and len(result) >= 2:
            msg = str(result[1])
            _task_log(task_id, "INFO", "任务执行完成: %s", msg)
            _set_task_finished(task_id, True, msg)
            return True, result[0], msg
        msg = str(result) if result is not None else "已执行"
        _task_log(task_id, "INFO", "任务执行完成")
        _set_task_finished(task_id, True, msg)
        return True, result, msg
    except Exception as e:
        _task_log(task_id, "ERROR", "任务执行异常: %s", e)
        _set_task_finished(task_id, False, str(e))
        return False, None, str(e)


def get_scheduler():
    """获取全局调度器实例（懒创建）。"""
    global _scheduler
    if _scheduler is None:
        from apscheduler.schedulers.background import BackgroundScheduler
        _scheduler = BackgroundScheduler()
    return _scheduler


def _register_jobs_from_config() -> None:
    """从配置文件加载任务并注册到调度器（tasks.json，可由种子文件按规范初始化）。跳过 enabled=false 的任务。"""
    from apscheduler.triggers.cron import CronTrigger
    from scheduler.task_config import list_tasks

    sched = get_scheduler()
    for task in list_tasks():
        task_id = task.get("id")
        if not task.get("enabled", True):
            logger.info("跳过已禁用任务: id=%s name=%s", task_id, task.get("name"))
            continue
        cron = (task.get("cron") or "").strip() or "0 * * * *"
        if not task_id or len(cron.split()) < 5:
            continue
        try:
            trigger = CronTrigger.from_crontab(cron)
            sched.add_job(
                lambda tid=task_id: _run_task_by_id(tid),
                trigger=trigger,
                id=task_id,
                name=task.get("name") or task_id,
                replace_existing=True,
            )
            logger.info("已注册定时任务: id=%s name=%s cron=%s", task_id, task.get("name"), cron)
        except Exception as e:
            logger.warning("注册任务失败 id=%s: %s", task_id, e)


def start_scheduler() -> bool:
    """启动定时任务调度器（从配置加载任务并 start）。"""
    from config import Config

    if not getattr(Config, "SCHEDULER_ENABLED", True):
        logger.info("定时任务模块未启用 (SCHEDULER_ENABLED=False)，跳过")
        return False
    try:
        sched = get_scheduler()
        _register_jobs_from_config()
        if not sched.get_jobs():
            logger.info("无定时任务，调度器不启动")
            return False
        sched.start()
        logger.info("定时任务调度器已启动")
        return True
    except Exception as e:
        logger.error("启动定时任务调度器失败: %s", e, exc_info=True)
        return False


def shutdown_scheduler() -> None:
    """关闭定时任务调度器。"""
    global _scheduler
    if _scheduler is not None:
        try:
            _scheduler.shutdown(wait=False)
            logger.info("定时任务调度器已关闭")
        except Exception as e:
            logger.debug("关闭调度器时: %s", e)
        _scheduler = None


def list_jobs() -> List[Dict[str, Any]]:
    """返回任务列表：配置中的 id/name/type/data/cron + 调度器中的 next_run_time + 执行状态。"""
    from scheduler.task_config import list_tasks

    sched = get_scheduler()
    tasks = list_tasks()
    all_status = get_all_task_status()
    handlers = get_task_handlers()
    out = []
    for t in tasks:
        tid = t.get("id")
        job = sched.get_job(tid) if sched else None
        next_run = str(job.next_run_time) if job and job.next_run_time else None
        enabled = t.get("enabled", True)
        status = all_status.get(tid, {})
        handler = handlers.get(t.get("type"))
        type_name = handler["name"] if handler else t.get("type", "")
        out.append({
            "id": tid,
            "name": t.get("name") or tid,
            "type": t.get("type"),
            "type_name": type_name,
            "data": t.get("data"),
            "cron": t.get("cron"),
            "enabled": enabled,
            "next_run_time": next_run if enabled else None,
            "running": status.get("running", False),
            "started_at": status.get("started_at"),
            "last_run": status.get("last_run"),
            "last_success": status.get("last_success"),
            "last_message": status.get("last_message"),
        })
    return out


def add_task_and_register(name: str, task_type: str, data: Optional[Dict[str, Any]] = None, cron: str = "0 * * * *") -> Dict[str, Any]:
    """新增任务配置并注册到调度器。返回任务项。"""
    from apscheduler.triggers.cron import CronTrigger
    from scheduler.task_config import add_task as config_add_task

    task = config_add_task(name=name, task_type=task_type, data=data, cron=cron)
    cron = (task.get("cron") or "").strip() or "0 * * * *"
    if len(cron.split()) >= 5:
        try:
            sched = get_scheduler()
            trigger = CronTrigger.from_crontab(cron)
            sched.add_job(
                lambda tid=task["id"]: _run_task_by_id(tid),
                trigger=trigger,
                id=task["id"],
                name=task.get("name") or task["id"],
                replace_existing=True,
            )
            if not sched.running:
                sched.start()
        except Exception as e:
            logger.warning("注册新任务到调度器失败: %s", e)
    return task


def remove_task_and_unregister(task_id: str) -> bool:
    """删除任务配置并从调度器移除。"""
    from scheduler.task_config import remove_task as config_remove_task

    if not config_remove_task(task_id):
        return False
    try:
        get_scheduler().remove_job(task_id)
    except Exception as e:
        logger.debug("从调度器移除任务时: %s", e)
    return True


def pause_task(task_id: str) -> bool:
    """暂停任务：从调度器移除 job，配置标记 enabled=false。"""
    from scheduler.task_config import update_task_field
    update_task_field(task_id, "enabled", False)
    try:
        sched = get_scheduler()
        if sched.get_job(task_id):
            sched.remove_job(task_id)
            logger.info("已暂停任务: id=%s", task_id)
    except Exception as e:
        logger.debug("从调度器移除暂停任务时: %s", e)
    return True


def resume_task(task_id: str) -> bool:
    """恢复任务：配置标记 enabled=true，重新注册到调度器。"""
    from apscheduler.triggers.cron import CronTrigger
    from scheduler.task_config import get_task, update_task_field

    update_task_field(task_id, "enabled", True)
    task = get_task(task_id)
    if not task:
        return False
    cron = (task.get("cron") or "").strip() or "0 * * * *"
    if len(cron.split()) < 5:
        return False
    try:
        sched = get_scheduler()
        trigger = CronTrigger.from_crontab(cron)
        sched.add_job(
            lambda tid=task_id: _run_task_by_id(tid),
            trigger=trigger,
            id=task_id,
            name=task.get("name") or task_id,
            replace_existing=True,
        )
        if not sched.running:
            sched.start()
        logger.info("已恢复任务: id=%s", task_id)
    except Exception as e:
        logger.warning("恢复任务到调度器失败: %s", e)
    return True


def get_task_types() -> List[Dict[str, str]]:
    """返回可用的任务类型列表（用于前端下拉）。"""
    handlers = get_task_handlers()
    return [{"type": k, "name": v.get("name", k)} for k, v in handlers.items()]
