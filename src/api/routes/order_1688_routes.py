"""
1688 订单提取 API
"""
import os
from flask import Blueprint, request, jsonify
from api.routes.context import get_browser_pool
from utils.logger import get_logger

routes_logger = get_logger("Routes")
bp = Blueprint("order_1688", __name__, url_prefix="/api/order_1688")


@bp.route("/execute", methods=["POST"])
def order_1688_execute():
    """
    执行 1688 订单提取：打开待收货列表页并逐个进入详情页取收货信息。
    返回提取的订单列表（totalPrice 已转为分）。
    """
    try:
        pool = get_browser_pool()
        if not pool:
            return jsonify({"success": False, "error": "浏览器池未初始化"}), 500

        from spider.order_1688 import run_extract, normalize_list_total_price

        list_ = pool.execute(run_extract, timeout=300)
        list_ = list_ if list_ is not None else []
        normalize_list_total_price(list_)

        return jsonify({"success": True, "list": list_, "count": len(list_)}), 200
    except Exception as e:
        routes_logger.error(f"1688 订单提取异常: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/sync_feishu", methods=["POST"])
def order_1688_sync_feishu():
    """
    将请求体中的订单列表同步到飞书多维表格（按订单号：已存在则更新，不存在则新增）。
    请求体: { "list": [ { "orderId", "orderTime", ... }, ... ] }
    """
    try:
        data = request.get_json() or {}
        list_ = data.get("list") or []
        if not list_:
            return jsonify({"success": True, "message": "无数据", "create_count": 0, "update_count": 0, "fail_count": 0}), 200

        from spider.order_1688 import sync_1688_orders_to_feishu

        app_token = os.environ.get("FEISHU_1688_APP_TOKEN", "ORSHbpajoaANQ4sFg25c917jnTc")
        table_id = os.environ.get("FEISHU_1688_TABLE_ID", "tblpx3szhgwxAxDa")
        result = sync_1688_orders_to_feishu(list_, app_token, table_id)
        return jsonify({"success": result.get("success", False), **result}), 200
    except Exception as e:
        routes_logger.error(f"1688 同步飞书异常: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/fill_detail", methods=["GET"])
def order_1688_fill_detail():
    """
    补详情：从当日缓存中选缺收货信息且 _detail_visit_count < 3 的订单，
    在本小时剩余配额内（最多 20/h）逐个进入详情页拉取收货信息并回写缓存。
    定时任务会按 tasks.json 配置自动调用；也可直接调此接口手动执行。
    """
    routes_logger.info("1688 补详情 API 被调用，开始执行")
    try:
        pool = get_browser_pool()
        if not pool:
            routes_logger.warning("1688 补详情失败: 浏览器池未初始化")
            return jsonify({"success": False, "error": "浏览器池未初始化"}), 500

        from spider.order_1688 import run_detail_fill_batch

        routes_logger.info("1688 补详情: 即将在浏览器池中执行 run_detail_fill_batch（超时 300s）")
        result = pool.execute(run_detail_fill_batch, timeout=300)
        filled, message = 0, ""
        if isinstance(result, (list, tuple)) and len(result) >= 2:
            filled = int(result[0]) if result[0] is not None else 0
            message = str(result[1] or "")
        elif result is not None:
            message = str(result)
        routes_logger.info("1688 补详情完成: filled_count=%s message=%s", filled, message)
        return jsonify({
            "success": True,
            "filled_count": filled,
            "message": message,
        }), 200
    except Exception as e:
        routes_logger.error("1688 补详情异常: %s", e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500
