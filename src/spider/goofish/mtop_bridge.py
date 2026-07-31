"""在闲鱼页面上下文中直调 mtop 接口。

闲鱼卖家工作台全局加载了 lib-mtop（已验证），可直接复用页面里的登录态调接口，
比拦截 XHR 或抓 DOM 更确定：分页可控、不依赖点击 UI、不受 CSS 改版影响。
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from spider.goofish.config import SESSION_EXPIRED_CODES
from utils.logger import get_logger

logger = get_logger('GoofishMtop')

_HAS_MTOP_JS = """
() => !!(window.lib && window.lib.mtop && typeof window.lib.mtop.request === 'function')
"""

_CALL_JS = """
async (args) => {
  const lib = window.lib;
  if (!lib || !lib.mtop || typeof lib.mtop.request !== 'function') {
    return { ok: false, error: 'lib.mtop 不可用（页面可能未加载完成）' };
  }
  const req = { api: args.api, v: args.v || '1.0', data: args.data || {} };
  if (args.needLogin === false) req.ecode = 0;
  try {
    const res = await lib.mtop.request(req);
    return { ok: true, ret: (res && res.ret) || [], data: (res && res.data) != null ? res.data : null };
  } catch (e) {
    let ret = [];
    let data = null;
    if (e && typeof e === 'object') {
      if (Array.isArray(e.ret)) ret = e.ret;
      if (e.data != null) data = e.data;
    }
    return {
      ok: false,
      ret: ret,
      data: data,
      error: String((e && (e.message || e.msg)) || (ret.length ? ret[0] : e)),
    };
  }
}
"""


def has_mtop(frame) -> bool:
    """当前 frame 是否可用 lib.mtop。"""
    try:
        return bool(frame.evaluate(_HAS_MTOP_JS))
    except Exception:
        return False


def ret_is_success(ret: Any) -> bool:
    for item in ret or []:
        if 'SUCCESS' in str(item).upper():
            return True
    return False


def ret_is_session_expired(ret: Any) -> bool:
    joined = ' '.join(str(x) for x in (ret or [])).upper()
    if not joined:
        return False
    if 'SESSION' in joined and 'EXPIRED' in joined:
        return True
    return any(code.upper() in joined for code in SESSION_EXPIRED_CODES)


def call_mtop(
    frame,
    api: str,
    *,
    data: Optional[Dict[str, Any]] = None,
    version: str = '1.0',
    need_login: bool = True,
) -> Dict[str, Any]:
    """在 frame 上下文调用 mtop。

    Returns:
        { ok, ret, data, error?, sessionExpired }
    """
    payload = {
        'api': api,
        'v': version,
        'data': data or {},
        'needLogin': need_login,
    }
    try:
        result = frame.evaluate(_CALL_JS, payload)
    except Exception as exc:
        logger.warning('mtop 调用异常 api=%s err=%s', api, exc)
        return {'ok': False, 'ret': [], 'data': None, 'error': str(exc), 'sessionExpired': False}

    result = result or {}
    ret = result.get('ret') or []
    expired = ret_is_session_expired(ret)
    result['sessionExpired'] = expired
    if not result.get('ok'):
        logger.info('mtop 调用失败 api=%s ret=%s', api, ret)
    return result
