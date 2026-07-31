"""闲鱼卖家工作台自动化配置。

选择器与 API 名集中在此，便于前端改版后单点修正。
探测依据见 docs/goofish/闲鱼后台-探测记录.md。
"""
from __future__ import annotations

from pathlib import Path

from utils.path_helper import get_safe_data_path

# ── 数据目录（总表 + 单品目录） ──────────────────────────────
GOOFISH_DATA_DIR = Path(r'C:\Users\yao\Desktop\work\电商数据\闲鱼')
SUMMARY_EXCEL_NAME = '闲鱼商品汇总.xlsx'
PRODUCT_EXCEL_NAME = '商品信息.xlsx'

# ── 站点 URL ────────────────────────────────────────────────
SITE_PARAM = 'site=COMMONPRO'
SELLER_HOME = f'https://seller.goofish.com/?{SITE_PARAM}#/'
PUBLISH_URL = f'https://seller.goofish.com/?{SITE_PARAM}#/seller-item/publish'
ITEM_LIST_URL = f'https://seller.goofish.com/?{SITE_PARAM}#/seller-item/list'
LOGIN_URL = 'https://seller.goofish.com/#/login'

# 商品详情链接模板。Phase 0 未能在登录态确认后台使用的域名，
# 这里用闲鱼公开详情页格式；探测确认后按实际值修正。
ITEM_URL_TEMPLATE = 'https://www.goofish.com/item?id={item_id}'

# ── 超时与节流 ──────────────────────────────────────────────
DEFAULT_TIMEOUT_MS = 45_000
SUBMIT_TIMEOUT_MS = 120_000
NAV_TIMEOUT_MS = 60_000

# 图片逐张上传间隔（对齐淘宝，规避上传并发限制）
UPLOAD_BETWEEN_SEC = 6
# 连续发布最小间隔，抗平台发布频次风控
PUBLISH_INTERVAL_SEC = 30
# 登录轮询默认上限
DEFAULT_WAIT_LOGIN_SEC = 180

# ── 日志 ────────────────────────────────────────────────────
LOG_ROOT = get_safe_data_path('logs/goofish-pw')
PROBE_ROOT = LOG_ROOT / 'probe'

# ── mtop 接口 ───────────────────────────────────────────────
# 已验证存在（shell bundle 静态提取）
API_LOGIN_INFO = 'mtop.alibaba.idle.seller.platform.query.login.merchant.info'
API_MENU_QUERY = 'mtop.alibaba.idle.seller.platform.sys.menu.query'
API_DELIVERY_ADDRESS = 'mtop.alibaba.idle.seller.platform.merchant.delivery.address.list.query'

# 未登录态下无法取得，需运行时探测后填入（POST /api/goofish/probe）。
# 留空时列表功能自动回落到 DOM 抓取。
ITEM_LIST_API = ''
ITEM_LIST_API_VERSION = '1.0'

# 探测时优先匹配的 API 名关键词（用于从捕获结果里筛出商品列表接口）
PROBE_ITEM_KEYWORDS = ('item', 'goods', 'publish', 'shelf', 'onsale', 'sold')

# mtop 未登录/会话失效的错误码
SESSION_EXPIRED_CODES = ('FAIL_SYS_SESSION_EXPIRED', 'FAIL_SYS_TOKEN_EXOIRED', 'FAIL_SYS_TOKEN_EMPTY')

# ── 选择器 ──────────────────────────────────────────────────
# 硬性约束：禁止使用带 CSS Modules 构建哈希的 class（形如 loginPage--ScuLfa2N），
# 它们每次前端发版都会变。只用稳定 ID、语义属性或文本匹配。

# shell 挂载点（已验证）
SEL_APP_ROOT = '#ice-container'
SEL_APP_MAIN = '#J_AppMain'

# 登录页特征（已验证）
SEL_LOGIN_IFRAME_WRAP = '#xy-login-iframe'
SEL_LOGIN_BOX = '#alibaba-login-box'
LOGIN_URL_HASH = '#/login'
LOGIN_TITLE_KEYWORD = '登录'

# 业务页在 iframe 内（已验证 shell 只有 iframe 路由）。
# 通过 URL 关键词定位业务 frame。
BUSINESS_FRAME_URL_KEYWORDS = ('seller-item', 'item', 'publish', 'goofish.com')

# 发布表单选择器 —— 待登录态探测确认，先用文本/语义候选。
# 每项是候选列表，按序尝试第一个命中的。
SEL_PUBLISH_FORM_ANCHORS = [
    '[class*="publish"]',
    'form',
    'textarea',
]
SEL_IMAGE_UPLOAD_INPUT = 'input[type="file"]'
TEXT_SUBMIT_BUTTONS = ('确认发布', '立即发布', '发布', '提交')
TEXT_DISMISS_POPUPS = ('我知道了', '知道了', '取消', '关闭', '暂不', '跳过')

# ── 发布字段缺省值 ──────────────────────────────────────────
DEFAULT_CONDITION = '全新'
DEFAULT_FREE_SHIPPING = True
DEFAULT_CATEGORY = ''
DEFAULT_SHIP_FROM = ''

# 成色可选值（待探测确认真实文案）
CONDITION_CHOICES = ('全新', '几乎全新', '轻微使用痕迹', '明显使用痕迹', '功能正常')
