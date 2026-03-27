"""
MiniMax LLM适配器

支持MiniMax API（Anthropic兼容模式）
"""

from .anthropic_base_adapter import AnthropicCompatibleAdapter


class MiniMaxAdapter(AnthropicCompatibleAdapter):
    """MiniMax LLM适配器

    API格式:
    - Base URL: https://api.minimaxi.com/anthropic
    - 模型: MiniMax-M2.7
    - 协议: Anthropic SDK兼容
    """

    def __init__(
        self,
        api_key: str,
        model: str = "MiniMax-M2.7",
        base_url: str = "https://api.minimaxi.com/anthropic",
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
