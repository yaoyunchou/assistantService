"""
安特 PC 商城 · 限时秒杀

POST /api/antexiadan/seckill-list/sync   webAuto 采集结果入库
GET  /api/antexiadan/seckill-list/products  查询当前态商品
GET  /api/antexiadan/seckill-list/batch/latest  最近一次抓取批次
"""
from flask import Blueprint, jsonify, request
from flasgger import swag_from

from spider.antexiadan.seckill_store import (
    get_latest_batch,
    list_products,
    sync_payload,
)
from utils.logger import get_logger

logger = get_logger('AntexiadanRoutes')
bp = Blueprint('antexiadan', __name__, url_prefix='/api/antexiadan')


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

    items = list_products(
        activity_status=activity_status,
        group_title=group_title,
        slot_time=slot_time,
        limit=limit,
        offset=offset,
    )
    return jsonify({'success': True, 'count': len(items), 'items': items})


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
