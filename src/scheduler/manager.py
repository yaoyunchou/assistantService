"""
定时任务管理器：基于 APScheduler，任务配置存 JSON（id=uuid, name, type, data, cron），按 type 执行对应 handler。
"""
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

from utils.logger import get_logger

logger = get_logger("Scheduler")

_scheduler = None


def _run_order_1688_fill_detail(data: Dict[str, Any]) -> Tuple[int, str]:
    """
    定时器只负责调用业务 API，不执行业务逻辑。
    入参 data 来自任务配置 task["data"]（tasks.json 里该任务的 data 字段，或前端新增时填的「运行参数」）。
    - 若 data.url 存在且为合法 http(s) 地址，则请求该 URL；
    - 否则使用默认：Config.HOST + Config.PORT + /api/order_1688/fill_detail。
    请求体使用 data.data（未配置则为 {}）。
    """
    from config import Config
    import requests
    data = data or {}
    url = (data.get("url") or "").strip()
    if url and url.startswith("http"):
        logger.info("使用任务配置 URL: %s", url)
    else:
        url = f"http://{Config.HOST}:{Config.PORT}/api/order_1688/fill_detail"
        logger.info("任务未配置 url，使用默认: %s", url)
    body = data.get("data") if isinstance(data.get("data"), dict) else {}
    logger.info("调用业务 API: POST %s", url)
    try:
        r = requests.post(url, json=body, timeout=300)
        resp_body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        if not resp_body.get("success"):
            err = resp_body.get("error") or resp_body.get("message") or r.text or str(r.status_code)
            logger.warning("业务 API 返回失败: %s", err)
            return 0, err
        filled = int(resp_body.get("filled_count", 0) or 0)
        msg = str(resp_body.get("message") or "已执行")
        logger.info("业务 API 返回成功: filled_count=%s message=%s", filled, msg)
        return filled, msg
    except Exception as e:
        logger.warning("调用 1688 补详情 API 失败: %s", e)
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
        logger.debug("ERP 定时同步原始响应: %s", raw)
    try:
        from config import Config
        from tools.feishu.message_sender import get_message_sender

        sender = get_message_sender()
        if not Config.FEISHU_ENABLED or not sender.client.is_configured():
            logger.info("飞书未配置或未启用，跳过 ERP 同步结果通知")
            return
        if not (feishu_user_id or "").strip() and not sender.default_user_id:
            logger.info("未配置 FEISHU_USER_ID 且任务未指定 feishu_user_id，跳过 ERP 同步结果通知")
            return
        text = f"{title}\n{body}"
        if len(text) > 4500:
            text = text[:4497] + "..."
        if sender.send_custom_message(text, user_id=feishu_user_id):
            logger.info("已发送 ERP 同步结果飞书通知")
        else:
            logger.warning("ERP 同步结果飞书通知发送返回失败")
    except Exception as e:
        logger.warning("发送 ERP 同步结果飞书通知异常: %s", e, exc_info=True)


