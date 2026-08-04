"""
配置文件
"""
import os
import json
import sys
from pathlib import Path
from typing import Dict, Any, Optional, List

# 加载环境变量（打包后 .env 须放在 exe 同目录，或由 main.spec 从项目根复制到 dist）
try:
    from dotenv import load_dotenv

    def _dotenv_candidates() -> List[Path]:
        """开发：项目根 .env。冻结：优先 exe 同目录，其次当前工作目录（快捷方式 cwd 不同时兜底）。"""
        paths: List[Path] = []
        if getattr(sys, 'frozen', False):
            exe_dir = Path(sys.executable).resolve().parent
            paths.append(exe_dir / '.env')
            paths.append(Path.cwd() / '.env')
        else:
            paths.append(Path(__file__).resolve().parent.parent / '.env')
        seen: set[str] = set()
        out: List[Path] = []
        for p in paths:
            k = str(p.resolve())
            if k not in seen:
                seen.add(k)
                out.append(p)
        return out

    def _try_load_dotenv(env_file: Path) -> bool:
        """尝试用 UTF-8 / GBK 兜底加载 .env，返回是否成功。"""
        for enc in ('utf-8', 'gbk', 'utf-8-sig'):
            try:
                load_dotenv(env_file, encoding=enc, override=False)
                print(f"[Config] 已加载环境变量文件: {env_file}（编码: {enc}）")
                return True
            except UnicodeDecodeError:
                continue
            except Exception as ex:
                print(f"[Config] 加载 .env 失败（编码: {enc}）: {ex}")
                return False
        print(f"[Config] .env 编码无法识别，已跳过: {env_file}")
        return False

    _loaded = False
    _cands = _dotenv_candidates()
    for env_file in _cands:
        if env_file.is_file():
            if _try_load_dotenv(env_file):
                _loaded = True
                break
    if not _loaded:
        _hint = Path(sys.executable).resolve().parent / '.env' if getattr(sys, 'frozen', False) else _cands[0]
        print(f"[Config] 未找到.env文件（已尝试: {', '.join(str(p) for p in _cands)}）。AI/飞书等依赖 .env 时请放在: {_hint}")
except ImportError:
    print("[Config] python-dotenv 未安装，跳过环境变量加载")
except Exception as e:
    print(f"[Config] 加载环境变量失败: {e}")


