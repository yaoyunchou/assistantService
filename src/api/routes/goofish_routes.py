"""
闲鱼商品 API

GET  /api/goofish/login-status        检查卖家登录态
POST /api/goofish/open-publish       打开发布页（可见窗口）
POST /api/goofish/open-items         打开商品列表页（可见窗口）
GET  /api/goofish/pending            本地待发布队列
POST /api/goofish/publish            按 keyword / title 发布单条
POST /api/goofish/publish-next       发布队列第一条
POST /api/goofish/mark-uploaded      手动回填上架信息
POST /api/goofish/probe              探测后台真实 mtop 接口（补全 config）
GET  /api/goofish/items              在线商品列表
POST /api/goofish/items/<id>/online  上架
POST /api/goofish/items/<id>/offline 下架
POST /api/goofish/items/<id>/delete  删除（需 confirm=true）
POST /api/goofish/items/<id>/edit    编辑（改价 / 改描述）

约定：业务失败（未登录、选择器失效）返回 200 + { ok: false }，
避免前端把可预期的业务状态当成服务器异常。
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request
from flasgger import swag_from

from utils.logger import get_logger

logger = get_logger('GoofishRoutes')
bp = Blueprint('goofish', __name__, url_prefix='/api/goofish')

# 单条发布耗时上限；与登录等待时间叠加后作为 pool.execute 超时
PUBLISH_TIMEOUT_SEC = 600
LIST_TIMEOUT_SEC = 300
ACTION_TIMEOUT_SEC = 240
DEFAULT_WAIT_LOGIN_SEC = 180


def _pool():
    from api.routes.context import get_browser_pool
    return get_browser_pool()


def _no_pool():
    return jsonify({'ok': False, 'error': '浏览器池未初始化'}), 500


def _prepare_browser(pool, *, open_url: str | None = None):
    """闲鱼操作前切可见窗口并打开后台。

    BrowserPool 只有一个长驻 page（与拼多多/淘宝共用），因此每次都要显式导航。
    """
    from spider.goofish.browser_visible import prepare_goofish_browser
    return prepare_goofish_browser(pool, open_url=open_url)


def _wait_login_sec(body: dict) -> int:
    if not body.get('wait_for_login', True):
        return 0
    try:
        return int(body.get('wait_login_timeout_sec') or DEFAULT_WAIT_LOGIN_SEC)
    except (TypeError, ValueError):
        return DEFAULT_WAIT_LOGIN_SEC


def _publish_timeout(wait_login_sec: int) -> float:
    return float(PUBLISH_TIMEOUT_SEC + max(0, wait_login_sec))


# ── 登录与浏览器 ────────────────────────────────────────────

@bp.route('/login-status', methods=['GET'])
@swag_from({
    'tags': ['闲鱼'],
    'summary': '检查闲鱼卖家后台登录状态',
    'responses': {200: {'description': '登录状态'}, 500: {'description': '浏览器池未初始化'}},
})
def goofish_login_status():
    """用 mtop 探针判定登录态（不依赖 URL/DOM）"""
    try:
        pool = _pool()
        if not pool:
            return _no_pool()

        browser_info = _prepare_browser(pool)

        def _check(page):
            from spider.goofish.client import GoofishClient
            return GoofishClient(page=page).check_login()

        result = pool.execute(_check, timeout=120)
        return jsonify({'ok': True, 'browser': browser_info, **(result or {})}), 200
    except Exception as e:
        logger.error('[login-status] 异常: %s', e, exc_info=True)
        return jsonify({'ok': False, 'error': str(e)}), 500


@bp.route('/open-publish', methods=['POST'])
@swag_from({
    'tags': ['闲鱼'],
    'summary': '打开闲鱼发布页（可见 Chromium 窗口）',
    'responses': {200: {'description': '打开结果'}},
})
def goofish_open_publish():
    """打开发布页，供人工扫码登录"""
    try:
        pool = _pool()
        if not pool:
            return _no_pool()
        from spider.goofish.config import PUBLISH_URL
        return jsonify(_prepare_browser(pool, open_url=PUBLISH_URL)), 200
    except Exception as e:
        logger.error('[open-publish] 异常: %s', e, exc_info=True)
        return jsonify({'ok': False, 'error': str(e)}), 500


@bp.route('/open-items', methods=['POST'])
@swag_from({
    'tags': ['闲鱼'],
    'summary': '打开闲鱼商品列表页（可见 Chromium 窗口）',
    'responses': {200: {'description': '打开结果'}},
})
def goofish_open_items():
    """打开商品管理页"""
    try:
        pool = _pool()
        if not pool:
            return _no_pool()
        from spider.goofish.config import ITEM_LIST_URL
        return jsonify(_prepare_browser(pool, open_url=ITEM_LIST_URL)), 200
    except Exception as e:
        logger.error('[open-items] 异常: %s', e, exc_info=True)
        return jsonify({'ok': False, 'error': str(e)}), 500


# ── 本地队列与发布 ──────────────────────────────────────────

@bp.route('/pending', methods=['GET'])
@swag_from({
    'tags': ['闲鱼'],
    'summary': '本地待发布商品队列（有图且上架链接为空）',
    'responses': {200: {'description': '列表'}},
})
def goofish_pending():
    """读 Excel 汇总表，不需要浏览器"""
    try:
        from spider.goofish.client import GoofishClient
        items = GoofishClient().list_pending()
        return jsonify({'ok': True, 'count': len(items), 'items': items}), 200
    except FileNotFoundError as e:
        return jsonify({
            'ok': False,
            'items': [],
            'count': 0,
            'error': f'{e}。请先在数据目录创建汇总表',
        }), 200
    except Exception as e:
        logger.error('[pending] 异常: %s', e, exc_info=True)
        return jsonify({'ok': False, 'error': str(e)}), 500


def _run_publish(mode: str):
    pool = _pool()
    if not pool:
        return _no_pool()

    body = request.get_json(silent=True) or {}
    keyword = (body.get('keyword') or '').strip()
    title = (body.get('title') or '').strip()
    stop_after = (body.get('stop_after') or '').strip() or None
    wait_login_sec = _wait_login_sec(body)

    if mode == 'one' and not keyword and not title:
        return jsonify({'ok': False, 'error': '请提供 keyword 或 title'}), 400

    browser_info = _prepare_browser(pool)
    already_logged_in = bool(browser_info.get('logged_in'))

    def _run(page):
        from spider.goofish.client import GoofishClient
        client = GoofishClient(page=page)
        kwargs = {
            'stop_after': stop_after,
            'wait_login_timeout_sec': wait_login_sec,
            'skip_if_logged_in': already_logged_in,
        }
        if mode == 'next':
            return client.publish_next_pending(**kwargs)
        if title:
            return client.publish_by_title(title, **kwargs)
        return client.publish_by_keyword(keyword, **kwargs)

    result = pool.execute(_run, timeout=_publish_timeout(wait_login_sec)) or {}
    if not result.get('ok'):
        logger.warning(
            '[publish/%s] 未成功 step=%s msg=%s err=%s',
            mode, result.get('step'), result.get('message'), result.get('error'),
        )
    return jsonify({'browser': browser_info, **result}), 200


@bp.route('/publish', methods=['POST'])
@swag_from({
    'tags': ['闲鱼'],
    'summary': '发布指定商品',
    'parameters': [{
        'in': 'body',
        'name': 'body',
        'schema': {
            'type': 'object',
            'properties': {
                'keyword': {'type': 'string', 'description': '标题关键词'},
                'title': {'type': 'string', 'description': '完整标题（优先于 keyword）'},
                'stop_after': {'type': 'string', 'enum': ['upload', 'fill', 'submit'], 'description': '调试断点'},
                'wait_for_login': {'type': 'boolean', 'default': True},
                'wait_login_timeout_sec': {'type': 'integer', 'default': 180},
            },
        },
    }],
    'responses': {200: {'description': '执行结果'}},
})
def goofish_publish():
    """按 keyword / title 发布单条商品"""
    try:
        return _run_publish('one')
    except Exception as e:
        logger.error('[publish] 异常: %s', e, exc_info=True)
        return jsonify({'ok': False, 'error': str(e)}), 500


@bp.route('/publish-next', methods=['POST'])
@swag_from({
    'tags': ['闲鱼'],
    'summary': '发布待发布队列的第一条商品',
    'responses': {200: {'description': '执行结果'}},
})
def goofish_publish_next():
    """发布队列第一条"""
    try:
        return _run_publish('next')
    except Exception as e:
        logger.error('[publish-next] 异常: %s', e, exc_info=True)
        return jsonify({'ok': False, 'error': str(e)}), 500


@bp.route('/mark-uploaded', methods=['POST'])
@swag_from({
    'tags': ['闲鱼'],
    'summary': '手动回填上架信息（发布成功但未解析到商品 ID 时用）',
    'parameters': [{
        'in': 'body',
        'name': 'body',
        'schema': {
            'type': 'object',
            'required': ['title'],
            'properties': {
                'title': {'type': 'string'},
                'item_id': {'type': 'string'},
                'item_url': {'type': 'string'},
            },
        },
    }],
    'responses': {200: {'description': '回填结果'}},
})
def goofish_mark_uploaded():
    """手动写回上架链接，避免重复发布"""
    try:
        body = request.get_json(silent=True) or {}
        title = (body.get('title') or '').strip()
        item_id = (body.get('item_id') or '').strip()
        item_url = (body.get('item_url') or '').strip()
        if not title:
            return jsonify({'ok': False, 'error': '缺少 title'}), 400
        if not item_id and not item_url:
            return jsonify({'ok': False, 'error': '需提供 item_id 或 item_url'}), 400

        from spider.goofish.data.backfill import backfill_upload_result
        result = backfill_upload_result(title=title, item_id=item_id, item_url=item_url)
        return jsonify(result), 200
    except Exception as e:
        logger.error('[mark-uploaded] 异常: %s', e, exc_info=True)
        return jsonify({'ok': False, 'error': str(e)}), 500


# ── 接口探测 ────────────────────────────────────────────────

@bp.route('/probe', methods=['POST'])
@swag_from({
    'tags': ['闲鱼'],
    'summary': '探测闲鱼后台真实 mtop 接口（结果落盘，用于补全 config.ITEM_LIST_API）',
    'parameters': [{
        'in': 'body',
        'name': 'body',
        'schema': {
            'type': 'object',
            'properties': {
                'target_url': {'type': 'string', 'description': '默认商品列表页'},
                'wait_for_login': {'type': 'boolean', 'default': True},
                'scroll_steps': {'type': 'integer', 'default': 3},
            },
        },
    }],
    'responses': {200: {'description': '探测结果'}},
})
def goofish_probe():
    """登录态下捕获真实接口，补全未登录时无法取得的 API 名"""
    try:
        pool = _pool()
        if not pool:
            return _no_pool()

        body = request.get_json(silent=True) or {}
        target_url = (body.get('target_url') or '').strip() or None
        wait_login_sec = _wait_login_sec(body)
        try:
            scroll_steps = int(body.get('scroll_steps') or 3)
        except (TypeError, ValueError):
            scroll_steps = 3

        browser_info = _prepare_browser(pool, open_url=target_url)

        def _run(page):
            from spider.goofish.api_probe import probe_apis
            return probe_apis(
                page,
                target_url=target_url,
                wait_login_timeout_sec=wait_login_sec,
                scroll_steps=scroll_steps,
            )

        result = pool.execute(_run, timeout=float(LIST_TIMEOUT_SEC + wait_login_sec)) or {}
        return jsonify({'browser': browser_info, **result}), 200
    except Exception as e:
        logger.error('[probe] 异常: %s', e, exc_info=True)
        return jsonify({'ok': False, 'error': str(e)}), 500


# ── 在线商品管理 ────────────────────────────────────────────

@bp.route('/items', methods=['GET'])
@swag_from({
    'tags': ['闲鱼'],
    'summary': '在线商品列表（mtop 直调优先，DOM 兜底）',
    'parameters': [
        {'in': 'query', 'name': 'status', 'type': 'string', 'description': 'online / offline / sold'},
        {'in': 'query', 'name': 'page_size', 'type': 'integer', 'default': 40},
        {'in': 'query', 'name': 'max_pages', 'type': 'integer', 'default': 5},
    ],
    'responses': {200: {'description': '商品列表，source 字段标明取数路径'}},
})
def goofish_items():
    """拉取在线商品；返回体 source 标明走的是 mtop / capture / dom-fallback"""
    try:
        pool = _pool()
        if not pool:
            return _no_pool()

        status = (request.args.get('status') or '').strip()
        try:
            page_size = int(request.args.get('page_size') or 40)
            max_pages = int(request.args.get('max_pages') or 5)
        except (TypeError, ValueError):
            page_size, max_pages = 40, 5
        wait_login_sec = 0 if request.args.get('wait_for_login') == 'false' else DEFAULT_WAIT_LOGIN_SEC

        browser_info = _prepare_browser(pool)

        def _run(page):
            from spider.goofish.client import GoofishClient
            return GoofishClient(page=page).list_items(
                status=status,
                page_size=page_size,
                max_pages=max_pages,
                wait_login_timeout_sec=wait_login_sec,
            )

        result = pool.execute(_run, timeout=float(LIST_TIMEOUT_SEC + wait_login_sec)) or {}
        return jsonify({'browser': browser_info, **result}), 200
    except Exception as e:
        logger.error('[items] 异常: %s', e, exc_info=True)
        return jsonify({'ok': False, 'error': str(e), 'items': []}), 500


def _run_item_action(item_id: str, action: str):
    pool = _pool()
    if not pool:
        return _no_pool()

    body = request.get_json(silent=True) or {}
    # 上下架是可逆操作，默认直接执行；删除必须显式确认
    default_confirm = action != 'delete'
    confirm = bool(body.get('confirm', default_confirm))
    wait_login_sec = _wait_login_sec(body)

    browser_info = _prepare_browser(pool)

    def _run(page):
        from spider.goofish.client import GoofishClient
        return GoofishClient(page=page).run_item_action(
            item_id, action, confirm=confirm, wait_login_timeout_sec=wait_login_sec,
        )

    result = pool.execute(_run, timeout=float(ACTION_TIMEOUT_SEC + wait_login_sec)) or {}
    return jsonify({'browser': browser_info, **result}), 200


@bp.route('/items/<item_id>/online', methods=['POST'])
@swag_from({
    'tags': ['闲鱼'],
    'summary': '上架商品',
    'responses': {200: {'description': '执行结果'}},
})
def goofish_item_online(item_id):
    """重新上架"""
    try:
        return _run_item_action(item_id, 'online')
    except Exception as e:
        logger.error('[items/online] 异常: %s', e, exc_info=True)
        return jsonify({'ok': False, 'error': str(e)}), 500


@bp.route('/items/<item_id>/offline', methods=['POST'])
@swag_from({
    'tags': ['闲鱼'],
    'summary': '下架商品',
    'responses': {200: {'description': '执行结果'}},
})
def goofish_item_offline(item_id):
    """下架"""
    try:
        return _run_item_action(item_id, 'offline')
    except Exception as e:
        logger.error('[items/offline] 异常: %s', e, exc_info=True)
        return jsonify({'ok': False, 'error': str(e)}), 500


@bp.route('/items/<item_id>/delete', methods=['POST'])
@swag_from({
    'tags': ['闲鱼'],
    'summary': '删除商品（不可逆，必须传 confirm=true）',
    'parameters': [{
        'in': 'body',
        'name': 'body',
        'schema': {
            'type': 'object',
            'required': ['confirm'],
            'properties': {'confirm': {'type': 'boolean', 'description': '必须显式为 true'}},
        },
    }],
    'responses': {200: {'description': '执行结果'}},
})
def goofish_item_delete(item_id):
    """删除商品；未传 confirm=true 时拒绝执行"""
    try:
        return _run_item_action(item_id, 'delete')
    except Exception as e:
        logger.error('[items/delete] 异常: %s', e, exc_info=True)
        return jsonify({'ok': False, 'error': str(e)}), 500


@bp.route('/items/<item_id>/edit', methods=['POST'])
@swag_from({
    'tags': ['闲鱼'],
    'summary': '编辑商品（首期支持改价与改描述）',
    'parameters': [{
        'in': 'body',
        'name': 'body',
        'schema': {
            'type': 'object',
            'properties': {
                'price': {'type': 'string'},
                'description': {'type': 'string'},
            },
        },
    }],
    'responses': {200: {'description': '执行结果'}},
})
def goofish_item_edit(item_id):
    """改价 / 改描述"""
    try:
        pool = _pool()
        if not pool:
            return _no_pool()

        body = request.get_json(silent=True) or {}
        changes = {}
        if body.get('price') not in (None, ''):
            changes['price'] = body.get('price')
        if body.get('description'):
            changes['description'] = body.get('description')
        if not changes:
            return jsonify({'ok': False, 'error': '未提供要修改的字段（支持 price / description）'}), 400

        wait_login_sec = _wait_login_sec(body)
        browser_info = _prepare_browser(pool)

        def _run(page):
            from spider.goofish.client import GoofishClient
            return GoofishClient(page=page).edit_item(
                item_id, changes, wait_login_timeout_sec=wait_login_sec,
            )

        result = pool.execute(_run, timeout=float(ACTION_TIMEOUT_SEC + wait_login_sec)) or {}
        return jsonify({'browser': browser_info, **result}), 200
    except Exception as e:
        logger.error('[items/edit] 异常: %s', e, exc_info=True)
        return jsonify({'ok': False, 'error': str(e)}), 500
