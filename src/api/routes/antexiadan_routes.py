"""
安特 PC 商城 · 限时秒杀

POST /api/antexiadan/seckill-list/fetch          服务端直连 pcapi（需 ANTEXI_API_KEY）
POST /api/antexiadan/seckill-list/fetch-browser  浏览器拦截请求自动获取 key 并入库
POST /api/antexiadan/seckill-list/sync           webAuto 采集结果入库
GET  /api/antexiadan/seckill-list/products       查询当前态商品
GET  /api/antexiadan/seckill-list/batch/latest   最近一次抓取批次
POST /api/antexiadan/goods-search/fetch-browser  浏览器搜索商品并写入 antexiadan_goods_search
GET  /api/antexiadan/goods-search                按 keyword 查本地缓存
"""
from flask import Blueprint, jsonify, request
from flasgger import swag_from

from api.routes.context import get_browser_pool
from spider.antexiadan.goods_search import ensure_goods_search
from spider.antexiadan.goods_search_store import get_by_keyword, init_db, list_records, serialize_row
from spider.antexiadan.seckill_store import (
    fetch_and_sync,
    get_latest_batch,
    list_presale_active_unmarked,
    list_products,
    sync_payload,
)
from utils.logger import get_logger

logger = get_logger('AntexiadanRoutes')
bp = Blueprint('antexiadan', __name__, url_prefix='/api/antexiadan')


@bp.route('/seckill-list/fetch-browser', methods=['POST'])
@swag_from({
    'tags': ['安特'],
    'summary': '通过浏览器自动采集（无需手动复制 key）',
    'parameters': [{
        'in': 'body', 'name': 'body', 'required': False,
        'schema': {'type': 'object', 'properties': {
            'writeSnapshot': {'type': 'boolean', 'default': True},
        }},
    }],
    'responses': {200: {'description': '采集并入库结果'}},
})
def seckill_list_fetch_browser():
    """用浏览器打开首页，自动拦截 seckill-list 请求提取 key，再直连 pcapi 入库。"""
    from urllib.parse import urlparse, parse_qs

    data = request.get_json(silent=True) or {}
    write_snapshot = data.get('writeSnapshot', True)
    if isinstance(write_snapshot, str):
        write_snapshot = write_snapshot.lower() not in ('0', 'false', 'no')

    pool = get_browser_pool()
    if not pool:
        return jsonify({'success': False, 'ok': False, 'error': '浏览器池未初始化'}), 500

    def _capture_key(page):
        captured = {}

        def on_request(req):
            if 'seckill-list' in req.url and not captured.get('key'):
                try:
                    qs = parse_qs(urlparse(req.url).query)
                    k = (qs.get('key') or [None])[0]
                    if k:
                        captured['key'] = k
                        logger.info('安特：拦截到 seckill-list key（长度 %d）', len(k))
                except Exception:
                    pass

        page.on('request', on_request)
        try:
            page.goto('https://pc.antexiadan.com/homepage',
                      wait_until='domcontentloaded', timeout=60_000)
        except Exception:
            pass
        # 等待请求触发，最多 10 秒
        for _ in range(20):
            if captured.get('key'):
                break
            page.wait_for_timeout(500)

        page.remove_listener('request', on_request)
        return captured.get('key', '')

    try:
        api_key = pool.execute(_capture_key, timeout=90)
    except Exception as e:
        return jsonify({'success': False, 'ok': False, 'error': f'浏览器执行异常: {e}'}), 500

    if not api_key:
        return jsonify({
            'success': False, 'ok': False,
            'error': '未能从浏览器拦截到 seckill-list 请求，请确认已登录 pc.antexiadan.com',
        }), 400

    result = fetch_and_sync(api_key=api_key, write_snapshot=bool(write_snapshot))
    status = 200 if result.get('ok') else 500
    if result.get('ok'):
        logger.info('浏览器采集入库: batchId=%s upserted=%s', result.get('batchId'), result.get('upserted'))
    else:
        logger.warning('浏览器采集失败: %s', result.get('error'))
    return jsonify({'success': result.get('ok', False), **result}), status


