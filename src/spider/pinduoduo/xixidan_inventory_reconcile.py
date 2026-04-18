#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
夕夕单 Base：扣减库存日志 × 库存信息 — 按「库存关联」汇总出库，与「商品名称」精确匹配，测算或写回剩余库存。

数据来源：本机已登录的 `lark-cli base +record-list`（默认 --as user）。

**作为模块被后台调用**（不经过命令行）::

    from xixidan_inventory_reconcile import (
        ReconcileOptions,
        ReconcileResult,
        reconcile_inventory,
        reconcile_inventory_apply,
        reconcile_result_to_dict,
    )

    r = reconcile_inventory()  # 只读测算
    r = reconcile_inventory_apply()  # 写回库存 + 勾选日志

    # 自定义
    r = reconcile_inventory(
        ReconcileOptions(base_token="xxx", skip_consumed_rows=False),
    )

命令行：默认打印测算；**`--apply`** 写回后成功时 stdout 无输出（错误在 stderr）。

口径与 `dd/高效提问.md` / `dd/夕夕单多维表格分析.md` 一致。
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, replace
from typing import Any, Dict, List, Optional, Tuple

PAGE_SIZE = 200


# —— 默认与《夕夕单多维表格分析》中字段一致；可用参数覆盖 ——
DEFAULT_BASE_TOKEN = "ORSHbpajoaANQ4sFg25c917jnTc"
DEFAULT_LOG_TABLE = "tblXXipFcgH1EQH7"  # 扣减库存日志
DEFAULT_INV_TABLE = "tbljLwzLLKafXl0h"  # 库存信息

FID_LOG_LINK = "fldY5myg8A"  # 库存关联
FID_LOG_QTY = "fld5vO51nw"  # 出库数量
FID_LOG_CONSUMED = "fldQb4eiZB"  # 库存已核销（checkbox）
FID_INV_NAME = "fld13ee1wV"  # 商品名称
FID_INV_STOCK = "fldXNlCYVE"  # 数量


@dataclass
class ReconcileOptions:
    """供 `reconcile_inventory` / `reconcile_inventory_apply` 使用；可用 `dataclasses.replace()` 派生变体。"""

    base_token: str = DEFAULT_BASE_TOKEN
    log_table_id: str = DEFAULT_LOG_TABLE
    inv_table_id: str = DEFAULT_INV_TABLE
    lark_cli: str = "lark-cli"
    identity: str = "user"
    page_size: int = PAGE_SIZE
    exclude_unmatched: bool = False
    consumed_field_id: Optional[str] = FID_LOG_CONSUMED
    skip_consumed_rows: bool = True
    fid_log_link: str = FID_LOG_LINK
    fid_log_qty: str = FID_LOG_QTY
    fid_inv_name: str = FID_INV_NAME
    fid_inv_stock: str = FID_INV_STOCK


@dataclass
class LogSkipStats:
    empty_link: int = 0
    unmatched: int = 0
    consumed: int = 0

    def total(self) -> int:
        return self.empty_link + self.unmatched + self.consumed


@dataclass
class ReconcileResult:
    """一次测算结果（不写库时即为最终态；`apply` 后数值与本次写回一致）。"""

    deduct_by_link: Dict[str, int]
    inventory: List[Dict[str, Any]]
    orphan_links: List[Tuple[str, int]]
    skip_stats: LogSkipStats

    @property
    def total_deduct_matched(self) -> int:
        return sum(int(r.get("qty_deduct") or 0) for r in self.inventory)


@dataclass
class RecordListPayload:
    field_id_list: List[str]
    fields: List[str]
    data: List[List[Any]]
    record_id_list: List[str]
    has_more: bool = False


