"""
AI 大脑 — LLM 客户端
封装 OpenAI 兼容接口，供 ask() / ask_stream() 使用。
其他模块通过 src/ai/__init__.py 的公共 API 调用，不直接使用本模块。
"""
from __future__ import annotations

import logging
from typing import Iterator, List, Optional

logger = logging.getLogger('ai.client')


class LLMClient:
    """OpenAI 兼容 LLM 客户端（懒加载，首次调用时才初始化）"""

    def __init__(
        self,
        api_key: str = '',
        base_url: str = '',
        default_model: str = '',
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._default_model = default_model
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
        )
    return _default_client
