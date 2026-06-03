"""安特限时秒杀商品本地 SQLite 存储。"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from config import Config
from utils.logger import get_logger
from utils.path_helper import get_safe_data_path

logger = get_logger('AntexiadanSeckillStore')


def _db_path() -> Path:
    path_str = (getattr(Config, 'ANTEXIADAN_SECKILL_DB_PATH', None) or '').strip()
    if path_str:
        p = Path(path_str)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    return get_safe_data_path('data/antexiadan_seckill.sqlite')


def _connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = _connect()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS antexiadan_seckill_fetch_batch (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fetched_at TEXT NOT NULL,
                server_time TEXT,
                server_unix INTEGER,
                api_version TEXT,
                source TEXT NOT NULL DEFAULT 'pcapi',
                item_count INTEGER NOT NULL DEFAULT 0,
                api_flag INTEGER,
                api_msg TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
            );

            CREATE TABLE IF NOT EXISTS antexiadan_seckill_product (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                seckill_id TEXT NOT NULL UNIQUE,
                goods_id TEXT NOT NULL,
                goods_basic_id TEXT,
                title TEXT NOT NULL,
                price_min REAL,
                price_max REAL,
                price_display TEXT,
                group_title TEXT,
                slot_time TEXT,
                group_sub_title TEXT,
                activity_status TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                start_unix INTEGER NOT NULL,
                end_unix INTEGER NOT NULL,
                seckill_state TEXT,
                seckill_image TEXT,
                goods_url TEXT,
                goods_is_offline INTEGER NOT NULL DEFAULT 0,
                homepage_display INTEGER NOT NULL DEFAULT 1,
                is_flash_title INTEGER NOT NULL DEFAULT 1,
                last_fetch_batch_id INTEGER,
                last_fetched_at TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (last_fetch_batch_id) REFERENCES antexiadan_seckill_fetch_batch(id)
            );

            CREATE TABLE IF NOT EXISTS antexiadan_seckill_product_snapshot (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fetch_batch_id INTEGER NOT NULL,
                seckill_id TEXT NOT NULL,
                goods_id TEXT NOT NULL,
                goods_basic_id TEXT,
                title TEXT NOT NULL,
                price_min REAL,
                price_max REAL,
                price_display TEXT,
                group_title TEXT,
                slot_time TEXT,
                group_sub_title TEXT,
                activity_status TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                start_unix INTEGER NOT NULL,
                end_unix INTEGER NOT NULL,
                seckill_state TEXT,
                seckill_image TEXT,
                goods_url TEXT,
                goods_is_offline INTEGER NOT NULL DEFAULT 0,
                homepage_display INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                UNIQUE (fetch_batch_id, seckill_id),
                FOREIGN KEY (fetch_batch_id) REFERENCES antexiadan_seckill_fetch_batch(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_seckill_product_start ON antexiadan_seckill_product(start_time);
            CREATE INDEX IF NOT EXISTS idx_seckill_product_status ON antexiadan_seckill_product(activity_status);
            CREATE INDEX IF NOT EXISTS idx_seckill_product_group ON antexiadan_seckill_product(group_title, slot_time);
            CREATE INDEX IF NOT EXISTS idx_seckill_snapshot_batch ON antexiadan_seckill_product_snapshot(fetch_batch_id);
            """
        )
        conn.commit()
    finally:
        conn.close()


def _bool_int(v: Any) -> int:
    return 1 if v in (True, 1, '1', 'true', 'True') else 0


def _row_tuple(row: Dict[str, Any], batch_id: int, fetched_at: str) -> Tuple[Any, ...]:
    return (
        str(row.get('seckillId') or ''),
        str(row.get('goodsId') or ''),
        str(row.get('goodsBasicId') or ''),
        str(row.get('title') or ''),
        row.get('priceMin'),
        row.get('priceMax'),
        str(row.get('priceDisplay') or ''),
        str(row.get('groupTitle') or ''),
        str(row.get('slotTime') or ''),
        str(row.get('groupSubTitle') or ''),
        str(row.get('activityStatus') or ''),
        str(row.get('startTime') or ''),
        str(row.get('endTime') or ''),
        int(row.get('startUnix') or 0),
        int(row.get('endUnix') or 0),
        str(row.get('seckillState') or ''),
        str(row.get('seckillImage') or ''),
        str(row.get('goodsUrl') or ''),
        _bool_int(row.get('goodsIsOffline')),
        _bool_int(row.get('homepageDisplay')),
        _bool_int(row.get('isFlashTitle')),
        batch_id,
        fetched_at,
    )


