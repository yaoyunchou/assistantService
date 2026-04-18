"""拼多多 ERP 审核记录本地 SQLite 存储。"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import Config
from utils.logger import get_logger
from utils.path_helper import get_safe_data_path

logger = get_logger('PinduoduoAuditStore')


def _db_path() -> Path:
    if Config.PINDUODUO_ERP_AUDIT_DB_PATH:
        p = Path(Config.PINDUODUO_ERP_AUDIT_DB_PATH)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    return get_safe_data_path('data/pdd_erp_audit.sqlite')


def _connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = _connect()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_no TEXT NOT NULL,
                audited_at TEXT NOT NULL,
                audit_date TEXT NOT NULL,
                goods_json TEXT NOT NULL,
                feishu_synced_at TEXT,
                feishu_record_id TEXT
            )
            """
        )
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_audit_events_date ON audit_events(audit_date)'
        )
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_audit_events_order ON audit_events(order_no)'
        )
        conn.commit()
    finally:
        conn.close()


def insert_after_audit(
    order_no: str,
    goods: Any,
    *,
    audited_at: Optional[datetime] = None,
) -> Optional[int]:
    """写入一条审核记录，返回 row id。"""
    init_db()
    at = audited_at or datetime.now()
    audit_date = at.strftime('%Y-%m-%d')
    audited_iso = at.isoformat(timespec='seconds')
    payload = json.dumps(goods, ensure_ascii=False) if not isinstance(goods, str) else goods

    conn = _connect()
    try:
        cur = conn.execute(
            """
            INSERT INTO audit_events (order_no, audited_at, audit_date, goods_json)
            VALUES (?, ?, ?, ?)
            """,
            (order_no.strip(), audited_iso, audit_date, payload),
        )
        conn.commit()
        return int(cur.lastrowid) if cur.lastrowid is not None else None
    except Exception as e:
        logger.error('写入审核记录失败: %s', e, exc_info=True)
        return None
    finally:
        conn.close()


def insert_batch_from_submit_rows(
    rows: List[Dict[str, Any]],
    *,
    audited_at: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """根据脚本返回的 rows（含 orderNo、goods）批量写入，返回可供飞书同步的记录 dict（含 id）。"""
    at = audited_at or datetime.now()
    audited_iso = at.isoformat(timespec='seconds')
    audit_date = at.strftime('%Y-%m-%d')
    out: List[Dict[str, Any]] = []
    for row in rows:
        on = (row.get('orderNo') or '').strip()
        if not on:
            continue
        goods = row.get('goods') or []
        rid = insert_after_audit(on, goods, audited_at=at)
        if rid is None:
            continue
        out.append({
            'id': rid,
            'order_no': on,
            'audited_at': audited_iso,
            'audit_date': audit_date,
            'goods': goods,
            'goods_json': json.dumps(goods, ensure_ascii=False),
        })
    return out


def list_by_audit_date(audit_date: str) -> List[Dict[str, Any]]:
    """audit_date: YYYY-MM-DD"""
    init_db()
    conn = _connect()
    try:
        cur = conn.execute(
            """
            SELECT id, order_no, audited_at, audit_date, goods_json, feishu_synced_at, feishu_record_id
            FROM audit_events WHERE audit_date = ? ORDER BY id DESC
            """,
            (audit_date,),
        )
        return [_row_to_dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def list_today_local() -> List[Dict[str, Any]]:
    d = datetime.now().strftime('%Y-%m-%d')
    return list_by_audit_date(d)


def list_unsynced_for_feishu(limit: int = 200) -> List[Dict[str, Any]]:
    init_db()
    conn = _connect()
    try:
        cur = conn.execute(
            """
            SELECT id, order_no, audited_at, audit_date, goods_json, feishu_synced_at, feishu_record_id
            FROM audit_events WHERE feishu_synced_at IS NULL ORDER BY id ASC LIMIT ?
            """,
            (limit,),
        )
        return [_row_to_dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def mark_synced(record_ids: List[int], feishu_record_ids: Optional[List[str]] = None) -> None:
    if not record_ids:
        return
    now = datetime.now().isoformat(timespec='seconds')
    conn = _connect()
    try:
        for i, rid in enumerate(record_ids):
            frid = None
            if feishu_record_ids and i < len(feishu_record_ids):
                frid = feishu_record_ids[i]
            conn.execute(
                """
                UPDATE audit_events SET feishu_synced_at = ?, feishu_record_id = COALESCE(?, feishu_record_id)
                WHERE id = ?
                """,
                (now, frid, rid),
            )
        conn.commit()
    finally:
        conn.close()


def _row_to_dict(r: sqlite3.Row) -> Dict[str, Any]:
    d = dict(r)
    gj = d.get('goods_json') or '[]'
    try:
        d['goods'] = json.loads(gj)
    except Exception:
        d['goods'] = []
    return d
