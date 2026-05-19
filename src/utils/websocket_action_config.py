"""WebSocket ``action`` 事件：action_id → 本机 HTTP 调用（与 Socket.IO 对接）。"""


def _assistant_http_base() -> str:
    """本机如意助手 HTTP 根（与 assistant_http 相对 URL 拼接一致）。"""
    try:
        from utils.assistant_http_invoke import get_assistant_http_origin

        return get_assistant_http_origin().rstrip('/')
    except Exception:
        return 'http://127.0.0.1:8887'


def _action_definitions() -> dict:
    base = _assistant_http_base()
    return {
        'pinduoduo-sync-orders': {
            'url': f'{base}/api/pinduoduo/execute',
            'method': 'POST',
            'timeout': 120,
        },
        'pinduoduo-presell-collect': {
            'url': f'{base}/api/pinduoduo/erp-presell/collect',
            'method': 'POST',
            'json': {},
            'timeout': 600,
        },
        'tu-sync-orders': {
            'url': 'http://127.0.0.1:8080/api/tu/execute',
            'method': 'POST',
            'timeout': 60,
        },
    }


def execute_action(action_id):
    item = _action_definitions().get(action_id)
    if not item or not item.get('url'):
        return {'success': False, 'message': f'Action {action_id} not found'}
    try:
        import requests

        timeout = float(item.get('timeout', 60))
        kwargs: dict = {
            'method': item.get('method') or 'POST',
            'url': item['url'],
            'timeout': timeout,
        }
        if 'json' in item:
            kwargs['json'] = item['json']
        resp = requests.request(**kwargs)
        resp.raise_for_status()
        return {'success': True, 'message': f'Action {action_id} executed successfully'}
    except Exception as e:
        return {'success': False, 'message': f'Action {action_id} failed: {e}'}
