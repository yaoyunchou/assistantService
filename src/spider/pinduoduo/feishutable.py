"""
spider/pinduoduo/feishutable.py — 兼容转发层

实际实现已迁移到 storage/feishu/pdd_table.py。
此文件保留以确保现有 import 路径不受影响，请勿在新代码中使用此路径。
新代码请使用：from storage.feishu.pdd_table import ...
"""
from storage.feishu.pdd_table import (  # noqa: F401
    SENSITIVE_FIELD_KEYS,
    ERP_ORDER_PRIMARY_KEY,
    ERP_SENSITIVE_FIELD_KEYS,
    ERP_FEISHU_NUMBER_FIELD_KEYS,
    ERP_FEISHU_DATETIME_FIELD_KEYS,
    ERP_FEISHU_OMIT_FIELD_KEYS,
    ERP_FEISHU_PARTIAL_UPDATE_FIELD_KEYS,
    AFTER_SALE_PRIMARY_KEY,
    AFTER_SALE_LOGISTICS_FIELD_KEYS,
    AFTER_SALE_HANDLED_KEY,
    AUDIT_FEISHU_DATETIME_FIELD_KEYS,
    feishu_field_to_text,
    sync_orders_to_feishu,
    sync_erp_order_rows_to_feishu,
    sync_after_sale_logistics_to_feishu,
    sync_audit_events_to_feishu,
    delete_feishu_rows_without_order_sn,
)
