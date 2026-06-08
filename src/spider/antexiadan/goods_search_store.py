"""安特商品搜索缓存 MySQL 存储（表 antexiadan_goods_search）。

按 keyword 缓存 search-goods-list 结果，供秒杀预购对照等场景复用。
搜索采集走浏览器登录会话（见 goods_search.py），本模块负责读写本地表。

连接参数通过 Config 读取（与 seckill_store 相同）：
  ANTEXIADAN_DB_HOST / ANTEXIADAN_DB_PORT / ANTEXIADAN_DB_USER
  ANTEXIADAN_DB_PASSWORD / ANTEXIADAN_DB_NAME / ANTEXIADAN_DB_CHARSET
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

import pymysql
import pymysql.cursors

from config import Config
from utils.logger import get_logger

logger = get_logger('AntexiadanGoodsSearchStore')

_INIT_SQL = """
CREATE TABLE IF NOT EXISTS antexiadan_goods_search (
  id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '自增主键',
  keyword         VARCHAR(64)     NOT NULL COMMENT '搜索关键词，如 120002 / 008312',
  goods_id        VARCHAR(32)     NOT NULL COMMENT '安特 goods_id',
  goods_basic_id  VARCHAR(32)     NULL     COMMENT '安特 goods_basicid',
  goods_name      VARCHAR(512)    NOT NULL COMMENT '商品名称',
  goods_image     VARCHAR(512)    NULL     COMMENT '主图 URL',
  seckill_id      VARCHAR(32)     NULL     COMMENT '搜索 API 返回的 seckill_id，可能为 null',
  activity_type   INT             NULL     DEFAULT 0 COMMENT '活动类型，0=普通商品',
  activity_id     INT             NULL     DEFAULT 0 COMMENT '活动 ID',
  goods_url       VARCHAR(512)    NULL     COMMENT 'H5 商品链接',
  price_min       DECIMAL(12,2)   NULL     COMMENT '批发最低价',
  price_max       DECIMAL(12,2)   NULL     COMMENT '批发最高价',
  api_flag        INT             NULL     COMMENT '接口 flag',
  api_msg         VARCHAR(255)    NULL     COMMENT '接口 msg',
  searched_at     DATETIME        NOT NULL COMMENT '最近一次搜索时间',
  created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_keyword (keyword),
  KEY idx_goods_id (goods_id),
  KEY idx_seckill_id (seckill_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""

_UPSERT_SQL = """
INSERT INTO antexiadan_goods_search (
    keyword, goods_id, goods_basic_id, goods_name, goods_image,
    seckill_id, activity_type, activity_id, goods_url,
    price_min, price_max, api_flag, api_msg, searched_at
) VALUES (
    %s, %s, %s, %s, %s,
    %s, %s, %s, %s,
    %s, %s, %s, %s, %s
)
ON DUPLICATE KEY UPDATE
    goods_id        = VALUES(goods_id),
    goods_basic_id  = VALUES(goods_basic_id),
    goods_name      = VALUES(goods_name),
    goods_image     = VALUES(goods_image),
    seckill_id      = VALUES(seckill_id),
    activity_type   = VALUES(activity_type),
    activity_id     = VALUES(activity_id),
    goods_url       = VALUES(goods_url),
    price_min       = VALUES(price_min),
    price_max       = VALUES(price_max),
    api_flag        = VALUES(api_flag),
    api_msg         = VALUES(api_msg),
    searched_at     = VALUES(searched_at)
"""


def _connect() -> pymysql.connections.Connection:
    return pymysql.connect(
        host=Config.ANTEXIADAN_DB_HOST,
        port=Config.ANTEXIADAN_DB_PORT,
        user=Config.ANTEXIADAN_DB_USER,
        password=Config.ANTEXIADAN_DB_PASSWORD,
        database=Config.ANTEXIADAN_DB_NAME,
        charset=Config.ANTEXIADAN_DB_CHARSET,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


def _now() -> str:
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _to_decimal(value: Any) -> Optional[Decimal]:
    if value is None or value == '':
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _normalize_keyword(keyword: str) -> str:
    return str(keyword or '').strip()


def _normalize_api_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """将 search-goods-list list[] 单项转为入库字段。"""
    seckill_id = item.get('seckill_id')
    if seckill_id is not None and str(seckill_id).strip() == '':
        seckill_id = None
    return {
        'goods_id': str(item.get('goods_id') or ''),
        'goods_basic_id': str(item.get('goods_basicid') or item.get('goods_basic_id') or '') or None,
        'goods_name': str(item.get('goods_name') or ''),
        'goods_image': str(item.get('goods_image') or '') or None,
        'seckill_id': str(seckill_id) if seckill_id is not None else None,
        'activity_type': int(item.get('activity_type') or 0),
        'activity_id': int(item.get('activity_id') or 0),
        'goods_url': str(item.get('goods_url') or '') or None,
        'price_min': _to_decimal(item.get('goods_wholesale_price_min') or item.get('price_min')),
        'price_max': _to_decimal(item.get('goods_wholesale_price_max') or item.get('price_max')),
    }


def init_db() -> None:
    """创建 antexiadan_goods_search 表（若不存在）。"""
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(_INIT_SQL)
        conn.commit()
        logger.info('[antexiadan] antexiadan_goods_search 表已就绪')
    finally:
        conn.close()


def get_by_keyword(keyword: str) -> Optional[Dict[str, Any]]:
    """按搜索词查询一条缓存记录。"""
    kw = _normalize_keyword(keyword)
    if not kw:
        return None

    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT * FROM antexiadan_goods_search WHERE keyword = %s LIMIT 1',
                (kw,),
            )
            return cur.fetchone()
    finally:
        conn.close()


def get_by_keywords(keywords: List[str]) -> Dict[str, Dict[str, Any]]:
    """批量按 keyword 查询，返回 { keyword: row }。"""
    keys = [_normalize_keyword(k) for k in keywords if _normalize_keyword(k)]
    if not keys:
        return {}

    placeholders = ','.join(['%s'] * len(keys))
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f'SELECT * FROM antexiadan_goods_search WHERE keyword IN ({placeholders})',
                keys,
            )
            rows = cur.fetchall() or []
        return {str(r['keyword']): r for r in rows}
    finally:
        conn.close()


def upsert_from_search(
    keyword: str,
    item: Dict[str, Any],
    *,
    api_flag: Optional[int] = None,
    api_msg: Optional[str] = None,
    searched_at: Optional[str] = None,
) -> Dict[str, Any]:
    """将 search-goods-list 的单条商品写入/更新缓存。"""
    kw = _normalize_keyword(keyword)
    if not kw:
        raise ValueError('keyword 不能为空')

    normalized = _normalize_api_item(item)
    if not normalized['goods_id']:
        raise ValueError('goods_id 不能为空')
    if not normalized['goods_name']:
        raise ValueError('goods_name 不能为空')

    searched = searched_at or _now()
    params = (
        kw,
        normalized['goods_id'],
        normalized['goods_basic_id'],
        normalized['goods_name'],
        normalized['goods_image'],
        normalized['seckill_id'],
        normalized['activity_type'],
        normalized['activity_id'],
        normalized['goods_url'],
        normalized['price_min'],
        normalized['price_max'],
        api_flag,
        (str(api_msg).strip() or None) if api_msg is not None else None,
        searched,
    )

    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(_UPSERT_SQL, params)
        conn.commit()
        row = get_by_keyword(kw)
        logger.info('[antexiadan] 商品搜索缓存 UPSERT keyword=%s goods_id=%s', kw, normalized['goods_id'])
        return row or {'keyword': kw, **normalized, 'searched_at': searched}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def upsert_from_api_response(
    keyword: str,
    api_body: Dict[str, Any],
    *,
    searched_at: Optional[str] = None,
) -> Dict[str, Any]:
    """从 search-goods-list 完整响应体取 list[0] 并入库。"""
    kw = _normalize_keyword(keyword)
    flag = api_body.get('flag')
    msg = api_body.get('msg')
    data = api_body.get('data') or {}
    items = data.get('list') or []
    if not items:
        raise ValueError(f'搜索无结果: keyword={kw}, msg={msg}')

    return upsert_from_search(
        kw,
        items[0],
        api_flag=int(flag) if flag is not None else None,
        api_msg=str(msg) if msg is not None else None,
        searched_at=searched_at,
    )


def list_records(
    *,
    keyword_like: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """分页列出搜索缓存（管理/调试）。"""
    sql = 'SELECT * FROM antexiadan_goods_search WHERE 1=1'
    params: List[Any] = []
    if keyword_like:
        sql += ' AND keyword LIKE %s'
        params.append(f'%{keyword_like.strip()}%')
    sql += ' ORDER BY searched_at DESC, keyword ASC LIMIT %s OFFSET %s'
    params.extend([limit, offset])

    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall() or []
    finally:
        conn.close()


def serialize_row(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """将 DB 行转为 API 友好 dict（Decimal/datetime 转字符串）。"""
    if not row:
        return None
    out: Dict[str, Any] = {}
    for k, v in row.items():
        if isinstance(v, Decimal):
            out[k] = str(v)
        elif hasattr(v, 'strftime'):
            out[k] = v.strftime('%Y-%m-%d %H:%M:%S')
        else:
            out[k] = v
    return out