@bp.route('/seckill-list/fetch', methods=['POST'])
@swag_from(
    {
        'tags': ['安特'],
        'summary': '服务端直拉 pcapi 并入库',
        'parameters': [
            {
                'in': 'body',
                'name': 'body',
                'required': False,
                'schema': {
                    'type': 'object',
                    'properties': {
                        'apiKey':        {'type': 'string', 'description': '可选，覆盖 .env ANTEXI_API_KEY'},
                        'writeSnapshot': {'type': 'boolean', 'default': True},
                    },
                },
            }
        ],
        'responses': {200: {'description': '采集并入库结果'}},
    }
)
def seckill_list_fetch():
    """直连 pcapi 拉取秒杀列表并入库，无需浏览器。"""
    data = request.get_json(silent=True) or {}
    api_key = str(data.get('apiKey') or '').strip()
    write_snapshot = data.get('writeSnapshot', True)
    if isinstance(write_snapshot, str):
        write_snapshot = write_snapshot.lower() not in ('0', 'false', 'no')

    result = fetch_and_sync(api_key=api_key, write_snapshot=bool(write_snapshot))
    status = 200 if result.get('ok') else 500
    if result.get('ok'):
        logger.info('秒杀采集入库: batchId=%s upserted=%s count=%s',
                    result.get('batchId'), result.get('upserted'), result.get('count'))
    else:
        logger.warning('秒杀采集失败: %s', result.get('error'))
    return jsonify({'success': result.get('ok', False), **result}), status


@bp.route('/seckill-list/sync', methods=['POST'])
@swag_from(
    {
        'tags': ['安特'],
        'summary': '限时秒杀列表同步入库',
        'parameters': [
            {
                'in': 'body',
                'name': 'body',
                'required': True,
                'schema': {
                    'type': 'object',
                    'properties': {
                        'fetchedAt': {'type': 'string'},
                        'serverTime': {'type': 'string'},
                        'rows': {'type': 'array', 'items': {'type': 'object'}},
                        'writeSnapshot': {'type': 'boolean'},
                    },
                },
            }
        ],
        'responses': {200: {'description': '同步结果'}},
    }
)
def seckill_list_sync():
    """接收 webAuto antexiadan-seckill-list.js / antexiadan-seckill-fetch.py 的 POST body。"""
    data = request.get_json(silent=True) or {}
    rows = data.get('rows')
    if not isinstance(rows, list):
        return jsonify({'success': False, 'ok': False, 'error': '缺少 rows 数组'}), 400

    write_snapshot = data.get('writeSnapshot', True)
    if isinstance(write_snapshot, str):
        write_snapshot = write_snapshot.lower() not in ('0', 'false', 'no')

    result = sync_payload(data, write_snapshot=bool(write_snapshot))
    status = 200 if result.get('ok') else 500
    logger.info(
        '秒杀同步: ok=%s batchId=%s upserted=%s',
        result.get('ok'),
        result.get('batchId'),
        result.get('upserted'),
    )
    return jsonify({'success': result.get('ok', False), **result}), status


@bp.route('/seckill-list/products', methods=['GET'])
@swag_from(
    {
        'tags': ['安特'],
        'summary': '查询秒杀商品当前态',
        'parameters': [
            {'name': 'activity_status', 'in': 'query', 'type': 'string'},
            {'name': 'group_title', 'in': 'query', 'type': 'string'},
            {'name': 'slot_time', 'in': 'query', 'type': 'string'},
            {
                'name': 'exclude_offline',
                'in': 'query',
                'type': 'boolean',
                'description': 'true 时排除 goods_is_offline=1（平台已标记下架）',
            },
            {
                'name': 'presale_active',
                'in': 'query',
                'type': 'boolean',
                'description': 'true 时等价于 activity_status=预热/待开始 且 group_title=预热中',
            },
            {'name': 'limit', 'in': 'query', 'type': 'integer', 'default': 500},
            {'name': 'offset', 'in': 'query', 'type': 'integer', 'default': 0},
        ],
        'responses': {200: {'description': '商品列表'}},
    }
)
def seckill_list_products():
    activity_status = request.args.get('activity_status')
    group_title = request.args.get('group_title')
    slot_time = request.args.get('slot_time')
    limit = min(int(request.args.get('limit', 500)), 2000)
    offset = max(int(request.args.get('offset', 0)), 0)
    exclude_offline = str(request.args.get('exclude_offline', '')).lower() in ('1', 'true', 'yes')
    presale_active = str(request.args.get('presale_active', '')).lower() in ('1', 'true', 'yes')

    if presale_active:
        activity_status = activity_status or '预热/待开始'
        group_title = group_title or '预热中'

    items = list_products(
        activity_status=activity_status,
        group_title=group_title,
        slot_time=slot_time,
        exclude_offline=exclude_offline,
        limit=limit,
        offset=offset,
    )
    return jsonify({'success': True, 'count': len(items), 'items': items})


