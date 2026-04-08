"""
定时任务：读飞书 ERP「全部店铺」订单表，维护库存信息表与扣减库存日志表（纯飞书 API）。

- **默认 table_id**（与 `config.Config` 一致，可用环境变量或 `run_inventory_sync_job` 的 options 覆盖）：
  - ERP 源表：`tblyAX9t4DJK2wuJ` → `PINDUODUO_ERP_FEISHU_TABLE_ID`
  - 库存信息表：`tbljLwzLLKafXl0h` → `PINDUODUO_FEISHU_INVENTORY_INFO_TABLE_ID`
  - 扣减日志表：`tblXXipFcgH1EQH7` → `PINDUODUO_FEISHU_INVENTORY_LOG_TABLE_ID`

- 条件：有平台订单号，且付款时间 **严格晚于** 配置日整天（见下方 `INVENTORY_SYNC_PAY_AFTER_OVERRIDE` / `Config` / `pay_after_date`）。
- 库存信息表：按订单号无则新增（从订单行复制常用列）。
- 扣减日志表：默认仅当「快递单号」非空时新增/更新出库相关列。
- 提醒列命中退货关键词时，若已有日志行则更新退货时间/数量（与已有值相同则跳过 API）。
- 「库存关联」列（扣减日志表）：扫描库存信息表**全部行**的「商品名称」（SKU 短名，如 "30W 充电头-白色"），
  用字符多集覆盖 + 功率 + 类别 + Jaccard 综合打分，取分最高的候选；
  分数 ≥ 阈值（默认 80）则写入该名称，否则写未匹配说明（含商品信息、店铺、失败原因）。
- **平台订单号**：三表比对时统一规范化（NFKC、全角横线→-、去空白），避免字符差异导致误判重复。
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

from config import Config
from spider.pinduoduo.feishutable import feishu_field_to_text
from spider.pinduoduo.order_address_sync import _feishu_cell_to_epoch_ms
from tools.feishu.feishu_table_client import FeishuTableClient
from utils.logger import get_logger

logger = get_logger('PinduoduoInventorySync')

# 与「上海时区」对齐的固定 UTC+8（不依赖 zoneinfo，兼容 Python 3.8）
TZ_SH = timezone(timedelta(hours=8))

# 临时测试：付款对比基准日（YYYY-MM-DD），严格晚于该日整天后的订单才纳入；会覆盖 Config / .env（仍可用 options['pay_after_date'] 覆盖）。
# 测完请改回 None，恢复 `PINDUODUO_INVENTORY_PAY_AFTER_DATE` 默认 2026-04-07。
INVENTORY_SYNC_PAY_AFTER_OVERRIDE: Optional[str] = '2026-04-05'

# 写入库存信息表时从 ERP 行复制的列。
# 库存信息表只有「平台订单号」是必须存在的；其余 ERP 字段（店铺/商品信息等）
# 在库存表里不一定有对应列，写入会导致 FieldNameNotFound 报错，故不复制。
# 若你在飞书库存信息表里手动建了其他列，可在此追加对应列名。
_INVENTORY_COPY_TEXT = ('平台订单号',)
_INVENTORY_COPY_DATE: tuple = ()
_INVENTORY_COPY_NUMBER: tuple = ()

# 日志表业务列名（与多维表格表头一致）
_LOG_COL_ORDER = '平台订单号'
_LOG_COL_DATE = '日期'
_LOG_COL_STOCK_LINK = '库存关联'
_LOG_COL_OUT_TIME = '出库时间'
_LOG_COL_OUT_QTY = '出库数量'
_LOG_COL_RET_TIME = '退货时间'
_LOG_COL_RET_QTY = '退货数量'
# 新增三列
_LOG_COL_PRODUCT_INFO = '商品信息'   # ERP 原始商品信息文本
_LOG_COL_PRODUCT_NAME = '商品标题'   # 非套装=商品信息原文；套装=匹配到的单品名称（对应飞书「商品标题」列）
_LOG_COL_IS_BUNDLE = '组合'          # "是"（套装）/ "否"（非套装）


def _matched_name_only(stock_link: str) -> str:
    """从 stock_link 中提取干净的匹配名称。
    若 stock_link 是「未匹配|原因：...」形式的报错文本，返回空字符串；
    匹配成功则直接返回 stock_link（即 SKU 名称）。
    报错内容已写入库存关联列，商品标题不再重复展示。
    """
    return '' if (stock_link or '').startswith('未匹配') else (stock_link or '')


def _split_bundle_descriptions(info_raw: str) -> tuple:
    """将套装描述拆成（充电头描述, 数据线描述）两段。
    套装格式通常为：「{充电头描述} +{数量}米{线材描述}x1」
    按第一个加号（+）分割；若找不到加号则两段都返回原文。
    返回 (charger_desc, cable_desc)，均已 strip。
    """
    t = (info_raw or '').strip()
    # 找 ` +` 或 `+` 作为分隔符（套装描述里线材前通常有空格+加号）
    idx = t.find(' +')
    if idx == -1:
        idx = t.find('+')
    if idx == -1:
        return t, t
    charger_desc = t[:idx].strip()
    cable_desc = t[idx + 1:].strip().lstrip('+').strip()
    return charger_desc or t, cable_desc or t


def _detect_accessory_kind(s: str) -> str:
    """粗分：充电头类 / 数据线类 / 二者都提到（套装）/ 未知。"""
    t = s or ''
    cable = any(
        k in t
        for k in (
            '数据线', '充电线', '快充线', '苹果线', '安卓线', '线材',
            'PD线', '双C线', '双c线', 'C线', 'L线',
            'CtoC', 'C to C', 'CtoL', 'C to L',
            'Type-C线', 'type-c线', 'typec线',
        )
    )
    charger = any(
        k in t for k in ('充电头', '充电器', '快充头', '插头', '氮化镓', 'GaN', 'gan充电', 'GAN充电')
    )
    if cable and charger:
        return 'both'
    if cable:
        return 'cable'
    if charger:
        return 'charger'
    return 'unknown'


def _detect_is_bundle(s: str) -> bool:
    """是否为套装（充电头 + 线的组合，或明确含「套装」字）。"""
    return '套装' in (s or '') or _detect_accessory_kind(s) == 'both'


_SYSTEM_PROMPT_NORMAL = (
    '你是电商库存匹配助手。根据 ERP 商品信息，从候选商品名称列表中找出最匹配的一条。\n'
    '匹配规则（全部满足才算匹配）：\n'
    '  · 功率（如 30W/45W/60W）必须一致\n'
    '  · 颜色（白/蓝/粉/橙等，白色=白）必须一致\n'
    '  · 类型（充电头 vs 数据线）必须一致\n'
    '  · 线材接口（PD线/CtoL/苹果线 为同类；双C线/CtoC 为同类）必须一致\n'
    '  · 线材长度（1.2米/2米等）必须一致\n'
    '  · 套装（充电头+线组合）只匹配套装候选\n'
    '输出要求：只返回候选列表中的原文名称，无匹配则只返回"无匹配"，禁止任何解释。'
)

_SYSTEM_PROMPT_BUNDLE_CABLE = (
    '你是电商库存匹配助手。ERP 商品信息是一条套装订单（充电头+数据线组合），你的任务是从候选列表中找出最匹配的数据线商品名称。\n'
    '匹配规则（全部满足才算匹配）：\n'
    '  · 线材接口类型（PD线/CtoL/苹果线 为同类；双C线/CtoC 为同类）必须一致\n'
    '  · 线材长度（1.2米/2米等）必须一致\n'
    '  · 功率（如 30W/45W/60W）必须一致\n'
    '  · 颜色：套装线材颜色与充电头颜色相同，套装颜色标签（如【蓝色套装】）即为线材颜色，必须一致\n'
    '输出要求：只返回候选列表中的原文名称，无匹配则只返回"无匹配"，禁止任何解释。'
)

_SYSTEM_PROMPT_BUNDLE_CHARGER = (
    '你是电商库存匹配助手。ERP 商品信息是一条套装订单（充电头+数据线组合），你的任务是从候选列表中找出最匹配的充电头商品名称。\n'
    '匹配规则（全部满足才算匹配）：\n'
    '  · 功率（如 30W/45W/60W）必须一致\n'
    '  · 颜色（套装颜色标签如【蓝色套装】即为充电头颜色，白色=白）必须一致\n'
    '  · 类型必须是充电头/充电器，不能是数据线\n'
    '输出要求：只返回候选列表中的原文名称，无匹配则只返回"无匹配"，禁止任何解释。'
)


def _ai_match_product_name(
    erp_info: str,
    candidates: List[str],
    api_key: str,
    base_url: str,
    model: str,
    *,
    system_prompt: str = _SYSTEM_PROMPT_NORMAL,
) -> str:
    """
    调用 AI 从候选商品名称中找出最匹配的一条。
    返回候选中的原文名称；无匹配或调用失败返回空字符串。
    """
    try:
        from openai import OpenAI  # noqa: PLC0415
    except ImportError:
        logger.warning('openai 包未安装，无法使用 AI 匹配；请执行 pip install openai')
        return ''
    try:
        client = OpenAI(api_key=api_key, base_url=base_url)
        candidates_text = '\n'.join(f'- {name}' for name in candidates)
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {'role': 'system', 'content': system_prompt},
                {
                    'role': 'user',
                    'content': f'ERP 商品信息：{erp_info}\n\n候选商品名称：\n{candidates_text}',
                },
            ],
            max_tokens=60,
            temperature=0,
        )
        result = (resp.choices[0].message.content or '').strip()
        return result if result in candidates else ''
    except Exception as e:
        logger.warning('AI 匹配调用失败: %s', e)
        return ''


_STOCK_LINK_CELL_MAX_LEN = 2000


def _truncate_stock_link_cell(s: str, max_len: int = _STOCK_LINK_CELL_MAX_LEN) -> str:
    if len(s) <= max_len:
        return s
    return s[: max_len - 3].rstrip() + '...'


def _stock_link_unmatched_text(
    *,
    info_raw: str,
    shop: str,
    reason_lines: List[str],
) -> str:
    """未匹配时写入日志表「库存关联」的说明文本。"""
    if not (info_raw or '').strip():
        info_display = '（空）'
    else:
        info_display = info_raw.strip()
        if len(info_display) > 600:
            info_display = info_display[:597] + '...'

    reason_s = '；'.join(reason_lines) if reason_lines else '未达匹配条件'
    chunks = ['未匹配', f'原因：{reason_s}', f'商品信息：{info_display}']
    if (shop or '').strip():
        chunks.append(f'店铺：{shop.strip()}')

    return _truncate_stock_link_cell('｜'.join(chunks))


def _normalize_platform_order_sn(raw: str) -> str:
    """三表「平台订单号」可能存在全角横线、空白等差异，统一成查找键；写入飞书仍用 ERP 原文。"""
    t = unicodedata.normalize('NFKC', (raw or '').strip())
    for ch in ('－', '﹣', '–', '—', '−', '‐', '‑', '‒', '⁃', '﹘'):
        t = t.replace(ch, '-')
    t = re.sub(r'\s+', '', t)
    return t


def _merge_feishu_fields(submitted: Dict[str, Any], api_fields: Any) -> Dict[str, Any]:
    """创建接口返回的 fields 常不完整，与提交体合并，避免本地缓存缺列读不到「商品名称」。"""
    out = dict(submitted or {})
    if isinstance(api_fields, dict):
        out.update(api_fields)
    return out


def _parse_pay_after_cutoff_ms(date_str: str) -> int:
    """
    付款时间需 **严格晚于** 配置日「当天」：即仅 次日 0 点（含）之后的时刻满足条件。
    例如 pay_after=2026-04-07 时，2026-04-07 任意时刻均不满足，2026-04-08 0 点起满足。
    """
    s = (date_str or '').strip()[:10]
    y, m, d = 2026, 4, 5
    if len(s) >= 10 and s[4] == '-' and s[7] == '-':
        try:
            y, m, d = int(s[:4]), int(s[5:7]), int(s[8:10])
        except ValueError:
            pass
    dt = datetime(y, m, d, 23, 59, 59, 999000, tzinfo=TZ_SH)
    return int(dt.timestamp() * 1000)


def _start_of_day_shanghai_ms(ms: int) -> int:
    dt = datetime.fromtimestamp(ms / 1000.0, tz=TZ_SH)
    sod = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    return int(sod.timestamp() * 1000)


def _cell_float(val: Any) -> Optional[float]:
    if val is None or isinstance(val, bool):
        return None
    if isinstance(val, (int, float)):
        return float(val)
    t = feishu_field_to_text(val).replace(',', '').replace('元', '').replace('¥', '').replace('￥', '').strip()
    if not t:
        return None
    try:
        return float(t)
    except ValueError:
        return None



def _build_inventory_fields(src: Dict[str, Any], order_field: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    pk = feishu_field_to_text(src.get(order_field)).strip()
    if pk:
        out[order_field] = pk
    for k in _INVENTORY_COPY_TEXT:
        if k == order_field:
            continue
        s = feishu_field_to_text(src.get(k)).strip()
        if s:
            out[k] = s
    for k in _INVENTORY_COPY_DATE:
        ms = _feishu_cell_to_epoch_ms(src.get(k))
        if ms is not None:
            out[k] = ms
    for k in _INVENTORY_COPY_NUMBER:
        n = _cell_float(src.get(k))
        if n is not None:
            out[k] = n
    return out


def _find_best_stock_link(
    erp_fields: Dict[str, Any],
    product_names: List[str],
    *,
    ai_api_key: str = '',
    ai_base_url: str = '',
    ai_model: str = 'deepseek-v3',
    ai_cache: Optional[Dict[str, str]] = None,
) -> str:
    """
    先按类型（充电头/数据线/套装）预筛候选，再调 AI 从中找最匹配的「商品名称」。
    ai_cache 用于同一次任务内相同 ERP 商品信息的结果复用，避免重复 API 调用。
    """
    info_raw = feishu_field_to_text(erp_fields.get('商品信息')).strip()
    shop = feishu_field_to_text(erp_fields.get('店铺')).strip()

    if not product_names:
        return _stock_link_unmatched_text(
            info_raw=info_raw,
            shop=shop,
            reason_lines=['库存信息表暂无「商品名称」候选，请先在库存表维护商品名称'],
        )

    if not info_raw:
        return _stock_link_unmatched_text(
            info_raw=info_raw,
            shop=shop,
            reason_lines=['ERP 订单「商品信息」为空'],
        )

    # 类型预筛：套装只匹配套装，充电头/数据线分别匹配
    info_bundle = _detect_is_bundle(info_raw)
    info_kind = _detect_accessory_kind(info_raw)
    filtered: List[str] = []
    for name in product_names:
        name_bundle = _detect_is_bundle(name)
        if info_bundle != name_bundle:
            continue
        if not info_bundle:
            name_kind = _detect_accessory_kind(name)
            if name_kind != 'unknown' and info_kind != 'unknown' and name_kind != info_kind:
                continue
        filtered.append(name)

    if not filtered:
        return _stock_link_unmatched_text(
            info_raw=info_raw,
            shop=shop,
            reason_lines=['按商品类型筛选后无匹配候选（充电头/数据线/套装类型不符）'],
        )

    if not ai_api_key or not ai_base_url:
        return _stock_link_unmatched_text(
            info_raw=info_raw,
            shop=shop,
            reason_lines=['未配置 AI_API_KEY / AI_BASE_URL，无法进行 AI 匹配'],
        )

    # 同一商品信息在本次任务内直接复用缓存结果
    cache_key = info_raw
    if ai_cache is not None and cache_key in ai_cache:
        cached = ai_cache[cache_key]
        if cached:
            return _truncate_stock_link_cell(cached)
        return _stock_link_unmatched_text(
            info_raw=info_raw,
            shop=shop,
            reason_lines=['AI 未找到匹配商品名称'],
        )

    matched = _ai_match_product_name(info_raw, filtered, ai_api_key, ai_base_url, ai_model)
    if ai_cache is not None:
        ai_cache[cache_key] = matched

    if matched:
        return _truncate_stock_link_cell(matched)
    return _stock_link_unmatched_text(
        info_raw=info_raw,
        shop=shop,
        reason_lines=['AI 未找到匹配商品名称'],
    )


def _find_stock_link_for_kind(
    erp_fields: Dict[str, Any],
    kind_candidates: List[str],
    kind_label: str,
    *,
    ai_api_key: str = '',
    ai_base_url: str = '',
    ai_model: str = 'deepseek-v3',
    ai_cache: Optional[Dict[str, str]] = None,
    system_prompt: str = _SYSTEM_PROMPT_NORMAL,
) -> str:
    """
    套装拆解时，针对单一类别（充电头 / 数据线）的候选列表调 AI 匹配。
    cache_key 在普通 info_raw 后追加类别标签，与非套装缓存互不干扰。
    """
    info_raw = feishu_field_to_text(erp_fields.get('商品信息')).strip()
    shop = feishu_field_to_text(erp_fields.get('店铺')).strip()

    if not kind_candidates:
        return _stock_link_unmatched_text(
            info_raw=info_raw,
            shop=shop,
            reason_lines=[f'库存表中无{kind_label}类候选商品名称'],
        )
    if not ai_api_key or not ai_base_url:
        return _stock_link_unmatched_text(
            info_raw=info_raw,
            shop=shop,
            reason_lines=['未配置 AI_API_KEY / AI_BASE_URL，无法进行 AI 匹配'],
        )

    cache_key = f'{info_raw}\x00{kind_label}'
    if ai_cache is not None and cache_key in ai_cache:
        cached = ai_cache[cache_key]
        if cached:
            return _truncate_stock_link_cell(cached)
        return _stock_link_unmatched_text(
            info_raw=info_raw,
            shop=shop,
            reason_lines=[f'AI 未找到匹配的{kind_label}'],
        )

    matched = _ai_match_product_name(
        info_raw, kind_candidates, ai_api_key, ai_base_url, ai_model,
        system_prompt=system_prompt,
    )
    if ai_cache is not None:
        ai_cache[cache_key] = matched

    if matched:
        return _truncate_stock_link_cell(matched)
    return _stock_link_unmatched_text(
        info_raw=info_raw,
        shop=shop,
        reason_lines=[f'AI 未找到匹配的{kind_label}'],
    )


def _outbound_qty(src: Dict[str, Any]) -> Optional[float]:
    n = _cell_float(src.get('商品总数'))
    if n is not None:
        return float(int(n)) if n == int(n) else n
    return None


def _outbound_time_ms(src: Dict[str, Any]) -> Optional[int]:
    for key in ('发货时间', '付款时间'):
        ms = _feishu_cell_to_epoch_ms(src.get(key))
        if ms is not None:
            return ms
    return None


def _normalize_compare(val: Any, *, as_number: bool = False, as_date: bool = False) -> Any:
    if val is None:
        return None
    if as_date:
        return _feishu_cell_to_epoch_ms(val)
    if as_number:
        n = _cell_float(val)
        return n
    s = feishu_field_to_text(val).strip()
    return s if s else None


def _values_equal(
    proposed: Any,
    existing_cell: Any,
    *,
    as_number: bool = False,
    as_date: bool = False,
) -> bool:
    a = proposed
    b = _normalize_compare(existing_cell, as_number=as_number, as_date=as_date)
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    if as_number:
        return abs(float(a) - float(b)) < 1e-6
    if as_date:
        return int(a) == int(b)
    return str(a).strip() == str(b).strip()


def _filter_delta(new_fields: Dict[str, Any], existing_fields: Dict[str, Any]) -> Dict[str, Any]:
    """仅保留与飞书现有单元格不同的键（日期/数字/文本分别规范化）。"""
    out: Dict[str, Any] = {}
    date_keys = {_LOG_COL_DATE, _LOG_COL_OUT_TIME, _LOG_COL_RET_TIME}
    num_keys = {_LOG_COL_OUT_QTY, _LOG_COL_RET_QTY}
    for k, v in new_fields.items():
        if v is None:
            continue
        ex = existing_fields.get(k)
        if k in date_keys:
            if not _values_equal(v, ex, as_date=True):
                out[k] = v
        elif k in num_keys:
            if not _values_equal(v, ex, as_number=True):
                out[k] = v
        else:
            if not _values_equal(v, ex):
                out[k] = v
    return out


def _parse_return_keywords(s: str) -> List[str]:
    parts = [x.strip() for x in (s or '').replace('，', ',').split(',')]
    return [p for p in parts if p]


def _reminder_has_return(reminder: str, keywords: List[str]) -> bool:
    t = (reminder or '').strip()
    if not t or not keywords:
        return False
    return any(kw in t for kw in keywords if kw)


def run_inventory_sync_job(options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    执行一轮同步。options 可覆盖 Config（与定时任务 data 合并后传入）。

    Returns:
        success, message, 以及各类计数。
    """
    opt = options or {}

    app_token = (opt.get('app_token') or Config.PINDUODUO_FEISHU_APP_TOKEN or '').strip()
    erp_table = (opt.get('erp_table_id') or Config.PINDUODUO_ERP_FEISHU_TABLE_ID or '').strip()
    erp_view = (opt.get('erp_view_id') or Config.PINDUODUO_ERP_FEISHU_VIEW_ID or '').strip() or None
    inv_table = (opt.get('inventory_info_table_id') or Config.PINDUODUO_FEISHU_INVENTORY_INFO_TABLE_ID or '').strip()
    log_table = (opt.get('inventory_log_table_id') or Config.PINDUODUO_FEISHU_INVENTORY_LOG_TABLE_ID or '').strip()

    order_field = (opt.get('inventory_order_field') or Config.PINDUODUO_INVENTORY_INFO_ORDER_FIELD or '平台订单号').strip()
    inv_name_field = (
        opt.get('inventory_product_name_field') or Config.PINDUODUO_INVENTORY_PRODUCT_NAME_FIELD or '商品名称'
    ).strip()
    ai_api_key = (opt.get('ai_api_key') or Config.AI_API_KEY or '').strip()
    ai_base_url = (opt.get('ai_base_url') or Config.AI_BASE_URL or '').strip()
    ai_model = (opt.get('ai_model') or Config.AI_STOCK_LINK_MODEL or 'deepseek-v3').strip()
    ai_cache: Dict[str, str] = {}

    _pad = opt.get('pay_after_date')
    if _pad is not None and str(_pad).strip():
        pay_after = str(_pad).strip()
    elif INVENTORY_SYNC_PAY_AFTER_OVERRIDE:
        pay_after = INVENTORY_SYNC_PAY_AFTER_OVERRIDE.strip()
    else:
        pay_after = (Config.PINDUODUO_INVENTORY_PAY_AFTER_DATE or '2026-04-07').strip()
    cutoff_ms = _parse_pay_after_cutoff_ms(pay_after)

    kw_src = opt.get('return_keywords')
    if isinstance(kw_src, list):
        return_keywords = [str(x).strip() for x in kw_src if str(x).strip()]
    else:
        return_keywords = _parse_return_keywords(
            str(kw_src) if kw_src else (Config.PINDUODUO_INVENTORY_RETURN_KEYWORDS or '')
        )

    rex = opt.get('require_express')
    if rex is not None:
        if isinstance(rex, bool):
            require_express = rex
        else:
            require_express = str(rex).strip().lower() not in ('0', 'false', 'no', 'off')
    else:
        require_express = bool(Config.PINDUODUO_INVENTORY_LOG_REQUIRE_EXPRESS)

    if not app_token or not erp_table:
        return {
            'success': False,
            'message': '缺少 app_token 或 ERP 表 table_id',
            'eligible_count': 0,
        }
    if not inv_table:
        return {
            'success': False,
            'message': '库存信息表 table_id 为空：请在 .env 设置 PINDUODUO_FEISHU_INVENTORY_INFO_TABLE_ID 或在请求 data 中传 inventory_info_table_id',
            'eligible_count': 0,
        }
    if not log_table:
        return {
            'success': False,
            'message': '未配置扣减日志表：请在 .env 设置 PINDUODUO_FEISHU_INVENTORY_LOG_TABLE_ID',
            'eligible_count': 0,
        }

    erp_client = FeishuTableClient(app_token, erp_table)
    inv_client = FeishuTableClient(app_token, inv_table)
    log_client = FeishuTableClient(app_token, log_table)

    erp_records = erp_client.get_all_records(view_id=erp_view)
    inv_records = inv_client.get_all_records()
    log_records = log_client.get_all_records()

    # 库存表所有「商品名称」候选（用于「库存关联」匹配；只读，不写入库存表）
    product_names: List[str] = []
    _seen_product_names: Set[str] = set()
    for rec in inv_records:
        f = rec.get('fields') or {}
        name = feishu_field_to_text(f.get(inv_name_field)).strip()
        if name and name not in _seen_product_names:
            _seen_product_names.add(name)
            product_names.append(name)

    logger.info(
        '库存同步任务开始 erp_table=%s inv_table=%s log_table=%s pay_after=%s require_express=%s product_name_candidates=%d',
        erp_table,
        inv_table,
        log_table,
        pay_after,
        require_express,
        len(product_names),
    )

    # key=规范化订单号，value=该订单在日志表的所有行（套装订单可能有2行）
    log_by_order: Dict[str, List[Dict[str, Any]]] = {}
    for rec in log_records:
        rid = rec.get('record_id')
        fields = rec.get('fields') or {}
        ok_raw = feishu_field_to_text(fields.get(_LOG_COL_ORDER)).strip()
        ok_key = _normalize_platform_order_sn(ok_raw)
        if ok_key and rid:
            log_by_order.setdefault(ok_key, []).append({'record_id': rid, 'fields': fields})

    eligible_count = 0
    log_created = 0
    log_updated_out = 0
    log_skipped_out = 0
    ret_updated = 0
    ret_skipped = 0
    log_failed = 0

    log_batch: List[Dict[str, Any]] = []
    outbound_updates: List[Dict[str, Any]] = []
    return_updates: List[Dict[str, Any]] = []

    def flush_log() -> None:
        nonlocal log_batch, log_created, log_failed
        if not log_batch:
            return
        batch = log_batch
        log_batch = []
        try:
            created = log_client.batch_create_records(batch)
            if created:
                log_created += len(created)
                for item, rec in zip(batch, created):
                    flds = item.get('fields') or {}
                    ok_raw = feishu_field_to_text(flds.get(_LOG_COL_ORDER)).strip()
                    ok_key = _normalize_platform_order_sn(ok_raw)
                    rid = (rec or {}).get('record_id')
                    merged = _merge_feishu_fields(flds, (rec or {}).get('fields'))
                    if ok_key and rid:
                        log_by_order.setdefault(ok_key, []).append({'record_id': rid, 'fields': merged})
            else:
                for item in batch:
                    r = log_client.create_record(item['fields'])
                    if r and r.get('record_id'):
                        log_created += 1
                        flds = item.get('fields') or {}
                        ok_raw = feishu_field_to_text(flds.get(_LOG_COL_ORDER)).strip()
                        ok_key = _normalize_platform_order_sn(ok_raw)
                        merged = _merge_feishu_fields(flds, r.get('fields'))
                        log_by_order.setdefault(ok_key, []).append({'record_id': r['record_id'], 'fields': merged})
                    else:
                        log_failed += 1
        except Exception as e:
            logger.exception('批量创建扣减日志失败: %s', e)
            log_failed += len(batch)

    for rec in erp_records:
        fields = rec.get('fields') or {}
        pk_raw = feishu_field_to_text(fields.get(order_field)).strip()
        pk_key = _normalize_platform_order_sn(pk_raw)
        if not pk_key:
            continue
        pay_ms = _feishu_cell_to_epoch_ms(fields.get('付款时间'))
        if pay_ms is None or pay_ms <= cutoff_ms:
            continue

        eligible_count += 1

        express = feishu_field_to_text(fields.get('快递单号')).strip()
        can_log = bool(express) or not require_express

        if can_log:
            out_ms = _outbound_time_ms(fields)
            qty = _outbound_qty(fields)
            if out_ms is not None and qty is not None:
                day_ms = _start_of_day_shanghai_ms(out_ms)
                info_raw = feishu_field_to_text(fields.get('商品信息')).strip()
                is_bundle = _detect_is_bundle(info_raw)
                if is_bundle:
                    # 套装拆两条：第0条=充电头，第1条=数据线
                    # 充电头颜色=套装颜色；数据线颜色不强制对齐套装颜色（用专属 prompt）
                    charger_desc, cable_desc = _split_bundle_descriptions(info_raw)
                    charger_cands = [n for n in product_names if _detect_accessory_kind(n) == 'charger']
                    cable_cands = [n for n in product_names if _detect_accessory_kind(n) == 'cable']
                    charger_link = _find_stock_link_for_kind(
                        fields, charger_cands, '充电头',
                        ai_api_key=ai_api_key, ai_base_url=ai_base_url,
                        ai_model=ai_model, ai_cache=ai_cache,
                        system_prompt=_SYSTEM_PROMPT_BUNDLE_CHARGER,
                    )
                    cable_link = _find_stock_link_for_kind(
                        fields, cable_cands, '数据线',
                        ai_api_key=ai_api_key, ai_base_url=ai_base_url,
                        ai_model=ai_model, ai_cache=ai_cache,
                        system_prompt=_SYSTEM_PROMPT_BUNDLE_CABLE,
                    )
                    proposed_log_fields_list: List[Dict[str, Any]] = [
                        {
                            _LOG_COL_ORDER: pk_raw,
                            _LOG_COL_DATE: day_ms,
                            _LOG_COL_STOCK_LINK: charger_link,
                            _LOG_COL_OUT_TIME: out_ms,
                            _LOG_COL_OUT_QTY: qty,
                            _LOG_COL_PRODUCT_INFO: info_raw,
                            _LOG_COL_PRODUCT_NAME: _matched_name_only(charger_link) or charger_desc,
                            _LOG_COL_IS_BUNDLE: '是',
                        },
                        {
                            _LOG_COL_ORDER: pk_raw,
                            _LOG_COL_DATE: day_ms,
                            _LOG_COL_STOCK_LINK: cable_link,
                            _LOG_COL_OUT_TIME: out_ms,
                            _LOG_COL_OUT_QTY: qty,
                            _LOG_COL_PRODUCT_INFO: info_raw,
                            _LOG_COL_PRODUCT_NAME: _matched_name_only(cable_link) or cable_desc,
                            _LOG_COL_IS_BUNDLE: '是',
                        },
                    ]
                else:
                    stock_link = _find_best_stock_link(
                        fields, product_names,
                        ai_api_key=ai_api_key, ai_base_url=ai_base_url,
                        ai_model=ai_model, ai_cache=ai_cache,
                    )
                    proposed_log_fields_list = [
                        {
                            _LOG_COL_ORDER: pk_raw,
                            _LOG_COL_DATE: day_ms,
                            _LOG_COL_STOCK_LINK: stock_link,
                            _LOG_COL_OUT_TIME: out_ms,
                            _LOG_COL_OUT_QTY: qty,
                            _LOG_COL_PRODUCT_INFO: info_raw,
                            _LOG_COL_PRODUCT_NAME: info_raw,  # 非套装=商品信息原文
                            _LOG_COL_IS_BUNDLE: '否',
                        }
                    ]

                existing_entries = log_by_order.get(pk_key, [])
                for idx, log_flds in enumerate(proposed_log_fields_list):
                    # 按位置对应已有日志行；套装第0条=充电头行，第1条=数据线行
                    matched_entry = existing_entries[idx] if idx < len(existing_entries) else None
                    if matched_entry is None:
                        log_batch.append({'fields': log_flds})
                        if len(log_batch) >= 20:
                            flush_log()
                    else:
                        delta = _filter_delta(log_flds, matched_entry['fields'])
                        if delta:
                            outbound_updates.append(
                                {'record_id': matched_entry['record_id'], 'fields': delta}
                            )
                        else:
                            log_skipped_out += 1

    flush_log()

    # 退货：须在日志行已落库（含本批新建）后再处理，避免与 log_batch 同轮竞态
    for rec in erp_records:
        fields = rec.get('fields') or {}
        pk_raw = feishu_field_to_text(fields.get(order_field)).strip()
        pk_key = _normalize_platform_order_sn(pk_raw)
        if not pk_key:
            continue
        pay_ms = _feishu_cell_to_epoch_ms(fields.get('付款时间'))
        if pay_ms is None or pay_ms <= cutoff_ms:
            continue
        reminder = feishu_field_to_text(fields.get('提醒'))
        if not _reminder_has_return(reminder, return_keywords) or pk_key not in log_by_order:
            continue
        now_ms = int(datetime.now(tz=TZ_SH).timestamp() * 1000)
        rq = _outbound_qty(fields)
        if rq is None:
            rq = 1.0
        ret_fields = {
            _LOG_COL_RET_TIME: now_ms,
            _LOG_COL_RET_QTY: float(int(rq)) if rq == int(rq) else rq,
        }
        # 套装有两条日志行，退货信息同步写入所有条目
        for entry in log_by_order.get(pk_key, []):
            delta = _filter_delta(ret_fields, entry['fields'])
            if delta:
                return_updates.append({'record_id': entry['record_id'], 'fields': delta})
            else:
                ret_skipped += 1

    for i in range(0, len(outbound_updates), 20):
        chunk = outbound_updates[i : i + 20]
        try:
            ok = log_client.batch_update_records(chunk)
            if ok:
                log_updated_out += len(chunk)
                for u in chunk:
                    rid = u['record_id']
                    for entries in log_by_order.values():
                        for meta in entries:
                            if meta['record_id'] == rid:
                                meta['fields'].update(u['fields'])
                                break
            else:
                for u in chunk:
                    r = log_client.update_record(u['record_id'], u['fields'])
                    if r is not None:
                        log_updated_out += 1
                        rid = u['record_id']
                        for entries in log_by_order.values():
                            for meta in entries:
                                if meta['record_id'] == rid:
                                    meta['fields'].update(u['fields'])
                                    break
                    else:
                        log_failed += 1
        except Exception as e:
            logger.exception('批量更新出库列失败: %s', e)
            log_failed += len(chunk)

    for i in range(0, len(return_updates), 20):
        chunk = return_updates[i : i + 20]
        try:
            ok = log_client.batch_update_records(chunk)
            if ok:
                ret_updated += len(chunk)
                for u in chunk:
                    rid = u['record_id']
                    for entries in log_by_order.values():
                        for meta in entries:
                            if meta['record_id'] == rid:
                                meta['fields'].update(u['fields'])
                                break
            else:
                for u in chunk:
                    r = log_client.update_record(u['record_id'], u['fields'])
                    if r is not None:
                        ret_updated += 1
        except Exception as e:
            logger.exception('批量更新退货列失败: %s', e)
            log_failed += len(chunk)

    msg = (
        f'扫描 ERP {len(erp_records)} 行，符合条件 {eligible_count}；'
        f'日志新建 {log_created}，出库更新 {log_updated_out}，出库无变化跳过 {log_skipped_out}；'
        f'退货更新 {ret_updated}，退货无变化跳过 {ret_skipped}；日志失败 {log_failed}'
    )
    logger.info(msg)
    return {
        'success': True,
        'message': msg,
        'eligible_count': eligible_count,
        'erp_row_count': len(erp_records),
        'log_created': log_created,
        'log_outbound_updated': log_updated_out,
        'log_outbound_skipped_no_delta': log_skipped_out,
        'log_return_updated': ret_updated,
        'log_return_skipped_no_delta': ret_skipped,
        'log_failed': log_failed,
    }