class Config:
    """应用配置类"""
    # 运行环境：'production' | 'development'，由入口文件设置
    APP_ENV = os.getenv('APP_ENV', 'production')

    # HTTP服务配置
    HOST = '127.0.0.1'
    PORT = int(os.getenv('PORT', '8887'))          # 生产默认 8887
    DEV_PORT = int(os.getenv('DEV_PORT', '8886'))  # 开发默认 8886
    
    # 浏览器配置
    # HEADLESS = True  # 是否使用无头模式
    HEADLESS = False  # 是否使用无头模式

    
    # 查询配置
    MAX_RETRY = 3  # 最大重试次数
    
    # Web界面配置
    APP_NAME = '如意助手'
    APP_VERSION = '2.0.3'
    AUTO_OPEN_BROWSER = True  # 启动时自动打开浏览器（已废弃，使用 USE_NATIVE_WINDOW）
    USE_NATIVE_WINDOW = True  # 使用原生窗口（True）还是浏览器（False）
    
    # 原生窗口配置
    WINDOW_TITLE = '如意助手'  # 窗口标题
    WINDOW_WIDTH = 1200  # 窗口宽度
    WINDOW_HEIGHT = 800  # 窗口高度
    WINDOW_MIN_WIDTH = 800  # 最小宽度
    WINDOW_MIN_HEIGHT = 600  # 最小高度
    WINDOW_RESIZABLE = True  # 是否可调整大小
    
    # 系统托盘配置
    TRAY_ENABLED = True  # 是否启用系统托盘
    TRAY_ICON_PATH = None  # 托盘图标路径，None则使用默认图标（优先使用logo_default.jpg）
    
    # 日志配置
    LOG_DIR = None  # 日志文件目录，None则使用项目根目录下的logs文件夹
    LOG_LEVEL = 'INFO'  # 日志级别：DEBUG, INFO, WARNING, ERROR, CRITICAL
    
    # 窗口调试配置
    SHOW_CONSOLE = False  # 是否显示控制台窗口（开发时可用，打包后建议False）
    ENABLE_DEVTOOLS = False  # 是否启用开发者工具（F12调试窗口）
    
    # 模块配置
    MODULE_CONFIG_FILE = None  # 模块配置文件路径，None则使用默认配置
    BROWSER_LAZY_INIT = True  # 延迟初始化浏览器
    BROWSER_IDLE_TIMEOUT = 300  # 浏览器空闲超时（秒）
    ENABLE_RESOURCE_MONITOR = True  # 启用资源监控
    MAX_MEMORY_MB = 200  # 最大内存限制（MB）
    
    # 拼多多配置
    # 状态文件将保存在用户数据目录，避免权限问题
    PINDUODUO_STATUS_PATH = None  # None表示使用默认的用户数据目录
    PINDUODUO_TARGET_URL = 'https://mms.pinduoduo.com/home'
    # 商家订单列表（同步地址、前端脚本场景与浏览器一致，使用 tab=0）
    PINDUODUO_ORDERS_LIST_URL = os.getenv(
        'PINDUODUO_ORDERS_LIST_URL',
        'https://mms.pinduoduo.com/orders/list?tab=0',
    )
    # 订单导出链接
    PINDUODUO_ORDER_EXPORT_URL = 'https://mms.pinduoduo.com/orders/exportExcel?exportType=0'
    # 拼多多飞书多维表格（订单/地址等，可通过环境变量覆盖）
    PINDUODUO_FEISHU_APP_TOKEN = os.getenv('PINDUODUO_FEISHU_APP_TOKEN', 'ORSHbpajoaANQ4sFg25c917jnTc')
    PINDUODUO_FEISHU_TABLE_ID = os.getenv('PINDUODUO_FEISHU_TABLE_ID', 'tblyxGarbBwHi25M')
    # 与多维表格 URL 中 view= 一致；列出记录不传 view_id 时可能拿到 0 条（与网页当前视图不一致）
    PINDUODUO_FEISHU_VIEW_ID = os.getenv('PINDUODUO_FEISHU_VIEW_ID', 'vewygiHiu9')
    # 同步订单地址：只处理订单时间在最近 N 天内的记录（见 order_address_sync 时间列解析）
    _addr_days = os.getenv('PINDUODUO_ADDRESS_SYNC_RECENT_DAYS', '2').strip() or '2'
    try:
        PINDUODUO_ADDRESS_SYNC_RECENT_DAYS = max(1, min(int(_addr_days), 90))
    except ValueError:
        PINDUODUO_ADDRESS_SYNC_RECENT_DAYS = 2
    # 列出记录时按该字段降序（新单优先，易早停）；留空则不传 sort，避免列名不符导致接口失败
    PINDUODUO_ADDRESS_SYNC_SORT_FIELD = (os.getenv('PINDUODUO_ADDRESS_SYNC_SORT_FIELD') or '').strip() or None
    # 官方 ERP 全部订单页（脚本 pdd-erp-order-all-table.js）
    PINDUODUO_ERP_ORDER_ALL_URL = os.getenv(
        'PINDUODUO_ERP_ORDER_ALL_URL',
        'https://mms.pinduoduo.com/erp/order/all',
    )
    # ERP 订单表同步目标（飞书多维表格，与 URL 中 table= / view= 一致）
    PINDUODUO_ERP_FEISHU_TABLE_ID = os.getenv(
        'PINDUODUO_ERP_FEISHU_TABLE_ID',
        'tblyAX9t4DJK2wuJ',
    )
    PINDUODUO_ERP_FEISHU_VIEW_ID = os.getenv(
        'PINDUODUO_ERP_FEISHU_VIEW_ID',
        'vew1HQrDsN',
    )
    # ERP 待审核订单页（脚本 pdd-erp-order-audit-goods.js）
    PINDUODUO_ERP_ORDER_AUDIT_URL = os.getenv(
        'PINDUODUO_ERP_ORDER_AUDIT_URL',
        'https://mms.pinduoduo.com/erp/order/audit',
    ).strip()
    # ERP 待发货页（脚本 pdd-erp-order-delivering-print-ship.js）
    PINDUODUO_ERP_ORDER_DELIVERING_URL = os.getenv(
        'PINDUODUO_ERP_ORDER_DELIVERING_URL',
        'https://mms.pinduoduo.com/erp/order/delivering',
    ).strip()
    # ERP 已发货订单页（脚本 pdd-erp-order-delivered-query.js，今日已打印快递单等筛选）
    PINDUODUO_ERP_ORDER_DELIVERED_URL = os.getenv(
        'PINDUODUO_ERP_ORDER_DELIVERED_URL',
        'https://mms.pinduoduo.com/erp/order/delivered',
    ).strip()
    # ERP 售后退货页（脚本 pdd-after-sale-return-logistics.js）
    PINDUODUO_ERP_AFTER_SALE_URL = os.getenv(
        'PINDUODUO_ERP_AFTER_SALE_URL',
        'https://mms.pinduoduo.com/erp/after-sale/manage',
    ).strip()
    # 退货物流同步目标（飞书多维表格，与 URL 中 table= / view= 一致）
    PINDUODUO_ERP_AFTER_SALE_FEISHU_TABLE_ID = os.getenv(
        'PINDUODUO_ERP_AFTER_SALE_FEISHU_TABLE_ID',
        'tblP5HCIUXMsntTI',
    ).strip()
    PINDUODUO_ERP_AFTER_SALE_FEISHU_VIEW_ID = os.getenv(
        'PINDUODUO_ERP_AFTER_SALE_FEISHU_VIEW_ID',
        'vewRw2erpG',
    ).strip()
    # ERP 预售订单页（脚本 pdd-erp-order-presell-list.js）
    PINDUODUO_ERP_PRESELL_URL = os.getenv(
        'PINDUODUO_ERP_PRESELL_URL',
        'https://mms.pinduoduo.com/erp/order/presell',
    ).strip()

    # 审核记录同步目标（飞书多维表格 table_id；与 docs/next/pinduoduo-erp-audit-feishu-table.md 一致）
    # 未在 .env 中显式配置时使用默认值，避免「审核完没自动同步飞书」的静默失败
    PINDUODUO_ERP_AUDIT_FEISHU_TABLE_ID = (
        os.getenv('PINDUODUO_ERP_AUDIT_FEISHU_TABLE_ID') or 'tblVgYVKU5DbyKdM'
    ).strip()
    # 可选：SQLite 绝对路径；留空则用 get_safe_data_path('data/pdd_erp_audit.sqlite')
    PINDUODUO_ERP_AUDIT_DB_PATH = (os.getenv('PINDUODUO_ERP_AUDIT_DB_PATH') or '').strip()
    # 安特限时秒杀 MySQL 连接（与 .env 通用 DB_* 字段对齐）
    ANTEXIADAN_DB_HOST     = (os.getenv('DB_HOST')     or 'localhost').strip()
    ANTEXIADAN_DB_PORT     = int((os.getenv('DB_PORT') or '3306').strip() or '3306')
    ANTEXIADAN_DB_USER     = (os.getenv('DB_USERNAME') or 'root').strip()
    ANTEXIADAN_DB_PASSWORD = (os.getenv('DB_PASSWORD') or '').strip()
    ANTEXIADAN_DB_NAME     = (os.getenv('DB_DATABASE') or 'cursor').strip()
    ANTEXIADAN_DB_CHARSET  = (os.getenv('ANTEXIADAN_DB_CHARSET') or 'utf8mb4').strip()
    # 安特 pcapi key（从 Chrome Network seckill-list 请求复制 key 参数；定期更新）
    ANTEXI_API_KEY         = (os.getenv('ANTEXI_API_KEY') or '').strip()
    ANTEXI_API_VERSION     = (os.getenv('ANTEXI_API_VERSION') or '20251218').strip()
    # 安特 PC 商城登录（Playwright 自动登录门禁；仅从 .env 读取，勿写死默认值）
    ANTEXIADAN_USERNAME    = (os.getenv('ANTEXIADAN_USERNAME') or '').strip()
    ANTEXIADAN_PASSWORD    = (os.getenv('ANTEXIADAN_PASSWORD') or '').strip()
    # 登录后「安全验证」滑块：Cursor Agent 最多尝试次数（默认 5），失败发 Webhook
    ANTEXIADAN_CAPTCHA_MAX_ATTEMPTS = int(
        (os.getenv('ANTEXIADAN_CAPTCHA_MAX_ATTEMPTS') or '5').strip() or '5'
    )
    # 兼容旧配置（人工等待秒数，现已改为 Agent 自动尝试）
    ANTEXIADAN_CAPTCHA_TIMEOUT_SEC = int(
        (os.getenv('ANTEXIADAN_CAPTCHA_TIMEOUT_SEC') or '120').strip() or '120'
    )
    # Nest 识图距离修正（像素，负值略往回拖；默认 -5）
    ANTEXIADAN_CAPTCHA_DRAG_OFFSET_PX = int(
        (os.getenv('ANTEXIADAN_CAPTCHA_DRAG_OFFSET_PX') or '-5').strip() or '-5'
    )
    # Nest 识图后是否删除本地截图（默认删；联调可设 0/false 保留）
    _cap_del = (os.getenv('ANTEXIADAN_CAPTCHA_DELETE_SCREENSHOTS') or '1').strip().lower()
    ANTEXIADAN_CAPTCHA_DELETE_SCREENSHOTS = _cap_del not in ('0', 'false', 'no', 'off')
    # 预售抢购：开售前多少分钟加入购物车（默认 20）
    ANTEXIADAN_PRESALE_CART_ADVANCE_MIN = int(
        (os.getenv('ANTEXIADAN_PRESALE_CART_ADVANCE_MIN') or '20').strip() or '20'
    )
    # 库存同步：ERP 全部店铺表 → 库存信息表 + 扣减日志表（定时任务 inventory_sync_job）
    # 库存信息表 / 扣减日志表均有默认 table_id，可用环境变量覆盖（与你们飞书实际表不一致时请改 .env）
    PINDUODUO_FEISHU_INVENTORY_INFO_TABLE_ID = os.getenv(
        'PINDUODUO_FEISHU_INVENTORY_INFO_TABLE_ID',
        'tbljLwzLLKafXl0h',
    ).strip()
    PINDUODUO_FEISHU_INVENTORY_LOG_TABLE_ID = os.getenv(
        'PINDUODUO_FEISHU_INVENTORY_LOG_TABLE_ID',
        'tblXXipFcgH1EQH7',
    ).strip()
    # 付款时间须严格晚于该日「整天」后（见 inventory_sync_job._parse_pay_after_cutoff_ms）
    PINDUODUO_INVENTORY_PAY_AFTER_DATE = os.getenv(
        'PINDUODUO_INVENTORY_PAY_AFTER_DATE',
        '2026-04-07',
    ).strip()
    # 日志出库行：是否要求快递单号非空才写入/更新（1/true/yes 为是）
    _inv_req_ex = (os.getenv('PINDUODUO_INVENTORY_LOG_REQUIRE_EXPRESS', '1') or '1').strip().lower()
    PINDUODUO_INVENTORY_LOG_REQUIRE_EXPRESS = _inv_req_ex not in ('0', 'false', 'no', 'off')
    # 提醒列包含以下任一子串则更新日志退货列（逗号分隔）
    PINDUODUO_INVENTORY_RETURN_KEYWORDS = os.getenv(
        'PINDUODUO_INVENTORY_RETURN_KEYWORDS',
        '退货,退款,售后,换货',
    ).strip()
    # 库存信息表中与 ERP「平台订单号」对应的列名（表结构一致时勿改）
    PINDUODUO_INVENTORY_INFO_ORDER_FIELD = (
        os.getenv('PINDUODUO_INVENTORY_INFO_ORDER_FIELD') or '平台订单号'
    ).strip()
    # 库存信息表中「商品名称」列名（用于与 ERP「商品信息」算库存关联匹配分）
    PINDUODUO_INVENTORY_PRODUCT_NAME_FIELD = (
        os.getenv('PINDUODUO_INVENTORY_PRODUCT_NAME_FIELD') or '商品名称'
    ).strip()
    # 匹配分权重 JSON，可选。键：weight_char_cover, weight_power, weight_kind, weight_symmetric_jaccard
    # 示例：{"weight_char_cover":0.45,"weight_power":0.3,"weight_kind":0.15,"weight_symmetric_jaccard":0.1}
    PINDUODUO_INVENTORY_STOCK_LINK_WEIGHTS_JSON = (
        os.getenv('PINDUODUO_INVENTORY_STOCK_LINK_WEIGHTS_JSON') or ''
    ).strip()
    # 匹配分 ≥ 此值（0–100）时，扣减日志「库存关联」写入与库存表「商品名称」相同文案；否则仍为「店铺 / 商品信息」
    _slm = (os.getenv('PINDUODUO_INVENTORY_STOCK_LINK_MATCH_MIN_SCORE') or '80').strip()
    try:
        _slm_v = int(_slm)
        PINDUODUO_INVENTORY_STOCK_LINK_MATCH_MIN_SCORE = _slm_v if 0 <= _slm_v <= 100 else 80
    except ValueError:
        PINDUODUO_INVENTORY_STOCK_LINK_MATCH_MIN_SCORE = 80

    # PINDUODUO_TARGET_URL = 'https://www.doubao.com/chat/28899721294850?open_from_ext=1'

    
    # 途强物联网平台配置（iot.tqiot.com）
    TU_TARGET_URL = 'https://iot.tqiot.com/#/?to=reportDown'
    TU_STATUS_PATH = None  # None 表示使用默认用户数据目录
    TU_ACCOUNT = os.getenv('TU_ACCOUNT', '18038361262')
    TU_PASSWORD = os.getenv('TU_PASSWORD', 'yao625625')
    # 设备ID，用于 locator/segment/find 接口；不填则从页面请求中自动捕获
    TU_DEVICE_ID = os.getenv('TU_DEVICE_ID', '14165920973')

    # 飞书配置
    FEISHU_ENABLED = True  # 是否启用飞书通知
    # 自定义机器人 Webhook：通用渠道见 FEISHU_SYNC_WEBHOOK_URL；按业务拆分见 tools.feishu.webhook.qudao_notify
    FEISHU_SYNC_WEBHOOK_URL = (os.getenv('FEISHU_SYNC_WEBHOOK_URL') or '').strip() or None

    # 定时任务（APScheduler）
    SCHEDULER_ENABLED = True  # 是否启用定时任务模块
    # 1688 订单补详情：cron 表达式，默认每小时整点执行一次
    SCHEDULER_ORDER_1688_FILL_CRON = os.getenv("SCHEDULER_ORDER_1688_FILL_CRON", "0 * * * *")  # 分 时 日 月 周

    # WebSocket（Socket.IO）客户端配置（对接 docs/websocket-api.md，默认开启；main/dev 启动后自动连接）
    WS_CLIENT_ENABLED = True  # 是否启用
    # Socket.IO engine 路径（服务端 Nest.js 配置了 /xcx/socket.io）
    WS_CLIENT_PATH_DEFAULT = '/xcx/socket.io/'
    # 可为纯域名/IP，或含协议如 https://nestapi.xfysj.top（见 build_socket_io_server_url：无端口时用 443/80，不读下面 PORT）
    WS_CLIENT_HOST = os.getenv('WS_CLIENT_HOST', 'localhost')
    # 仅当 HOST 为「无协议的 host」时使用；完整 https URL 未带端口时不参与拼接
    WS_CLIENT_PORT = int(os.getenv('WS_CLIENT_PORT', '8080'))
    WS_CLIENT_PATH = (os.getenv('WS_CLIENT_PATH') or WS_CLIENT_PATH_DEFAULT).strip() or WS_CLIENT_PATH_DEFAULT
    # Nest 等网关：握手 Query 自动带 assistantKey（见 docs/pinduoduo-erp-remote-api.md §2）
    # 未设置环境变量时默认 erp-001（生产）；开发环境在加载 toml 后改为 erp-dev-001（见 _apply_ws_assistant_key_for_app_env）
    # 设置 WS_CLIENT_ASSISTANT_KEY= 且留空表示不携带 assistantKey
    WS_CLIENT_ASSISTANT_KEY_PRODUCTION_DEFAULT = 'erp-001'
    WS_CLIENT_ASSISTANT_KEY_DEVELOPMENT_DEFAULT = 'erp-dev-001'
    _ws_ak_env = os.getenv('WS_CLIENT_ASSISTANT_KEY')
    if _ws_ak_env is None:
        WS_CLIENT_ASSISTANT_KEY = WS_CLIENT_ASSISTANT_KEY_PRODUCTION_DEFAULT
    else:
        WS_CLIENT_ASSISTANT_KEY = (_ws_ak_env or '').strip() or None

    # Socket.IO「assistant_http」本地回环：无 host 的 url 拼到此地址（默认 http://HOST:PORT）
    ASSISTANT_HTTP_BASE = (os.getenv('ASSISTANT_HTTP_BASE') or '').strip() or None

    # AI API 配置（兼容 OpenAI 接口格式，用于库存关联商品名称匹配等 AI 任务）
    # 使用 DMXAPI 时：AI_BASE_URL=https://www.dmxapi.cn/v1
    AI_BASE_URL = os.getenv('AI_BASE_URL', '').strip()
    AI_API_KEY = os.getenv('AI_API_KEY', '').strip()
    # 库存关联匹配模型（推荐高性价比国产模型：deepseek-v3 / qwen3-flash 等）
    AI_STOCK_LINK_MODEL = os.getenv('AI_STOCK_LINK_MODEL', 'qwen-flash-2025-07-28').strip()
    # 视觉识图模型（安特滑块等）；DMXAPI 可用 gpt-4o-mini / gemini-2.0-flash 等
    AI_VISION_MODEL = os.getenv('AI_VISION_MODEL', 'gpt-4o-mini').strip()

    # Cursor SDK（已弃用，保留配置项避免旧 .env 报错；AI 统一走 Nest）
    CURSOR_API_KEY = os.getenv('CURSOR_API_KEY', '').strip()
    CURSOR_MODEL = os.getenv('CURSOR_MODEL', 'composer-2.5').strip()

    # Nest CMS REST（全项目 AI：/ai/chat、/ai/generate 等）
    NEST_API_BASE = os.getenv('NEST_API_BASE', '').strip().rstrip('/')
    NEST_DEVICE_KEY = os.getenv('NEST_DEVICE_KEY', '').strip()
    NEST_USERNAME = os.getenv('NEST_USERNAME', '').strip()
    NEST_PASSWORD = os.getenv('NEST_PASSWORD', '').strip()
    NEST_JWT = os.getenv('NEST_JWT', '').strip()
    # 可选：传给 Nest /ai/chat 的模型（与 Cursor 客户端里选的 Composer 无关，须 Nest 后端支持该字段）
    NEST_CHAT_MODEL = os.getenv('NEST_CHAT_MODEL', '').strip()
    NEST_CHAT_TIMEOUT = int((os.getenv('NEST_CHAT_TIMEOUT') or '120').strip() or '120')
    NEST_CHAT_TIMEOUT_MULTIMODAL = int((os.getenv('NEST_CHAT_TIMEOUT_MULTIMODAL') or '360').strip() or '360')


