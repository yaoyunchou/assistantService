"""拼多多 ERP 预售订单 MySQL 存储（表 erp_order_presell，Nest 业务库）。

markFilter 与 Nest 接口一致：
  - unmarked → purchased = 0（未标记已采购/已处理）
  - marked   → purchased = 1
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pymysql
import pymysql.cursors

from config import Config
from utils.logger import get_logger

logger = get_logger('PinduoduoPresellStore')


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


def _parse_online(value: Optional[str]) -> Optional[bool]:
    if value is None or value == '':
        return None
    return str(value).lower() in ('1', 'true', 'yes')


def _apply_mark_filter(where: List[str], mark_filter: Optional[str]) -> None:
    mf = (mark_filter or '').strip().lower()
    if mf == 'unmarked':
        where.append('(purchased = 0 OR purchased IS NULL)')
    elif mf == 'marked':
        where.append('purchased = 1')
    elif mf and mf not in ('all', 'any'):
        raise ValueError(f'不支持的 markFilter: {mark_filter}')


def list_presell_records(
    *,
    online: Optional[bool] = None,
    mark_filter: Optional[str] = None,
    page: int = 1,
    page_size: int = 10,
) -> Dict[str, Any]:
    """分页查询 erp_order_presell。"""
    page = max(int(page or 1), 1)
    page_size = min(max(int(page_size or 10), 1), 200)
    offset = (page - 1) * page_size

    where = ['1=1']
    params: List[Any] = []
    if online is True:
        where.append('online = 1')
    elif online is False:
        where.append('online = 0')
    _apply_mark_filter(where, mark_filter)

    where_sql = ' AND '.join(where)
    count_sql = f'SELECT COUNT(*) AS total FROM erp_order_presell WHERE {where_sql}'
    list_sql = (
        f'SELECT * FROM erp_order_presell WHERE {where_sql} '
        f'ORDER BY payTime DESC, orderNo DESC LIMIT %s OFFSET %s'
    )

    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(count_sql, params)
            total = int((cur.fetchone() or {}).get('total') or 0)
            cur.execute(list_sql, params + [page_size, offset])
            rows = cur.fetchall()
    except Exception as e:
        logger.error('查询预售表失败: %s', e, exc_info=True)
        raise
    finally:
        conn.close()

    return {
        'total': total,
        'page': page,
        'pageSize': page_size,
        'items': rows,
    }


def mark_purchased(
    order_nos: List[str],
    *,
    purchased: int = 1,
) -> Dict[str, Any]:
    """按平台订单号批量标记预售单 purchased（1=已采购，0=取消标记）。"""
    nos = []
    seen = set()
    for raw in order_nos or []:
        no = str(raw or '').strip()
        if not no or no in seen:
            continue
        seen.add(no)
        nos.append(no)
    if not nos:
        return {'ok': True, 'updated': 0, 'orderNos': []}

    flag = 1 if int(purchased or 0) else 0
    placeholders = ','.join(['%s'] * len(nos))
    sql = (
        f'UPDATE erp_order_presell SET purchased = %s, updatedAt = NOW() '
        f'WHERE orderNo IN ({placeholders})'
    )
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, [flag] + nos)
            updated = int(cur.rowcount or 0)
        logger.info('预售单标记 purchased=%s updated=%s nos=%s', flag, updated, nos[:10])
        return {'ok': True, 'updated': updated, 'orderNos': nos, 'purchased': flag}
    except Exception as e:
        logger.error('标记预售单失败: %s', e, exc_info=True)
        return {'ok': False, 'updated': 0, 'orderNos': nos, 'error': str(e)}
    finally:
        conn.close()
