"""
1688 订单列表提取与飞书同步

供 Web 页面「1688 订单提取」/api/order_1688 使用，逻辑集中在 spider.order_1688 模块。
- 主流程只拉列表页并与当日缓存合并，不进入详情页。
- 详情由定时任务/补详情接口分批执行：每小时最多 20 次进详情，每条订单最多进 3 次（_detail_visit_count 0~3）。
"""
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from utils.path_helper import get_safe_data_path
from utils.logger import get_logger

logger = get_logger("Order1688")

# 每条订单最多进入详情页次数；每小时全局最多进入详情页次数（防封控）
DETAIL_VISIT_COUNT_MAX = 3
DETAIL_VISIT_QUOTA_PER_HOUR = 20

ORDER_LIST_URL = (
    "https://air.1688.com/app/ctf-page/trade-order-list/buyer-order-list.html"
    "?tradeStatus=waitbuyerreceive&page=1&pageSize=100"
)

EXTRACT_JS = """
(function() {
  function getText(el) { return el ? el.textContent.trim() : ''; }
  function normalizeSpace(s) {
    if (!s || typeof s !== 'string') return '';
    return s.replace(/\\s+/g, ' ').trim();
  }
  function getOrderIdFromArgs(el) {
    var args = el.getAttribute('data-tracker-args');
    if (!args) return '';
    var m = args.match(/orderId=([^&]+)/);
    return m ? m[1].trim() : '';
  }
  function fromItem(el) {
    var sr = el.shadowRoot;
    var totalPrice = '';
    var productName = '';
    var productSkuInfo = '';
    var detailUrl = '';
    var orderTime = '';
    var orderStatus = '';
    var logisticsNo = '';
    var orderIdFromLogistics = '';
    if (sr) {
      var timeEl = sr.querySelector('div.order-item-header > div.item-header-left > span.order-time');
      orderTime = getText(timeEl);
      var logisticsEl = sr.querySelector('div.order-logistics-container > div:nth-child(1)');
      var logisticsText = getText(logisticsEl);
      if (logisticsText) {
        var orderIdMatch = logisticsText.match(/订单号[：:\s]+(\d+)/);
        if (orderIdMatch) orderIdFromLogistics = orderIdMatch[1].trim();
        var logisticsMatch = logisticsText.match(/(?:物流单号|快递单号|运单号|[\\u4e00-\\u9fa5]*快递)[：:\\s]+([A-Za-z0-9]+)/);
        if (logisticsMatch) logisticsNo = logisticsMatch[1].trim();
        if (!logisticsNo) {
          var fallbackRe = /[：:]\s*([A-Za-z0-9]+)/g;
          var m;
          while ((m = fallbackRe.exec(logisticsText)) !== null) {
            if (/[A-Za-z]/.test(m[1])) { logisticsNo = m[1].trim(); break; }
          }
        }
      }
      var unitPriceEl = sr.querySelector('div.order-item-content > div > div > order-item-entry-unit-price');
      if (unitPriceEl && unitPriceEl.shadowRoot) {
        var div = unitPriceEl.shadowRoot.querySelector('div');
        totalPrice = getText(div);
      }
      var entryProduct = sr.querySelector('div.order-item-content > div > div > order-item-entry-product');
      if (entryProduct && entryProduct.shadowRoot) {
        var nameEl = entryProduct.shadowRoot.querySelector('div > div > div.product-info-name > a.product-name');
        productName = getText(nameEl);
        var skuEl = entryProduct.shadowRoot.querySelector('div > div > div.product-sku-info');
        productSkuInfo = getText(skuEl);
      }
      var statusEl = sr.querySelector('div.order-item-content > order-item-status');
      if (statusEl && statusEl.shadowRoot) {
        var a = statusEl.shadowRoot.querySelector('a');
        if (a && a.href) detailUrl = a.href;
        var statusDiv = statusEl.shadowRoot.querySelector('div');
        orderStatus = getText(statusDiv);
      }
    }
    if (!totalPrice && !productName) {
      orderTime = getText(el.querySelector('.order-time') || (sr && sr.querySelector('.order-time')));
      totalPrice = getText(el.querySelector('.total-price') || (sr && sr.querySelector('.total-price')));
      productName = getText(el.querySelector('.product-name') || (sr && sr.querySelector('.product-name')));
      productSkuInfo = getText(el.querySelector('.product-sku-info') || (sr && sr.querySelector('.product-sku-info')));
    }
    var orderId = getOrderIdFromArgs(el) || orderIdFromLogistics;
    return {
      orderId: orderId,
      orderTime: normalizeSpace(orderTime),
      orderStatus: normalizeSpace(orderStatus),
      logisticsNo: logisticsNo,
      totalPrice: normalizeSpace(totalPrice),
      productName: normalizeSpace(productName),
      productSkuInfo: normalizeSpace(productSkuInfo),
      detailUrl: detailUrl
    };
  }
  var list = [];
  var listContainer = null;
  var appRoot = document.querySelector('body > article > app-root');
  if (appRoot && appRoot.shadowRoot) {
    var orderListEl = appRoot.shadowRoot.querySelector('div > main > q-theme > order-list');
    if (orderListEl && orderListEl.shadowRoot) {
      listContainer = orderListEl.shadowRoot.querySelector('div > div.order-list-content');
    }
  }
  if (!listContainer) listContainer = document.querySelector('.order-list-content');
  if (!listContainer) return list;
  var items = listContainer.querySelectorAll('order-item');
  if (!items.length) items = listContainer.querySelectorAll('.order-item');
  for (var i = 0; i < items.length; i++) list.push(fromItem(items[i]));
  return list;
})();
"""