_PRODUCT_UPSERT_SQL = """
INSERT INTO antexiadan_seckill_product (
    seckill_id, goods_id, goods_basic_id, title,
    price_min, price_max, price_display,
    group_title, slot_time, group_sub_title, activity_status,
    start_time, end_time, start_unix, end_unix,
    seckill_state, seckill_image, goods_url,
    goods_is_offline, homepage_display, is_flash_title,
    last_fetch_batch_id, last_fetched_at, updated_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now','localtime'))
ON CONFLICT(seckill_id) DO UPDATE SET
    goods_id=excluded.goods_id,
    goods_basic_id=excluded.goods_basic_id,
    title=excluded.title,
    price_min=excluded.price_min,
    price_max=excluded.price_max,
    price_display=excluded.price_display,
    group_title=excluded.group_title,
    slot_time=excluded.slot_time,
    group_sub_title=excluded.group_sub_title,
    activity_status=excluded.activity_status,
    start_time=excluded.start_time,
    end_time=excluded.end_time,
    start_unix=excluded.start_unix,
    end_unix=excluded.end_unix,
    seckill_state=excluded.seckill_state,
    seckill_image=excluded.seckill_image,
    goods_url=excluded.goods_url,
    goods_is_offline=excluded.goods_is_offline,
    homepage_display=excluded.homepage_display,
    is_flash_title=excluded.is_flash_title,
    last_fetch_batch_id=excluded.last_fetch_batch_id,
    last_fetched_at=excluded.last_fetched_at,
    updated_at=datetime('now','localtime')
"""

_SNAPSHOT_INSERT_SQL = """
INSERT OR REPLACE INTO antexiadan_seckill_product_snapshot (
    fetch_batch_id, seckill_id, goods_id, goods_basic_id, title,
    price_min, price_max, price_display,
    group_title, slot_time, group_sub_title, activity_status,
    start_time, end_time, start_unix, end_unix,
    seckill_state, seckill_image, goods_url,
    goods_is_offline, homepage_display
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def sync_payload(payload: Dict[str, Any], *, write_snapshot: bool = True) -> Dict[str, Any]:
    """
    将 webAuto 同步体写入 SQLite。
    payload 字段：fetchedAt, serverTime, serverUnix, apiVersion, rows[], count, byStatus, groups
    """
    init_db()
    rows: List[Dict[str, Any]] = payload.get('rows') or []
    if not rows:
        return {'ok': False, 'error': 'rows 为空', 'upserted': 0}

    fetched_at = str(payload.get('fetchedAt') or datetime.now().strftime('%Y-%m-%d %H:%M'))
    server_time = payload.get('serverTime')
    server_unix = payload.get('serverUnix')
    api_version = str(payload.get('apiVersion') or '')
    api_flag = payload.get('apiFlag')
    api_msg = str(payload.get('apiMsg') or payload.get('msg') or '')

    conn = _connect()
    try:
        cur = conn.execute(
            """
            INSERT INTO antexiadan_seckill_fetch_batch (
                fetched_at, server_time, server_unix, api_version,
                item_count, api_flag, api_msg
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fetched_at,
                server_time,
                server_unix,
                api_version,
                len(rows),
                api_flag,
                api_msg,
            ),
        )
        batch_id = int(cur.lastrowid)

        upserted = 0
        for row in rows:
            if not row.get('seckillId'):
                continue
            conn.execute(_PRODUCT_UPSERT_SQL, _row_tuple(row, batch_id, fetched_at))
            if write_snapshot:
                t = _row_tuple(row, batch_id, fetched_at)
                conn.execute(
                    _SNAPSHOT_INSERT_SQL,
                    (
                        batch_id,
                        t[0], t[1], t[2], t[3],
                        t[4], t[5], t[6],
                        t[7], t[8], t[9], t[10],
                        t[11], t[12], t[13], t[14],
                        t[15], t[16], t[17],
                        t[18], t[19],
                    ),
                )
            upserted += 1

        conn.commit()
        return {
            'ok': True,
            'batchId': batch_id,
            'upserted': upserted,
            'dbPath': str(_db_path()),
            'writeSnapshot': write_snapshot,
        }
    except Exception as e:
        conn.rollback()
        logger.error('秒杀同步入库失败: %s', e, exc_info=True)
        return {'ok': False, 'error': str(e), 'upserted': 0}
    finally:
        conn.close()


def list_products(
    *,
    activity_status: Optional[str] = None,
    group_title: Optional[str] = None,
    slot_time: Optional[str] = None,
    limit: int = 500,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    init_db()
    sql = 'SELECT * FROM antexiadan_seckill_product WHERE 1=1'
    params: List[Any] = []
    if activity_status:
        sql += ' AND activity_status = ?'
        params.append(activity_status)
    if group_title:
        sql += ' AND group_title = ?'
        params.append(group_title)
    if slot_time:
        sql += ' AND slot_time = ?'
        params.append(slot_time)
    sql += ' ORDER BY start_time ASC, seckill_id ASC LIMIT ? OFFSET ?'
    params.extend([limit, offset])

    conn = _connect()
    try:
        cur = conn.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def get_latest_batch() -> Optional[Dict[str, Any]]:
    init_db()
    conn = _connect()
    try:
        cur = conn.execute(
            'SELECT * FROM antexiadan_seckill_fetch_batch ORDER BY id DESC LIMIT 1'
        )
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()
