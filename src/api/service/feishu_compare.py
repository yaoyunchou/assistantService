"""
飞书多维表格数据对比服务：按「快递单号」匹配表 A 与表 B，并更新表 A 的「是否关联」与「关联订单号」。
"""
from typing import Dict, List, Any, Optional

from tools.feishu.feishu_table_client import FeishuTableClient
from utils.logger import get_logger

logger = get_logger('FeishuCompare')

# 默认使用的 base 与表 ID（与需求中的两个链接一致）
DEFAULT_APP_TOKEN = "ORSHbpajoaANQ4sFg25c917jnTc"
TABLE_A_ID = "tblpx3szhgwxAxDa"   # 被更新的表（1688 订单）
TABLE_B_ID = "tblpV1RrhyUAzfSy"   # 用于匹配的表（拼多多等）

FIELD_EXPRESS_NO = "快递单号"
FIELD_ORDER_NO = "订单号"
# 表 A 单选字段「是否关联」，可选值：关联正常、关联失败、未关联
FIELD_IS_RELATED = "是否关联"
FIELD_RELATED_ORDER_NO = "关联订单号"
OPTION_RELATED_OK = "关联正常"


def _normalize_express_no(v: Any) -> Optional[str]:
    """将单元格值规范为可比较的快递单号字符串，空则返回 None。"""
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def run_feishu_order_compare(
    app_token: Optional[str] = None,
    table_a_id: Optional[str] = None,
    table_b_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    按「快递单号」对比表 A 与表 B，匹配到的表 A 记录更新为：是否关联=「关联正常」，关联订单号=表 B 的订单号。

    Args:
        app_token: 多维表格 app_token，不传则用默认 DEFAULT_APP_TOKEN
        table_a_id: 被更新的表 ID（不传则用 TABLE_A_ID）
        table_b_id: 用于匹配的表 ID（不传则用 TABLE_B_ID）

    Returns:
        {
            "success": bool,
            "message": str,
            "updated_count": int,
            "matched_express_nos": list[str],
            "error": str | None,
        }
    """
    app_token = app_token or DEFAULT_APP_TOKEN
    table_a_id = table_a_id or TABLE_A_ID
    table_b_id = table_b_id or TABLE_B_ID

    client = FeishuTableClient(app_token=app_token)

    try:
        # 1. 拉取表 B 全量，构建 快递单号 -> 订单号 映射（同一单号保留第一个）
        logger.info(f"拉取表 B 记录，table_id={table_b_id}")
        records_b = client.get_all_records(app_token=app_token, table_id=table_b_id)
        if records_b is None:
            return {
                "success": False,
                "message": "获取表 B 记录失败",
                "updated_count": 0,
                "matched_express_nos": [],
                "error": "get_all_records(table_b) returned None",
            }

        express_to_order: Dict[str, str] = {}
        for rec in records_b:
            fields = rec.get("fields") or {}
            express_no = _normalize_express_no(fields.get(FIELD_EXPRESS_NO))
            order_no = fields.get(FIELD_ORDER_NO)
            if express_no and order_no is not None and str(order_no).strip():
                if express_no not in express_to_order:
                    express_to_order[express_no] = str(order_no).strip()

        logger.info(f"表 B 共 {len(records_b)} 条，有效快递单号映射 {len(express_to_order)} 条")

        # 2. 拉取表 A 全量，找出需更新的记录
        logger.info(f"拉取表 A 记录，table_id={table_a_id}")
        records_a = client.get_all_records(app_token=app_token, table_id=table_a_id)
        if records_a is None:
            return {
                "success": False,
                "message": "获取表 A 记录失败",
                "updated_count": 0,
                "matched_express_nos": [],
                "error": "get_all_records(table_a) returned None",
            }

        to_update: List[Dict[str, Any]] = []
        matched_express_nos: List[str] = []
        for rec in records_a:
            record_id = rec.get("record_id")
            fields = rec.get("fields") or {}
            express_no = _normalize_express_no(fields.get(FIELD_EXPRESS_NO))
            if not record_id or not express_no:
                continue
            order_no_b = express_to_order.get(express_no)
            if order_no_b is None:
                continue
            to_update.append({
                "record_id": record_id,
                "fields": {
                    FIELD_IS_RELATED: OPTION_RELATED_OK,
                    FIELD_RELATED_ORDER_NO: order_no_b,
                },
            })
            matched_express_nos.append(express_no)

        if not to_update:
            return {
                "success": True,
                "message": "无需要更新的记录",
                "updated_count": 0,
                "matched_express_nos": [],
                "error": None,
            }

        # 3. 批量更新表 A（每批 500 条，飞书限制）
        batch_size = 500
        updated_count = 0
        for i in range(0, len(to_update), batch_size):
            batch = to_update[i : i + batch_size]
            result = client.batch_update_records(
                records=batch,
                app_token=app_token,
                table_id=table_a_id,
            )
            if result:
                updated_count += len(result)
            else:
                logger.warning(f"批量更新第 {i // batch_size + 1} 批失败，本批 {len(batch)} 条")

        return {
            "success": True,
            "message": f"已更新 {updated_count} 条记录",
            "updated_count": updated_count,
            "matched_express_nos": matched_express_nos,
            "error": None,
        }

    except Exception as e:
        logger.exception("飞书订单对比执行异常")
        return {
            "success": False,
            "message": str(e),
            "updated_count": 0,
            "matched_express_nos": [],
            "error": str(e),
        }
