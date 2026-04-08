"""
拼多多订单数据同步到飞书多维表格
"""
from typing import List, Dict, Any, Optional
from datetime import datetime
from tools.feishu.feishu_table_client import FeishuTableClient
from utils.logger import get_logger

logger = get_logger('PinduoduoFeishuTable')

# 更新时若表格中该字段的 * 多于新数据（视为已加密），则不再覆盖
SENSITIVE_FIELD_KEYS = ('收件人', '收件人地址', '收件人手机号')

# 官方 ERP 全表同步（pdd-erp-order-all-table.js）写入表时使用
ERP_ORDER_PRIMARY_KEY = '平台订单号'
ERP_SENSITIVE_FIELD_KEYS = (
    '收件人',
    '收件电话',
    '收件详细地址',
    '收件省',
    '收件市',
    '收件区',
)

# 与 pdd-erp-order-all-table.js 输出对应；飞书表中为「数字」类型列时必须传 float/int，不能传字符串
ERP_FEISHU_NUMBER_FIELD_KEYS = (
    '重量',
    '体积',
    '商品总数',
    '商品金额',
    '运费',
    '店铺优惠金额',
    '平台优惠金额',
    '实收金额',
)
# 飞书「日期」列需 Unix 毫秒时间戳（与旧版订单同步一致）
ERP_FEISHU_DATETIME_FIELD_KEYS = ('付款时间', '审核时间', '发货时间')

# 已存在「平台订单号」时，仅 PATCH 下列字段（其余列保留表中原值，避免每次全表同步覆盖人工改动）
ERP_FEISHU_PARTIAL_UPDATE_FIELD_KEYS = (
    '快递公司',
    '快递单号',
    '订单状态',
    '提醒',
    '运费',
    '是否打印快递单',
    '是否有售后',
)


def _count_asterisks(s: Any) -> int:
    if s is None:
        return 0
    return str(s).count('*')


def _merge_erp_sensitive_fields_for_update(
    new_fields: Dict[str, Any],
    existing_fields: Dict[str, Any],
) -> Dict[str, Any]:
    """ERP 行更新：地址/电话类字段若表格中 * 更多则保留原值。"""
    out = dict(new_fields)
    for key in ERP_SENSITIVE_FIELD_KEYS:
        if key not in out:
            continue
        existing_val = existing_fields.get(key)
        new_val = out.get(key)
        if _count_asterisks(existing_val) > _count_asterisks(new_val):
            del out[key]
    return out