# 在Config类定义后，尝试从配置文件加载配置
def _load_config_from_file():
    """从配置文件加载配置（如果存在）"""
    try:
        # 延迟导入避免循环导入
        from utils.config_manager import get_config_manager
        config_manager = get_config_manager()
        saved_config = config_manager.load_config()
        
        # 应用已保存的配置
        if saved_config:
            if 'host' in saved_config:
                Config.HOST = str(saved_config['host'])
            if 'port' in saved_config:
                port = int(saved_config['port'])
                if 1024 <= port <= 65535:
                    Config.PORT = port
            if 'headless' in saved_config:
                Config.HEADLESS = bool(saved_config['headless'])
            if 'window_width' in saved_config:
                Config.WINDOW_WIDTH = int(saved_config['window_width'])
            if 'window_height' in saved_config:
                Config.WINDOW_HEIGHT = int(saved_config['window_height'])
            if 'tray_enabled' in saved_config:
                Config.TRAY_ENABLED = bool(saved_config['tray_enabled'])
            if 'use_native_window' in saved_config:
                Config.USE_NATIVE_WINDOW = bool(saved_config['use_native_window'])
            if 'log_level' in saved_config:
                Config.LOG_LEVEL = str(saved_config['log_level'])
            if 'browser_lazy_init' in saved_config:
                Config.BROWSER_LAZY_INIT = bool(saved_config['browser_lazy_init'])
            if 'browser_idle_timeout' in saved_config:
                Config.BROWSER_IDLE_TIMEOUT = int(saved_config['browser_idle_timeout'])
            if 'enable_resource_monitor' in saved_config:
                Config.ENABLE_RESOURCE_MONITOR = bool(saved_config['enable_resource_monitor'])
            if 'max_memory_mb' in saved_config:
                Config.MAX_MEMORY_MB = int(saved_config['max_memory_mb'])
            if 'ws_client_enabled' in saved_config:
                Config.WS_CLIENT_ENABLED = bool(saved_config['ws_client_enabled'])
            if 'ws_client_host' in saved_config:
                Config.WS_CLIENT_HOST = str(saved_config['ws_client_host'])
            if 'ws_client_port' in saved_config:
                port = int(saved_config['ws_client_port'])
                if 1 <= port <= 65535:
                    Config.WS_CLIENT_PORT = port
            if 'ws_client_path' in saved_config:
                Config.WS_CLIENT_PATH = (
                    str(saved_config['ws_client_path']).strip() or Config.WS_CLIENT_PATH_DEFAULT
                )
            if 'ws_client_assistant_key' in saved_config:
                v = saved_config['ws_client_assistant_key']
                if v is None or (isinstance(v, str) and not str(v).strip()):
                    Config.WS_CLIENT_ASSISTANT_KEY = None
                else:
                    Config.WS_CLIENT_ASSISTANT_KEY = str(v).strip()
    except Exception as _cfg_load_err:
        import traceback as _tb
        print(f"[Config] 加载配置文件失败，使用默认配置: {_cfg_load_err}\n{_tb.format_exc()}")
    _apply_ws_assistant_key_for_app_env()


