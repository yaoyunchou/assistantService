"""
途强物联网平台自动化客户端
负责自动登录、状态管理、最近 30 天记录获取等核心功能
"""
import json
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout
from config import Config
from utils.logger import get_logger
from utils.path_helper import get_safe_data_path
from spider.tu.feishutable import sync_tu_data_to_feishu

logger = get_logger('TuClient')


class TuClient:
    """途强物联网平台自动化客户端（账号密码自动登录）"""

    # 登录页 / 首页
    BASE_URL = 'https://iot.tqiot.com'
    LOGIN_OR_INDEX = 'https://iot.tqiot.com/'
    TARGET_URL = 'https://iot.tqiot.com/#/?to=reportDown'

    def __init__(self, page: Optional[Page] = None):
        self.page = page
        self.status_path = self._get_status_path()
        self.target_url = getattr(Config, 'TU_TARGET_URL', None) or self.TARGET_URL
        self.account = getattr(Config, 'TU_ACCOUNT', '') or ''
        self.password = getattr(Config, 'TU_PASSWORD', '') or ''
        self.status_path.parent.mkdir(parents=True, exist_ok=True)

    def _get_status_path(self) -> Path:
        path = getattr(Config, 'TU_STATUS_PATH', None)
        if path is None:
            return get_safe_data_path('tu/tu_status.json')
        p = Path(path)
        return p if p.is_absolute() else get_safe_data_path(path)

    def set_page(self, page: Page):
        self.page = page

    def _is_login_intercepted(self) -> bool:
        """
        检测当前页面是否被登录拦截。
        只有同时存在「账号/手机输入框」和「密码输入框」时才判定为登录页，
        避免把报表页的搜索/筛选框误判为登录框导致误填账号密码报错。
        """
        if not self.page:
            return False
        account_selectors = [
            'input[placeholder*="手机"]',
            'input[placeholder*="账号"]',
            'input[name="phone"]',
            'input[name="username"]',
            'input[name="account"]',
        ]
        pwd_selectors = [
            'input[type="password"]',
            'input[placeholder*="密码"]',
            'input[name="password"]',
        ]
        has_account = False
        for sel in account_selectors:
            try:
                if self.page.locator(sel).first.count() > 0:
                    has_account = True
                    break
            except Exception:
                continue
        if not has_account:
            return False
        for sel in pwd_selectors:
            try:
                if self.page.locator(sel).first.count() > 0:
                    return True
            except Exception:
                continue
        return False

    def _do_login_on_current_page(self) -> bool:
        """在当前页面（如 reportDown 被拦截时的登录框）执行账号密码登录。返回是否成功。"""
        if not self.page:
            return False
        if not self.account or not self.password:
            logger.warning("未配置途强账号或密码（TU_ACCOUNT / TU_PASSWORD），无法自动登录")
            return False
        try:
            account_selectors = [
                'input[placeholder*="手机"]',
                'input[placeholder*="账号"]',
                'input[name="phone"]',
                'input[name="username"]',
                'input[name="account"]',
                'input[type="text"]',
            ]
            pwd_selectors = [
                'input[type="password"]',
                'input[placeholder*="密码"]',
                'input[name="password"]',
            ]
            btn_selectors = [
                'button:has-text("登录")',
                'button:has-text("登 录")',
                'a:has-text("登录")',
                'button[type="submit"]',
                '.login-btn',
                '[class*="login"] button',
            ]

            account_el = None
            for sel in account_selectors:
                try:
                    loc = self.page.locator(sel).first
                    if loc.count() > 0 and loc.is_visible():
                        account_el = loc
                        logger.info(f"找到账号输入框: {sel}")
                        break
                except Exception:
                    continue
            if not account_el:
                logger.warning("未找到可见的账号输入框")
                return False

            pwd_el = None
            for sel in pwd_selectors:
                try:
                    loc = self.page.locator(sel).first
                    if loc.count() > 0 and loc.is_visible():
                        pwd_el = loc
                        logger.info(f"找到密码输入框: {sel}")
                        break
                except Exception:
                    continue
            if not pwd_el:
                logger.warning("未找到可见的密码输入框")
                return False

            # 先清空再逐字输入，更好地触发前端框架的事件监听
            account_el.click()
            time.sleep(0.2)
            account_el.fill('')
            account_el.type(self.account, delay=50)
            logger.info(f"已输入账号: {self.account[:3]}***")
            time.sleep(0.3)

            pwd_el.click()
            time.sleep(0.2)
            pwd_el.fill('')
            pwd_el.type(self.password, delay=50)
            logger.info("已输入密码")
            time.sleep(0.5)

            clicked = False
            for sel in btn_selectors:
                try:
                    btn = self.page.locator(sel).first
                    if btn.count() > 0 and btn.is_visible():
                        btn.click(timeout=3000)
                        logger.info(f"已点击登录按钮: {sel}")
                        clicked = True
                        break
                except Exception:
                    continue
            if not clicked:
                logger.info("未找到登录按钮，尝试按回车提交")
                pwd_el.press('Enter')

            # 等待页面跳转（给多一些时间，有些登录较慢）
            time.sleep(5)

            # 多检测几次（等待可能的页面跳转动画）
            for check in range(3):
                if not self._is_login_intercepted():
                    logger.info("登录成功！")
                    return True
                time.sleep(2)

            logger.warning("提交后仍为登录页，可能账号密码错误或需验证码")
            # 尝试截图保存以便调试
            try:
                from utils.path_helper import get_safe_data_path
                screenshot_path = get_safe_data_path('cache/tu_login_failed.png')
                self.page.screenshot(path=str(screenshot_path))
                logger.info(f"登录失败截图已保存: {screenshot_path}")
            except Exception:
                pass
            return False
        except Exception as e:
            logger.error(f"登录过程异常: {e}", exc_info=True)
            return False

    def wait_for_manual_login(self, url: Optional[str] = None, timeout: int = 300) -> Dict[str, Any]:
        """
        打开登录页面，等待用户手动登录。

        适用场景：自动登录失败（验证码等），需要用户手动在浏览器窗口中完成登录。
        登录成功后 Cookie 会自动保存到持久化缓存，后续操作无需再次登录。

        Args:
            url: 登录页面 URL（默认使用途强首页）
            timeout: 最长等待时间（秒），默认5分钟

        Returns:
            {'success': True/False, 'message': ...}
        """
        if not self.page:
            return {"success": False, "message": "Page 未设置"}

        target = url or self.LOGIN_OR_INDEX
        try:
            self.page.bring_to_front()
        except Exception:
            pass

        logger.info(f"打开登录页面: {target}，等待手动登录（最多 {timeout} 秒）...")
        self.page.goto(target, wait_until='domcontentloaded', timeout=30000)

        try:
            self.page.wait_for_load_state('networkidle', timeout=15000)
        except Exception:
            pass

        # 如果已经登录了，直接返回
        if not self._is_login_intercepted():
            return {"success": True, "message": "已处于登录状态，无需重新登录"}

        logger.info("请在浏览器窗口中手动登录...")
        start = time.time()
        while time.time() - start < timeout:
            time.sleep(3)
            try:
                if not self._is_login_intercepted():
                    logger.info("检测到登录成功！Cookie 已缓存。")
                    return {"success": True, "message": "登录成功！Cookie 已保存，后续操作无需再次登录。"}
            except Exception:
                pass

        return {"success": False, "message": f"等待 {timeout} 秒后仍未检测到登录，请重试"}

    def execute_automation(self, url: Optional[str] = None) -> Dict[str, Any]:
        """
        每次执行：1. 先挂好 XHR 拦截  2. 打开 reportDown 页面（加载时 XHR 被拦截拿到 authorization）
        3. 若被登录拦截则登录后重新打开  4. 用拿到的 authorization 执行 fetch 获取 30 天数据。
        """
        if not self.page:
            return {"success": False, "message": "Page 未设置"}

        target = url or self.target_url
        captured_auth: List[Optional[str]] = [None]

        def on_request(request):
            if request.resource_type not in ('xhr', 'fetch'):
                return
            if 'iot.tqiot.com/api/saas-iot' not in request.url:
                return
            auth = (request.headers.get('authorization') or request.headers.get('Authorization') or '').strip()
            if auth and (auth.startswith('Bearer ') or auth.startswith('bearer ')):
                captured_auth[0] = auth
                logger.info("已从 XHR 拦截到 Authorization")

        try:
            try:
                self.page.bring_to_front()
            except Exception:
                pass
            # 1. 先挂拦截，再打开页面（这样页面加载时的 XHR 才会被拦到）
            self.page.on('request', on_request)
            logger.info(f"打开页面: {target}")
            self.page.goto(target, wait_until='domcontentloaded', timeout=30000)
            # 强制刷新，确保触发页面加载时的 XHR 请求（特别是 SPA 页面 hash 路由可能不触发刷新）
            try:
                self.page.reload(wait_until='domcontentloaded', timeout=30000)
            except Exception as e:
                logger.warning(f"刷新页面失败: {e}")
            
            try:
                self.page.wait_for_load_state('networkidle', timeout=15000)
            except Exception:
                pass
            time.sleep(3)

            # 2. 若被登录拦截则登录，再重新打开页面（拦截仍在，会再拦到 XHR）
            if self._is_login_intercepted():
                logger.info("检测到登录拦截，执行自动登录...")
                if not self._do_login_on_current_page():
                    self._save_execution_status(success=False, message="登录失败")
                    return {"success": False, "message": "自动登录失败，请检查账号密码或页面是否变更"}
                self.page.goto(target, wait_until='domcontentloaded', timeout=30000)
                # 登录后再次强制刷新，确保触发数据请求
                try:
                    self.page.reload(wait_until='domcontentloaded', timeout=30000)
                except Exception:
                    pass

                try:
                    self.page.wait_for_load_state('networkidle', timeout=15000)
                except Exception:
                    pass
                time.sleep(3)

            token = captured_auth[0]
            if not token:
                self._save_execution_status(success=False, message="未拦截到 Authorization")
                return {
                    "success": False,
                    "message": "未拦截到带 Authorization 的 XHR，请确保已登录且页面有请求途强接口",
                    "records_result": {"success": False, "message": "未拦截到 Authorization", "records": []},
                }

            # 3. 用拦截到的 authorization 执行 fetch 获取 30 天数据
            records_result = self._fetch_30_days_with_token(token)
            self._save_execution_status(
                success=records_result.get('success', False),
                message=records_result.get('message', ''),
            )
            feishu_sync_result = None
            if records_result.get('success') and records_result.get('records'):
                try:
                    feishu_sync_result = sync_tu_data_to_feishu(records_result['records'])
                    logger.info(f"飞书同步结果: {feishu_sync_result.get('message', '')}")
                except Exception as e:
                    logger.warning(f"同步到飞书表格失败: {e}", exc_info=True)
                    feishu_sync_result = {"success": False, "message": str(e)}
            return {
                "success": records_result.get('success', False),
                "message": records_result.get('message', ''),
                "records_result": records_result,
                "feishu_sync": feishu_sync_result,
            }
        except PlaywrightTimeout:
            logger.error("页面加载超时")
            self._save_execution_status(success=False, message="页面加载超时")
            return {"success": False, "message": "页面加载超时"}
        except Exception as e:
            logger.error(f"执行失败: {e}", exc_info=True)
            self._save_execution_status(success=False, message=str(e))
            return {"success": False, "message": f"执行失败: {str(e)}"}

    def _fetch_30_days_with_token(self, authorization: str) -> Dict[str, Any]:
        """用已拿到的 authorization 执行 fetch 获取最近 30 天数据（只动态传时间）。"""
        if not self.page:
            return {"success": False, "message": "Page 未设置", "records": []}

        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        start_str = start_date.strftime('%Y-%m-%d')
        end_str = end_date.strftime('%Y-%m-%d')
        from_time = f"{start_str} 00:00:00"
        to_time = f"{end_str} 23:59:59"

        device_id = (getattr(Config, "TU_DEVICE_ID", None) or "").strip()
        if not device_id:
            return {"success": False, "message": "请配置 TU_DEVICE_ID", "records": []}

        try:
            result = self.page.evaluate(
                """async ({ fromTime, toTime, deviceId, authorization }) => {
                    const res = await fetch("https://iot.tqiot.com/api/saas-iot/web/v1/locator/segment/find", {
                        method: "POST",
                        headers: {
                            "accept": "application/json, text/plain, */*",
                            "authorization": authorization,
                            "content-type": "application/json",
                            "language": "zh-CN",
                            "platform": "web"
                        },
                        body: JSON.stringify({
                            deviceId: deviceId,
                            fromTime: fromTime,
                            toTime: toTime,
                            type: "2"
                        }),
                        credentials: "include"
                    });
                    const data = await res.json();
                    return { ok: res.ok, status: res.status, data };
                }""",
                {
                    "fromTime": from_time,
                    "toTime": to_time,
                    "deviceId": device_id,
                    "authorization": authorization,
                },
            )
        except Exception as e:
            logger.error(f"获取记录异常: {e}", exc_info=True)
            return {"success": False, "message": str(e), "records": []}

        if not result.get("ok"):
            msg = result.get("data") or {}
            if isinstance(msg, dict):
                msg = msg.get("message") or msg.get("msg") or str(msg)
            else:
                msg = str(msg)
            return {"success": False, "message": f"接口错误: {msg}", "records": []}

        data = result.get("data") or {}
        if not isinstance(data, dict):
            return {"success": False, "message": "接口返回格式异常", "records": []}

        all_records: List[Any] = []
        for key in ("data", "result", "list", "records", "items", "pageList"):
            if key in data and isinstance(data[key], list):
                all_records.extend(data[key])
                break
        if not all_records and isinstance(data.get("result"), dict):
            for k in ("list", "data", "records", "items", "pageList"):
                if k in data["result"] and isinstance(data["result"][k], list):
                    all_records.extend(data["result"][k])
                    break

        seen = set()
        unique = []
        for r in all_records:
            key = json.dumps(r, sort_keys=True, ensure_ascii=False)
            if key not in seen:
                seen.add(key)
                unique.append(r)

        cache_path = self._get_records_cache_path()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "fetch_time": datetime.now().isoformat(),
            "start_date": start_str,
            "end_date": end_str,
            "days": 30,
            "device_id": device_id,
            "records": unique,
            "total": len(unique),
        }
        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"写入缓存失败: {e}")

        return {
            "success": True,
            "message": f"已获取最近 30 天记录共 {len(unique)} 条",
            "total": len(unique),
            "cache_path": str(cache_path),
            "records": unique,
        }

    def _get_records_cache_path(self) -> Path:
        return get_safe_data_path('cache/tu_report_recent_30d.json')

    def _save_execution_status(self, success: bool, message: str):
        try:
            if self.status_path.exists():
                with open(self.status_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            else:
                data = {
                    "last_success": None,
                    "last_failure": None,
                    "last_execution": None,
                    "status": "unknown",
                    "message": "",
                }
            now = datetime.now().isoformat()
            data["last_execution"] = now
            data["status"] = "success" if success else "failed"
            data["last_success"] = now if success else data.get("last_success")
            data["last_failure"] = now if not success else data.get("last_failure")
            data["message"] = message
            self.status_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.status_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存状态失败: {e}", exc_info=True)

    def get_last_execution_status(self) -> Dict[str, Any]:
        if not self.status_path.exists():
            return {
                "last_success": None,
                "last_failure": None,
                "last_execution": None,
                "status": "unknown",
                "message": "尚未执行过",
            }
        try:
            with open(self.status_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"读取状态失败: {e}")
            return {
                "last_success": None,
                "last_failure": None,
                "last_execution": None,
                "status": "error",
                "message": str(e),
            }