EXTRACT_RECEIPT_JS = """
(function() {
  var appRoot = document.querySelector('body > article > app-root');
  if (!appRoot || !appRoot.shadowRoot) return '';
  var orderInfo = appRoot.shadowRoot.querySelector('div > main > q-theme > div.detail-container > div.order-info > order-info');
  if (!orderInfo || !orderInfo.shadowRoot) return '';
  var receipt = orderInfo.shadowRoot.querySelector('div > order-info-receipt');
  if (!receipt || !receipt.shadowRoot) return '';
  var desc = receipt.shadowRoot.querySelector('order-info-description');
  return desc ? desc.textContent.trim() : '';
})();
"""


def get_order_1688_cache_dir() -> Path:
    """1688 订单缓存目录：cache/order_1688，使用安全路径（项目目录或用户数据目录）。"""
    cache_dir = get_safe_data_path("cache/order_1688")
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def get_today_cache_path() -> Path:
    """当日缓存文件路径：orders_YYYY-MM-DD.json"""
    return get_order_1688_cache_dir() / f"orders_{date.today().isoformat()}.json"


def load_today_cache() -> Optional[List[Dict[str, Any]]]:
    """加载当日缓存；不存在或解析失败返回 None。"""
    path = get_today_cache_path()
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else None
    except Exception:
        return None


def save_today_cache(list_: List[Dict[str, Any]]) -> None:
    """将订单列表写入当日缓存文件，确保每条含 _detail_visit_count（缺则补 0）。"""
    for item in list_:
        item.setdefault("_detail_visit_count", 0)
    path = get_today_cache_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(list_, f, ensure_ascii=False, indent=2)


def cleanup_old_cache_files() -> None:
    """删除 cache/order_1688 目录下非当日的 JSON 文件。"""
    today_file = get_today_cache_path().name
    for p in get_order_1688_cache_dir().iterdir():
        if p.suffix.lower() == ".json" and p.name != today_file:
            try:
                p.unlink()
            except OSError:
                pass


def get_detail_quota_path() -> Path:
    """详情页访问配额文件路径（按小时限流）。"""
    return get_order_1688_cache_dir() / "detail_quota.json"


def _now_ts() -> float:
    return datetime.now(timezone.utc).timestamp()