def run_record_list(
    *,
    base_token: str,
    table_id: str,
    limit: int,
    offset: int,
    identity: str,
    lark_cli: str,
) -> RecordListPayload:
    cmd = [
        lark_cli,
        "base",
        "+record-list",
        "--base-token",
        base_token,
        "--table-id",
        table_id,
        "--limit",
        str(limit),
        "--offset",
        str(offset),
        "--as",
        identity,
    ]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"lark-cli 失败 (exit {proc.returncode}): {proc.stderr or proc.stdout}"
        )
    raw = proc.stdout.strip()
    if not raw:
        raise RuntimeError("lark-cli 无输出")
    try:
        outer = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"lark-cli 输出不是合法 JSON: {e}\n{raw[:500]}") from e
    if not outer.get("ok"):
        raise RuntimeError(f"lark-cli 返回 ok=false: {raw[:800]}")
    data = outer.get("data") or {}
    payload = RecordListPayload(
        field_id_list=list(data.get("field_id_list") or []),
        fields=list(data.get("fields") or []),
        data=list(data.get("data") or []),
        record_id_list=list(data.get("record_id_list") or []),
        has_more=bool(data.get("has_more")),
    )
    if not payload.field_id_list:
        raise RuntimeError("响应缺少 field_id_list")
    return payload


def run_record_list_all(
    *,
    base_token: str,
    table_id: str,
    identity: str,
    lark_cli: str,
    page_size: int = PAGE_SIZE,
) -> RecordListPayload:
    """分页拉取直到 has_more 为 false。"""
    offset = 0
    merged_data: List[List[Any]] = []
    merged_ids: List[str] = []
    first: Optional[RecordListPayload] = None
    while True:
        chunk = run_record_list(
            base_token=base_token,
            table_id=table_id,
            limit=page_size,
            offset=offset,
            identity=identity,
            lark_cli=lark_cli,
        )
        if first is None:
            first = chunk
        elif chunk.field_id_list != first.field_id_list:
            raise RuntimeError("分页过程中 field_id_list 不一致")
        merged_data.extend(chunk.data)
        merged_ids.extend(chunk.record_id_list)
        if not chunk.has_more:
            break
        offset += len(chunk.data)
        if len(chunk.data) == 0:
            break
    assert first is not None
    return RecordListPayload(
        field_id_list=first.field_id_list,
        fields=first.fields,
        data=merged_data,
        record_id_list=merged_ids,
        has_more=False,
    )


def field_display_name(payload: RecordListPayload, field_id: str) -> str:
    for i, fid in enumerate(payload.field_id_list):
        if fid == field_id:
            if i < len(payload.fields) and payload.fields[i]:
                return str(payload.fields[i])
            break
    return field_id


def run_record_upsert(
    *,
    base_token: str,
    table_id: str,
    record_id: str,
    fields_body: Dict[str, Any],
    identity: str,
    lark_cli: str,
) -> None:
    cmd = [
        lark_cli,
        "base",
        "+record-upsert",
        "--base-token",
        base_token,
        "--table-id",
        table_id,
        "--record-id",
        record_id,
        "--as",
        identity,
        "--json",
        json.dumps(fields_body, ensure_ascii=False),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(
            f"record-upsert 失败 record_id={record_id}: "
            f"{proc.stderr or proc.stdout}"
        )
    raw = proc.stdout.strip()
    if raw:
        try:
            outer = json.loads(raw)
        except json.JSONDecodeError:
            outer = {}
        if not outer.get("ok", True):
            raise RuntimeError(f"record-upsert ok=false record_id={record_id}: {raw[:500]}")


def rows_as_dicts(payload: RecordListPayload) -> List[Dict[str, Any]]:
    idx = {fid: i for i, fid in enumerate(payload.field_id_list)}
    ids = payload.record_id_list
    out: List[Dict[str, Any]] = []
    for ri, row in enumerate(payload.data):
        rec: Dict[str, Any] = {}
        for fid, i in idx.items():
            rec[fid] = row[i] if i < len(row) else None
        if ri < len(ids):
            rec["_record_id"] = ids[ri]
        out.append(rec)
    return out


def is_consumed_cell(rec: Dict[str, Any], fid: str) -> bool:
    """checkbox：True 视为已核销；缺字段或未勾选视为未核销。"""
    if fid not in rec:
        return False
    v = rec[fid]
    if v is True:
        return True
    if v is False or v is None:
        return False
    if isinstance(v, str):
        return v.strip().lower() in ("true", "1", "是", "yes")
    if isinstance(v, (int, float)):
        return v != 0
    return bool(v)


def to_int(v: Any, default: int = 0) -> int:
    if v is None:
        return default
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v)
    s = str(v).strip()
    if not s:
        return default
    try:
        return int(float(s))
    except ValueError:
        return default


