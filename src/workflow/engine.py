"""
workflow.engine — 工作流执行引擎
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from workflow.registry import StepRegistry, get_registry
from workflow.step import StepContext, StepResult
from utils.logger import get_logger

logger = get_logger("WorkflowEngine")


@dataclass
class WorkflowResult:
    success: bool
    message: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    step_results: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    logs: List[str] = field(default_factory=list)


class WorkflowEngine:
    """
    工作流执行引擎。

    工作流定义格式（JSON / dict）：
    {
      "id": "pdd_erp_full_sync",
      "name": "拼多多 ERP 订单全量同步",
      "steps": [
        {
          "step": "pdd.check_login",
          "params": { "target_url": "erp/order/all" },
          "on_error": "abort",           // abort(默认) | skip | continue
          "condition": {                 // 可选：满足条件才执行
            "key": "login_status",
            "equals": true
          }
        },
        ...
      ]
    }
    """

    def __init__(self, registry: Optional[StepRegistry] = None):
        self.registry = registry or get_registry()

    def run(
        self,
        workflow_def: Dict[str, Any],
        initial_data: Optional[Dict[str, Any]] = None,
    ) -> WorkflowResult:
        """
        执行工作流。

        Args:
            workflow_def:  工作流定义字典
            initial_data:  初始上下文数据

        Returns:
            WorkflowResult（含每步结果、整体成功标志、日志）
        """
        wf_name = workflow_def.get("name", workflow_def.get("id", "unnamed"))
        logger.info("工作流开始: %s", wf_name)

        ctx = StepContext(initial_data)
        step_results: List[Dict[str, Any]] = []

        steps = workflow_def.get("steps", [])
        for i, step_def in enumerate(steps):
            step_name = step_def.get("step", "")
            params = step_def.get("params", {})
            on_error = step_def.get("on_error", "abort")
            condition = step_def.get("condition")

            # 条件判断
            if condition and not self._check_condition(condition, ctx):
                logger.info("步骤 [%s] 条件不满足，跳过", step_name)
                step_results.append({"step": step_name, "skipped": True, "reason": "condition_not_met"})
                continue

            # 获取步骤实例
            try:
                step = self.registry.get(step_name)
            except ValueError as e:
                msg = str(e)
                logger.error("步骤 [%s] 未找到: %s", step_name, msg)
                step_results.append({"step": step_name, "success": False, "error": msg})
                if on_error == "abort":
                    return WorkflowResult(
                        success=False,
                        message=f"步骤 [{step_name}] 未注册，工作流中止",
                        step_results=step_results,
                        errors=ctx.errors,
                        logs=ctx.logs,
                    )
                continue

            # 前置校验
            if not step.validate(ctx):
                msg = f"步骤 [{step_name}] 前置校验失败"
                logger.warning(msg)
                step_results.append({"step": step_name, "success": False, "error": msg})
                if on_error == "abort":
                    return WorkflowResult(
                        success=False, message=msg,
                        step_results=step_results, errors=ctx.errors, logs=ctx.logs,
                    )
                continue

            # 执行步骤
            logger.info("执行步骤 [%d/%d] %s", i + 1, len(steps), step_name)
            try:
                result: StepResult = step.execute(ctx, params)
            except Exception as exc:
                msg = f"步骤 [{step_name}] 异常: {exc}"
                logger.exception(msg)
                result = StepResult.fail(msg)

            step_results.append({
                "step": step_name,
                "success": result.success,
                "message": result.message,
                "data": result.data,
            })

            if result.success:
                # 将步骤输出写入上下文
                if result.data:
                    ctx.merge(result.data)
                logger.info("步骤 [%s] 完成: %s", step_name, result.message or "OK")
            else:
                ctx.add_error(f"[{step_name}] {result.message}")
                logger.warning("步骤 [%s] 失败: %s", step_name, result.message)

                if on_error == "abort":
                    return WorkflowResult(
                        success=False,
                        message=f"步骤 [{step_name}] 失败，工作流中止: {result.message}",
                        data=ctx.to_dict(),
                        step_results=step_results,
                        errors=ctx.errors,
                        logs=ctx.logs,
                    )
                # skip / continue：继续执行后续步骤

        logger.info("工作流完成: %s", wf_name)
        return WorkflowResult(
            success=True,
            message=f"工作流 [{wf_name}] 执行完成，共 {len(steps)} 步",
            data=ctx.to_dict(),
            step_results=step_results,
            errors=ctx.errors,
            logs=ctx.logs,
        )

    @staticmethod
    def _check_condition(condition: Dict[str, Any], ctx: StepContext) -> bool:
        """
        简单条件判断。

        支持格式：
          { "key": "login_status", "equals": true }
          { "key": "row_count", "gt": 0 }
          { "key": "ai_verdict", "in": ["normal", "ok"] }
        """
        key = condition.get("key")
        val = ctx.get(key)

        if "equals" in condition:
            return val == condition["equals"]
        if "not_equals" in condition:
            return val != condition["not_equals"]
        if "gt" in condition:
            return (val or 0) > condition["gt"]
        if "gte" in condition:
            return (val or 0) >= condition["gte"]
        if "lt" in condition:
            return (val or 0) < condition["lt"]
        if "in" in condition:
            return val in condition["in"]
        if "not_in" in condition:
            return val not in condition["not_in"]
        if "exists" in condition:
            return (val is not None) == condition["exists"]

        return bool(val)
