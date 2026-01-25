"""
Spider模块
包含浏览器池管理和物流查询相关功能
"""

# 浏览器池（通用基础设施）
from .query_manager import BrowserPool, BrowserTimeoutError

# 业务逻辑服务
from .logistics_service import query_with_retry, batch_query_waybill_numbers

# 底层查询功能
from .logistics_query import get_logistics_info

__all__ = [
    # 浏览器池
    'BrowserPool',
    'BrowserTimeoutError',
    # 业务服务
    'query_with_retry',
    'batch_query_waybill_numbers',
    # 底层功能
    'get_logistics_info',
]