def _apply_ws_assistant_key_for_app_env() -> None:
    """
    app_config.toml 通常写生产用 assistantKey（erp-001）。
    开发入口（APP_ENV=development）且未显式设置 WS_CLIENT_ASSISTANT_KEY 环境变量时，
    改用 WS_CLIENT_ASSISTANT_KEY_DEVELOPMENT_DEFAULT（erp-dev-001），避免与生产 Nest 映射冲突。
    """
    if os.getenv('WS_CLIENT_ASSISTANT_KEY') is not None:
        return
    env = (os.getenv('APP_ENV') or getattr(Config, 'APP_ENV', '') or 'production').strip().lower()
    if env == 'development':
        Config.WS_CLIENT_ASSISTANT_KEY = Config.WS_CLIENT_ASSISTANT_KEY_DEVELOPMENT_DEFAULT


# 文件配置加载改由 config/__init__.py 在导出完成后再调用，避免循环导入。


_MODULE_CONFIG_HEADER = """\
===== 功能模块配置 =====
enabled: 是否启用  init_on_startup: 启动时初始化  requires_browser: 是否需要浏览器"""


def get_module_config_file_path() -> Path:
    """
    获取模块配置文件路径
    
    Returns:
        配置文件路径
    """
    if Config.MODULE_CONFIG_FILE:
        return Path(Config.MODULE_CONFIG_FILE)
    
    if getattr(__import__('sys'), 'frozen', False):
        base = Path(__import__('sys').executable).parent
    else:
        base = Path(__file__).parent.parent

    toml_path = base / 'module_config.toml'

    # 首次升级：自动把旧 JSON 迁移为 TOML
    from utils.toml_helper import migrate_json_to_toml
    migrate_json_to_toml(base / 'module_config.json', toml_path, header=_MODULE_CONFIG_HEADER)

    return toml_path


def load_module_config() -> Dict[str, Dict[str, Any]]:
    """
    加载模块配置
    
    Returns:
        模块配置字典
    """
    from config.modules import get_default_module_config
    from utils.toml_helper import load_toml
    
    config = get_default_module_config()
    
    config_file = get_module_config_file_path()
    if config_file.exists():
        try:
            user_config = load_toml(config_file)
            for module_name, module_config in user_config.items():
                if not isinstance(module_config, dict):
                    continue
                if module_name in config:
                    config[module_name].update(module_config)
                else:
                    config[module_name] = module_config
        except Exception as e:
            print(f"[Config] 加载模块配置文件失败: {e}")
    
    return config


def save_module_config(config: Dict[str, Dict[str, Any]]) -> bool:
    """
    保存模块配置到文件
    
    Args:
        config: 模块配置字典
        
    Returns:
        是否保存成功
    """
    from utils.toml_helper import dump_toml

    config_file = get_module_config_file_path()
    try:
        dump_toml(config, config_file, header=_MODULE_CONFIG_HEADER)
        return True
    except Exception as e:
        print(f"[Config] 保存模块配置文件失败: {e}")
        return False