def load_detail_quota() -> int:
    """
    返回本小时内剩余可进入详情页次数（最多 DETAIL_VISIT_QUOTA_PER_HOUR）。
    若距上次窗口已超过 1 小时则重置窗口，返回 20。
    """
    path = get_detail_quota_path()
    if not path.exists():
        return DETAIL_VISIT_QUOTA_PER_HOUR
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        window_start = float(data.get("window_start", 0))
        count = int(data.get("count", 0))
        if _now_ts() - window_start >= 3600:
            return DETAIL_VISIT_QUOTA_PER_HOUR
        return max(0, DETAIL_VISIT_QUOTA_PER_HOUR - count)
    except Exception:
        return DETAIL_VISIT_QUOTA_PER_HOUR


def consume_detail_quota() -> bool:
    """消耗 1 次详情页配额并落盘；若需重置窗口则先重置。返回是否消耗成功。"""
    path = get_detail_quota_path()
    now = _now_ts()
    try:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            window_start = float(data.get("window_start", 0))
            count = int(data.get("count", 0))
            if now - window_start >= 3600:
                window_start = now
                count = 0
        else:
            window_start = now
            count = 0
        if count >= DETAIL_VISIT_QUOTA_PER_HOUR:
            return False
        count += 1
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"window_start": window_start, "count": count}, f)
        return True
    except Exception:
        return False


def normalize_space(s: str) -> str:
    if not s or not isinstance(s, str):
        return ""
    return re.sub(r"\s+", " ", s).strip()


def parse_total_price(s) -> int:
    if not s or not isinstance(s, str):
        return 0
    s = re.sub(r"[¥￥\s,]", "", s.strip())
    if not s:
        return 0
    try:
        return int(round(float(s) * 100))
    except (ValueError, TypeError):
        return 0


def parse_receipt_text(text: str):
    if not text or not text.strip():
        return "", "", ""
    text = normalize_space(text)
    name = phone = addr = ""
    m = re.search(r"收货人[：:\s]+([^\s手机收货地址]+)", text)
    if m:
        name = normalize_space(m.group(1))
    m = re.search(r"手机[号]?[：:\s]+([\d\-]+)", text)
    if m:
        phone = m.group(1).strip()
    m = re.search(r"收货地址[：:\s]+(.+)", text, re.DOTALL)
    if m:
        addr = normalize_space(m.group(1))
    return name, phone, addr


def _normalize_total_price_for_feishu(v) -> int:
    """将 totalPrice 转为飞书「总价」：支持 int/float（分）或字符串如 '¥ 27.51'。"""
    if v is None:
        return 0
    if isinstance(v, (int, float)):
        return int(v) if v == int(v) else int(round(float(v)))
    if isinstance(v, str):
        return parse_total_price(v)
    return 0


def count_asterisks(s: str) -> int:
    """统计字符串中 '*' 的个数，用于判断脱敏程度（* 多表示信息更少）。"""
    if not s or not isinstance(s, str):
        return 0
    return s.count("*")


# 更新时需按「* 数量」对比的字段：订单状态、收货人、收货电话、收货地址
UPDATE_COMPARE_FIELDS = ("订单状态", "收货人", "收货电话", "收货地址")


def merge_update_fields(
    old_fields: Dict[str, Any],
    new_fields: Dict[str, Any],
    compare_keys: tuple = UPDATE_COMPARE_FIELDS,
) -> Dict[str, Any]:
    """
    合并更新字段：新值为空则不更新；对 compare_keys 中的字段，
    若老数据的 '*' 更少则保留老数据（不覆盖），否则用新数据。
    其他字段直接使用新数据。
    """
    merged = dict(new_fields)
    for key in compare_keys:
        if key not in merged and key not in old_fields:
            continue
        new_val = (merged.get(key) if key in merged else "") or ""
        if isinstance(new_val, str):
            new_val = new_val.strip()
        old_val = (old_fields.get(key) or "") if key in old_fields else ""
        if isinstance(old_val, str):
            old_val = old_val.strip()
        # 新值为空：不更新，保留老数据
        if not new_val:
            merged[key] = old_val
            continue
        # 老数据的 * 更少：不更新该字段，保留老数据
        if count_asterisks(old_val) < count_asterisks(new_val):
            merged[key] = old_val
    return merged


