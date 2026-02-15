"""
测试飞书多维表格客户端
"""
import sys
from pathlib import Path

# 将 src 目录添加到 Python 路径，以便可以直接运行此文件
current_file = Path(__file__).resolve()
src_dir = current_file.parent.parent.parent  # 从 src/tools/feishu/ 向上三级到 src/
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from tools.feishu.feishu_table_client import FeishuTableClient


if __name__ == '__main__':
    feishu_table_client = FeishuTableClient('ORSHbpajoaANQ4sFg25c917jnTc', 'tblpV1RrhyUAzfSy')
    app_info = feishu_table_client.get_app_info()
    print(app_info)
    list_fields = feishu_table_client.list_fields()
    print(list_fields)

    get_table_schema = feishu_table_client.get_table_schema()
    print(get_table_schema)