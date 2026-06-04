"""
workflow — 可组合工作流引擎

公共接口
--------
    from workflow import WorkflowEngine, StepContext, StepResult, BaseStep, get_registry

    # 运行工作流
    engine = WorkflowEngine()
    result = engine.run(workflow_def, initial_data={"order_count": 10})

    # 注册自定义步骤
    registry = get_registry()
    registry.register(MyCustomStep)

    # 列出已注册步骤
    print(registry.list_steps())
"""
from workflow.step import BaseStep, StepContext, StepResult
from workflow.registry import StepRegistry, get_registry
from workflow.engine import WorkflowEngine, WorkflowResult

__all__ = [
    "BaseStep",
    "StepContext",
    "StepResult",
    "StepRegistry",
    "get_registry",
    "WorkflowEngine",
    "WorkflowResult",
]