def log_row_in_aggregate(
    rec: Dict[str, Any],
    *,
    fid_link: str,
    exclude_unmatched: bool,
    consumed_fid: Optional[str],
    skip_consumed: bool,
) -> bool:
    """与 aggregate_log 相同的纳入条件（用于 --apply 后勾选日志行）。"""
    if skip_consumed and consumed_fid and is_consumed_cell(rec, consumed_fid):
        return False
    link = rec.get(fid_link)
    if link is None:
        return False
    key = str(link)
    if exclude_unmatched and "未匹配" in key:
        return False
    return True


def aggregate_log(
    rows: List[Dict[str, Any]],
    *,
    fid_link: str,
    fid_qty: str,
    exclude_unmatched: bool,
    consumed_fid: Optional[str],
    skip_consumed: bool,
) -> Tuple[Dict[str, int], LogSkipStats]:
    """返回 (link_key -> sum_qty), 跳过行统计。"""
    sums: Dict[str, int] = defaultdict(int)
    stats = LogSkipStats()
    for rec in rows:
        if skip_consumed and consumed_fid and is_consumed_cell(rec, consumed_fid):
            stats.consumed += 1
            continue
        link = rec.get(fid_link)
        if link is None:
            stats.empty_link += 1
            continue
        key = str(link)
        if exclude_unmatched and "未匹配" in key:
            stats.unmatched += 1
            continue
        sums[key] += to_int(rec.get(fid_qty))
    return dict(sums), stats


def reconcile_result_to_dict(result: ReconcileResult) -> Dict[str, Any]:
    """供 HTTP JSON 响应或日志序列化（`inventory` 中含 `_record_id`）。"""
    return {
        "deduct_by_link": result.deduct_by_link,
        "inventory": result.inventory,
        "orphan_links": [
            {"link_key": k, "qty_out": v} for k, v in result.orphan_links
        ],
        "skipped_log_rows": result.skip_stats.total(),
        "skipped_breakdown": asdict(result.skip_stats),
        "total_deduct_matched": result.total_deduct_matched,
    }


def _clamp_page_size(page_size: int) -> int:
    return max(1, min(int(page_size), 500))


def _consumed_fid_from_options(o: ReconcileOptions) -> Optional[str]:
    s = (o.consumed_field_id or "").strip()
    return s or None


def _load_and_compute(
    o: ReconcileOptions,
) -> Tuple[
    ReconcileResult,
    RecordListPayload,
    RecordListPayload,
    List[Dict[str, Any]],
    List[Dict[str, Any]],
]:
    ps = _clamp_page_size(o.page_size)
    log_payload = run_record_list_all(
        base_token=o.base_token,
        table_id=o.log_table_id,
        identity=o.identity,
        lark_cli=o.lark_cli,
        page_size=ps,
    )
    inv_payload = run_record_list_all(
        base_token=o.base_token,
        table_id=o.inv_table_id,
        identity=o.identity,
        lark_cli=o.lark_cli,
        page_size=ps,
    )
    log_rows = rows_as_dicts(log_payload)
    inv_rows = rows_as_dicts(inv_payload)
    consumed_fid = _consumed_fid_from_options(o)
    skip_consumed = o.skip_consumed_rows
    deduct_by_link, skip_stats = aggregate_log(
        log_rows,
        fid_link=o.fid_log_link,
        fid_qty=o.fid_log_qty,
        exclude_unmatched=o.exclude_unmatched,
        consumed_fid=consumed_fid,
        skip_consumed=skip_consumed,
    )
    inv_list, orphan_links = reconcile(
        inv_rows,
        deduct_by_link,
        fid_name=o.fid_inv_name,
        fid_stock=o.fid_inv_stock,
    )
    result = ReconcileResult(
        deduct_by_link=deduct_by_link,
        inventory=inv_list,
        orphan_links=orphan_links,
        skip_stats=skip_stats,
    )
    return result, log_payload, inv_payload, log_rows, inv_rows


def reconcile_inventory(
    options: Optional[ReconcileOptions] = None,
    **overrides: Any,
) -> ReconcileResult:
    """
    拉取两表并计算应扣与扣减后数量；**不写飞书**。

    ``overrides`` 中与 :class:`ReconcileOptions` 同名的关键字会覆盖对应字段，例如
    ``reconcile_inventory(base_token="xxx")``。
    """
    o = replace(options or ReconcileOptions(), **overrides)
    result, _, _, _, _ = _load_and_compute(o)
    return result


