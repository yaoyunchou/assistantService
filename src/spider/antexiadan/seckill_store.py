"""安特限时秒杀商品 MySQL 存储。

连接参数通过 Config 读取（对应 .env 环境变量）：
  ANTEXIADAN_DB_HOST / ANTEXIADAN_DB_PORT / ANTEXIADAN_DB_USER
  ANTEXIADAN_DB_PASSWORD / ANTEXIADAN_DB_NAME / ANTEXIADAN_DB_CHARSET
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pymysql
import pymysql.cursors

from config import Config
from utils.logger import get_logger

logger = get_logger('AntexiadanSeckillStore')


# ---------------------------------------------------------------------------
# 连接
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------

def _bool_int(v: Any) -> int:
    return 1 if v in (True, 1, '1', 'true', 'True') else 0


def _now() -> str:
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _row_tuple(row: Dict[str, Any], batch_id: int, fetched_at: str) -> Tuple[Any, ...]:
    return (
        str(row.get('seckillId') or ''),
        str(row.get('goodsId') or ''),
        str(row.get('goodsBasicId') or '') or None,
        str(row.get('title') or ''),
        row.get('priceMin'),
        row.get('priceMax'),
        str(row.get('priceDisplay') or '') or None,
        str(row.get('groupTitle') or '') or None,
        str(row.get('slotTime') or '') or None,
        str(row.get('groupSubTitle') or '') or None,
        str(row.get('activityStatus') or ''),
        str(row.get('startTime') or ''),
        str(row.get('endTime') or ''),
        int(row.get('startUnix') or 0),
        int(row.get('endUnix') or 0),
        str(row.get('seckillState') or '') or None,
        str(row.get('seckillImage') or '') or None,
        str(row.get('goodsUrl') or '') or None,
        _bool_int(row.get('goodsIsOffline')),
        _bool_int(row.get('homepageDisplay')),
        _bool_int(row.get('isFlashTitle')),
        batch_id,
        fetched_at,
    )


# ---------------------------------------------------------------------------
# UPSERT SQL（MySQL ON DUPLICATE KEY UPDATE）
# ---------------------------------------------------------------------------

_PRODUCT_UPSERT_SQL = """
INSERT INTO antexiadan_seckill_product (
    seckill_id, goods_id, goods_basic_id, title,
    price_min, price_max, price_display,
    group_title, slot_time, group_sub_title, activity_status,
    start_time, end_time, start_unix, end_unix,
    seckill_state, seckill_image, goods_url,
    goods_is_offline, homepage_display, is_flash_title,
    last_fetch_batch_id, last_fetched_at
) VALUES (
    %s, %s, %s, %s,
    %s, %s, %s,
    %s, %s, %s, %s,
    %s, %s, %s, %s,
    %s, %s, %s,
    %s, %s, %s,
    %s, %s
)
ON DUPLICATE KEY UPDATE
    goods_id            = VALUES(goods_id),
    goods_basic_id      = VALUES(goods_basic_id),
    title               = VALUES(title),
    price_min           = VALUES(price_min),
    price_max           = VALUES(price_max),
    price_display       = VALUES(price_display),
    group_title         = VALUES(group_title),
    slot_time           = VALUES(slot_time),
    group_sub_title     = VALUES(group_sub_title),
    activity_status     = VALUES(activity_status),
    start_time          = VALUES(start_time),
    end_time            = VALUES(end_time),
    start_unix          = VALUES(start_unix),
    end_unix            = VALUES(end_unix),
    seckill_state       = VALUES(seckill_state),
    seckill_image       = VALUES(seckill_image),
    goods_url           = VALUES(goods_url),
    goods_is_offline    = VALUES(goods_is_offline),
    homepage_display    = VALUES(homepage_display),
    is_flash_title      = VALUES(is_flash_title),
    last_fetch_batch_id = VALUES(last_fetch_batch_id),
    last_fetched_at     = VALUES(last_fetched_at)