@bp.route('/seckill-list/products/presale-active-unmarked', methods=['GET'])
@swag_from(
    {
        'tags': ['安特'],
        'summary': '正在预售且未标记下架的商品',
        'description': (
            '返回 activity_status=预热/待开始、group_title=预热中、goods_is_offline=0 的商品。'
            '「预告」分组或已下架商品不在结果内。'
        ),
        'parameters': [
            {'name': 'limit', 'in': 'query', 'type': 'integer', 'default': 500},
            {'name': 'offset', 'in': 'query', 'type': 'integer', 'default': 0},
        ],
        'responses': {200: {'description': '商品列表'}},
    }
)
def seckill_list_products_presale_active_unmarked():
    limit = min(int(request.args.get('limit', 500)), 2000)
    offset = max(int(request.args.get('offset', 0)), 0)
    items = list_presale_active_unmarked(limit=limit, offset=offset)
    return jsonify({
        'success': True,
        'count': len(items),
        'filter': {
            'activity_status': '预热/待开始',
            'group_title': '预热中',
            'exclude_offline': True,
        },
        'items': items,
    })


@bp.route('/seckill-list/batch/latest', methods=['GET'])
@swag_from(
    {
        'tags': ['安特'],
        'summary': '最近一次秒杀抓取批次',
        'responses': {200: {'description': '批次信息'}},
    }
)
def seckill_list_batch_latest():
    batch = get_latest_batch()
    return jsonify({'success': True, 'batch': batch})


@bp.route('/goods-search/fetch-browser', methods=['POST'])
@swag_from({
    'tags': ['安特'],
    'summary': '浏览器搜索安特商品并写入 antexiadan_goods_search',
    'parameters': [{
        'in': 'body', 'name': 'body', 'required': True,
        'schema': {'type': 'object', 'properties': {
            'keyword': {'type': 'string', 'description': '搜索词，如 120002 / 008312'},
            'forceRefresh': {'type': 'boolean', 'default': False},
        }},
    }],
    'responses': {200: {'description': '搜索并入库结果'}},
})
def goods_search_fetch_browser():
    """已登录浏览器拦截 pcapi key，调用 search-goods-list 并 UPSERT。"""
    data = request.get_json(silent=True) or {}
    keyword = str(data.get('keyword') or '').strip()
    if not keyword:
        return jsonify({'success': False, 'ok': False, 'error': '缺少 keyword'}), 400

    force_refresh = data.get('forceRefresh', False)
    if isinstance(force_refresh, str):
        force_refresh = force_refresh.lower() not in ('0', 'false', 'no')

    pool = get_browser_pool()
    if not pool:
        return jsonify({'success': False, 'ok': False, 'error': '浏览器池未初始化'}), 500

    try:
        init_db()
    except Exception as e:
        logger.warning('goods_search init_db: %s', e)

    result = ensure_goods_search(
        keyword,
        browser_pool=pool,
        force_refresh=bool(force_refresh),
    )
    ok = bool(result.get('ok'))
    status = 200 if ok else (400 if result.get('error') else 500)
    if ok:
        logger.info('商品搜索入库 keyword=%s fromCache=%s', keyword, result.get('fromCache'))
    else:
        logger.warning('商品搜索失败 keyword=%s: %s', keyword, result.get('error'))
    return jsonify({'success': ok, 'ok': ok, **result}), status


@bp.route('/goods-search', methods=['GET'])
@swag_from({
    'tags': ['安特'],
    'summary': '查询 antexiadan_goods_search 本地缓存',
    'parameters': [
        {'name': 'keyword', 'in': 'query', 'type': 'string'},
        {'name': 'keyword_like', 'in': 'query', 'type': 'string'},
        {'name': 'limit', 'in': 'query', 'type': 'integer', 'default': 100},
        {'name': 'offset', 'in': 'query', 'type': 'integer', 'default': 0},
    ],
    'responses': {200: {'description': '缓存记录'}},
})
def goods_search_query():
    keyword = str(request.args.get('keyword') or '').strip()
    if keyword:
        row = get_by_keyword(keyword)
        return jsonify({
            'success': True,
            'found': bool(row),
            'item': serialize_row(row),
        })

    keyword_like = request.args.get('keyword_like')
    limit = min(int(request.args.get('limit', 100)), 500)
    offset = max(int(request.args.get('offset', 0)), 0)
    items = list_records(keyword_like=keyword_like, limit=limit, offset=offset)
    return jsonify({
        'success': True,
        'count': len(items),
        'items': [serialize_row(r) for r in items],
    })