def reconcile_inventory_apply(
    options: Optional[ReconcileOptions] = None,
    *,
    mark_log: bool = True,
    write_delay_s: float = 0.55,
    **overrides: Any,
) -> ReconcileResult:
    """
    在 :func:`reconcile_inventory` 基础上，按结果 **写回「库存信息」数量**，
    并在 ``mark_log=True`` 时对参与扣减的日志行勾选「库存已核销」。
    返回本次测算结果（与写回使用的数值一致）。
    """
    o = replace(options or ReconcileOptions(), **overrides)
    result, log_p, inv_p, log_rows, _inv_rows = _load_and_compute(o)
    consumed_fid = _consumed_fid_from_options(o)
    skip_consumed = o.skip_consumed_rows
    apply_inventory_and_logs(
        log_payload=log_p,
        inv_payload=inv_p,
        log_rows=log_rows,
        inv_results=result.inventory,
        base_token=o.base_token,
        log_table=o.log_table_id,
        inv_table=o.inv_table_id,
        identity=o.identity,
        lark_cli=o.lark_cli,
        consumed_fid=consumed_fid,
        skip_consumed=skip_consumed,
        exclude_unmatched=o.exclude_unmatched,
        mark_log=mark_log,
        write_delay_s=max(0.0, write_delay_s),
        fid_inv_stock=o.fid_inv_stock,
        fid_log_link=o.fid_log_link,
        consumed_field_id_for_name=(consumed_fid or FID_LOG_CONSUMED),
    )
    return result


def reconcile(
    inv_rows: List[Dict[str, Any]],
    deduct_by_link: Dict[str, int],
    *,
    fid_name: str,
    fid_stock: str,
) -> Tuple[List[Dict[str, Any]], List[Tuple[str, int]]]:
    """
    返回：
    - inventory 行结果列表（sku, stock, deduct, after）
    - 日志分组键存在但主档无同名商品名称的 (key, qty)
    """
    inv_names = set()
    for rec in inv_rows:
        name = rec.get(fid_name)
        if name is not None and str(name).strip() != "":
            inv_names.add(str(name))

    results: List[Dict[str, Any]] = []
    for rec in inv_rows:
        name = rec.get(fid_name)
        sku = "" if name is None else str(name)
        stock = to_int(rec.get(fid_stock))
        deduct = deduct_by_link.get(sku, 0)
        results.append(
            {
                "sku_name": sku,
                "stock_on_hand": stock,
                "qty_deduct": deduct,
                "stock_after": stock - deduct,
                "_record_id": rec.get("_record_id"),
            }
        )
    results.sort(key=lambda x: x["sku_name"])

    orphan_links: List[Tuple[str, int]] = []
    for k, v in sorted(deduct_by_link.items(), key=lambda x: (-x[1], x[0])):
        if k not in inv_names:
            orphan_links.append((k, v))
    return results, orphan_links


def print_text_report(
    deduct_by_link: Dict[str, int],
    inv_results: List[Dict[str, Any]],
    orphan_links: List[Tuple[str, int]],
    *,
    skip_stats: LogSkipStats,
) -> None:
    print("=== 按「库存关联」汇总（出库数量）===")
    for k, v in sorted(deduct_by_link.items(), key=lambda x: (-x[1], x[0])):
        display = k if len(k) <= 100 else k[:97] + "…"
        print(f"  {v:>5}  |  {display}")
    print()

    print("=== 与「商品名称」精确匹配 — 扣减后剩余 ===")
    for r in inv_results:
        sku = r["sku_name"] or "(空名称)"
        print(f"  {sku}")
        print(
            f"    当前数量: {r['stock_on_hand']}  |  应扣: {r['qty_deduct']}  |  剩余: {r['stock_after']}"
        )
    print()

    if orphan_links:
        print("=== 日志有分组、主档无同名「商品名称」===")
        for k, v in orphan_links:
            display = k if len(k) <= 100 else k[:97] + "…"
            print(f"  {v:>5}  |  {display}")
        print()

    total_deduct = sum(r["qty_deduct"] for r in inv_results)
    print("=== 汇总 ===")
    print(f"  主档行数: {len(inv_results)}")
    print(f"  日志参与汇总的键数: {len(deduct_by_link)}")
    print(f"  匹配到主档的应扣件数合计: {total_deduct}")
    if skip_stats.total():
        print(
            f"  跳过日志行数: 共 {skip_stats.total()} "
            f"（已核销 {skip_stats.consumed}；空库存关联 {skip_stats.empty_link}；"
            f"未匹配过滤 {skip_stats.unmatched}）"
        )