def _merge_sensitive_fields_for_update(
    new_fields: Dict[str, Any],
    existing_fields: Dict[str, Any]
) -> Dict[str, Any]:
    """
    合并待更新字段：收件人、收件人地址、收件人手机号若在表格中*更多（已加密）则保留不更新。
    """
    out = dict(new_fields)
    for key in SENSITIVE_FIELD_KEYS:
        if key not in out:
            continue
        existing_val = existing_fields.get(key)
        new_val = out.get(key)
        if _count_asterisks(existing_val) > _count_asterisks(new_val):
            # 表格里已加密，不覆盖
            del out[key]
    return out


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
        
        # 1. 先获取所有现有记录，建立订单号到 record_id 及现有字段的映射
        logger.info("正在获取现有订单记录，建立订单号映射...")
        existing_records = feishu_table_client.get_all_records()
        order_sn_to_record = {}  # order_sn -> { record_id, fields }
        for record in existing_records:
            record_id = record.get('record_id')
            fields = record.get('fields', {})
            order_sn = fields.get('订单号')
            if order_sn and record_id:
                order_sn_to_record[order_sn] = {'record_id': record_id, 'fields': fields}
        
        logger.info(f"已获取 {len(order_sn_to_record)} 条现有订单记录")
        
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
            
            if order_sn_str in order_sn_to_record:
                # 订单已存在，需要更新（对收件人/地址/手机号：若已有数据*更多表示已加密则不再覆盖）
                rec = order_sn_to_record[order_sn_str]
                merged_fields = _merge_sensitive_fields_for_update(
                    new_fields=fields,
                    existing_fields=rec['fields']
                )
                orders_to_update.append({
                    'record_id': rec['record_id'],
                    'fields': merged_fields
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
    - 收件人手机号 (Text)
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
    
    # 13.1 收件人手机号 (Text)
    phone = order.get('receive_phone') or order.get('receiver_phone')
    if not phone and isinstance(order.get('consumerAddress'), dict):
        addr = order['consumerAddress']
        phone = addr.get('mobile') or addr.get('phone') or addr.get('receive_phone')
    if phone is not None and phone != '':
        fields['收件人手机号'] = str(phone)
    
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


def feishu_field_to_text(val: Any, _depth: int = 0) -> str:
    """将飞书多维表格单元格值转为纯文本（兼容 text / 数字 / 富文本多段 / 嵌套 text 等）。"""
    if _depth > 14:
        return ''
    if val is None:
        return ''
    if isinstance(val, str):
        return val.strip()
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, list):
        if not val:
            return ''
        parts: List[str] = []
        for item in val:
            t = feishu_field_to_text(item, _depth + 1)
            if t:
                parts.append(t)
        return ''.join(parts).strip()
    if isinstance(val, dict):
        if 'text' in val:
            return feishu_field_to_text(val.get('text'), _depth + 1)
        if 'value' in val:
            return feishu_field_to_text(val.get('value'), _depth + 1)
        # 单选/关联/公式等偶见独立可读字段
        for k in ('name', 'caption', 'display_value', 'title', 'label'):
            if k in val and val.get(k) not in (None, '', []):
                t = feishu_field_to_text(val.get(k), _depth + 1)
                if t:
                    return t
    return str(val).strip()


def delete_feishu_rows_without_order_sn(
    app_token: str,
    table_id: str,
) -> Dict[str, Any]:
    """
    删除表格中「订单号」为空的记录（无字段或空字符串视为无订单号）。
    """
    if not app_token or not table_id:
        return {'success': False, 'message': 'app_token 或 table_id 未配置', 'deleted_count': 0}

    client = FeishuTableClient(app_token, table_id)
    records = client.get_all_records()
    ids_to_delete: List[str] = []
    for rec in records:
        rid = rec.get('record_id')
        if not rid:
            continue
        fields = rec.get('fields') or {}
        order_sn = feishu_field_to_text(fields.get('订单号'))
        if not order_sn:
            ids_to_delete.append(rid)

    if not ids_to_delete:
        logger.info('无「订单号」为空的记录需删除')
        return {
            'success': True,
            'message': '没有需要删除的记录（均无空订单号）',
            'deleted_count': 0,
            'total_scanned': len(records),
        }

    batch_size = 500
    deleted = 0
    for i in range(0, len(ids_to_delete), batch_size):
        batch = ids_to_delete[i:i + batch_size]
        if client.batch_delete_records(batch):
            deleted += len(batch)
        else:
            logger.error(f'批量删除失败，批次起始 {i}')
            return {
                'success': False,
                'message': f'删除中断：已成功删除 {deleted} 条，后续批次失败',
                'deleted_count': deleted,
                'total_scanned': len(records),
            }

    logger.info(f'已删除无订单号记录 {deleted} 条')
    return {
        'success': True,
        'message': f'已删除 {deleted} 条无「订单号」记录',
        'deleted_count': deleted,
        'total_scanned': len(records),
    }


def _parse_erp_cell_to_float(val: Any) -> Optional[float]:
    """解析 ERP 页面/脚本中的金额、重量等字符串为 float。"""
    if val is None:
        return None
    if isinstance(val, bool):
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    if not s:
        return None
    t = (
        s.replace(',', '')
        .replace('元', '')
        .replace('¥', '')
        .replace('￥', '')
        .replace(' ', '')
        .strip()
    )
    try:
        return float(t)
    except ValueError:
        return None


def _parse_erp_cell_to_datetime_ms(val: Any) -> Optional[int]:
    """
    将脚本 formatFeishuDateTime 输出的 `yyyy/MM/dd HH:mm` 等转为飞书日期字段所需的毫秒时间戳。
    """
    if val is None:
        return None
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        n = float(val)
        if n > 1e14:
            return int(n / 1000)
        if n > 1e12:
            return int(n)
        if n > 1e9:
            return int(n * 1000)
        return None
    s = str(val).strip()
    if not s:
        return None
    norm = s.replace('年', '-').replace('月', '-').replace('日', ' ')
    norm = norm.replace('/', '-').replace('T', ' ')
    norm = ' '.join(norm.split())
    for fmt, maxlen in (('%Y-%m-%d %H:%M:%S', 19), ('%Y-%m-%d %H:%M', 16), ('%Y-%m-%d', 10)):
        try:
            chunk = norm[:maxlen].strip()
            if fmt == '%Y-%m-%d' and len(chunk) < 10:
                continue
            dt = datetime.strptime(chunk, fmt)
            return int(dt.timestamp() * 1000)
        except ValueError:
            continue
    logger.debug('ERP 日期列无法解析为飞书时间戳: %r', s[:100])
    return None


def _erp_row_to_fields(row: Dict[str, Any]) -> Dict[str, Any]:
    """
    脚本返回的 rows 元素列名与飞书一致。
    文本列保持 str；数字/日期列转为 float 或毫秒 int，避免 NumberFieldConvFail / DatetimeFieldConvFail。
    无法解析的数字/日期列会跳过该字段并打日志（不再把字符串强写给数字/日期列）。
    """
    if not isinstance(row, dict):
        return {}
    out: Dict[str, Any] = {}
    for k_raw, v in row.items():
        k = str(k_raw)
        if v is None:
            continue

        if k in ERP_FEISHU_NUMBER_FIELD_KEYS:
            if isinstance(v, str) and not v.strip():
                continue
            num = _parse_erp_cell_to_float(v)
            if num is None:
                logger.warning(
                    'ERP 同步跳过无法解析的数字列（避免飞书 NumberFieldConvFail）: %s=%r',
                    k,
                    (str(v)[:120] + '…') if len(str(v)) > 120 else v,
                )
                continue
            out[k] = num
            continue

        if k in ERP_FEISHU_DATETIME_FIELD_KEYS:
            s = str(v).strip() if v is not None else ''
            if s == '':
                continue
            ms = _parse_erp_cell_to_datetime_ms(v)
            if ms is None:
                logger.warning(
                    'ERP 同步跳过无法解析的日期列（避免飞书 DatetimeFieldConvFail）: %s=%r',
                    k,
                    (str(v)[:120] + '…') if len(str(v)) > 120 else v,
                )
                continue
            out[k] = ms
            continue

        s = str(v).strip()
        if s == '':
            continue
        out[k] = s
    return out


def _erp_fields_for_partial_update(row: Dict[str, Any]) -> Dict[str, Any]:
    """
    从当前行解析出「仅增量更新」允许的字段子集（类型转换规则与 _erp_row_to_fields 一致）。
    若某列在页面为空，则不会出现在结果中，飞书该列保持原值。
    """
    full = _erp_row_to_fields(row)
    return {k: full[k] for k in ERP_FEISHU_PARTIAL_UPDATE_FIELD_KEYS if k in full}


def sync_erp_order_rows_to_feishu(
    rows: List[Dict[str, Any]],
    app_token: Optional[str] = None,
    table_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    将 pdd-erp-order-all-table.js 产出的 rows 写入飞书（列名与多维表格一致）。

    匹配键：**平台订单号**（与飞书表主键列一致）。
    - **新建**：表中尚无该「平台订单号」时，写入本行解析后的**全部非空字段**（含类型转换）。
    - **更新**：已存在时，仅更新 ``ERP_FEISHU_PARTIAL_UPDATE_FIELD_KEYS`` 中在本行有值的列；
      未出现在本次解析结果中的列**不改**；子集内与收件信息无关，不再做 * 脱敏合并。
    """
    from config import Config

    app_token = app_token or Config.PINDUODUO_FEISHU_APP_TOKEN
    table_id = table_id or Config.PINDUODUO_ERP_FEISHU_TABLE_ID

    if not rows:
        return {
            'success': True,
            'message': '无表格行可同步',
            'success_count': 0,
            'fail_count': 0,
            'create_count': 0,
            'update_count': 0,
            'update_skipped_no_delta': 0,
            'total_count': 0,
        }

    try:
        feishu_table_client = FeishuTableClient(app_token, table_id)
        success_count = 0
        fail_count = 0
        update_count = 0
        create_count = 0
        update_skipped_no_delta = 0
        total_count = len(rows)

        existing_records = feishu_table_client.get_all_records()
        key_to_record: Dict[str, Dict[str, Any]] = {}
        for record in existing_records:
            record_id = record.get('record_id')
            fields = record.get('fields', {})
            pk = feishu_field_to_text(fields.get(ERP_ORDER_PRIMARY_KEY))
            if pk and record_id:
                key_to_record[pk] = {'record_id': record_id, 'fields': fields}

        orders_to_create: List[Dict[str, Any]] = []
        orders_to_update: List[Dict[str, Any]] = []

        for row in rows:
            # 主键优先从原始行取，避免 _erp_row_to_fields 因空串丢掉「平台订单号」
            pk = feishu_field_to_text(
                row.get(ERP_ORDER_PRIMARY_KEY) if isinstance(row, dict) else None
            )
            if not pk:
                logger.warning('ERP 行缺少「平台订单号」，跳过: %s', row)
                fail_count += 1
                continue

            if pk in key_to_record:
                partial = _erp_fields_for_partial_update(row)
                if not partial:
                    update_skipped_no_delta += 1
                    logger.debug(
                        'ERP 行「平台订单号」=%s 已存在，但增量字段均为空，跳过更新',
                        pk,
                    )
                    continue
                rec = key_to_record[pk]
                orders_to_update.append({'record_id': rec['record_id'], 'fields': partial})
            else:
                fields = _erp_row_to_fields(row)
                orders_to_create.append({'fields': fields})

        batch_size = 20
        if orders_to_create:
            for i in range(0, len(orders_to_create), batch_size):
                batch = orders_to_create[i:i + batch_size]
                try:
                    result = feishu_table_client.batch_create_records(batch)
                    if result:
                        batch_success = len(result)
                        create_count += batch_success
                        success_count += batch_success
                        fail_count += len(batch) - batch_success
                    else:
                        for record in batch:
                            r = feishu_table_client.create_record(record['fields'])
                            if r:
                                create_count += 1
                                success_count += 1
                            else:
                                fail_count += 1
                except Exception as e:
                    logger.error('ERP 创建批次失败: %s', e, exc_info=True)
                    for record in batch:
                        try:
                            r = feishu_table_client.create_record(record['fields'])
                            if r:
                                create_count += 1
                                success_count += 1
                            else:
                                fail_count += 1
                        except Exception as e2:
                            logger.error('ERP 单条创建失败: %s', e2)
                            fail_count += 1

        if orders_to_update:
            for i in range(0, len(orders_to_update), batch_size):
                batch = orders_to_update[i:i + batch_size]
                try:
                    result = feishu_table_client.batch_update_records(batch)
                    if result:
                        batch_success = len(result)
                        update_count += batch_success
                        success_count += batch_success
                        fail_count += len(batch) - batch_success
                    else:
                        for record in batch:
                            r = feishu_table_client.update_record(
                                record_id=record['record_id'],
                                fields=record['fields'],
                            )
                            if r:
                                update_count += 1
                                success_count += 1
                            else:
                                fail_count += 1
                except Exception as e:
                    logger.error('ERP 更新批次失败: %s', e, exc_info=True)
                    for record in batch:
                        try:
                            r = feishu_table_client.update_record(
                                record_id=record['record_id'],
                                fields=record['fields'],
                            )
                            if r:
                                update_count += 1
                                success_count += 1
                            else:
                                fail_count += 1
                        except Exception as e2:
                            logger.error('ERP 单条更新失败: %s', e2)
                            fail_count += 1

        msg_parts = [
            f'同步完成: 成功 {success_count} (新建 {create_count}, 更新 {update_count})',
            f'失败 {fail_count}',
        ]
        if update_skipped_no_delta:
            msg_parts.append(f'已存在但无增量字段跳过 {update_skipped_no_delta}')
        return {
            'success': True,
            'message': ', '.join(msg_parts),
            'success_count': success_count,
            'fail_count': fail_count,
            'create_count': create_count,
            'update_count': update_count,
            'update_skipped_no_delta': update_skipped_no_delta,
            'total_count': total_count,
        }
    except Exception as e:
        logger.error('ERP 订单行同步飞书失败: %s', e, exc_info=True)
        return {
            'success': False,
            'message': f'同步失败: {str(e)}',
            'success_count': 0,
            'fail_count': len(rows),
            'create_count': 0,
            'update_count': 0,
            'update_skipped_no_delta': 0,
            'total_count': len(rows),
        }
