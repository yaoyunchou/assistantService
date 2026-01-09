"""
物流信息查询模块
"""
import requests
import random
import time
from playwright.sync_api import Page, TimeoutError
from typing import Dict, Optional


def get_express_type(waybill_number: str, page: Optional[Page] = None) -> Optional[str]:
    """
    获取快递类型（type）
    
    Args:
        waybill_number: 运单号
        page: Playwright Page 对象，必须提供，使用浏览器实例进行AJAX请求（避免被拦截）
        
    Returns:
        快递类型代码（如 'jd'），如果失败返回 None
    """
    if page is None:
        print("获取快递类型需要浏览器实例，请提供 page 参数")
        return None
    
    # 先访问快递100页面建立会话（模拟真实浏览器行为）
    try:
        referer_url = f'https://www.kuaidi100.com/?nu={waybill_number}'
        print(f"[快递100查询] 正在访问快递100页面建立会话（获取快递类型）...")
        page.goto(referer_url, wait_until='domcontentloaded', timeout=15000)
        time.sleep(random.uniform(0.3, 0.6))  # 随机延迟，模拟人类行为
    except Exception as e:
        print(f"[快递100查询] 访问页面警告: {e}，继续尝试查询...")
        # 即使访问页面失败，也继续尝试查询
    
    url = f"https://www.kuaidi100.com/autonumber/autoComNum?text={waybill_number}"
    
    headers = {
        'accept': 'application/json, text/javascript, */*; q=0.01',
        'accept-language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
        'sec-ch-ua': '"Google Chrome";v="141", "Not?A_Brand";v="8", "Chromium";v="141"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'x-requested-with': 'XMLHttpRequest',
        'referer': f'https://www.kuaidi100.com/?nu={waybill_number}'
    }
    
    try:
        # 使用 Playwright 的 request API 进行请求（避免被拦截）
        print(f"[快递100查询] 正在通过浏览器实例获取快递类型...")
        response = page.request.post(url, headers=headers, timeout=10000)
        if response.ok:
            data = response.json()
        else:
            print(f"获取快递类型失败: HTTP {response.status}")
            return None
        
        # 返回第一个匹配的快递类型
        if data and isinstance(data.get('auto'), list) and len(data['auto']) > 0:
            return data['auto'][0].get('comCode')
        
        return None
    except Exception as e:
        print(f"获取快递类型失败: {e}")
        return None


def query_logistics_kuaidi100(waybill_number: str, page: Optional[Page] = None) -> Optional[Dict]:
    """
    通过快递100 API 查询物流信息
    
    Args:
        waybill_number: 运单号
        page: Playwright Page 对象，用于通过浏览器实例进行AJAX请求（避免被拦截）
        
    Returns:
        物流信息字典，格式：
        {
            'success': True,
            'company': '京东快递',
            'state': '3',
            'data': [
                {
                    'time': '2024-01-01 12:00:00',
                    'context': '快件已签收',
                    'location': '北京市'
                },
                ...
            ]
        }
        如果失败返回 None
    """
    # 步骤1: 获取快递类型（使用浏览器实例避免被拦截）
    express_type = get_express_type(waybill_number, page=page)
    if not express_type:
        print(f"无法识别快递类型: {waybill_number}")
        return {
            'success': False,
            'error': '无法识别快递类型'
        }
    
    # 步骤2: 查询物流信息（使用浏览器实例避免被拦截）
    if page is None:
        return {
            'success': False,
            'error': '查询物流信息需要浏览器实例，请提供 page 参数'
        }
    
    # 先访问快递100页面建立会话（模拟真实浏览器行为）
    try:
        referer_url = f'https://www.kuaidi100.com/?nu={waybill_number}'
        print(f"[快递100查询] 正在访问快递100页面建立会话...")
        page.goto(referer_url, wait_until='domcontentloaded', timeout=15000)
        time.sleep(random.uniform(0.5, 1.0))  # 随机延迟，模拟人类行为
    except Exception as e:
        print(f"[快递100查询] 访问页面警告: {e}，继续尝试查询...")
        # 即使访问页面失败，也继续尝试查询
    
    temp = random.random()
    url = f"https://www.kuaidi100.com/query?type={express_type}&postid={waybill_number}&temp={temp}&phone="
    
    headers = {
        'accept': 'application/json, text/javascript, */*; q=0.01',
        'accept-language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
        'sec-ch-ua': '"Google Chrome";v="141", "Not?A_Brand";v="8", "Chromium";v="141"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'x-requested-with': 'XMLHttpRequest',
        'referer': f'https://www.kuaidi100.com/?nu={waybill_number}'
    }
    
    try:
        # 使用 Playwright 的 request API 进行请求（避免被拦截）
        print(f"[快递100查询] 正在通过浏览器实例查询物流信息...")
        response = page.request.get(url, headers=headers, timeout=10000)
        if response.ok:
            data = response.json()
        else:
            print(f"查询物流信息失败: HTTP {response.status}")
            return {
                'success': False,
                'error': f'查询失败：HTTP {response.status}'
            }
        
        # 检查返回状态
        if data.get('status') == '200' or data.get('message') == 'ok':
            # 过滤有效数据
            valid_data = [
                item for item in data.get('data', [])
                if item.get('context') and 
                   item.get('context').strip() != '' and 
                   item.get('context') != '查无结果'
            ]
            
            if valid_data:
                return {
                    'success': True,
                    'company': data.get('com', '未知快递公司'),
                    'state': data.get('state', '0'),
                    'data': [
                        {
                            'time': item.get('time') or item.get('ftime', ''),
                            'context': item.get('context', ''),
                            'location': item.get('location', '')
                        }
                        for item in valid_data
                    ]
                }
        
        return {
            'success': False,
            'error': '未查询到物流信息，请检查运单号是否正确'
        }
    except Exception as e:
        print(f"查询物流信息失败: {e}")
        return {
            'success': False,
            'error': f'查询失败：{str(e)}'
        }


