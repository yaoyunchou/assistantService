"""
飞书自定义机器人 Webhook 通知。

文档：https://open.feishu.cn/document/client-docs/bot-v3/add-custom-bot
交互卡片字段说明：https://open.feishu.cn/document/common-capabilities/message-card/message-cards-content/using-markdown-tags
上传图片（换 img_key）：https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/im-v1/image/create

说明：
- 若机器人开启了「签名校验」或「关键词」，需在飞书端配置；返回 code=19024 常见为关键词不匹配。
- **Base64 二维码 / 截图**：Webhook 卡片内「图片」组件必须使用 **img_key**。本模块会解码 base64 后调用开放平台 **im/v1/images**（需配置 FEISHU_APP_ID / FEISHU_APP_SECRET，且应用具备上传图片相关权限）。
- **image_url**：仍用 lark_md 的 ![](url)，需公网 HTTPS。
"""
from __future__ import annotations

import base64
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import requests

from tools.feishu.feishu_client import FeishuClient
from utils.logger import get_logger

logger = get_logger('FeishuWebhook')

# 标题栏配色：blue | wathet | turquoise | green | yellow | orange | red | carmine | violet | purple | indigo | grey
_DEFAULT_HEADER_TEMPLATE = 'blue'

_IMG_UPLOAD_URL = 'https://open.feishu.cn/open-apis/im/v1/images'


def _decode_base64_image(image_base64: str) -> Tuple[bytes, str]:
    """
    将 data URL 或纯 base64 解码为图片字节。
    Returns: (bytes, filename_for_upload)
    """
    s = (image_base64 or '').strip()
    if not s:
        raise ValueError('image_base64 为空')

    filename = 'qrcode.png'
    if s.startswith('data:'):
        meta, _, b64_part = s.partition(',')
        meta_lower = meta.lower()
        if 'png' in meta_lower:
            filename = 'qrcode.png'
        elif 'jpeg' in meta_lower or 'jpg' in meta_lower:
            filename = 'qrcode.jpg'
        elif 'gif' in meta_lower:
            filename = 'qrcode.gif'
        elif 'webp' in meta_lower:
            filename = 'qrcode.webp'
        s = b64_part

    raw = base64.b64decode(s, validate=False)
    if not raw:
        raise ValueError('base64 解码后长度为 0')
    return raw, filename


def upload_image_get_img_key(
    client: FeishuClient,
    image_bytes: bytes,
    filename: str = 'qrcode.png',
) -> Optional[str]:
    """调用 im/v1/images 上传图片，返回用于卡片 img 组件的 image_key。"""
    token = client.get_tenant_access_token()
    if not token:
        logger.error('无法获取 tenant_access_token，不能上传二维码图片')
        return None

    try:
        files = {'image': (filename, image_bytes)}
        data = {'image_type': 'message'}
        headers = {'Authorization': f'Bearer {token}'}
        r = requests.post(_IMG_UPLOAD_URL, headers=headers, files=files, data=data, timeout=60)
        body = r.json()
        if body.get('code') == 0 and body.get('data'):
            key = body['data'].get('image_key')
            if key:
                logger.info('飞书图片上传成功，image_key 已就绪')
                return key
        logger.warning('飞书图片上传失败: %s', body)
    except Exception as e:
        logger.exception('飞书图片上传异常: %s', e)
    return None