"""

_SNAPSHOT_INSERT_SQL = """
INSERT IGNORE INTO antexiadan_seckill_product_snapshot (
    fetch_batch_id, seckill_id, goods_id, goods_basic_id, title,
    price_min, price_max, price_display,
    group_title, slot_time, group_sub_title, activity_status,
    start_time, end_time, start_unix, end_unix,
    seckill_state, seckill_image, goods_url,
    goods_is_offline, homepage_display
) VALUES (
    %s, %s, %s, %s, %s,
    %s, %s, %s,
    %s, %s, %s, %s,
    %s, %s, %s, %s,
    %s, %s, %s,
    %s, %s
)
"""


# ---------------------------------------------------------------------------
# 公共接口
# ---------------------------------------------------------------------------

def sync_payload(payload: Dict[str, Any], *, write_snapshot: bool = True) -> Dict[str, Any]:
    """将 webAuto 同步体写入 MySQL。ON DUPLICATE KEY UPDATE 按 seckill_id 更新。"""
    rows: List[Dict[str, Any]] = payload.get('rows') or []
    if not rows:
        return {'ok': False, 'error': 'rows 为空', 'upserted': 0}

    fetched_at  = str(payload.get('fetchedAt') or _now())
    server_time = payload.get('serverTime') or None
    server_unix = payload.get('serverUnix') or None
    api_version = str(payload.get('apiVersion') or '')
    api_flag    = payload.get('apiFlag') or None
    api_msg     = str(payload.get('apiMsg') or payload.get('msg') or '') or None

    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO antexiadan_seckill_fetch_batch
                    (fetched_at, server_time, server_unix, api_version,
                     item_count, api_flag, api_msg)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (fetched_at, server_time, server_unix, api_version,
                 len(rows), api_flag, api_msg),
            )
            batch_id = cur.lastrowid

            inserted = 0
            updated  = 0
            for row in rows:
                if not row.get('seckillId'):
                    continue
                t = _row_tuple(row, batch_id, fetched_at)
                cur.execute(_PRODUCT_UPSERT_SQL, t)
                # MySQL ON DUPLICATE KEY UPDATE: rowcount=1 新增, rowcount=2 更新
                if cur.rowcount == 1:
                    inserted += 1
                else:
                    updated += 1
                if write_snapshot:
                    cur.execute(
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

        conn.commit()
        return {
            'ok': True,
            'batchId': batch_id,
            'upserted':  inserted + updated,
            'inserted':  inserted,
            'updated':   updated,
            'writeSnapshot': write_snapshot,
        }
    except Exception as e:
        conn.rollback()
        logger.error('秒杀同步入库失败: %s', e, exc_info=True)
        return {'ok': False, 'error': str(e), 'upserted': 0, 'inserted': 0, 'updated': 0}
    finally:
        conn.close()


_AUTO_EXPIRE_SQL = """
    UPDATE antexiadan_seckill_product
    SET    activity_status = '已结束'
    WHERE  end_time IS NOT NULL
      AND  end_time < NOW()
      AND  activity_status != '已结束'
