"""
workflow.registry — 步骤注册表
"""
from __future__ import annotations

import importlib
import pkgutil
from typing import Dict, List, Type

from workflow.step import BaseStep


class StepRegistry:
    """步骤注册表（单例）。"""

    def __init__(self):
        self._steps: Dict[str, Type[BaseStep]] = {}

    def register(self, step_cls: Type[BaseStep]) -> None:
        if not step_cls.name:
            raise ValueError(f"步骤类 {step_cls.__name__} 未设置 name 属性")
        self._steps[step_cls.name] = step_cls

    def get(self, name: str) -> BaseStep:
        cls = self._steps.get(name)
        if cls is None:
            available = ", ".join(sorted(self._steps.keys()))
            raise ValueError(f"未知步骤: '{name}'。已注册步骤: [{available}]")
        return cls()

    def auto_discover(self, package: str = "workflow.steps") -> None:
        """自动扫描 package 下所有模块，注册其中的 BaseStep 子类。"""
        try:
            pkg = importlib.import_module(package)
        except ImportError:
            return
        for _, module_name, _ in pkgutil.iter_modules(pkg.__path__):
            try:
                mod = importlib.import_module(f"{package}.{module_name}")
            except ImportError:
                continue
            for attr_name in dir(mod):
                obj = getattr(mod, attr_name)
                if (
                    isinstance(obj, type)
                    and issubclass(obj, BaseStep)
                    and obj is not BaseStep
                    and obj.name
                ):
                    self.register(obj)

    def list_steps(self) -> List[dict]:
        return [
            {
                "name": cls.name,
                "display_name": cls.display_name,
                "description": cls.description,
                "input_keys": cls.input_keys,
                "output_keys": cls.output_keys,
            }
            for cls in self._steps.values()
        ]

    def __contains__(self, name: str) -> bool:
        return name in self._steps


_default_registry: StepRegistry | None = None


def get_registry() -> StepRegistry:
    """获取全局步骤注册表（懒加载 + 自动发现）。"""
    global _default_registry
    if _default_registry is None:
        _default_registry = StepRegistry()
        _default_registry.auto_discover()
    return _default_registry