def order_to_feishu_fields(item: Dict[str, Any]) -> Dict[str, Any]:
    """将 1688 订单项转为飞书表格字段，含 totalPrice→总价、receiverPhone→收货电话 等。"""
    return {
        "订单号": str(item.get("orderId") or ""),
        "下单时间": str(item.get("orderTime") or ""),
        "订单状态": str(item.get("orderStatus") or ""),
        "快递单号": str(item.get("logisticsNo") or ""),
        "总价": _normalize_total_price_for_feishu(item.get("totalPrice")),
        "商品名称": str(item.get("productName") or ""),
        "规格": str(item.get("productSkuInfo") or ""),
        "详情链接": str(item.get("detailUrl") or ""),
        "收货人": str(item.get("receiverName") or ""),
        "收货电话": str(item.get("receiverPhone") or ""),
        "收货地址": str(item.get("receiverAddress") or ""),
    }


def sync_1688_orders_to_feishu(
    list_: List[Dict[str, Any]], app_token: str, table_id: str
) -> Dict[str, Any]:
    if not list_:
        return {"success": True, "message": "无数据", "create_count": 0, "update_count": 0, "fail_count": 0}
    try:
        from tools.feishu.feishu_table_client import FeishuTableClient

        client = FeishuTableClient(app_token=app_token, table_id=table_id)
        existing = client.get_all_records()
        order_id_to_record = {}
        for rec in existing:
            rid = rec.get("record_id")
            fields = rec.get("fields") or {}
            oid = (fields.get("订单号") or "").strip()
            if oid and rid:
                order_id_to_record[oid] = {"record_id": rid, "fields": fields}

        to_create = []
        to_update = []
        for item in list_:
            oid = str(item.get("orderId") or "").strip()
            if not oid:
                continue
            new_fields = order_to_feishu_fields(item)
            if oid in order_id_to_record:
                old_info = order_id_to_record[oid]
                merged_fields = merge_update_fields(
                    old_info["fields"], new_fields, UPDATE_COMPARE_FIELDS
                )
                to_update.append({
                    "record_id": old_info["record_id"],
                    "fields": merged_fields,
                })
            else:
                to_create.append({"fields": new_fields})

        create_count = update_count = fail_count = 0
        batch_size = 20

        for i in range(0, len(to_create), batch_size):
            batch = to_create[i : i + batch_size]
            result = client.batch_create_records(batch)
            if result:
                create_count += len(result)
            else:
                for rec in batch:
                    if client.create_record(rec["fields"]):
                        create_count += 1
                    else:
                        fail_count += 1

        for i in range(0, len(to_update), batch_size):
            batch = to_update[i : i + batch_size]
            result = client.batch_update_records(batch)
            if result:
                update_count += len(result)
            else:
                for rec in batch:
                    if client.update_record(rec["record_id"], rec["fields"]):
                        update_count += 1
                    else:
                        fail_count += 1

        return {
            "success": True,
            "message": f"成功 创建{create_count} 更新{update_count} 失败{fail_count}",
            "create_count": create_count,
            "update_count": update_count,
            "fail_count": fail_count,
        }
    except Exception as e:
        return {
            "success": False,
            "message": str(e),
            "create_count": 0,
            "update_count": 0,
            "fail_count": len(list_),
        }


def extract_from_page(page) -> List[Dict[str, Any]]:
    try:
        list_ = page.evaluate(EXTRACT_JS)
        if list_ and len(list_) > 0:
            return list_
    except Exception:
        pass
    for frame in page.frames:
        if frame == page.main_frame:
            continue
        try:
            list_ = frame.evaluate(EXTRACT_JS)
            if list_ and len(list_) > 0:
                return list_
        except Exception:
            continue
    return []