def query_logistics_baidu(page: Page, waybill_number: str, max_attempts: int = 30, is_first_time: bool = False) -> Optional[Dict]:
    """
    通过百度搜索查询物流信息
    
    Args:
        page: Playwright Page 对象
        waybill_number: 运单号
        max_attempts: 最大轮询次数
        is_first_time: 是否是第一次使用此页面（需要初始化）
        
    Returns:
        物流信息字典，格式同 query_logistics_kuaidi100
    """
    print(f"[百度查询] 开始查询运单号: {waybill_number}")
    
    try:
        # 反爬虫措施1: 设置更真实的浏览器指纹
        # 添加额外的 HTTP 头，模拟真实浏览器
        page.set_extra_http_headers({
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
        
        # 检查是否有 hitAntibot（在查找输入框前）
        try:
            content = page.content()
            if 'hitAntibot' in content or '"hitAntibot":"1"' in content:
                print(f"[百度查询] 检测到反爬虫拦截（hitAntibot），返回错误")
                return {
                    'success': False,
                    'error': '百度反爬虫拦截（hitAntibot）'
                }
        except:
            pass
        
        # 查找输入框并输入运单号
        print(f"[百度查询] 正在查找输入框...")
        search_input = page.locator('input[placeholder*="快递单号"]').first
        
        if search_input.count() == 0:
            print(f"[百度查询] 错误: 未找到搜索输入框")
            # 如果找到id="chat-submit-button"的按钮，则点击它
            chat_submit_button = page.locator('#chat-submit-button').first
            if chat_submit_button.count() > 0:
                chat_submit_button.click()
                print(f"[百度查询] 点击了chat-submit-button按钮")
                # 等待1s 让我手动验证一下
                time.sleep(1) 
            else:
                # 等待10s 让我手动验证一下
                time.sleep(120)
                # 尝试查找所有输入框，用于调试
                all_inputs = page.locator('input').all()
                print(f"[百度查询] 调试: 页面中共有 {len(all_inputs)} 个输入框")
            
                return {
                    'success': False,
                    'error': '未找到搜索输入框'
                }
            # 进行重新查询
            # return query_logistics_baidu(page, waybill_number, max_attempts)
        print(f"[百度查询] 找到输入框，正在输入运单号: {waybill_number}")
        
        # 反爬虫措施4: 模拟人类输入（更真实的输入方式）
        # 先悬停到输入框
        try:
            search_input.hover()
            time.sleep(random.uniform(0.3, 0.6))
        except:
            pass
        
        search_input.click()  # 点击输入框
        time.sleep(random.uniform(0.4, 0.7))  # 增加延迟
        
        # 清空输入框（模拟真实用户行为）
        search_input.fill('')
        time.sleep(random.uniform(0.3, 0.5))
        
        # 逐字符输入，模拟真实打字（增加延迟）  这个模拟老是触发百度的检查对应快递的接口
        # for i, char in enumerate(waybill_number):
        #     search_input.type(char, delay=random.randint(80, 200))  # 每个字符延迟80-200ms
            
        #     # 偶尔暂停（模拟思考）
        #     if i > 0 and i % 3 == 0:
        #         time.sleep(random.uniform(0.2, 0.4))

        search_input.fill(waybill_number)
        time.sleep(random.uniform(0.3, 0.5))
        # 触发事件，确保 JavaScript 能够响应
        search_input.dispatch_event('input')
        time.sleep(random.uniform(0.2, 0.4))
        search_input.dispatch_event('change')
        time.sleep(random.uniform(0.2, 0.4))
        search_input.dispatch_event('keyup')
        time.sleep(random.uniform(0.2, 0.4))
        print(f"[百度查询] 运单号输入完成")
        
        # 等待页面 JavaScript 响应（增加延迟）
        time.sleep(random.uniform(1.0, 1.5))  # 增加延迟，确保 JS 处理完成
        
        # 再次检查是否有 hitAntibot
        try:
            content = page.content()
            if 'hitAntibot' in content or '"hitAntibot":"1"' in content:
                print(f"[百度查询] 输入后检测到反爬虫拦截，返回错误")
                return {
                    'success': False,
                    'error': '百度反爬虫拦截（hitAntibot）'
                }
        except:
            pass
        
        # 查找并点击查询按钮
        print(f"[百度查询] 正在查找查询按钮...")
        button_found = False
        button_selectors = [
            '.cos-button-primary .cos-button-content',
        ]
        
        for selector in button_selectors:
            button = page.locator(selector).first
            if button.count() > 0 and button.is_visible():
                print(f"[百度查询] 找到查询按钮 (选择器: {selector})")
                # 反爬虫措施5: 模拟鼠标移动到按钮上再点击
                try:
                    button.hover()  # 鼠标悬停
                    time.sleep(random.uniform(0.1, 0.3))
                except:
                    pass
                button.click()
                button_found = True
                break
        
        # 如果没找到，尝试通过文本匹配
        if not button_found:
            print(f"[百度查询] 通过选择器未找到按钮，尝试通过文本匹配...")
            buttons = page.locator('button').all()
            print(f"[百度查询] 调试: 页面中共有 {len(buttons)} 个按钮")
            for btn in buttons:
                text = btn.text_content()
                if text and ('查询' in text or '搜索' in text) and btn.is_visible():
                    print(f"[百度查询] 找到查询按钮 (文本: {text})")
                    # 反爬虫措施5: 模拟鼠标移动到按钮上再点击
                    try:
                        btn.hover()  # 鼠标悬停
                        time.sleep(random.uniform(0.1, 0.3))
                    except:
                        pass
                    btn.click()
                    button_found = True
                    break
        
        if not button_found:
            print(f"[百度查询] 错误: 未找到查询按钮")
            return {
                'success': False,
                'error': '未找到查询按钮'
            }
        
        print(f"[百度查询] 查询按钮已点击，等待响应...")
        
        # 等待并轮询提取物流信息（增加延迟）
        time.sleep(random.uniform(2, 3))  # 增加延迟，等待点击响应
        
        # 检查是否有 hitAntibot
        try:
            content = page.content()
            if 'hitAntibot' in content or '"hitAntibot":"1"' in content:
                print(f"[百度查询] 点击后检测到反爬虫拦截，返回错误")
                return {
                    'success': False,
                    'error': '百度反爬虫拦截（hitAntibot）'
                }
        except:
            pass
        
        print(f"[百度查询] 开始轮询提取物流信息 (最多 {max_attempts} 次)...")
        for attempt in range(max_attempts):
            try:
                # 查找物流信息容器
                aladdin_container = page.locator('div[class*="_aladdin_"]').first
                # 如果找不到aladdin_container，则返回错误 reduction-show-null-progress
                
                if aladdin_container.count() > 0:
                    print(f"[百度查询] 第 {attempt + 1} 次尝试: 找到 aladdin 容器")
                    # 如果找到reduction-show-null-progress，则返回错误
                    reduction_show_null_progress = aladdin_container.locator('div[class*="show-null-progress"]').first

                    # 判断如果找到reduction_show_null_progress 则是没有找到物流信息，更新当前数据，将可更新数据改为0
                    if reduction_show_null_progress.count() > 0:
                        print(f"[百度查询] 找到 reduction-show-null-progress，没有找到物流信息")
                        # 刷新一下当前页面，避免被拦截
                        page.reload(wait_until='domcontentloaded', timeout=20000)
                        time.sleep(random.uniform(1, 2))
                        return {
                            'success': True,
                            'company': '未知快递公司',  # 百度方案可能无法获取公司名称
                            'state': '0',  # 百度方案可能无法获取状态
                            'can_not_update': True, # 不能进行更新
                            'data': []
                        }
                    

                    # 查找标题
                    title_element = aladdin_container.locator('div[class*="show-tracking"]').first
                    
                    if title_element.count() > 0:
                        title_text = title_element.text_content()
                        print(f"[百度查询] 找到标题元素，文本: {title_text}")
                        if title_text and "物流追踪" in title_text:
                            print(f"[百度查询] 标题包含'物流追踪'，开始提取时间轴...")
                            # 查找时间轴容器
                            timeline_container = aladdin_container.locator('div[class*="show-tracking-time"]').first
                            
                            if timeline_container.count() > 0:
                                print(f"[百度查询] 找到时间轴容器")
                                # 提取时间轴项
                                timeline_items = timeline_container.locator('div[class*="show-track-item_"]').all()
                                print(f"[百度查询] 找到 {len(timeline_items)} 个时间轴项")
                                
                                if len(timeline_items) > 0:
                                    timeline = []
                                    for idx, item in enumerate(timeline_items, 1):
                                        time_elem = item.locator('div[class*="show-track-item-content-time"]').first
                                        context_elem = item.locator('div[class*="show-track-item-content-message"]').first
                                        
                                        time_text = time_elem.text_content() if time_elem.count() > 0 else ''
                                        context_text = context_elem.text_content() if context_elem.count() > 0 else ''
                                        
                                        if context_text and context_text.strip():
                                            timeline.append({
                                                'time': time_text.strip() if time_text else '',
                                                'context': context_text.strip(),
                                                'location': ''  # 百度方案可能没有位置信息
                                            })
                                            print(f"[百度查询] 提取第 {idx} 条: [{time_text}] {context_text[:50]}")
                                    
                                    if timeline:
                                        print(f"[百度查询] 成功提取 {len(timeline)} 条物流信息")
                                        return {
                                            'success': True,
                                            'company': '未知快递公司',  # 百度方案可能无法获取公司名称
                                            'state': '0',  # 百度方案可能无法获取状态
                                            'data': timeline
                                        }
                                    else:
                                        print(f"[百度查询] 警告: 时间轴项为空")
                                else:
                                    print(f"[百度查询] 第 {attempt + 1} 次尝试: 未找到时间轴项")
                            else:
                                print(f"[百度查询] 第 {attempt + 1} 次尝试: 未找到时间轴容器")
                        else:
                            print(f"[百度查询] 第 {attempt + 1} 次尝试: 标题不包含'物流追踪'，标题文本: {title_text}")
                    else:
                        print(f"[百度查询] 第 {attempt + 1} 次尝试: 未找到标题元素")
                else:
                    if attempt % 10 == 0:  # 每10次打印一次，避免日志过多
                        print(f"[百度查询] 第 {attempt + 1} 次尝试: 未找到 aladdin 容器")
            
            except Exception as e:
                print(f"[百度查询] 第 {attempt + 1} 次尝试提取失败: {e}")
                import traceback
                traceback.print_exc()
            
            # 等待后继续轮询
            time.sleep(0.1)
        
        print(f"[百度查询] 错误: 轮询 {max_attempts} 次后仍未找到物流信息")
        # 多次还是没有找到需要重新刷新当前page， 继续后面的逻辑
        page.reload(wait_until='domcontentloaded', timeout=20000)
        time.sleep(random.uniform(1, 2))
        return {
            'success': False,
            'error': f'轮询 {max_attempts} 次后仍未找到物流信息'
        }
        
    except TimeoutError as e:
        print(f"[百度查询] 错误: 页面加载超时 - {e}")
        return {
            'success': False,
            'error': '页面加载超时'
        }
    except Exception as e:
        print(f"[百度查询] 错误: 查询失败 - {e}")
        import traceback
        traceback.print_exc()
        return {
            'success': False,
            'error': f'查询失败：{str(e)}'
        }


def get_logistics_info(page: Optional[Page], waybill_number: str, is_first_time: bool = False) -> Optional[Dict]:
    """
    根据运单号获取物流信息（自动选择方案）
    
    Args:
        page: Playwright Page 对象（所有方案都需要，用于通过浏览器实例进行AJAX请求以避免被拦截）
        waybill_number: 运单号
        is_first_time: 是否是第一次使用此页面（仅对百度搜索有效）
        
    Returns:
        物流信息字典
    """
    # 根据运单号前缀选择方案
    if waybill_number.upper().startswith('JD'):
        # JD 运单号使用快递100 API（传递 page 参数以使用浏览器实例进行AJAX请求）
        return query_logistics_kuaidi100(waybill_number, page=page)
    else:
        # 其他运单号使用百度搜索
        if page is None:
            return {
                'success': False,
                'error': '百度搜索方案需要浏览器实例'
            }
        return query_logistics_baidu(page, waybill_number, is_first_time=is_first_time)
