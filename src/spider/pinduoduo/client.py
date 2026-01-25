"""
拼多多自动化客户端
负责Cookie管理、登录检测、自动化执行等核心功能
"""
import json
import time
import base64
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
from playwright.sync_api import Page, Browser, BrowserContext, TimeoutError
from config import Config
from utils.logger import get_logger
from utils.path_helper import get_safe_data_path
from tools.feishu.message_sender import get_message_sender

logger = get_logger('PinduoduoClient')


class PinduoduoClient:
    """拼多多自动化客户端"""
    
    def __init__(self, page: Optional[Page] = None):
        """
        初始化拼多多客户端
        
        Args:
            page: Playwright Page对象，如果不提供则需要后续设置
        """
        self.page = page
        self.cookie_path = self._get_cookie_path()
        self.status_path = self._get_status_path()
        self.target_url = Config.PINDUODUO_TARGET_URL
        self._feishu_sender = None  # 延迟初始化
        
        # 确保cookies目录存在
        self.cookie_path.parent.mkdir(parents=True, exist_ok=True)
    
    @property
    def feishu_sender(self):
        """
        获取飞书消息发送器（延迟初始化）
        
        Returns:
            FeishuMessageSender实例
        """
        if self._feishu_sender is None:
            self._feishu_sender = get_message_sender()
        return self._feishu_sender
    
    def _get_cookie_path(self) -> Path:
        """
        获取Cookie文件路径
        使用安全的数据目录，避免权限问题
        """
        cookie_path = Config.PINDUODUO_COOKIE_PATH
        if cookie_path is None:
            # 使用默认的用户数据目录
            return get_safe_data_path('cookies/pinduoduo_cookies.json')
        elif Path(cookie_path).is_absolute():
            return Path(cookie_path)
        else:
            # 相对路径，使用安全路径处理
            return get_safe_data_path(cookie_path)
    
    def _get_status_path(self) -> Path:
        """
        获取状态文件路径
        使用安全的数据目录，避免权限问题
        """
        status_path = Config.PINDUODUO_STATUS_PATH
        if status_path is None:
            # 使用默认的用户数据目录
            return get_safe_data_path('cookies/pinduoduo_status.json')
        elif Path(status_path).is_absolute():
            return Path(status_path)
        else:
            # 相对路径，使用安全路径处理
            return get_safe_data_path(status_path)
    
    def set_page(self, page: Page):
        """
        设置Playwright Page对象
        
        Args:
            page: Playwright Page对象
        """
        self.page = page
    
    def load_cookies(self) -> bool:
        """
        从文件加载Cookie并注入到浏览器上下文
        
        Returns:
            是否加载成功
        """
        if not self.page:
            logger.error("Page对象未设置，无法加载Cookie")
            return False
        
        if not self.cookie_path.exists():
            logger.info(f"Cookie文件不存在: {self.cookie_path}")
            return False
        
        try:
            with open(self.cookie_path, 'r', encoding='utf-8') as f:
                cookie_data = json.load(f)
            
            cookies = cookie_data.get('cookies', [])
            if not cookies:
                logger.warning("Cookie文件中没有Cookie数据")
                return False
            
            # 注入Cookie到当前上下文
            context = self.page.context
            context.add_cookies(cookies)
            
            logger.info(f"成功加载Cookie，共{len(cookies)}个")
            return True
        
        except json.JSONDecodeError as e:
            logger.error(f"Cookie文件格式错误: {e}")
            return False
        except Exception as e:
            logger.error(f"加载Cookie失败: {e}", exc_info=True)
            return False
    
    def save_cookies(self) -> bool:
        """
        保存当前浏览器上下文的Cookie到文件
        
        Returns:
            是否保存成功
        """
        if not self.page:
            logger.error("Page对象未设置，无法保存Cookie")
            return False
        
        try:
            # 获取当前所有Cookie
            context = self.page.context
            cookies = context.cookies()
            
            # 构造Cookie数据
            cookie_data = {
                "cookies": cookies,
                "timestamp": datetime.now().isoformat(),
                "domain": "mms.pinduoduo.com"
            }
            
            # 确保目录存在
            self.cookie_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 保存到文件
            with open(self.cookie_path, 'w', encoding='utf-8') as f:
                json.dump(cookie_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"成功保存Cookie到: {self.cookie_path}")
            return True
        
        except Exception as e:
            logger.error(f"保存Cookie失败: {e}", exc_info=True)
            return False
    
    def clear_cookies(self) -> bool:
        """
        清除Cookie文件和浏览器Cookie
        
        Returns:
            是否清除成功
        """
        success = True
        
        # 删除Cookie文件
        if self.cookie_path.exists():
            try:
                self.cookie_path.unlink()
                logger.info("Cookie文件已删除")
            except Exception as e:
                logger.error(f"删除Cookie文件失败: {e}")
                success = False
        
        # 清除浏览器Cookie
        if self.page:
            try:
                context = self.page.context
                context.clear_cookies()
                logger.info("浏览器Cookie已清除")
            except Exception as e:
                logger.error(f"清除浏览器Cookie失败: {e}")
                success = False
        
        return success
    
    def execute_automation(self, url: Optional[str] = None) -> Dict[str, Any]:
        """
        执行自动化操作（当前仅检测登录状态）
        这是自动化操作的入口方法
        
        Args:
            url: 目标URL，如果不提供则使用默认URL
            
        Returns:
            执行结果字典
        """
        if not self.page:
            return {
                "success": False,
                "intercepted": False,
                "message": "Page对象未设置"
            }
        
        target = url or self.target_url
        
        try:
            # 加载Cookie
            self.load_cookies()
            
            # 访问目标页面
            logger.info(f"正在访问: {target}")
            self.page.goto(target, wait_until='domcontentloaded', timeout=30000)
            
            # 等待页面加载和导航完成
            # 先等待 DOM 加载完成，然后等待网络空闲，确保页面完全加载
            try:
                self.page.wait_for_load_state('domcontentloaded', timeout=5000)
                self.page.wait_for_load_state('networkidle', timeout=10000)
            except:
                # 如果超时，继续执行，至少 DOM 应该已经加载
                pass
            
            # 检测当前URL是否包含login（被拦截）
            # 等待页面稳定后，page.url 应该已经更新到实际 URL
            current_url = self.page.url
            logger.info(f"当前URL: {current_url}")
            
            if 'login' in current_url.lower():
                # 被拦截到登录页面
                logger.warning("检测到被拦截到登录页面")
                
                # 发送飞书通知
                if self.feishu_sender.is_available():
                    self.feishu_sender.send_pinduoduo_login_alert()
                    logger.info("已发送飞书通知")
                else:
                    logger.warning("飞书通知不可用，跳过发送")
                
                # 记录失败状态
                self._save_execution_status(success=False, message="被拦截到登录页面")
                
                return {
                    "success": False,
                    "intercepted": True,
                    "message": "被拦截到登录页面，已发送飞书通知"
                }
            else:
                # 未被拦截，执行成功
                logger.info("未被拦截，执行成功")
                
                # 记录成功状态
                self._save_execution_status(success=True, message="自动化执行成功")
                
                # TODO: 这里可以添加实际的自动化操作逻辑
                # 例如：抓取数据、执行操作等
                
                return {
                    "success": True,
                    "intercepted": False,
                    "message": "执行成功"
                }
        
        except TimeoutError:
            logger.error("页面加载超时")
            self._save_execution_status(success=False, message="页面加载超时")
            return {
                "success": False,
                "intercepted": False,
                "message": "页面加载超时"
            }
        except Exception as e:
            logger.error(f"执行自动化操作失败: {e}", exc_info=True)
            self._save_execution_status(success=False, message=f"执行失败: {str(e)}")
            return {
                "success": False,
                "intercepted": False,
                "message": f"执行失败: {str(e)}"
            }
    
    def _save_execution_status(self, success: bool, message: str):
        """
        保存执行状态到文件
        
        Args:
            success: 是否执行成功
            message: 状态消息
        """
        try:
            # 读取现有状态
            if self.status_path.exists():
                with open(self.status_path, 'r', encoding='utf-8') as f:
                    status_data = json.load(f)
            else:
                status_data = {
                    "last_success": None,
                    "last_failure": None,
                    "last_execution": None,
                    "status": "unknown",
                    "message": ""
                }
            
            # 更新状态
            now = datetime.now().isoformat()
            status_data["last_execution"] = now
            
            if success:
                status_data["last_success"] = now
                status_data["status"] = "success"
            else:
                status_data["last_failure"] = now
                status_data["status"] = "failed"
            
            status_data["message"] = message
            
            # 保存到文件
            self.status_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.status_path, 'w', encoding='utf-8') as f:
                json.dump(status_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"执行状态已保存: {message}")
        
        except Exception as e:
            logger.error(f"保存执行状态失败: {e}", exc_info=True)
    
    def get_last_execution_status(self) -> Dict[str, Any]:
        """
        获取最后一次执行状态
        
        Returns:
            状态字典
        """
        if not self.status_path.exists():
            return {
                "last_success": None,
                "last_failure": None,
                "last_execution": None,
                "status": "unknown",
                "message": "尚未执行过自动化操作"
            }
        
        try:
            with open(self.status_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"读取执行状态失败: {e}")
            return {
                "last_success": None,
                "last_failure": None,
                "last_execution": None,
                "status": "error",
                "message": f"读取状态失败: {str(e)}"
            }
    
    def show_login_qrcode(self) -> Optional[str]:
        """
        显示登录二维码（如果需要）
        
        逻辑：
        1. 先访问首页（target_url）
        2. 如果被拦截到登录页面，显示登录二维码
        3. 如果没有被拦截，直接返回成功（不需要二维码）
        
        Returns:
            二维码图片的Base64编码，如果已登录或失败返回None
            特殊返回值 "ALREADY_LOGGED_IN" 表示已经登录，不需要二维码
        """
        if not self.page:
            logger.error("Page对象未设置，无法显示二维码")
            return None
        
        try:
            # 先加载Cookie（如果有）
            self.load_cookies()
            
            # 访问首页（而不是直接访问登录页面）
            target = self.target_url
            logger.info(f"正在访问首页: {target}")
            self.page.goto(target, wait_until='domcontentloaded', timeout=30000)
            
            # 等待页面加载和导航完成
            try:
                self.page.wait_for_load_state('domcontentloaded', timeout=5000)
                self.page.wait_for_load_state('networkidle', timeout=10000)
            except:
                # 如果超时，继续执行，至少 DOM 应该已经加载
                pass
            
            # 检测当前URL是否包含login（被拦截）
            current_url = self.page.url
            logger.info(f"当前URL: {current_url}")
            
            if 'login' in current_url.lower():
                # 被拦截到登录页面，需要显示二维码
                logger.info("检测到被拦截到登录页面，需要显示登录二维码")
                
                # 等待二维码元素出现
                logger.info("等待二维码元素出现...")
                
                # 尝试多个可能的二维码选择器
                # 优先使用更精确的选择器（拼多多使用 div.qr-code > canvas）
                qr_selectors = [
                    '.qr-code canvas',  # 拼多多登录页面的二维码（div.qr-code > canvas）
                    'div.qr-code canvas',  # 更明确的选择器
                    'canvas[class*="qr"]',  # 包含 qr 的 canvas
                    '[class*="qr-code"] canvas',  # 包含 qr-code 的元素下的 canvas
                    'img[alt*="二维码"]',  # 图片形式的二维码
                    'img[src*="qr"]',  # src 包含 qr 的图片
                    '.qrcode img',  # 通用二维码容器下的图片
                    '#qrcode img',  # ID 为 qrcode 的元素下的图片
                    '[class*="qrcode"] img',  # 包含 qrcode 的元素下的图片
                    'img[class*="qr"]',  # class 包含 qr 的图片
                    'canvas'  # 最后的备用选择器（可能匹配到其他 canvas）
                ]
                
                qr_element = None
                qr_selector = None
                for selector in qr_selectors:
                    try:
                        element = self.page.wait_for_selector(selector, timeout=5000, state='visible')
                        if element:
                            logger.info(f"找到二维码元素: {selector}")
                            qr_element = element
                            qr_selector = selector
                            break
                    except TimeoutError:
                        continue
                    except Exception as e:
                        logger.debug(f"选择器 {selector} 查找失败: {e}")
                        continue
                
                # 如果是 canvas 元素，等待一小段时间确保绘制完成
                if qr_element and qr_selector and 'canvas' in qr_selector:
                    logger.info("检测到 canvas 二维码，等待绘制完成...")
                    time.sleep(0.5)  # 等待 canvas 绘制完成
                
                if not qr_element:
                    # 如果找不到二维码元素，截取整个页面
                    logger.warning("未找到二维码元素，截取整个页面作为二维码")
                    try:
                        screenshot_bytes = self.page.screenshot(full_page=False)
                        qrcode_base64 = base64.b64encode(screenshot_bytes).decode('utf-8')
                        logger.info("页面截图成功")
                        return f"data:image/png;base64,{qrcode_base64}"
                    except Exception as e:
                        logger.error(f"页面截图失败: {e}", exc_info=True)
                        return None
                
                # 截取二维码元素
                try:
                    # 确保元素可见
                    qr_element.wait_for_element_state('visible', timeout=2000)
                    screenshot_bytes = qr_element.screenshot()
                    qrcode_base64 = base64.b64encode(screenshot_bytes).decode('utf-8')
                    logger.info(f"二维码元素截图成功 (选择器: {qr_selector})")
                    return f"data:image/png;base64,{qrcode_base64}"
                except Exception as e:
                    logger.warning(f"二维码元素截图失败: {e}，尝试截取整个页面")
                    # 如果元素截图失败，截取整个页面
                    try:
                        screenshot_bytes = self.page.screenshot(full_page=False)
                        qrcode_base64 = base64.b64encode(screenshot_bytes).decode('utf-8')
                        logger.info("页面截图成功（备用方案）")
                        return f"data:image/png;base64,{qrcode_base64}"
                    except Exception as e2:
                        logger.error(f"页面截图也失败: {e2}", exc_info=True)
                        return None
            else:
                # 没有被拦截，说明已经登录成功
                logger.info("未被拦截，已经登录成功")
                
                # 等待页面完全加载
                try:
                    self.page.wait_for_load_state('networkidle', timeout=5000)
                except:
                    pass
                
                # 保存Cookie（更新登录状态）
                self.save_cookies()
                
                # 更新执行状态
                self._save_execution_status(success=True, message="登录成功（无需扫码）")
                
                # 返回特殊值，表示已经登录，不需要二维码
                return "ALREADY_LOGGED_IN"
        
        except TimeoutError:
            logger.error("页面加载超时")
            return None
        except Exception as e:
            logger.error(f"获取登录二维码失败: {e}", exc_info=True)
            return None
    
    def check_login_complete(self, timeout: int = 60) -> bool:
        """
        检查是否登录完成（轮询检查URL变化和页面内容）
        
        Args:
            timeout: 超时时间（秒）
            
        Returns:
            是否登录成功
        """
        if not self.page:
            logger.error("Page对象未设置，无法检查登录状态")
            return False
        
        try:
            # 如果timeout为0，只检查一次不等待
            if timeout == 0:
                return self._check_login_status_once()
            
            # timeout > 0，轮询检查
            start_time = time.time()
            check_interval = 1  # 每秒检查一次
            
            while time.time() - start_time < timeout:
                if self._check_login_status_once():
                    return True
                
                # 等待后再检查
                time.sleep(check_interval)
            
            logger.warning(f"等待登录超时（{timeout}秒）")
            return False
        
        except Exception as e:
            logger.error(f"检查登录状态失败: {e}", exc_info=True)
            return False
    
    def _check_login_status_once(self) -> bool:
        """
        检查一次登录状态（不等待）
        
        Returns:
            是否已登录
        """
        try:
            # 先等待页面稳定，确保 URL 已经更新
            # 使用较短的超时时间，避免阻塞太久
            try:
                self.page.wait_for_load_state('domcontentloaded', timeout=2000)
            except:
                # 如果超时，继续执行，使用当前 URL
                pass
            
            # 等待页面稳定后，page.url 应该已经更新到实际 URL
            current_url = self.page.url
            logger.debug(f"当前URL: {current_url}")
            
            # 方法1: 检查URL是否跳转到首页（不包含login）
            url_contains_login = 'login' in current_url.lower()
            
            # 方法2: 检查URL是否包含home（登录成功通常会跳转到home）
            url_contains_home = 'home' in current_url.lower() or 'mms.pinduoduo.com/home' in current_url.lower()
            
            # 方法3: 检查页面内容，查找登录后的特征元素
            # 拼多多登录后的页面通常会有特定的元素，比如用户信息、导航菜单等
            page_has_logged_in_content = False
            try:
                # 等待页面稳定
                self.page.wait_for_load_state('domcontentloaded', timeout=2000)
                
                # 检查是否有登录后的特征元素（可以根据实际页面调整）
                # 例如：用户头像、导航菜单、退出按钮等
                logged_in_indicators = [
                    'header',  # 登录后通常有header
                    '.user-info',  # 用户信息
                    '.nav-menu',  # 导航菜单
                    '[class*="header"]',  # 包含header的元素
                ]
                
                for indicator in logged_in_indicators:
                    try:
                        element = self.page.query_selector(indicator)
                        if element:
                            page_has_logged_in_content = True
                            logger.debug(f"找到登录后特征元素: {indicator}")
                            break
                    except:
                        continue
            except Exception as e:
                logger.debug(f"检查页面内容时出错: {e}")
            
            # 判断是否登录成功
            # 必须满足：URL不包含login（或者包含home），这是主要判断条件
            # 可选：页面有登录后的内容（作为辅助判断）
            # 注意：不能仅凭页面内容判断，因为登录页面可能也有header等元素
            url_indicates_logged_in = (not url_contains_login) or url_contains_home
            
            # 如果URL已经跳转到home，或者URL不包含login，则认为登录成功
            # 如果URL还包含login，即使页面有某些元素，也不认为登录成功
            is_logged_in = url_indicates_logged_in
            
            if is_logged_in:
                logger.info(f"检测到已登录 - URL: {current_url}, URL不包含login: {not url_contains_login}, URL包含home: {url_contains_home}, 有登录内容: {page_has_logged_in_content}")
                
                # 等待页面完全加载
                try:
                    self.page.wait_for_load_state('networkidle', timeout=5000)
                except:
                    pass
                
                # 保存Cookie
                self.save_cookies()
                
                # 更新执行状态
                self._save_execution_status(success=True, message="登录成功")
                
                return True
            else:
                logger.debug(f"尚未登录 - URL: {current_url}, URL包含login: {url_contains_login}, URL包含home: {url_contains_home}")
                return False
        
        except Exception as e:
            logger.error(f"检查登录状态时出错: {e}", exc_info=True)
            return False
