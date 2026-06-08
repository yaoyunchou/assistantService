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
