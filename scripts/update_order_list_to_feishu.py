#!/usr/bin/env python3
"""
将 order_list.json 或 src/testData/1688_order_list.json 按 orderId 更新到飞书多维表格。

默认会更新整行（可能覆盖飞书里已有数据）。修复数据时请用 --only-fields 只改指定字段，
其它字段（如快递单号）不会被触碰。

用法:
  # 只更新快递单号一列（用 order_list.json）
  python scripts/update_order_list_to_feishu.py --file order_list.json --only-fields logisticsNo

  # 只更新「总价」「收货电话」两列（修数据时用）
  python scripts/update_order_list_to_feishu.py --file src/testData/1688_order_list.json --only-fields totalPrice,receiverPhone

  # 使用根目录 order_list.json，按 orderId 匹配并更新整行
  python scripts/update_order_list_to_feishu.py

  # 仅处理指定 orderId 的一条
  python scripts/update_order_list_to_feishu.py --order-id xxx --only-fields totalPrice,receiverPhone

  # 匹配不到时在飞书新增（仅在全量同步时建议用，--only-fields 时一般不加）
  python scripts/update_order_list_to_feishu.py --allow-create

环境变量（可选）:
  FEISHU_1688_APP_TOKEN  飞书多维表格 app_token
  FEISHU_1688_TABLE_ID   飞书数据表 table_id
"""
import argparse
import json
import os
import sys
from pathlib import Path


def _setup_path():
    """把 src 加入 path，便于导入 spider.order_1688"""
    root = Path(__file__).resolve().parent.parent
    src = root / "src"
    if src.is_dir() and str(src) not in sys.path:
        sys.path.insert(0, str(src))
    return root


def load_order_list(file_path: Path) -> list:
    """加载订单 JSON，返回列表；无效或空则返回 []"""
    if not file_path.is_file():
        print(f"文件不存在: {file_path}", file=sys.stderr)
        return []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"读取 JSON 失败: {e}", file=sys.stderr)
        return []
    if not isinstance(data, list):
        print("JSON 根节点应为数组", file=sys.stderr)
        return []
    return data


def main():
    parser = argparse.ArgumentParser(description="将 order_list.json 按 orderId 更新到飞书表格")
    parser.add_argument(
        "--file",
        default="order_list.json",
        help="订单 JSON 路径，如 order_list.json 或 src/testData/1688_order_list.json（默认: order_list.json）",
    )
    parser.add_argument(
        "--order-id",
        help="仅处理该 orderId 的一条订单（可选）",
    )
    parser.add_argument(
        "--allow-create",
        action="store_true",
        help="匹配不到的订单在飞书中新增；默认仅更新已存在的记录",
    )
    parser.add_argument(
        "--only-fields",
        metavar="FIELD1,FIELD2",
        help="只更新这些字段，其它列（如快递单号）不改。例: totalPrice,receiverPhone",
    )
    args = parser.parse_args()

    root = _setup_path()
    os.chdir(root)

    file_path = Path(args.file)
    if not file_path.is_absolute():
        file_path = root / file_path

    orders = load_order_list(file_path)
    if not orders:
        print("无订单数据，退出")
        sys.exit(1)

    if args.order_id:
        orders = [o for o in orders if str(o.get("orderId") or "").strip() == args.order_id.strip()]
        if not orders:
            print(f"未找到 orderId={args.order_id} 的订单", file=sys.stderr)
            sys.exit(1)
        print(f"仅同步 1 条订单: orderId={args.order_id}")

    app_token = os.environ.get("FEISHU_1688_APP_TOKEN", "ORSHbpajoaANQ4sFg25c917jnTc")
    table_id = os.environ.get("FEISHU_1688_TABLE_ID", "tblpx3szhgwxAxDa")

    from spider.order_1688 import order_to_feishu_fields
    from tools.feishu.feishu_table_client import FeishuTableClient

    # JSON 字段名 -> 飞书字段名（仅 --only-fields 用）
    JSON_TO_FEISHU = {
        "logisticsNo": "快递单号",
        "totalPrice": "总价",
        "receiverPhone": "收货电话",
    }

    only_field_names = None
    if args.only_fields:
        only_field_names = [s.strip() for s in args.only_fields.split(",") if s.strip()]
        if not only_field_names:
            print("--only-fields 不能为空", file=sys.stderr)
            sys.exit(1)

    # 遍历匹配更新：先拉取飞书全量，建立 订单号 -> record_id 映射
    client = FeishuTableClient(app_token=app_token, table_id=table_id)
    existing = client.get_all_records()
    order_id_to_record = {}
    for rec in existing:
        rid = rec.get("record_id")
        fields = rec.get("fields") or {}
        oid = (fields.get("订单号") or "").strip()
        if oid and rid:
            order_id_to_record[oid] = rid

    # 遍历 order_list，按 orderId 匹配，收集需更新的记录
    to_update = []
    to_create = []
    for item in orders:
        oid = str(item.get("orderId") or "").strip()
        if not oid:
            continue
        if only_field_names:
            # 只更新指定字段，其它列（如快递单号）不写入、不会被改
            full = order_to_feishu_fields(item)
            fields = {}
            for jf in only_field_names:
                feishu_name = JSON_TO_FEISHU.get(jf) or jf
                if feishu_name in full:
                    fields[feishu_name] = full[feishu_name]
            if not fields:
                continue
        else:
            fields = order_to_feishu_fields(item)
        if oid in order_id_to_record:
            to_update.append({"record_id": order_id_to_record[oid], "fields": fields})
        elif args.allow_create and not only_field_names:
            to_create.append({"fields": fields})

    if not to_update and not to_create:
        print("飞书中没有匹配的订单号，且未启用 --allow-create，无需更新")
        sys.exit(0)

    update_count = fail_count = 0
    batch_size = 20

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

    create_count = 0
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

    msg = f"遍历匹配更新完成: 更新 {update_count} 条"
    if create_count:
        msg += f", 新增 {create_count} 条"
    if fail_count:
        msg += f", 失败 {fail_count} 条"
    print(msg)
    sys.exit(0 if fail_count == 0 else 1)


if __name__ == "__main__":
    main()
