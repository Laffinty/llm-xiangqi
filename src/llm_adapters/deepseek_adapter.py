"""
DeepSeek LLM适配器

支持DeepSeek Chat API（OpenAI兼容）
"""

from typing import Optional

from .openai_base_adapter import OpenAICompatibleAdapter


class DeepSeekAdapter(OpenAICompatibleAdapter):
    """DeepSeek LLM适配器

    API格式:
    - Base URL: https://api.deepseek.com
    - 模型: deepseek-chat, deepseek-reasoner
    - 协议: OpenAI兼容
    """

    def __init__(
        self,
        api_key: str,
        model: str = "deepseek-chat",
        base_url: str = "https://api.deepseek.com",
        timeout: int = 30,
        max_retries: int = 3,
        temperature: float = 0.7,
        max_tokens: int = 2048
    ):
        super().__init__(
            api_key=api_key,
            model=model,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            temperature=temperature,
            max_tokens=max_tokens
        )
