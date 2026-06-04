"""
workflow.step — 工作流核心数据结构

BaseStep、StepContext、StepResult 是整个工作流引擎的基础抽象。
每个原子步骤继承 BaseStep，通过 StepContext 传递数据，返回 StepResult。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class StepContext:
    """
    工作流执行上下文：步骤之间的数据传递容器。

    步骤通过 ctx.set(key, value) 写出结果，
    后续步骤通过 ctx.get(key) 读取前驱步骤的输出。
    """

    def __init__(self, initial_data: Optional[Dict[str, Any]] = None):
        self._data: Dict[str, Any] = dict(initial_data or {})
        self.errors: List[str] = []
        self.logs: List[str] = []

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def merge(self, data: Dict[str, Any]) -> None:
        self._data.update(data)

    def to_dict(self) -> Dict[str, Any]:
        return dict(self._data)

    def log(self, message: str) -> None:
        self.logs.append(message)

    def add_error(self, message: str) -> None:
        self.errors.append(message)


@dataclass
class StepResult:
    """步骤执行结果。"""
    success: bool
    message: str = ""
    data: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(cls, message: str = "", **kwargs: Any) -> "StepResult":
        return cls(success=True, message=message, data=kwargs)

    @classmethod
    def fail(cls, message: str, **kwargs: Any) -> "StepResult":
        return cls(success=False, message=message, data=kwargs)


class BaseStep(ABC):
    """
    原子步骤基类。

    子类需要：
      1. 设置 name（唯一标识，格式 namespace.action，如 pdd.check_login）
      2. 设置 display_name（中文名，用于日志和 UI 展示）
      3. 实现 execute(ctx, params) 方法

    可选：
      - input_keys / output_keys：声明 I/O schema，供 UI 展示和文档生成
      - validate(ctx)：执行前前置条件校验
    """

    name: str = ""
    display_name: str = ""
    description: str = ""
    input_keys: List[str] = []
    output_keys: List[str] = []

    @abstractmethod
    def execute(self, ctx: StepContext, params: Optional[Dict[str, Any]] = None) -> StepResult:
        """
        执行步骤主逻辑。

        Args:
            ctx:    工作流上下文（读取前驱输出 / 写入本步输出）
            params: 工作流 JSON 配置中该步骤的静态参数

        Returns:
            StepResult（success=True/False，含 message 和可选 data）
        """

    def validate(self, ctx: StepContext) -> bool:
        """前置条件校验，默认通过。子类可覆盖。"""
        return True