def fetch_list_page_only(page) -> List[Dict[str, Any]]:
    """仅打开列表页并提取订单列表，不进入详情页。列表项不含收货人/电话/地址。"""
    page.goto(ORDER_LIST_URL, wait_until="domcontentloaded", timeout=60000)
    try:
        page.wait_for_selector("body > article > app-root", timeout=15000)
        page.wait_for_timeout(2000)
    except Exception:
        try:
            page.wait_for_selector(".order-list-content .order-item, .order-item", timeout=10000)
        except Exception:
            pass
        page.wait_for_timeout(2000)
    order_list = extract_from_page(page)
    if not order_list:
        return order_list
    for item in order_list:
        item.setdefault("receiverName", "")
        item.setdefault("receiverPhone", "")
        item.setdefault("receiverAddress", "")
    return order_list


def merge_list_with_today_cache(
    list_from_page: List[Dict[str, Any]], cache: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """用当日缓存的收货信息及 _detail_visit_count 补全列表页数据（按 orderId）。"""
    cache_by_oid = {}
    for c in cache:
        oid = (c.get("orderId") or "").strip()
        if oid:
            cache_by_oid[oid] = c
    for item in list_from_page:
        oid = (item.get("orderId") or "").strip()
        if oid in cache_by_oid:
            old = cache_by_oid[oid]
            item["receiverName"] = old.get("receiverName") or ""
            item["receiverPhone"] = old.get("receiverPhone") or ""
            item["receiverAddress"] = old.get("receiverAddress") or ""
            item["_detail_visit_count"] = min(
                int(old.get("_detail_visit_count") or 0), DETAIL_VISIT_COUNT_MAX
            )
        else:
            item.setdefault("_detail_visit_count", 0)
    return list_from_page


def run_extract(page) -> List[Dict[str, Any]]:
    """
    提取订单：仅拉列表页，与当日缓存合并后返回，不进入任何详情页。
    若当日无缓存则保存仅含列表的缓存（_detail_visit_count=0），由定时任务/补详情接口分批进详情。
    """
    list_from_page = fetch_list_page_only(page)
    if not list_from_page:
        return list_from_page

    today_cache = load_today_cache()
    if today_cache:
        order_list = merge_list_with_today_cache(list_from_page, today_cache)
        save_today_cache(order_list)
    else:
        order_list = list_from_page
        for item in order_list:
            item.setdefault("_detail_visit_count", 0)
        save_today_cache(order_list)
    cleanup_old_cache_files()

    try:
        with open("order_list.json", "w", encoding="utf-8") as f:
            json.dump(order_list, f, ensure_ascii=False, indent=4)
    except OSError:
        pass
    return order_list


def _needs_detail_fill(item: Dict[str, Any]) -> bool:
    """是否缺少详情信息且未达最大进入次数。"""
    phone = (item.get("receiverPhone") or "").strip()
    name = (item.get("receiverName") or "").strip()
    addr = (item.get("receiverAddress") or "").strip()
    if not (item.get("detailUrl") or "").strip():
        return False
    count = min(int(item.get("_detail_visit_count") or 0), DETAIL_VISIT_COUNT_MAX)
    if count >= DETAIL_VISIT_COUNT_MAX:
        return False
    return not phone or not name or not addr


def run_detail_fill_batch(page) -> Tuple[int, str]:
    """
    补详情任务（供定时/cron 调用）：从当日缓存中选出缺收货信息且 _detail_visit_count < 3 的订单，
    在本小时剩余配额内（最多 20/h）逐个进入详情页拉取收货信息并回写缓存，每进一次详情 _detail_visit_count +1。
    返回 (本批补全条数, 说明文案)。
    """
    logger.info("补详情: 开始拉取列表页")
    list_from_page = fetch_list_page_only(page)
    if not list_from_page:
        logger.info("补详情: 列表页无数据，结束")
        return 0, "列表页无数据"

    logger.info("补详情: 列表页拉取到 %s 条", len(list_from_page))
    today_cache = load_today_cache()
    if today_cache:
        merged = merge_list_with_today_cache(list_from_page, today_cache)
        logger.info("补详情: 已与当日缓存合并，共 %s 条", len(merged))
    else:
        merged = list_from_page
        for item in merged:
            item.setdefault("_detail_visit_count", 0)
        save_today_cache(merged)
        logger.info("补详情: 无当日缓存，已保存列表共 %s 条", len(merged))

    need_detail = [i for i in merged if _needs_detail_fill(i)]
    if not need_detail:
        logger.info("补详情: 无待补详情的订单，结束")
        return 0, "无待补详情的订单"

    remaining = load_detail_quota()
    if remaining <= 0:
        logger.warning("补详情: 本小时详情页配额已用尽，结束")
        return 0, f"本小时详情页配额已用尽（{DETAIL_VISIT_QUOTA_PER_HOUR}/h），请稍后再试"

    to_fill = need_detail[: min(remaining, DETAIL_VISIT_QUOTA_PER_HOUR)]
    plan = len(to_fill)
    logger.info("补详情: 待补详情 %s 条，本小时剩余配额 %s，本批计划处理 %s 条", len(need_detail), remaining, plan)

    filled = 0
    cache_by_oid = {(c.get("orderId") or "").strip(): c for c in merged if (c.get("orderId") or "").strip()}

    for idx, item in enumerate(to_fill):
        if not consume_detail_quota():
            logger.info("补详情: 配额已用尽，本批提前结束")
            break
        detail_url = (item.get("detailUrl") or "").strip()
        oid = (item.get("orderId") or "").strip()
        if not detail_url:
            logger.debug("补详情: 第 %s/%s 条 orderId=%s 无详情链接，跳过", idx + 1, plan, oid)
            continue
        logger.info("补详情: 正在处理第 %s/%s 条 orderId=%s 进入详情页", idx + 1, plan, oid)
        try:
            page.goto(detail_url, wait_until="domcontentloaded", timeout=20000)
            try:
                page.wait_for_selector("body > article > app-root", timeout=10000)
                page.wait_for_timeout(1500)
            except Exception:
                page.wait_for_timeout(1000)
            receipt_text = ""
            try:
                receipt_text = page.evaluate(EXTRACT_RECEIPT_JS) or ""
            except Exception:
                pass
            name, phone, addr = parse_receipt_text(receipt_text)
            item["receiverName"] = name
            item["receiverPhone"] = phone
            item["receiverAddress"] = addr
            item["_detail_visit_count"] = min(
                int(item.get("_detail_visit_count") or 0) + 1, DETAIL_VISIT_COUNT_MAX
            )
            filled += 1
            if name or phone or addr:
                logger.info("补详情: orderId=%s 解析到 收货人=%s 电话=%s 地址=%s", oid, name or "(空)", phone or "(空)", (addr[:20] + "..." if addr and len(addr) > 20 else addr or "(空)"))
            else:
                logger.warning("补详情: orderId=%s 未解析到收货信息", oid)
            # 回写当日缓存
            if oid in cache_by_oid:
                cache_by_oid[oid].update({
                    "receiverName": item["receiverName"],
                    "receiverPhone": item["receiverPhone"],
                    "receiverAddress": item["receiverAddress"],
                    "_detail_visit_count": item["_detail_visit_count"],
                })
            else:
                cache_by_oid[oid] = dict(item)
            save_today_cache(merged)
        except Exception as e:
            logger.warning("补详情: orderId=%s 进入详情或解析失败: %s", oid, e)

    msg = f"本批补全 {filled} 条，本小时剩余配额 {load_detail_quota()}"
    logger.info("补详情: 结束 %s", msg)
    return filled, msg


def normalize_list_total_price(list_: List[Dict[str, Any]]) -> None:
    """原地将每条 totalPrice 转为数字（乘 100，单位：分）"""
    for item in list_:
        raw = item.get("totalPrice") or ""
        if isinstance(raw, str):
            item["totalPrice"] = parse_total_price(raw)
        elif isinstance(raw, (int, float)):
            item["totalPrice"] = int(raw) if raw == int(raw) else int(round(float(raw) * 100))
        else:
            item["totalPrice"] = 0
