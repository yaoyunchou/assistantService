"""
拼多多订单数据同步到飞书多维表格
"""
from typing import List, Dict, Any, Optional
from datetime import datetime
from tools.feishu.feishu_table_client import FeishuTableClient
from utils.logger import get_logger

logger = get_logger('PinduoduoFeishuTable')


def sync_orders_to_feishu(orders: List[Dict[str, Any]], 
                          app_token: str = 'ORSHbpajoaANQ4sFg25c917jnTc',
                          table_id: str = 'tblpV1RrhyUAzfSy') -> Dict[str, Any]:
    """
    将拼多多订单数据同步到飞书多维表格
    
    Args:
        orders: 订单数据数组，每个元素是一个订单字典
        app_token: 飞书多维表格的 app_token，默认值：'ORSHbpajoaANQ4sFg25c917jnTc'
        table_id: 飞书数据表的 table_id，默认值：'tblpV1RrhyUAzfSy'
        
    Returns:
        同步结果字典，包含成功和失败的数量
        
    示例:
        >>> orders = [
        ...     {
        ...         "order_sn": "260126-573487255881547",
        ...         "order_status": 1,
        ...         "goods_name": "商品名称",
        ...         ...
        ...     },
        ...     ...
        ... ]
        >>> result = sync_orders_to_feishu(orders)
        >>> print(f"成功: {result['success_count']}, 失败: {result['fail_count']}")
    """
    if not orders:
        logger.warning("订单数据为空，无需同步")
        return {
            "success": True,
            "message": "订单数据为空",
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
        update_count = 0
        create_count = 0
        total_count = len(orders)
        
        logger.info(f"开始同步 {total_count} 条订单数据到飞书表格")
        
        # 1. 先获取所有现有记录，建立订单号到 record_id 的映射
        logger.info("正在获取现有订单记录，建立订单号映射...")
        existing_records = feishu_table_client.get_all_records()
        order_sn_to_record_id = {}
        for record in existing_records:
            record_id = record.get('record_id')
            fields = record.get('fields', {})
            order_sn = fields.get('订单号')
            if order_sn and record_id:
                order_sn_to_record_id[order_sn] = record_id
        
        logger.info(f"已获取 {len(order_sn_to_record_id)} 条现有订单记录")
        
        # 2. 分离需要创建和需要更新的订单
        orders_to_create = []
        orders_to_update = []
        
        for order in orders:
            order_sn = order.get('order_sn')
            if not order_sn:
                logger.warning(f"订单缺少订单号，跳过: {order}")
                fail_count += 1
                continue
            
            fields = _convert_order_to_fields(order)
            order_sn_str = str(order_sn)
            
            if order_sn_str in order_sn_to_record_id:
                # 订单已存在，需要更新
                record_id = order_sn_to_record_id[order_sn_str]
                orders_to_update.append({
                    'record_id': record_id,
                    'fields': fields
                })
            else:
                # 订单不存在，需要创建
                orders_to_create.append({'fields': fields})
        
        logger.info(f"需要创建: {len(orders_to_create)} 条，需要更新: {len(orders_to_update)} 条")
        
        # 3. 批量创建新订单
        if orders_to_create:
            batch_size = 20  # 每批处理20条
            for i in range(0, len(orders_to_create), batch_size):
                batch = orders_to_create[i:i + batch_size]
                try:
                    result = feishu_table_client.batch_create_records(batch)
                    if result:
                        batch_success = len(result)
                        create_count += batch_success
                        success_count += batch_success
                        fail_count += (len(batch) - batch_success)
                        logger.info(f"创建批次 {i//batch_size + 1} 成功: {batch_success}/{len(batch)}")
                    else:
                        # 如果批量创建失败，尝试单条创建
                        logger.warning(f"创建批次 {i//batch_size + 1} 批量创建失败，尝试单条创建")
                        for record in batch:
                            result = feishu_table_client.create_record(record["fields"])
                            if result:
                                create_count += 1
                                success_count += 1
                            else:
                                fail_count += 1
                except Exception as e:
                    logger.error(f"创建批次 {i//batch_size + 1} 失败: {e}", exc_info=True)
                    # 批量失败时，尝试单条创建
                    for record in batch:
                        try:
                            result = feishu_table_client.create_record(record["fields"])
                            if result:
                                create_count += 1
                                success_count += 1
                            else:
                                fail_count += 1
                        except Exception as e2:
                            logger.error(f"单条记录创建失败: {e2}")
                            fail_count += 1
        
        # 4. 批量更新已存在的订单
        if orders_to_update:
            batch_size = 20  # 每批处理20条
            for i in range(0, len(orders_to_update), batch_size):
                batch = orders_to_update[i:i + batch_size]
                try:
                    result = feishu_table_client.batch_update_records(batch)
                    if result:
                        batch_success = len(result)
                        update_count += batch_success
                        success_count += batch_success
                        fail_count += (len(batch) - batch_success)
                        logger.info(f"更新批次 {i//batch_size + 1} 成功: {batch_success}/{len(batch)}")
                    else:
                        # 如果批量更新失败，尝试单条更新
                        logger.warning(f"更新批次 {i//batch_size + 1} 批量更新失败，尝试单条更新")
                        for record in batch:
                            result = feishu_table_client.update_record(
                                record_id=record['record_id'],
                                fields=record['fields']
                            )
                            if result:
                                update_count += 1
                                success_count += 1
                            else:
                                fail_count += 1
                except Exception as e:
                    logger.error(f"更新批次 {i//batch_size + 1} 失败: {e}", exc_info=True)
                    # 批量失败时，尝试单条更新
                    for record in batch:
                        try:
                            result = feishu_table_client.update_record(
                                record_id=record['record_id'],
                                fields=record['fields']
                            )
                            if result:
                                update_count += 1
                                success_count += 1
                            else:
                                fail_count += 1
                        except Exception as e2:
                            logger.error(f"单条记录更新失败: {e2}")
                            fail_count += 1
        
        logger.info(f"订单数据同步完成: 成功 {success_count}/{total_count} (创建 {create_count}, 更新 {update_count}), 失败 {fail_count}/{total_count}")
        
        return {
            "success": True,
            "message": f"同步完成: 成功 {success_count} (创建 {create_count}, 更新 {update_count}), 失败 {fail_count}",
            "success_count": success_count,
            "fail_count": fail_count,
            "create_count": create_count,
            "update_count": update_count,
            "total_count": total_count
        }
        
    except Exception as e:
        logger.error(f"同步订单数据到飞书表格失败: {e}", exc_info=True)
        return {
            "success": False,
            "message": f"同步失败: {str(e)}",
            "success_count": 0,
            "fail_count": len(orders) if orders else 0,
            "total_count": len(orders) if orders else 0
        }


def _convert_order_to_fields(order: Dict[str, Any]) -> Dict[str, Any]:
    """
    将订单数据转换为飞书表格字段格式
    
    根据真实的飞书表格字段进行映射：
    - 订单号 (Text, is_primary)
    - 订单状态 (Text, 取 order_status_str)
    - order_status (Number)
    - 商品名称 (Text)
    - 订单提交时间 (DateTime: yyyy/MM/dd)
    - order_time (Number)
    - shipping_time (Number)
    - 发货时间 (DateTime: yyyy/MM/dd)
    - 发货单号 (Text)
    - 商品规格 (Text)
    - 快递单号 (Text)
    - 快递公司 (Text, 取 waybillDTOList.shippingName 或者为‘’)
    - 收件人 (Text)
    - 收件人地址 (Text)
    - 昵称 (Text)
    - 商品总价(元) (Number) goods_amount
    - 用户实付金额(元) (Number) order_amount
    - 平台优惠折扣(元) (Number) platform_discount
    - 店铺优惠折扣(元) (Number)
    - 物流信息 (Text, 取 traceList 转 string)
    
    Args:
        order: 订单数据字典
        
    Returns:
        飞书表格字段字典
    """
    fields = {}
    
    # 1. 订单号 (Text, is_primary)
    if 'order_sn' in order:
        fields['订单号'] = str(order['order_sn'])
    
    # 2. 订单状态 (Text, 取 order_status_str)
    if 'order_status_str' in order and order['order_status_str']:
        fields['订单状态'] = str(order['order_status_str'])
    
    # 3. order_status (Number)
    if 'order_status' in order:
        fields['order_status'] = order['order_status']
    
    # 4. 商品名称 (Text)
    if 'goods_name' in order:
        fields['商品名称'] = str(order['goods_name'])
    
    # 5. 订单提交时间 (DateTime: yyyy/MM/dd)
    if 'order_time' in order and order['order_time']:
        try:
            order_time = datetime.fromtimestamp(order['order_time'])
            # 飞书 DateTime 字段格式：yyyy/MM/dd 或时间戳（毫秒）
            # 使用时间戳（毫秒）格式
            fields['订单提交时间'] = int(order['order_time'] * 1000)
        except:
            pass
    
    # 6. order_time (Number)
    if 'order_time' in order:
        fields['order_time'] = order['order_time']
    
    # 7. shipping_time (Number)
    if 'shipping_time' in order:
        fields['shipping_time'] = order['shipping_time'] if order['shipping_time'] else 0
    
    # 8. 发货时间 (DateTime: yyyy/MM/dd)
    if 'shipping_time' in order and order['shipping_time'] and order['shipping_time'] > 0:
        try:
            # 使用时间戳（毫秒）格式
            fields['发货时间'] = int(order['shipping_time'] * 1000)
        except:
            pass
    
    # 9. 发货单号 (Text)
    if 'shipping_id' in order and order['shipping_id']:
        fields['发货单号'] = str(order['shipping_id'])
    
    # 10. 商品规格 (Text)
    if 'spec' in order:
        fields['商品规格'] = str(order['spec'])
    
    # 11. 快递单号 (Text)
    if 'tracking_number' in order and order['tracking_number']:
        fields['快递单号'] = str(order['tracking_number'])
    
    # 12. 快递公司 (Text, 取 waybillDTOList 中每项的 shippingName)
    if 'waybillDTOList' in order and order['waybillDTOList']:
        names = []
        for item in order['waybillDTOList']:
            if isinstance(item, dict) and item.get('shippingName'):
                names.append(str(item['shippingName']))
        fields['快递公司'] = ','.join(names) if names else ''
    
    # 13. 收件人 (Text)
    if 'receive_name' in order:
        fields['收件人'] = str(order['receive_name'])
    
    # 14. 收件人地址 (Text)
    # 组合省市区和详细地址
    address_parts = []
    if 'province_name' in order and order['province_name']:
        address_parts.append(order['province_name'])
    if 'city_name' in order and order['city_name']:
        address_parts.append(order['city_name'])
    if 'district_name' in order and order['district_name']:
        address_parts.append(order['district_name'])
    
    # 如果有 consumerAddress，可以获取详细地址
    if 'consumerAddress' in order and order['consumerAddress']:
        addr = order['consumerAddress']
        if addr.get('address'):
            address_parts.append(addr['address'])
    
    if address_parts:
        fields['收件人地址'] = ''.join(address_parts)
    
    # 15. 昵称 (Text)
    if 'nickname' in order:
        fields['昵称'] = str(order['nickname'])
    
    # 16. 商品总价(元) (Number) <- goods_amount，无则用 goods_price
    amount = order.get('goods_amount') or order.get('goods_price')
    if amount is not None:
        fields['商品总价(元)'] = amount
    
    # 17. 用户实付金额(元) (Number) <- order_amount
    if 'order_amount' in order:
        fields['用户实付金额(元)'] = order['order_amount']
    
    # 18. 平台优惠折扣(元) (Number) <- platform_discount
    if 'platform_discount' in order:
        fields['平台优惠折扣(元)'] = order['platform_discount']
    
    # 19. 店铺优惠折扣(元) (Number) <- merchant_discount
    if 'merchant_discount' in order:
        fields['店铺优惠折扣(元)'] = order['merchant_discount']
    
    # 20. 物流信息 (Text, 取 traceList 转 string)
    if 'traceList' in order and order['traceList'] is not None:
        fields['物流信息'] = str(order['traceList'])
    
    return fields
