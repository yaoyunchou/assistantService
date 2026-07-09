"""ERP 待审核订单加锁：直接读写 Nest 共用 MySQL 表 dictionary（pingduoduo/lockGoods）。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pymysql
import pymysql.cursors

from config import Config
from utils.logger import get_logger
from utils.path_helper import get_safe_data_path

logger = get_logger('AuditLockStore')

LOCK_CATEGORY = 'pingduoduo'
LOCK_NAME = 'lockGoods'
LOCAL_FILE_REL = 'data/pdd_audit_locked_orders.json'


def _local_path() -> Path:
    return get_safe_data_path(LOCAL_FILE_REL)


def _connect() -> pymysql.connections.Connection:
    return pymysql.connect(
        host=Config.ANTEXIADAN_DB_HOST,
        port=Config.ANTEXIADAN_DB_PORT,
        user=Config.ANTEXIADAN_DB_USER,
        password=Config.ANTEXIADAN_DB_PASSWORD,
        database=Config.ANTEXIADAN_DB_NAME,
        charset=Config.ANTEXIADAN_DB_CHARSET,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


def parse_lock_order_nos(raw: Any) -> List[str]:
    if not isinstance(raw, str) or not raw.strip():
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return list(dict.fromkeys(s.strip() for s in parsed if str(s).strip()))


def _read_local() -> List[str]:
    path = _local_path()
    if not path.exists():
        return []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        nos = data.get('order_nos', [])
        if isinstance(nos, list):
            return list(dict.fromkeys(str(s).strip() for s in nos if str(s).strip()))
    except Exception as e:
        logger.warning('读取本地锁单缓存失败: %s', e)
    return []


def _write_local(order_nos: List[str]) -> None:
    path = _local_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({'order_nos': order_nos}, f, ensure_ascii=False, indent=2)


def _read_from_db() -> List[str]:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT `value` FROM `dictionary` '
                'WHERE `category` = %s AND `name` = %s AND `isEnabled` = 1 '
                'ORDER BY `sort` DESC, `createdAt` DESC LIMIT 1',
                (LOCK_CATEGORY, LOCK_NAME),
            )
            row = cur.fetchone()
        value = row.get('value') if row else None
        return parse_lock_order_nos(value)
    finally:
        conn.close()


def _write_to_db(order_nos: List[str]) -> None:
    value = json.dumps(order_nos, ensure_ascii=False)
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                'UPDATE `dictionary` SET `value` = %s, `updatedAt` = NOW() '
                'WHERE `category` = %s AND `name` = %s AND `isEnabled` = 1',
                (value, LOCK_CATEGORY, LOCK_NAME),
            )
            if cur.rowcount == 0:
                raise LookupError(
                    f"字典记录不存在：category={LOCK_CATEGORY}, name={LOCK_NAME}"
                )
    finally:
        conn.close()


def fetch_locked_order_nos() -> Dict[str, Any]:
    """拉取已锁单号；优先 MySQL dictionary 表，失败回退本地缓存。"""
    try:
        nos = _read_from_db()
        _write_local(nos)
        return {'success': True, 'order_nos': nos, 'source': 'database'}
    except Exception as e:
        logger.warning('字典表 lockGoods 读取失败，使用本地缓存: %s', e)
        nos = _read_local()
        return {
            'success': True,
            'order_nos': nos,
            'source': 'local',
            'message': f'数据库不可用，已使用本地缓存（{e}）',
        }


def normalize_order_nos(order_nos: List[str]) -> List[str]:
    return list(dict.fromkeys(str(s).strip() for s in order_nos if str(s).strip()))


def get_locked_order_nos_set() -> set[str]:
    resp = fetch_locked_order_nos()
    return set(resp.get('order_nos') or [])


def validate_submit_order_nos(order_nos: List[str]) -> Dict[str, Any]:
    normalized = normalize_order_nos(order_nos)
    lock_resp = fetch_locked_order_nos()
    locked_set = set(lock_resp.get('order_nos') or [])
    blocked = [no for no in normalized if no in locked_set]
    allowed = [no for no in normalized if no not in locked_set]
    return {
        'allowed': allowed,
        'blocked': blocked,
        'lock_source': lock_resp.get('source'),
    }


def update_locked_order_nos(order_nos: List[str]) -> Dict[str, Any]:
    """更新已锁单号；写入 MySQL dictionary 表，失败仅写本地。"""
    unique = normalize_order_nos(order_nos)
    try:
        _write_to_db(unique)
        _write_local(unique)
        return {'success': True, 'order_nos': unique, 'source': 'database'}
    except Exception as e:
        logger.warning('字典表 lockGoods 写入失败，仅保存本地: %s', e)
        _write_local(unique)
        return {
            'success': True,
            'order_nos': unique,
            'source': 'local',
            'message': f'数据库不可用，已仅保存到本机（{e}）',
        }
