"""
MiMo LLM适配器

支持小米MiMo系列API（OpenAI兼容）
"""

from .openai_base_adapter import OpenAICompatibleAdapter


class MiMoAdapter(OpenAICompatibleAdapter):
    """MiMo LLM适配器

    API格式:
    - Base URL: https://api.xiaomimimo.com/v1
    - 模型: mimo-v2-pro, mimo-v2-omni, mimo-v2-flash
    - 协议: OpenAI兼容
    """

    def __init__(
        self,
        api_key: str,
        model: str = "mimo-v2-pro",
        base_url: str = "https://api.xiaomimimo.com/v1",
        timeout: int = 60,
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
