"""
AI 大脑 — LLM 客户端
封装 OpenAI 兼容接口，供 ask() / ask_stream() / ask_vision() 使用。
其他模块通过 src/ai/__init__.py 的公共 API 调用，不直接使用本模块。
"""
from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Iterator, Optional, Union

logger = logging.getLogger('ai.client')


class LLMClient:
    """OpenAI 兼容 LLM 客户端（懒加载，首次调用时才初始化）"""

    def __init__(
        self,
        api_key: str = '',
        base_url: str = '',
        default_model: str = '',
        vision_model: str = '',
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._default_model = default_model
        self._vision_model = vision_model
        self._client = None  # 懒加载

    def _get_client(self):
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError:
                raise RuntimeError('openai 包未安装，请执行: pip install openai')
            if not self._api_key:
                raise RuntimeError('AI_API_KEY 未配置，无法使用 LLM 简单问答功能')
            self._client = OpenAI(
                api_key=self._api_key,
                base_url=self._base_url or None,
            )
        return self._client

    def complete(
        self,
        prompt: str,
        *,
        system: str = '',
        model: str = '',
        max_tokens: int = 500,
        temperature: float = 0.0,
    ) -> str:
        """同步文本补全，返回助手回复字符串"""
        client = self._get_client()
        messages = []
        if system:
            messages.append({'role': 'system', 'content': system})
        messages.append({'role': 'user', 'content': prompt})
        try:
            resp = client.chat.completions.create(
                model=model or self._default_model or 'gpt-3.5-turbo',
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return (resp.choices[0].message.content or '').strip()
        except Exception as e:
            logger.error('LLM complete 调用失败: %s', e)
            raise

    def complete_vision(
        self,
        prompt: str,
        image: Union[str, Path, bytes],
        *,
        system: str = '',
        model: str = '',
        max_tokens: int = 200,
        temperature: float = 0.0,
        mime_type: str = 'image/png',
    ) -> str:
        """多模态识图：把图片以 data URL 传给视觉模型，返回助手回复。"""
        client = self._get_client()
        if isinstance(image, (str, Path)):
            raw = Path(image).read_bytes()
        else:
            raw = image
        b64 = base64.b64encode(raw).decode()
        data_url = f'data:{mime_type};base64,{b64}'

        messages = []
        if system:
            messages.append({'role': 'system', 'content': system})
        messages.append({
            'role': 'user',
            'content': [
                {'type': 'text', 'text': prompt},
                {'type': 'image_url', 'image_url': {'url': data_url}},
            ],
        })
        use_model = (
            model
            or self._vision_model
            or self._default_model
            or 'gpt-4o-mini'
        )
        try:
            resp = client.chat.completions.create(
                model=use_model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return (resp.choices[0].message.content or '').strip()
        except Exception as e:
            logger.error('LLM vision 调用失败 model=%s: %s', use_model, e)
            raise

    def complete_stream(
        self,
        prompt: str,
        *,
        system: str = '',
        model: str = '',
        max_tokens: int = 2000,
    ) -> Iterator[str]:
        """流式文本补全，逐块 yield 文本"""
        client = self._get_client()
        messages = []
        if system:
            messages.append({'role': 'system', 'content': system})
        messages.append({'role': 'user', 'content': prompt})
        try:
            stream = client.chat.completions.create(
                model=model or self._default_model or 'gpt-3.5-turbo',
                messages=messages,
                max_tokens=max_tokens,
                stream=True,
            )
            for chunk in stream:
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    yield delta.content
        except Exception as e:
            logger.error('LLM stream 调用失败: %s', e)
            raise


# 模块级单例（懒初始化，首次调用时从 Config 读取）
_default_client: Optional[LLMClient] = None


def get_default_client() -> LLMClient:
    global _default_client
    if _default_client is None:
        from config import Config
        _default_client = LLMClient(
            api_key=Config.AI_API_KEY,
            base_url=Config.AI_BASE_URL,
            default_model=Config.AI_STOCK_LINK_MODEL,
            vision_model=getattr(Config, 'AI_VISION_MODEL', '') or '',
        )
    return _default_client
