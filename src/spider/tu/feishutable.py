"""
spider/tu/feishutable.py — 兼容转发层

实际实现已迁移到 storage/feishu/tu_table.py。
此文件保留以确保现有 import 路径不受影响，请勿在新代码中使用此路径。
新代码请使用：from storage.feishu.tu_table import ...
"""
from storage.feishu.tu_table import sync_tu_data_to_feishu  # noqa: F401
