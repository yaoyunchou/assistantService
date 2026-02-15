"""
API 路由模块（按功能拆分为 api.routes 包，并集成 Swagger 文档）
"""
from .routes import register_routes

__all__ = ['register_routes']