"""

def _auto_expire(conn) -> int:
    """把 end_time 已过期的商品状态更新为「已结束」，返回更新行数。"""
    with conn.cursor() as cur:
        cur.execute(_AUTO_EXPIRE_SQL)
        return cur.rowcount


def list_products(
    *,
    activity_status: Optional[str] = None,
    group_title: Optional[str] = None,
    slot_time: Optional[str] = None,
    exclude_offline: bool = False,
    exclude_ended: bool = False,
    limit: int = 500,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """查询商品当前态。

    exclude_offline=True 时排除 goods_is_offline=1（平台已标记下架/不可售）。
    exclude_ended=True 时排除 activity_status=已结束 或 end_time 已过的活动。
    """
    sql = 'SELECT * FROM antexiadan_seckill_product WHERE 1=1'
    params: List[Any] = []
    if activity_status:
        sql += ' AND activity_status = %s'
        params.append(activity_status)
    if group_title:
        sql += ' AND group_title = %s'
        params.append(group_title)
    if slot_time:
        sql += ' AND slot_time = %s'
        params.append(slot_time)
    if exclude_offline:
        sql += ' AND goods_is_offline = 0'
    if exclude_ended:
        sql += " AND activity_status != '已结束'"
        sql += ' AND (end_time IS NULL OR end_time >= NOW())'
    sql += ' ORDER BY start_time ASC, seckill_id ASC LIMIT %s OFFSET %s'
    params.extend([limit, offset])

    conn = _connect()
    try:
        expired = _auto_expire(conn)
        if expired:
            conn.commit()
            logger.info(f'[antexiadan] 自动标记 {expired} 条已过期秒杀为「已结束」')
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()
    finally:
        conn.close()


def list_presale_active_unmarked(
    *,
    limit: int = 500,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """正在预售且未被平台标记下架的商品。

    条件：
    - activity_status = 预热/待开始（尚未开秒）
    - group_title = 预热中（首页当前预售分组，非「预告」）
    - goods_is_offline = 0（未标记下架）
    """
    return list_products(
        activity_status='预热/待开始',
        group_title='预热中',
        exclude_offline=True,
        limit=limit,
        offset=offset,
    )


def get_latest_batch() -> Optional[Dict[str, Any]]:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT * FROM antexiadan_seckill_fetch_batch ORDER BY id DESC LIMIT 1'
            )
            return cur.fetchone()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 服务端直拉 pcapi
# ---------------------------------------------------------------------------

def fetch_and_sync(*, api_key: str = '', write_snapshot: bool = True) -> Dict[str, Any]:
    """
    直连 pcapi.antexiadan.com 拉取限时秒杀列表并入库。
    api_key 优先用传入值，否则读 Config.ANTEXI_API_KEY。
    """
    import json
    from datetime import datetime
    from urllib.parse import urlencode
    from urllib.request import Request, urlopen

    key = (api_key or '').strip() or Config.ANTEXI_API_KEY
    if not key:
        return {
            'ok': False,
            'error': '缺少 ANTEXI_API_KEY：请在 .env 配置 ANTEXI_API_KEY，'
                     '或从 Chrome Network 的 seckill-list 请求中复制 key 参数',
        }

    version = Config.ANTEXI_API_VERSION
    qs  = urlencode({'key': key, 'version': version})
    url = f'https://pcapi.antexiadan.com/v1/home/seckill-list?{qs}'

    try:
        req = Request(url, headers={'Accept': 'application/json'})
        with urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        return {'ok': False, 'error': f'请求 pcapi 失败: {e}'}

    if data.get('flag') != 200:
        return {'ok': False, 'error': f"API flag={data.get('flag')} msg={data.get('msg')}"}

    server_unix = int(data.get('server_time') or 0)

    def _fmt(ts: int) -> str:
        if not ts:
            return ''
        d = datetime.fromtimestamp(ts)
        return f'{d.year}-{d.month:02d}-{d.day:02d} {d.hour:02d}:{d.minute:02d}'

    def _activity_status(item: dict) -> str:
        st = int(item.get('start_time') or 0)
        et = int(item.get('end_time') or 0)
        now = server_unix or int(datetime.now().timestamp())
        if now >= st and now < et:
            return '秒杀中'
        if now < st:
            return '预热/待开始'
        return '已结束'

    def _slot(group: dict) -> str:
        title = str(group.get('title') or '')
        sub   = str(group.get('sub_title') or '')
        if title in ('秒杀中', '预热中'):
            return sub
        if title == '预告':
            return '下期预告'
        if title == '热卖':
            return sub or '昨日'
        return sub or title

    rows = []
    for group in data.get('data') or []:
        for item in group.get('lists') or []:
            title    = str(item.get('seckill_title') or '').strip()
            mn_s     = item.get('goods_wholesale_price_min')
            mx_s     = item.get('goods_wholesale_price_max')
            try:
                mn = float(mn_s) if mn_s not in (None, '') else None
            except (TypeError, ValueError):
                mn = None
            try:
                mx = float(mx_s) if mx_s not in (None, '') else None
            except (TypeError, ValueError):
                mx = None
            if mn is not None and mx is not None:
                disp = str(mn_s) if mn == mx else f'{mn_s}~{mx_s}'
            else:
                disp = ''
            su = int(item.get('start_time') or 0)
            eu = int(item.get('end_time')   or 0)
            rows.append({
                'seckillId':       str(item.get('seckill_id') or ''),
                'goodsId':         str(item.get('goods_id') or ''),
                'goodsBasicId':    str(item.get('goods_basicid') or ''),
                'title':           title,
                'priceMin':        mn,
                'priceMax':        mx,
                'priceDisplay':    disp,
                'groupTitle':      str(group.get('title') or ''),
                'slotTime':        _slot(group),
                'groupSubTitle':   str(group.get('sub_title') or ''),
                'activityStatus':  _activity_status(item),
                'startTime':       _fmt(su),
                'endTime':         _fmt(eu),
                'startUnix':       su,
                'endUnix':         eu,
                'seckillState':    str(item.get('seckill_state') or ''),
                'seckillImage':    str(item.get('seckill_image') or ''),
                'goodsUrl':        str(item.get('goods_url') or ''),
                'goodsIsOffline':  item.get('goods_is_offline') in ('1', 1, True),
                'homepageDisplay': item.get('homepage_display') in ('1', 1, True),
                'isFlashTitle':    '限时抢购' in title or '限时秒杀' in title,
            })

    by_status: Dict[str, int] = {}
    for r in rows:
        by_status[r['activityStatus']] = by_status.get(r['activityStatus'], 0) + 1

    payload = {
        'fetchedAt':  _fmt(int(datetime.now().timestamp())),
        'serverTime': _fmt(server_unix),
        'serverUnix': server_unix,
        'apiVersion': version,
        'apiFlag':    data.get('flag'),
        'apiMsg':     data.get('msg') or '',
        'count':      len(rows),
        'byStatus':   by_status,
        'groups': [
            {'title': g.get('title'), 'subTitle': g.get('sub_title'), 'count': len(g.get('lists') or [])}
            for g in data.get('data') or []
        ],
        'rows': rows,
    }

    result = sync_payload(payload, write_snapshot=write_snapshot)
    result['fetchedAt']   = payload['fetchedAt']
    result['serverTime']  = payload['serverTime']
    result['count']       = payload['count']
    result['byStatus']    = payload['byStatus']
    return result
