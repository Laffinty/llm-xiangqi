"""
Anthropic 兼容协议适配器基类

提取 MiniMax 等 Anthropic 兼容适配器的公共逻辑：
- system 消息提取（从 messages 中分离为独立参数）
- 消息格式转换（str content → content blocks 数组）
- 同步 SDK 异步包装（run_in_executor + wait_for）
- 递增超时重试策略（1.5x, cap 60s）
- 响应解析（thinking / text / tool_use 块）
"""

import os
import asyncio
from typing import List, Dict, Any, Optional

import anthropic

from .base_adapter import BaseLLMAdapter, LLMResponse


class AnthropicCompatibleAdapter(BaseLLMAdapter):
    """Anthropic 兼容协议适配器基类

    适用于所有使用 Anthropic Messages API 格式的 LLM 服务。
    子类只需覆盖 __init__ 中的默认 model 和 base_url。
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str,
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

        os.environ["ANTHROPIC_BASE_URL"] = base_url
        os.environ["ANTHROPIC_API_KEY"] = api_key

        self.client = anthropic.Anthropic(timeout=timeout)

    async def chat(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict]] = None,
        **kwargs
    ) -> LLMResponse:
        """发送聊天请求（支持 thinking 和 tool_use）"""

        # 提取 system 消息
        system_msg = ""
        filtered_messages = []
        for msg in messages:
            if msg.get("role") == "system":
                system_msg = msg.get("content", "")
            else:
                filtered_messages.append(msg)

        # 转换为 Anthropic content-blocks 格式
        anthropic_messages = []
        for msg in filtered_messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                anthropic_messages.append({
                    "role": msg["role"],
                    "content": [{"type": "text", "text": content}]
                })
            elif isinstance(content, list):
                anthropic_messages.append({
                    "role": msg["role"],
                    "content": content
                })

        params: Dict[str, Any] = {
            "model": self.model,
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
            "temperature": kwargs.get("temperature", self.temperature),
            "system": system_msg,
            "messages": anthropic_messages,
        }

        if tools:
            params["tools"] = tools

        # 重试逻辑（递增超时保护）
        last_error = None
        timeout = self.timeout

        for attempt in range(self.max_retries):
            try:
                loop = asyncio.get_event_loop()
                response = await asyncio.wait_for(
                    loop.run_in_executor(
                        None,
                        lambda: self.client.messages.create(**params)
                    ),
                    timeout=timeout
                )
                return self._parse_response(response)
            except asyncio.TimeoutError:
                last_error = Exception(f"{self.model} API timeout after {timeout}s")
                timeout = min(timeout * 1.5, 60)
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)

        raise last_error or Exception(f"{self.model} API call failed")

    def _parse_response(self, response) -> LLMResponse:
        """解析 Anthropic 响应，统一映射到 LLMResponse"""
        thought = None
        text_content = []
        tool_calls = None

        for block in response.content:
            if block.type == "thinking":
                thought = block.thinking
            elif block.type == "text":
                text_content.append(block.text)
            elif block.type == "tool_use":
                tool_calls = tool_calls or []
                tool_calls.append({
                    "name": block.name,
                    "arguments": block.input
                })

        return LLMResponse(
            content="\n".join(text_content),
            thought=thought,
            tool_calls=tool_calls,
            raw_response=response
        )

    async def close(self):
        """关闭连接（Anthropic SDK 不需要显式关闭）"""
        pass
