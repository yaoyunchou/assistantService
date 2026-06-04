"""
AI 助手工具
继承 BaseTool，注册为系统工具，提供 Web UI 入口。
"""
from tools.base import BaseTool


class AiTool(BaseTool):
    def __init__(self):
        super().__init__(
            name='ai_assistant',
            display_name='AI 智能助手',
            description='由 Cursor SDK 驱动的 AI 大脑，支持自然语言问答与浏览器自动化',
        )

    def get_info(self):
        return {
            'name': self.name,
            'display_name': self.display_name,
            'description': self.description,
            'icon': '🤖',
        }

    def initialize(self, **kwargs) -> bool:
        return True

    def cleanup(self):
        pass
