import json
from datetime import datetime

def format_timestamp(ts):
    if not ts:
        return ""
    return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')

def process_orders(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    orders = data.get('result', {}).get('pageItems', [])
    processed_data = []
    
    for item in orders:
        waybill_list = item.get('waybillDTOList')
        waybill = waybill_list[0] if waybill_list and len(waybill_list) > 0 else {}
        
        order_info = {
            "订单号": item.get('order_sn'),
            "订单状态": item.get('order_status_str'),
            "order_status": item.get('order_status'),
            "商品名称": item.get('goods_name'),
            "订单提交时间": format_timestamp(item.get('order_time')),
            "order_time": item.get('order_time'),
            "shipping_time": item.get('shipping_time'),
            "发货时间": format_timestamp(item.get('shipping_time')),
            "发货单号": item.get('tracking_number'),
            "商品规格": item.get('spec'),
            "快递单号": item.get('tracking_number'),
            "快递公司": waybill.get('shippingName'),
            "收件人": item.get('receive_name'),
            "收件人地址": f"{item.get('province_name')}{item.get('city_name')}{item.get('district_name')}",
            "昵称": item.get('nickname'),
            "商品总价(元)": item.get('goods_amount', 0) / 100.0,
            "店铺优惠折扣(元)": item.get('merchant_discount', 0) / 100.0,
            "用户实付金额(元)": item.get('order_amount', 0) / 100.0,
            "商品数量(件)": item.get('goods_number')
        }
        processed_data.append(order_info)
    
    return processed_data

if __name__ == "__main__":
    results = process_orders(r'c:\Users\Zz\Desktop\work\2026\python\assistantService\src\testData\订单数据.json')
    # Print the first few results as an example
    for i, res in enumerate(results[:5]):
        print(f"Order {i+1}:")
        for k, v in res.items():
            print(f"  {k}: {v}")
        print("-" * 20)
    
    # Also save to a new JSON for the user if needed, or just provide the summary
    with open(r'c:\Users\Zz\Desktop\work\2026\python\assistantService\src\testData\processed_orders.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
