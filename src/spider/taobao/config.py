"""淘宝上架流程配置。"""
from __future__ import annotations

from pathlib import Path

from utils.path_helper import get_safe_data_path

# 电商数据根目录（总表 + 单品目录）
TAOBAO_DATA_DIR = Path(r'C:\Users\yao\Desktop\work\电商数据\淘宝')
SUMMARY_EXCEL_NAME = '淘宝商品汇总.xlsx'

CATEGORY_URL = 'https://item.upload.taobao.com/sell/ai/category.htm'
LOGIN_URL = 'https://login.taobao.com/member/login.jhtml'
SELLER_HOME = 'https://myseller.taobao.com/home.htm'

HEADLESS = False
UPLOAD_BETWEEN_SEC = 6
DEFAULT_TIMEOUT_MS = 45_000
SUBMIT_TIMEOUT_MS = 120_000

# 日志与步骤快照
LOG_ROOT = get_safe_data_path('logs/taobao-pw')

# 干扰弹层关闭文案（不含图片空间弹框）
DISMISS_TEXTS = ('取消', '关闭', '知道了', '我知道了', '暂不', '跳过')
