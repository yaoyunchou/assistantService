"""
拼多多自动化客户端
负责状态管理、登录检测、自动化执行等核心功能
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
from .feishutable import sync_orders_to_feishu

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
        self.status_path = self._get_status_path()
        self.target_url = Config.PINDUODUO_TARGET_URL
        self._feishu_sender = None  # 延迟初始化
        
        # 确保目录存在
        self.status_path.parent.mkdir(parents=True, exist_ok=True)
    
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
                
                # 抓取最近30天订单数据
                logger.info("开始抓取最近30天订单数据...")
                order_result = self.fetch_recent_orders()
                
                return {
                    "success": True,
                    "intercepted": False,
                    "message": "执行成功",
                    "order_result": order_result
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
    
    def fetch_recent_orders(self) -> Dict[str, Any]:
        """
        获取最近30天的订单数据并缓存到本地
        
        Returns:
            执行结果字典
        """
        if not self.page:
            return {
                "success": False,
                "message": "Page对象未设置"
            }
        
        order_list_url = "https://mms.pinduoduo.com/orders/list"
        
        # 用于存储捕获的请求信息列表，每个item包含headers等信息
        captured_requests = []
        
        def handle_request(request):
            """处理网络请求，捕获包含 anti-content 的 XHR 请求信息"""
            # 检查是否是 XHR 或 fetch 请求
            resource_type = request.resource_type
            if resource_type in ['xhr', 'fetch']:
                # 获取请求头
                headers = dict(request.headers) if request.headers else {}
                
                # 检查请求头中是否包含 anti-content 字段
                if 'anti-content' in headers or 'antiContent' in headers:
                    url = request.url
                    logger.info(f"捕获到包含 anti-content 的 XHR 请求: {url} (类型: {resource_type})")
                    
                    # 获取POST请求体
                    post_data = None
                    post_data_parsed = None
                    try:
                        post_data = request.post_data
                        if post_data:
                            # 尝试解析JSON格式的请求体
                            try:
                                post_data_parsed = json.loads(post_data)
                                logger.info(f"请求体内容: {json.dumps(post_data_parsed, ensure_ascii=False, indent=2)}")
                            except:
                                logger.info(f"请求体内容（非JSON）: {post_data}")
                    except Exception as e:
                        logger.warning(f"获取请求体失败: {e}")
                    
                    # 添加到捕获列表
                    captured_requests.append({
                        "url": url,
                        "method": request.method,
                        "resource_type": resource_type,
                        "headers": headers,
                        "post_data": post_data,
                        "post_data_parsed": post_data_parsed,
                        "timestamp": datetime.now().isoformat()
                    })
                    
                    logger.info(f"已捕获 {len(captured_requests)} 个包含 anti-content 的 XHR 请求")
        
        try:
            # 0. 设置请求监听器（在访问页面之前）
            logger.info("设置网络请求监听器...")
            self.page.on("request", handle_request)
            
            # 1. 进入订单列表页面
            # 注意：使用 domcontentloaded 而不是 networkidle，因为现代SPA页面可能有持续的网络请求
            # 导致永远无法达到 networkidle 状态
            logger.info(f"正在访问订单列表页面: {order_list_url}")
            self.page.goto(order_list_url, wait_until='domcontentloaded', timeout=30000)
            
            # 等待页面基本加载完成
            try:
                self.page.wait_for_load_state('load', timeout=10000)
            except:
                logger.warning("等待 load 状态超时，继续执行...")
            
            # 尝试等待网络空闲，但设置较短的超时时间（5秒）
            # 如果超时也不影响，因为 DOM 已经加载完成
            try:
                self.page.wait_for_load_state('networkidle', timeout=5000)
                logger.info("页面网络已空闲")
            except:
                logger.warning("等待 networkidle 超时，但 DOM 已加载，继续执行...")
            
            # 等待一段时间，确保页面自动发起的AJAX请求被捕获
            logger.info("等待页面自动发起AJAX请求...")
            time.sleep(3)
            
            # 如果已经捕获到请求，保存请求信息
            if captured_requests:
                logger.info(f"成功捕获到 {len(captured_requests)} 个 XHR 请求")
                # 保存请求信息到文件
                request_info_path = get_safe_data_path('cache/pinduoduo_request_info.json')
                request_info_path.parent.mkdir(parents=True, exist_ok=True)
                
                # 准备保存的请求信息（保存整个列表）
                request_info = {
                    "capture_time": datetime.now().isoformat(),
                    "total_count": len(captured_requests),
                    "requests": captured_requests
                }
                
                with open(request_info_path, 'w', encoding='utf-8') as f:
                    json.dump(request_info, f, ensure_ascii=False, indent=2)
                
                logger.info(f"请求信息已保存到: {request_info_path}")
            else:
                logger.warning("未捕获到目标API请求，可能页面未自动发起请求")
            
            # 2. 准备 fetch 脚本
            # 计算30天的时间范围（Unix时间戳，秒）
            end_time = int(time.time())
            start_time = end_time - (30 * 24 * 60 * 60)
            
            
            # 处理 captured_requests 里面所有的 headers，转换为 JavaScript 可用的格式
            # 提取所有请求的 headers 列表
            if captured_requests and len(captured_requests) > 0:
                headers_list = [request["headers"] for request in captured_requests]
            else:
                # 如果没有捕获到请求，使用默认请求头
                headers_list = [{
                    "accept": "*/*",
                    "accept-language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
                    "cache-control": "no-cache",
                    "content-type": "application/json",
                    "pragma": "no-cache",
                    "priority": "u=1, i",
                    "sec-ch-ua": '"Chromium";v="143", "Not A(Brand";v="24"',
                    "sec-ch-ua-mobile": "?0",
                    "sec-ch-ua-platform": '"Windows"',
                    "sec-fetch-dest": "empty",
                    "sec-fetch-mode": "cors",
                    "sec-fetch-site": "same-origin",
                    "upgrade-insecure-requests": "1"
                }]
                logger.warning("未捕获到请求头，使用默认请求头")
            
            #  从第五个截取headers_list， 前面的有的请求有问题
            headers_list = headers_list[4:]
            # 将 headers 列表转换为 JSON 字符串，然后转义以便嵌入到 JavaScript 字符串中
            headers_list_json = json.dumps(headers_list, ensure_ascii=False)
            # 转义 JavaScript 字符串中的反斜杠、引号和换行符
            headers_list_js_escaped = headers_list_json.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")
            
            # 准备请求体：按当前逻辑计算时间（最近30天）
            end_time = int(time.time())
            start_time = end_time - (30 * 24 * 60 * 60)
           
            # 构建 fetch 脚本，在 JavaScript 中完成分页逻辑，获取最多5页数据
            fetch_script = f"""
            async () => {{
                const headersList = JSON.parse("{headers_list_js_escaped}");
                const apiUrl = "https://mms.pinduoduo.com/mangkhut/mms/recentOrderList?t=1&pageNumber=";
                const maxPages = 5;
                const pageSize = 20;
                const allPageItems = [];
                
                // 辅助函数：获取单页数据
                const fetchPage = async (pageNumber) => {{
                    // 使用对应页面的 headers，如果列表不够长则使用最后一个
                    const headers = headersList[pageNumber - 1] || headersList[headersList.length - 1] || {{}};
                    
                    const body = {{
                        "orderType": 0,
                        "afterSaleType": 0,
                        "remarkStatus": -1,
                        "urgeShippingStatus": -1,
                        "groupStartTime": {start_time},   
                        "groupEndTime": {end_time},     
                        "pageNumber": pageNumber,
                        "pageSize": pageSize,
                        "sortType": 7,
                        "hideRegionBlackDelayShipping": false,
                        "mobile": ""
                    }};
                    const response = await fetch(apiUrl+pageNumber, {{
                        "headers": headers,
                        "referrer": "{order_list_url}",
                        "body": JSON.stringify(body),
                        "method": "POST",
                        "mode": "cors",
                        "credentials": "include"
                    }});
                    return await response.json();
                }};
                
                // 获取第一页，获取总页数
                const firstPageData = await fetchPage(1);
                if (!firstPageData || !firstPageData.result) {{
                    return firstPageData;
                }}
                
                const totalItemNum = firstPageData.result.totalItemNum || 0;
                const firstPageItems = firstPageData.result.pageItems || [];
                allPageItems.push(...firstPageItems);
                
                // 计算总页数（最多获取5页）
                const totalPages = Math.min(Math.ceil(totalItemNum / pageSize), maxPages);
                
                // 如果有多页，使用 Promise.all 并发获取剩余页面（最多到第5页）
                // 因为每个请求使用不同的 headers，不会被风控
                if (totalPages > 1) {{
                    // 创建所有页面的请求 Promise
                    const pagePromises = [];
                    for (let pageNum = 2; pageNum <= totalPages; pageNum++) {{
                        pagePromises.push(fetchPage(pageNum));
                    }}
                    
                    // 并发执行所有请求
                    const pageResults = await Promise.all(pagePromises);
                    
                    // 合并所有页面的数据
                    pageResults.forEach((pageData) => {{
                        if (pageData && pageData.result && pageData.result.pageItems) {{
                            allPageItems.push(...pageData.result.pageItems);
                        }}
                    }});
                }}
                
                // 构建返回结果，合并所有页面的数据
                const result = {{
                    ...firstPageData,
                    result: {{
                        ...firstPageData.result,
                        pageItems: allPageItems,
                        totalItemNum: allPageItems.length  // 更新为实际获取的数量
                    }}
                }};
                
                return result;
            }}
            """
            
            logger.info("执行 fetch 请求获取订单数据（最多5页）...")
            order_data = self.page.evaluate(fetch_script)
            
            if order_data:
                # 3. 缓存数据到本地
                cache_path = self._get_orders_cache_path()
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                
                # 添加抓取时间
                result = {
                    "fetch_time": datetime.now().isoformat(),
                    "data": order_data
                }
                
                with open(cache_path, 'w', encoding='utf-8') as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)
                
                # 获取统计数据
                page_items = order_data.get('result', {}).get('pageItems', []) if isinstance(order_data, dict) else []
                total_item_num = order_data.get('result', {}).get('totalItemNum', 0) if isinstance(order_data, dict) else 0
                data_count = len(page_items)
                
                logger.info(f"订单数据已成功缓存到: {cache_path}，共获取 {data_count} 条订单数据")
                
                # 构建返回结果，包含捕获的请求信息
                return_result = {
                    "success": True,
                    "message": f"成功获取订单数据并缓存（共 {data_count} 条，最多5页）",
                    "data_count": data_count,
                    "total_item_num": total_item_num,
                    "cache_path": str(cache_path)
                }
                
                # 如果捕获到了请求信息，添加到返回结果中
                if captured_requests:
                    # 返回所有捕获到的请求信息
                    return_result["captured_requests"] = captured_requests
                    return_result["captured_requests_count"] = len(captured_requests)
                
                # 当获取到order_data.get('result', {}).get('pageItems', [])时，将数据存入飞书表格
                page_items = order_data.get('result', {}).get('pageItems', [])
                if page_items:
                    logger.info(f"开始同步 {len(page_items)} 条订单数据到飞书表格")
                    sync_result = sync_orders_to_feishu(page_items)
                    if sync_result.get('success'):
                        logger.info(f"订单数据同步完成: {sync_result.get('message')}")
                        return_result["feishu_sync"] = sync_result
                    else:
                        logger.error(f"订单数据同步失败: {sync_result.get('message')}")
                        return_result["feishu_sync"] = sync_result
                    

                return return_result
            else:
                return {
                    "success": False,
                    "message": "获取订单数据为空",
                    "captured_requests": captured_requests if captured_requests else [],
                    "captured_requests_count": len(captured_requests) if captured_requests else 0
                }
                
        except Exception as e:
            logger.error(f"获取订单数据失败: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"获取订单数据失败: {str(e)}",
                "captured_requests": captured_requests if captured_requests else [],
                "captured_requests_count": len(captured_requests) if captured_requests else 0
            }

    def _get_orders_cache_path(self) -> Path:
        """获取订单缓存文件路径"""
        return get_safe_data_path('cache/pinduoduo_orders_recent.json')

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
    
    def show_login_qrcode(self, skip_initial_navigation: bool = False) -> Optional[str]:
        """
        显示登录二维码（如果需要）
        
        逻辑：
        1. 默认先访问首页（target_url）；若 skip_initial_navigation=True 则使用当前页（适合已从订单页被重定向到登录的情况）
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
            if not skip_initial_navigation:
                # 访问首页（由于使用了持久化上下文，Cookie会自动由浏览器加载）
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
            else:
                logger.info("show_login_qrcode: 跳过初始导航，根据当前页面判断登录/二维码")
                try:
                    self.page.wait_for_load_state('domcontentloaded', timeout=5000)
                except:
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
                
                # 更新执行状态（持久化上下文中Cookie已自动保存）
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
            page_has_logged_in_content = False
            try:
                self.page.wait_for_load_state('domcontentloaded', timeout=2000)
                
                logged_in_indicators = [
                    'header',
                    '.user-info',
                    '.nav-menu',
                    '[class*="header"]',
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
            # 必须不包含 login 关键字，且必须包含 home 关键字或有特征元素
            # 这样可以避免 redirectUrl=...home 导致的误判
            is_logged_in = (not url_contains_login) and (url_contains_home or page_has_logged_in_content)
            
            if is_logged_in:
                logger.info(f"检测到已登录 - URL: {current_url}")
                
                # 等待页面完全加载
                try:
                    self.page.wait_for_load_state('networkidle', timeout=5000)
                except:
                    pass
                
                # 更新执行状态（持久化上下文中Cookie已自动保存）
                self._save_execution_status(success=True, message="登录成功")
                
                return True
            else:
                logger.debug(f"尚未登录 - URL: {current_url}")
                return False
        
        except Exception as e:
            logger.error(f"检查登录状态时出错: {e}", exc_info=True)
            return False
