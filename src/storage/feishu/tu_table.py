"""
途强数据同步到飞书多维表格。
逻辑：仅根据「开始时间」判断，开始时间不存在则新增，已存在则跳过（不做任何更新）。
"""
from typing import List, Dict, Any, Optional
from datetime import datetime
from tools.feishu.feishu_table_client import FeishuTableClient
from utils.logger import get_logger

logger = get_logger('TuFeishuTable')


def sync_tu_data_to_feishu(records: List[Dict[str, Any]], 
                           app_token: str = 'ORSHbpajoaANQ4sFg25c917jnTc',
                           table_id: str = 'tblfTMT4wa61ZJSz') -> Dict[str, Any]:
    """
    将途强设备记录数据同步到飞书多维表格。仅按「开始时间」判断是否已存在，不存在则新增，不做更新。
    
    Args:
        records: 记录数据数组
        app_token: 飞书多维表格的 app_token
        table_id: 飞书数据表的 table_id
        
    Returns:
        同步结果字典
    """
    if not records:
        logger.warning("数据为空，无需同步")
        return {
            "success": True,
            "message": "数据为空",
            "success_count": 0,
            "fail_count": 0,
            "total_count": 0
        }
    
    try:
        # 初始化飞书表格客户端
        feishu_table_client = FeishuTableClient(app_token, table_id)
        
        # 统计信息
        success_count = 0
        fail_count = 0
        create_count = 0
        total_count = len(records)
        
        logger.info(f"开始同步 {total_count} 条记录到飞书表格（仅新增，不更新）")
        
        # 1. 获取现有记录，用「开始时间」判断是否已存在
        logger.info("正在获取现有记录（按开始时间去重）...")
        existing_records = feishu_table_client.get_all_records()
        existing_start_times = set()
        for record in existing_records:
            fields = record.get('fields', {})
            key = fields.get('开始时间')
            if key:
                existing_start_times.add(str(key))
        
        logger.info(f"已存在 {len(existing_start_times)} 个开始时间")
        
        # 2. 仅对「开始时间」不存在的记录做新增
        records_to_create = []
        for item in records:
            fields = _convert_record_to_fields(item)
            key = fields.get('开始时间')
            if key and str(key) in existing_start_times:
                continue  # 已存在则跳过，不做更新
            if key:
                existing_start_times.add(str(key))  # 避免本批内重复
            records_to_create.append({'fields': fields})
        
        logger.info(f"需要新增: {len(records_to_create)} 条")
        
        # 3. 批量创建
        if records_to_create:
            batch_size = 20
            for i in range(0, len(records_to_create), batch_size):
                batch = records_to_create[i:i + batch_size]
                try:
                    result = feishu_table_client.batch_create_records(batch)
                    if result:
                        cnt = len(result)
                        create_count += cnt
                        success_count += cnt
                        fail_count += (len(batch) - cnt)
                    else:
                        for r in batch:
                            if feishu_table_client.create_record(r["fields"]):
                                create_count += 1
                                success_count += 1
                            else:
                                fail_count += 1
                except Exception as e:
                    logger.error(f"批量创建失败: {e}")
                    for r in batch:
                        try:
                            if feishu_table_client.create_record(r["fields"]):
                                create_count += 1
                                success_count += 1
                            else:
                                fail_count += 1
                        except:
                            fail_count += 1
        
        return {
            "success": True,
            "message": f"同步完成: 新增 {create_count} 条，失败 {fail_count}",
            "success_count": success_count,
            "fail_count": fail_count,
            "create_count": create_count,
            "total_count": total_count
        }

    except Exception as e:
        logger.error(f"同步到飞书表格失败: {e}", exc_info=True)
        return {
            "success": False,
            "message": f"同步失败: {str(e)}",
            "success_count": 0,
            "fail_count": len(records),
            "total_count": len(records)
        }


def _convert_record_to_fields(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    将途强记录转换为飞书表格字段
    只保留用户需要的字段：开始时间, 公里, startTime, endTime, 平均时速, 坐标
    """
    fields = {}
    
    start_info = item.get('start', {})
    end_info = item.get('end', {})
    
    # 1. 开始时间 (Text) - 作为唯一标识
    if start_info.get('devTime'):
        fields['开始时间'] = str(start_info.get('devTime'))
        
    # 2. 公里 (Number) - JSON 中 mileage 是米，转换为公里，飞书数字字段需传数字不能传字符串
    mileage = item.get('mileage')
    if mileage is not None:
        try:
            km = round(float(mileage) / 1000, 2)
            fields['公里'] = km
        except (TypeError, ValueError):
            fields['公里'] = 0
            
    # 3. startTime (DateTime)
    if start_info.get('devTime'):
        fields['startTime'] = _parse_time_to_ts(start_info.get('devTime'))
        
    # 4. endTime (DateTime)
    if end_info.get('devTime'):
        fields['endTime'] = _parse_time_to_ts(end_info.get('devTime'))
        
    # 5. 平均时速 (Number) - 飞书数字字段需传数字不能传字符串
    avg_speed = item.get('averageSpeed')
    if avg_speed is not None:
        try:
            fields['平均时速'] = round(float(avg_speed), 2)
        except (TypeError, ValueError):
            fields['平均时速'] = 0
            
    # 6. 坐标 (Text) - 使用结束位置的经纬度，格式：lng,lat
    if end_info.get('lng') and end_info.get('lat'):
        fields['坐标'] = f"{end_info.get('lng')},{end_info.get('lat')}"
        
    return fields


def _parse_time_to_ts(time_val: Any) -> int:
    """尝试将时间转换为毫秒时间戳"""
    try:
        if isinstance(time_val, int) or isinstance(time_val, float):
            # 假设是毫秒或秒
            if time_val > 1000000000000: # 毫秒
                return int(time_val)
            return int(time_val * 1000)
        elif isinstance(time_val, str):
            # 尝试解析 '2023-01-01 12:00:00'
            dt = datetime.strptime(time_val, "%Y-%m-%d %H:%M:%S")
            return int(dt.timestamp() * 1000)
    except:
        pass
    return 0