def print_json_report(
    *,
    deduct_by_link: Dict[str, int],
    inv_results: List[Dict[str, Any]],
    orphan_links: List[Tuple[str, int]],
    skip_stats: LogSkipStats,
) -> None:
    doc = {
        "deduct_by_link": deduct_by_link,
        "inventory": inv_results,
        "orphan_links": [{"link_key": k, "qty_out": v} for k, v in orphan_links],
        "skipped_log_rows": skip_stats.total(),
        "skipped_breakdown": {
            "consumed": skip_stats.consumed,
            "empty_link": skip_stats.empty_link,
            "unmatched_filter": skip_stats.unmatched,
        },
        "total_deduct_matched": sum(r["qty_deduct"] for r in inv_results),
    }
    json.dump(doc, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="夕夕单：扣减库存日志 × 库存信息 — 测算或写回「数量」。"
    )
    p.add_argument("--base-token", default=DEFAULT_BASE_TOKEN, help="Base token")
    p.add_argument("--log-table", default=DEFAULT_LOG_TABLE, help="扣减库存日志 table_id")
    p.add_argument("--inv-table", default=DEFAULT_INV_TABLE, help="库存信息 table_id")
    p.add_argument(
        "--page-size",
        type=int,
        default=PAGE_SIZE,
        help="+record-list 分页大小（默认 200）",
    )
    p.add_argument(
        "--as",
        dest="identity",
        default="user",
        choices=("user", "bot"),
        help="lark-cli 身份",
    )
    p.add_argument(
        "--exclude-unmatched",
        action="store_true",
        help="汇总前丢弃「库存关联」含「未匹配」的日志行",
    )
    p.add_argument(
        "--consumed-fid",
        default=FID_LOG_CONSUMED,
        help="「库存已核销」字段 field_id；设为空字符串则不按该列过滤",
    )
    p.add_argument(
        "--include-consumed",
        action="store_true",
        help="已核销行也参与汇总（对账用；默认跳过已勾选「库存已核销」的行）",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="输出 JSON（便于管道处理；与 --apply 互斥时以 --apply 为准）",
    )
    p.add_argument(
        "--apply",
        action="store_true",
        help="写回「库存信息.数量」；成功时 stdout 无输出。默认仍会勾选参与本次扣减的日志行。",
    )
    p.add_argument(
        "--no-mark-log",
        action="store_true",
        help="与 --apply 联用：只改库存，不勾选「库存已核销」（不推荐，易重复扣）",
    )
    p.add_argument(
        "--write-delay",
        type=float,
        default=0.55,
        help="两次 +record-upsert 之间的间隔秒数，降低频控风险",
    )
    p.add_argument(
        "--lark-cli",
        default="lark-cli",
        help="lark-cli 可执行文件路径",
    )
    return p.parse_args(argv)


