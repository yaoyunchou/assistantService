"""
workflow.steps.notify_steps — 通知类原子步骤

通过 notify 模块发送消息，不直接调用飞书 API。
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from workflow.step import BaseStep, StepContext, StepResult


class NotifyTaskResultStep(BaseStep):
    """
    发送任务执行结果通知（Webhook 卡片）。

    Context 读取：
        result_success (bool)   — 任务是否成功
        result_message (str)    — 结果描述

    Params（工作流 JSON）：
        source      (str) — 来源模块，如 'pinduoduo'
        title       (str) — 通知标题
        link_url    (str) — 可选跳转链接

    Context 写出：
        notify_sent (bool) — 是否发送成功
    """

    name = "notify.task_result"
    display_name = "发送任务结果通知"
    description = "通过 notify 模块发送任务执行结果的 Webhook 卡片通知"
    input_keys = ["result_success", "result_message"]
    output_keys = ["notify_sent"]

    def execute(self, ctx: StepContext, params: Optional[Dict[str, Any]] = None) -> StepResult:
        params = params or {}
        source = params.get("source", "system")
        title = params.get("title", "任务执行结果")
        link_url = params.get("link_url", "")

        success = bool(ctx.get("result_success", True))
        description = str(ctx.get("result_message", ""))

        try:
            from notify import task_result
            sent = task_result(source, title, description, success=success, link_url=link_url)
            ctx.set("notify_sent", sent)
            return StepResult.ok(f"通知已{'发送' if sent else '跳过'}", notify_sent=sent)
        except Exception as e:
            ctx.set("notify_sent", False)
            return StepResult.fail(f"通知发送失败: {e}")


class NotifyLoginAlertStep(BaseStep):
    """
    发送登录失效通知。

    Params：
        source (str) — 来源模块，如 'pinduoduo'

    Context 写出：
        notify_sent (bool)
    """

    name = "notify.login_alert"
    display_name = "发送登录失效通知"
    description = "通知用户指定平台需要重新登录"
    input_keys = []
    output_keys = ["notify_sent"]

    def execute(self, ctx: StepContext, params: Optional[Dict[str, Any]] = None) -> StepResult:
        params = params or {}
        source = params.get("source", "system")
        try:
            from notify import login_alert
            sent = login_alert(source)
            ctx.set("notify_sent", sent)
            return StepResult.ok(f"登录失效通知已{'发送' if sent else '跳过'}", notify_sent=sent)
        except Exception as e:
            ctx.set("notify_sent", False)
            return StepResult.fail(f"登录失效通知发送失败: {e}")
