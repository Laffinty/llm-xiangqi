"""
MiMo LLM适配器

支持小米MiMo系列API（OpenAI兼容）
"""

from typing import Optional

from .openai_base_adapter import OpenAICompatibleAdapter


class MiMoAdapter(OpenAICompatibleAdapter):
    # 实测：该供应商支持 response_format: json_schema + strict，且在完整对局
    # prompt 下优先于 tool_choice=required（它会忽视 required，F-025）。
    supports_response_format_json_schema = True

    """MiMo LLM适配器

    API格式:
    - Base URL: https://api.xiaomimimo.com/v1
    - 模型: mimo-v2.6-pro, mimo-v2.6-flash, mimo-v2.6-pro-ultraspeed
    - 协议: OpenAI兼容

    注: mimo-v2.5-pro / mimo-v2.5 将于 2026-10-21 下线；v2-pro / v2-omni / v2-flash 已不存在。
    """

    def __init__(
        self,
        api_key: str,
        model: str = "mimo-v2.6-flash",
        base_url: str = "https://api.xiaomimimo.com/v1",
        timeout: int = 60,
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