def apply_inventory_and_logs(
    *,
    log_payload: RecordListPayload,
    inv_payload: RecordListPayload,
    log_rows: List[Dict[str, Any]],
    inv_results: List[Dict[str, Any]],
    base_token: str,
    log_table: str,
    inv_table: str,
    identity: str,
    lark_cli: str,
    consumed_fid: Optional[str],
    skip_consumed: bool,
    exclude_unmatched: bool,
    mark_log: bool,
    write_delay_s: float,
    fid_inv_stock: str = FID_INV_STOCK,
    fid_log_link: str = FID_LOG_LINK,
    consumed_field_id_for_name: str = FID_LOG_CONSUMED,
) -> None:
    qty_col = field_display_name(inv_payload, fid_inv_stock)
    consumed_col = field_display_name(log_payload, consumed_field_id_for_name)

    updated_skus = {r["sku_name"] for r in inv_results if r["qty_deduct"] > 0}

    for r in inv_results:
        if r["qty_deduct"] <= 0:
            continue
        rid = r.get("_record_id")
        if not rid:
            raise RuntimeError(f"库存行无 record_id，无法写回：{r.get('sku_name')!r}")
        run_record_upsert(
            base_token=base_token,
            table_id=inv_table,
            record_id=str(rid),
            fields_body={qty_col: int(r["stock_after"])},
            identity=identity,
            lark_cli=lark_cli,
        )
        time.sleep(write_delay_s)

    if not mark_log or not consumed_fid:
        return

    for rec in log_rows:
        if not log_row_in_aggregate(
            rec,
            fid_link=fid_log_link,
            exclude_unmatched=exclude_unmatched,
            consumed_fid=consumed_fid,
            skip_consumed=skip_consumed,
        ):
            continue
        link = rec.get(fid_log_link)
        if link is None:
            continue
        if str(link) not in updated_skus:
            continue
        if is_consumed_cell(rec, consumed_fid):
            continue
        lid = rec.get("_record_id")
        if not lid:
            continue
        run_record_upsert(
            base_token=base_token,
            table_id=log_table,
            record_id=str(lid),
            fields_body={consumed_col: True},
            identity=identity,
            lark_cli=lark_cli,
        )
        time.sleep(write_delay_s)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    if not shutil.which(args.lark_cli):
        print(
            f"找不到 `{args.lark_cli}`，请先安装并登录（见 20260408飞书/lark-cli-安装与配置指南.md）。",
            file=sys.stderr,
        )
        return 2

    _cf_raw = (args.consumed_fid or "").strip()
    options = ReconcileOptions(
        base_token=args.base_token,
        log_table_id=args.log_table,
        inv_table_id=args.inv_table,
        lark_cli=args.lark_cli,
        identity=args.identity,
        page_size=args.page_size,
        exclude_unmatched=args.exclude_unmatched,
        consumed_field_id=_cf_raw if _cf_raw else None,
        skip_consumed_rows=not args.include_consumed,
    )

    try:
        result, log_payload, inv_payload, log_rows, _inv_rows = _load_and_compute(
            options
        )
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 1

    if args.apply:
        consumed_fid = _consumed_fid_from_options(options)
        try:
            apply_inventory_and_logs(
                log_payload=log_payload,
                inv_payload=inv_payload,
                log_rows=log_rows,
                inv_results=result.inventory,
                base_token=options.base_token,
                log_table=options.log_table_id,
                inv_table=options.inv_table_id,
                identity=options.identity,
                lark_cli=options.lark_cli,
                consumed_fid=consumed_fid,
                skip_consumed=options.skip_consumed_rows,
                exclude_unmatched=options.exclude_unmatched,
                mark_log=not args.no_mark_log,
                write_delay_s=max(0.0, args.write_delay),
                fid_inv_stock=options.fid_inv_stock,
                fid_log_link=options.fid_log_link,
                consumed_field_id_for_name=(consumed_fid or FID_LOG_CONSUMED),
            )
        except RuntimeError as e:
            print(str(e), file=sys.stderr)
            return 1
        return 0

    if args.json:
        print_json_report(
            deduct_by_link=result.deduct_by_link,
            inv_results=result.inventory,
            orphan_links=result.orphan_links,
            skip_stats=result.skip_stats,
        )
    else:
        print_text_report(
            result.deduct_by_link,
            result.inventory,
            result.orphan_links,
            skip_stats=result.skip_stats,
        )
    return 0


__all__ = [
    "DEFAULT_BASE_TOKEN",
    "DEFAULT_INV_TABLE",
    "DEFAULT_LOG_TABLE",
    "FID_INV_NAME",
    "FID_INV_STOCK",
    "FID_LOG_CONSUMED",
    "FID_LOG_LINK",
    "FID_LOG_QTY",
    "LogSkipStats",
    "PAGE_SIZE",
    "ReconcileOptions",
    "ReconcileResult",
    "RecordListPayload",
    "aggregate_log",
    "apply_inventory_and_logs",
    "reconcile",
    "reconcile_inventory",
    "reconcile_inventory_apply",
    "reconcile_result_to_dict",
    "rows_as_dicts",
    "run_record_list",
    "run_record_list_all",
    "run_record_upsert",
]

if __name__ == "__main__":
    raise SystemExit(main())
