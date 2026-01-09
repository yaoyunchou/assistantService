"""
运单号提取模块
"""
from playwright.sync_api import Page, TimeoutError
from typing import Optional


def extract_waybill_number_simple(page: Page, timeout: int = 10000) -> Optional[str]:
    """
    简化版运单号提取（使用 Playwright 的文本选择器）
    
    Args:
        page: Playwright Page 对象
        timeout: 超时时间（毫秒）
        
    Returns:
        运单号字符串，如果未找到则返回 None
    """
    try:
        # 等待弹框出现
        popup = page.wait_for_selector('.task-details-body-content', timeout=timeout)
        
        # 查找包含"运单号"文本的标题元素
        title = popup.locator('.task-details-component-title', has_text='运单号').first
        
        if title.count() > 0:
            # 获取父元素
            parent = title.locator('..')
            
            # 在父元素中查找 .show-value-content
            value_element = parent.locator('.show-value-content').first
            
            if value_element.count() > 0:
                # 优先获取 title 属性
                waybill_number = value_element.get_attribute('title')
                if not waybill_number:
                    waybill_number = value_element.text_content()
                    if waybill_number:
                        waybill_number = waybill_number.strip()
                
                if waybill_number:
                    return waybill_number
        
        return None
    except TimeoutError:
        print("等待弹框超时")
        return None
    except Exception as e:
        print(f"提取运单号失败: {e}")
        return None