def _run_pdd_erp_order_sync(data: Dict[str, Any]) -> Tuple[int, str]:
    """
    定时触发拼多多 ERP 全部订单 → 飞书同步（与页面「开始同步」同源 API）。

    task data（可选）:
        url: 完整 POST 地址；默认 {api_base}/api/pinduoduo/sync-erp-orders
        data: 请求 JSON 体（app_token、table_id、scroll_max_steps 等）
        timeout: 请求超时秒数，默认 780（应略大于路由内浏览器池超时）
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

    logger.info("定时 ERP 订单同步: POST %s timeout=%s", url, timeout)
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
            logger.warning("ERP 同步 API 未成功: %s", err)
            return 0, summary

        logger.info("ERP 同步定时任务完成:\n%s", summary)
        return int(resp.get("row_count") or 0), summary
    except Exception as e:
        summary = f"请求异常: {e}"
        uid = (data.get("feishu_user_id") or "").strip() or None
        _notify_pdd_erp_sync_result(False, summary, None, feishu_user_id=uid)
        logger.warning("调用 ERP 同步 API 失败: %s", e, exc_info=True)
        return 0, summary


def get_task_handlers() -> Dict[str, Dict[str, Any]]:
    """任务类型 -> { name, run(data) -> (code, message) or raise。"""
    return {
        "order_1688_fill_detail": {
            "name": "1688 订单补详情",
            "run": _run_order_1688_fill_detail,
        },
        "pdd_erp_order_sync": {
            "name": "拼多多 ERP 订单同步",
            "run": _run_pdd_erp_order_sync,
        },
    }


def _run_task_by_id(task_id: str) -> None:
    """供 APScheduler 定时调用：按 id 执行任务（只执行，不返回）。"""
    try:
        from scheduler.task_config import get_task
        task = get_task(task_id)
        if not task:
            logger.warning("定时执行时未找到任务: id=%s", task_id)
            return
        logger.info("定时触发执行任务: id=%s name=%s type=%s", task_id, task.get("name"), task.get("type"))
        handlers = get_task_handlers()
        handler_info = handlers.get(task.get("type"))
        if not handler_info:
            logger.warning("未知任务类型: type=%s", task.get("type"))
            return
        data = task.get("data") or {}
        result = handler_info["run"](data)
        if isinstance(result, (list, tuple)) and len(result) >= 2:
            logger.info("定时任务执行完成: id=%s message=%s", task_id, result[1])
        else:
            logger.info("定时任务执行完成: id=%s", task_id)
    except Exception as e:
        logger.error("定时任务执行异常: id=%s %s", task_id, e, exc_info=True)


def run_task_by_id(task_id: str) -> Tuple[bool, Any, str]:
    """
    立即执行指定任务。返回 (success, result_data, message)。
    result_data 可为 filled_count 等，供 API 返回。
    """
    from scheduler.task_config import get_task
    task = get_task(task_id)
    if not task:
        logger.warning("执行任务失败: 任务不存在 id=%s", task_id)
        return False, None, "任务不存在"
    handlers = get_task_handlers()
    handler_info = handlers.get(task.get("type"))
    if not handler_info:
        logger.warning("执行任务失败: 未知类型 id=%s type=%s", task_id, task.get("type"))
        return False, None, "未知任务类型: " + (task.get("type") or "")
    logger.info("开始执行任务: id=%s name=%s type=%s", task_id, task.get("name"), task.get("type"))
    try:
        data = task.get("data") or {}
        result = handler_info["run"](data)
        if isinstance(result, (list, tuple)) and len(result) >= 2:
            logger.info("任务执行完成: id=%s success=True message=%s", task_id, result[1])
            return True, result[0], str(result[1])
        logger.info("任务执行完成: id=%s success=True", task_id)
        return True, result, str(result) if result is not None else "已执行"
    except Exception as e:
        logger.error("任务执行异常: id=%s error=%s", task_id, e, exc_info=True)
        return False, None, str(e)


def get_scheduler():
    """获取全局调度器实例（懒创建）。"""
    global _scheduler
    if _scheduler is None:
        from apscheduler.schedulers.background import BackgroundScheduler
        _scheduler = BackgroundScheduler()
    return _scheduler


def _register_jobs_from_config() -> None:
    """从配置文件加载任务并注册到调度器（tasks.json，可由种子文件按规范初始化）。"""
    from apscheduler.triggers.cron import CronTrigger
    from scheduler.task_config import list_tasks

    sched = get_scheduler()
    for task in list_tasks():
        task_id = task.get("id")
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
    """返回任务列表：配置中的 id/name/type/data/cron + 调度器中的 next_run_time。"""
    from scheduler.task_config import list_tasks

    sched = get_scheduler()
    tasks = list_tasks()
    out = []
    for t in tasks:
        job = sched.get_job(t.get("id")) if sched else None
        next_run = str(job.next_run_time) if job and job.next_run_time else None
        out.append({
            "id": t.get("id"),
            "name": t.get("name") or t.get("id"),
            "type": t.get("type"),
            "data": t.get("data"),
            "cron": t.get("cron"),
            "next_run_time": next_run,
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


def get_task_types() -> List[Dict[str, str]]:
    """返回可用的任务类型列表（用于前端下拉）。"""
    handlers = get_task_handlers()
    return [{"type": k, "name": v.get("name", k)} for k, v in handlers.items()]