def build_sync_notification_card(
    system_title: str,
    description: str,
    link_url: str,
    link_text: str = '查看详情',
    image_url: Optional[str] = None,
    image_base64: Optional[str] = None,
    feishu_client: Optional[FeishuClient] = None,
    footer: Optional[str] = None,
    header_template: str = _DEFAULT_HEADER_TEMPLATE,
    custom_bot_keyword: Optional[str] = None,
) -> Dict[str, Any]:
    """
    构建「同步通知」交互式卡片 body（与 msg_type=interactive 一起 POST）。

    :param system_title: 卡片标题（对应系统 / 业务名称）
    :param description: 正文描述，支持少量 Markdown（换行即可）
    :param link_url: 主要跳转链接
    :param link_text: 主按钮文案
    :param image_url: 可选配图 URL（HTTPS，公网可访问；写入 lark_md）
    :param image_base64: 可选 **Base64 图片**（支持 `data:image/png;base64,....` 或纯 base64）。
           将经开放平台上传得到 **img_key** 后插入卡片 **img** 组件（与 Web 登录二维码一致时推荐此方式）。
    :param feishu_client: 用于上传图片；不传则在本函数内尝试 `FeishuClient()`（需已配置 App ID/Secret）
    :param footer: 底栏备注，默认带发送时间
    :param header_template: 标题栏颜色主题
    :param custom_bot_keyword: 自定义机器人若启用「关键词」安全设置，整条消息需 **包含** 该词，否则会返回 code=19024。
    """
    time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    footer_line = footer if footer is not None else f'发送时间 · {time_str} · 如意助手'

    kw = (custom_bot_keyword or '').strip()
    title_content = (system_title or '系统通知').strip()[:200]
    if kw and kw not in title_content:
        title_content = f'{kw} · {title_content}'[:200]

    desc_body = description.strip() or '（无补充说明）'
    if kw and kw not in desc_body:
        desc_body = f'{kw}\n\n{desc_body}'

    md_lines: List[str] = [
        '**📌 同步说明**',
        desc_body,
    ]
    if link_url:
        md_lines.append(f'**🔗 链接**　[{link_text}]({link_url})')

    img_key_for_card: Optional[str] = None
    if image_base64 and str(image_base64).strip():
        try:
            blob, fname = _decode_base64_image(image_base64)
            uploader = feishu_client
            if uploader is None and FeishuClient().is_configured():
                uploader = FeishuClient()
            if uploader and uploader.is_configured():
                img_key_for_card = upload_image_get_img_key(uploader, blob, filename=fname)
            if not img_key_for_card:
                md_lines.append('**📷 二维码**（图片上传失败：请检查飞书应用凭据与「上传图片/资源」类权限）')
        except Exception as e:
            logger.warning('解析或上传 Base64 图片失败: %s', e)
            md_lines.append(f'**📷 二维码**（Base64 处理失败: {e}）')

    if image_url and str(image_url).strip() and not img_key_for_card:
        md_lines.append('**📷 配图（链接）**')
        md_lines.append(f'![preview]({image_url.strip()})')

    if img_key_for_card:
        md_lines.append('**📷 二维码**（见下图）')

    elements: List[Dict[str, Any]] = [
        {
            'tag': 'div',
            'text': {
                'tag': 'lark_md',
                'content': '\n\n'.join(md_lines),
            },
        },
    ]

    if img_key_for_card:
        elements.append({
            'tag': 'img',
            'img_key': img_key_for_card,
            'alt': {'tag': 'plain_text', 'content': '二维码'},
        })

    if link_url:
        elements.append({
            'tag': 'action',
            'actions': [
                {
                    'tag': 'button',
                    'text': {'tag': 'plain_text', 'content': link_text[:80]},
                    'type': 'primary',
                    'url': link_url,
                },
            ],
        })

    elements.append({'tag': 'hr'})
    elements.append({
        'tag': 'note',
        'elements': [{'tag': 'plain_text', 'content': footer_line[:500]}],
    })

    card: Dict[str, Any] = {
        'config': {
            'wide_screen_mode': True,
            'enable_forward': True,
        },
        'header': {
            'template': header_template,
            'title': {
                'tag': 'plain_text',
                'content': title_content,
            },
        },
        'elements': elements,
    }

    return {
        'msg_type': 'interactive',
        'card': card,
    }


def send_webhook_raw(webhook_url: str, payload: Dict[str, Any], timeout: int = 15) -> Dict[str, Any]:
    """
    POST 原始 JSON 到飞书机器人 Webhook。

    Returns:
        解析后的响应 JSON；失败时仍尽量返回 dict（含 _http_error）
    """
    if not webhook_url or not str(webhook_url).strip():
        logger.warning('未配置 webhook_url，跳过发送')
        return {'ok': False, 'error': 'empty_webhook_url'}

    url = webhook_url.strip()
    try:
        r = requests.post(
            url,
            json=payload,
            headers={'Content-Type': 'application/json; charset=utf-8'},
            timeout=timeout,
        )
        text = r.text
        try:
            data = r.json()
        except Exception:
            data = {'raw': text[:2000]}

        ok = r.status_code == 200 and isinstance(data, dict) and data.get('code') == 0
        if ok:
            logger.info('飞书 Webhook 发送成功')
        else:
            logger.warning(
                '飞书 Webhook 返回非成功: http=%s body=%s',
                r.status_code,
                data,
            )
        return {'ok': ok, 'status_code': r.status_code, 'data': data}
    except requests.RequestException as e:
        logger.exception('飞书 Webhook 请求失败: %s', e)
        return {'ok': False, 'error': str(e), '_http_error': True}


def send_sync_notification(
    webhook_url: str,
    system_title: str,
    description: str,
    link_url: str,
    link_text: str = '查看详情',
    image_url: Optional[str] = None,
    image_base64: Optional[str] = None,
    feishu_client: Optional[FeishuClient] = None,
    footer: Optional[str] = None,
    header_template: str = _DEFAULT_HEADER_TEMPLATE,
    custom_bot_keyword: Optional[str] = None,
) -> Dict[str, Any]:
    """
    使用同步通知模板构建卡片并发送。
    """
    payload = build_sync_notification_card(
        system_title=system_title,
        description=description,
        link_url=link_url,
        link_text=link_text,
        image_url=image_url,
        image_base64=image_base64,
        feishu_client=feishu_client,
        footer=footer,
        header_template=header_template,
        custom_bot_keyword=custom_bot_keyword,
    )
    return send_webhook_raw(webhook_url, payload)
