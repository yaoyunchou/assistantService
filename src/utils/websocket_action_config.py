
map ={
    "pinduoduo-sync-orders": {
        "url": "http://127.0.0.1:8887/api/pinduoduo/execute",
        "method": "POST",
    },
    "tu-sync-orders": {
        "url": "http://127.0.0.1:8080/api/tu/execute",
        "method": "POST",
        "body": {},
    },
}

def execute_action(action_id):
    item = map.get(action_id)
    if not item.get('url'):
        return {'success': False, 'message': f'Action {action_id} not found'}
    try:
        import requests
        resp = requests.request(method=item.get('method'), url=item.get('url'), timeout=60)
        resp.raise_for_status()
        return {'success': True, 'message': f'Action {action_id} executed successfully'}
    except Exception as e:
        return {'success': False, 'message': f'Action {action_id} failed: {e}'}
    return {'success': True, 'message': f'Action {action_id} executed successfully'}