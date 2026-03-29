"""
按业务模块维护飞书自定义机器人 Webhook URL（渠道 / 模块维度）。

- 环境变量可覆盖代码中的默认 URL（推荐生产环境仅用 .env，避免 Hook 泄露到仓库）。
- 飞书若开启「自定义关键词」，消息正文须包含该词，否则会返回 **code=19024**（见开放平台说明）。

用法示例::

    from tools.feishu.webhook.qudao_notify import CHANNEL_PINDUODUO, get_webhook_url, get_custom_bot_keyword
    url = get_webhook_url(CHANNEL_PINDUODUO)
    kw = get_custom_bot_keyword(CHANNEL_PINDUODUO)
"""
from __future__ import annotations

import os
from typing import Dict, Optional

# —— 模块标识（引用时请使用常量，避免手写字符串散落）——
CHANNEL_PINDUODUO = 'pinduoduo'
CHANNEL_DEFAULT = 'default'  # 通用：读 FEISHU_SYNC_WEBHOOK_URL，无代码内默认 URL

# 环境变量名 → 覆盖对应模块的 Webhook（非空则优先于下方代码默认值）
_ENV_WEBHOOK_BY_CHANNEL: Dict[str, str] = {
    CHANNEL_PINDUODUO: 'FEISHU_WEBHOOK_PINDUODUO',
    CHANNEL_DEFAULT: 'FEISHU_SYNC_WEBHOOK_URL',
}

# 代码内默认 Hook（仅 pinduoduo；其它模块请通过 env 或后续扩展本表）
_DEFAULT_WEBHOOK_BY_CHANNEL: Dict[str, str] = {
    CHANNEL_PINDUODUO: (
        'https://open.feishu.cn/open-apis/bot/v2/hook/'
        '0e817c93-e7a2-4c33-ad20-c0ef08a71c7b'
    ),
}

# 关键词：若环境变量「已设置」（含置空），则以环境为准；未设置时用默认值，满足常见「拼多多」机器人关键词
_ENV_KEYWORD_BY_CHANNEL: Dict[str, str] = {
    CHANNEL_PINDUODUO: 'FEISHU_WEBHOOK_PINDUODUO_KEYWORD',
}

_DEFAULT_KEYWORD_BY_CHANNEL: Dict[str, str] = {
    CHANNEL_PINDUODUO: '拼多多',
}


def get_webhook_url(channel: str) -> Optional[str]:
    """
    解析指定模块的 Webhook 完整 URL。

    优先级：对应环境变量（非空） > 内置默认值（若有）> default 通道的 FEISHU_SYNC_WEBHOOK_URL（仅当 channel 为 pinduoduo 且无默认时不再fallback，pinduoduo 有内置 URL）。

    新增模块时：在 _ENV_WEBHOOK_BY_CHANNEL、可选 _DEFAULT_WEBHOOK_BY_CHANNEL 中登记。
    """
    ch = (channel or '').strip().lower()
    if not ch:
        ch = CHANNEL_DEFAULT

    env_name = _ENV_WEBHOOK_BY_CHANNEL.get(ch)
    if env_name:
        from_env = (os.getenv(env_name) or '').strip()
        if from_env:
            return from_env

    built_in = (_DEFAULT_WEBHOOK_BY_CHANNEL.get(ch) or '').strip()
    if built_in:
        return built_in

    if ch != CHANNEL_DEFAULT:
        # 未单独配置时，允许退回通用 Webhook
        return get_webhook_url(CHANNEL_DEFAULT)

    return (os.getenv(_ENV_WEBHOOK_BY_CHANNEL[CHANNEL_DEFAULT]) or '').strip() or None


def get_custom_bot_keyword(channel: str) -> Optional[str]:
    """
    飞书自定义机器人「关键词」校验用：返回需写入卡片标题/正文的词；不需要时返回 None。

    若设置环境变量 FEISHU_WEBHOOK_PINDUODUO_KEYWORD 且为空字符串，表示关闭注入（你在后台关闭了关键词时使用）。
    """
    ch = (channel or '').strip().lower()
    env_name = _ENV_KEYWORD_BY_CHANNEL.get(ch)
    if env_name and env_name in os.environ:
        v = (os.getenv(env_name) or '').strip()
        return v if v else None
    default = (_DEFAULT_KEYWORD_BY_CHANNEL.get(ch) or '').strip()
    return default if default else None
