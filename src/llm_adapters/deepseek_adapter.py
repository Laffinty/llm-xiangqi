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
    - 模型: deepseek-flash（通用/低延迟）, deepseek-v4-pro（复杂推理）
    - 协议: OpenAI兼容
    - 在线模型表: GET https://api.deepseek.com/models

    注: deepseek-chat / deepseek-reasoner 已于 2026-07-24 完全退役，不再可用。
    """

    def __init__(
        self,
        api_key: str,
        model: str = "deepseek-flash",
        base_url: str = "https://api.deepseek.com",
        timeout: int = 30,
        max_retries: int = 3,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        thinking: Optional[bool] = None
    ):
        super().__init__(
            api_key=api_key,
            model=model,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            temperature=temperature,
            max_tokens=max_tokens,
            thinking=thinking
        )
