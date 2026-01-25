"""
物流查询业务逻辑服务
将物流查询的业务逻辑从通用模块中分离
"""
from typing import List, Dict, Optional
from spider.logistics_query import get_logistics_info
from spider.query_manager import BrowserPool, BrowserTimeoutError


def query_with_retry(
    waybill_number: str,
    browser_pool: Optional[BrowserPool] = None,
    max_retry: int = 3,
    timeout: float = 60.0
) -> Optional[Dict]:
    """
    带重试机制的物流信息查询
    
    Args:
        waybill_number: 运单号
        browser_pool: 浏览器实例池
        max_retry: 最大重试次数
        timeout: 超时时间（秒），默认60秒（1分钟）
        
    Returns:
        物流信息字典，失败返回 None
    """
    # 如果包含SF就是顺丰的单， SF的单不用查询，没有办法查，直接返回空
    if 'SF' in waybill_number.upper():
        return {
            'success': True,
            'data': []
        }
    
    # 根据运单号类型获取对应的页面实例
    if browser_pool is None:
        return {
            'success': False,
            'error': '需要浏览器实例池（所有运单号都需要通过浏览器实例进行AJAX请求）'
        }
    
    # 使用上下文管理器获取页面
    try:
        with browser_pool.get_page(timeout=timeout) as page:
            is_first_time = False  # 持久化上下文会自动恢复状态
            
            # 重试查询
            for attempt in range(max_retry):
                try:
                    # 获取物流信息
                    result = get_logistics_info(page, waybill_number, is_first_time=is_first_time)
                    is_first_time = False
                    
                    if result and result.get('success'):
                        return result
                    
                    # 如果失败但不是最后一次尝试，继续重试
                    if attempt < max_retry - 1:
                        print(f"运单号 {waybill_number} 第 {attempt + 1} 次查询失败，重试中...")
                        continue
                    else:
                        # 最后一次尝试失败
                        return result
                        
                except Exception as e:
                    print(f"运单号 {waybill_number} 查询异常: {e}")
                    if attempt < max_retry - 1:
                        continue
                    else:
                        return {
                            'success': False,
                            'error': f'查询异常：{str(e)}'
                        }
            
            return None
    
    except BrowserTimeoutError as e:
        print(f"运单号 {waybill_number} 查询超时: {e}")
        return {
            'success': False,
            'error': f'查询超时：{str(e)}'
        }
            
    except Exception as e:
        print(f"运单号 {waybill_number} 创建浏览器上下文失败: {e}")
        return {
            'success': False,
            'error': f'创建浏览器上下文失败：{str(e)}'
        }


def batch_query_waybill_numbers(
    waybill_numbers: List[str],
    browser_pool: Optional[BrowserPool] = None,
    max_retry: int = 3
) -> Dict[str, Optional[Dict]]:
    """
    批量查询物流信息（顺序处理，使用浏览器实例池）
    
    Args:
        waybill_numbers: 运单号列表
        browser_pool: 浏览器实例池
        max_retry: 最大重试次数
        
    Returns:
        字典：{运单号: 物流信息}
    """
    results = {}
    
    # 顺序处理每个运单号
    total = len(waybill_numbers)
    for idx, waybill_number in enumerate(waybill_numbers, 1):
        try:
            # 查询物流信息
            result = query_with_retry(waybill_number, browser_pool, max_retry)
            # 将结果保存到字典中
            results[waybill_number] = result
            
            # 显示进度
            if idx % 10 == 0 or idx == total:
                success_count = sum(1 for r in results.values() if r and r.get('success'))
                print(f"进度: {idx}/{total}，成功: {success_count}")
                
        except Exception as e:
            print(f"运单号 {waybill_number} 查询失败: {e}")
            import traceback
            traceback.print_exc()
            results[waybill_number] = {
                'success': False,
                'error': f'查询异常：{str(e)}'
            }
    
    return results
