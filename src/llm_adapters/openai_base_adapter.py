"""
OpenAI 兼容协议适配器基类

提取 DeepSeek、MiMo 等 OpenAI 兼容适配器的公共逻辑：
- AsyncOpenAI 客户端创建
- chat() 参数构建 + 指数退避重试 + TimeoutError 处理
- 响应解析（tool_calls + reasoning_content → thought 映射）
- 资源释放
"""

import json
import asyncio
from typing import List, Dict, Any, Optional

from openai import AsyncOpenAI

from .base_adapter import BaseLLMAdapter, LLMResponse


class OpenAICompatibleAdapter(BaseLLMAdapter):
    """OpenAI 兼容协议适配器基类

    适用于所有使用 OpenAI Chat Completions API 格式的 LLM 服务。
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
        max_tokens: int = 2048,
        thinking: Optional[bool] = None,
    ):
        super().__init__(
            api_key=api_key,
            model=model,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            temperature=temperature,
            max_tokens=max_tokens,
            thinking=thinking,
        )

        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=timeout)

    async def chat(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict]] = None,
        **kwargs,
    ) -> LLMResponse:
        """发送聊天请求（支持 Function Calling）"""
        import time

        params = {
            "model": self.model,
            "messages": messages,
            "temperature": kwargs.get("temperature", self.temperature),
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
        }

        # 深度求两家都是 thinking model。开着 thinking 时思维链会吃光
        # max_tokens，content 返回空字符串、走步只能从截断的思考里正则刨
        # （见 docs/skill-mode-design.md 事实 F-017）。thinking=None 表示
        # 不干预，交给供应商默认行为。
        thinking = kwargs.get("thinking", self.thinking)
        if thinking is not None:
            params["extra_body"] = {"thinking": {"type": "enabled" if thinking else "disabled"}}

        if tools:
            params["tools"] = tools
            params["tool_choice"] = kwargs.get("tool_choice", "auto")

        # 路径二：response_format 约束。不是所有供应商都支持 json_schema（
        # DeepSeek 直接返回 400，见 F-012），故不能无条件注入。
        if kwargs.get("response_format") is not None:
            params["response_format"] = kwargs["response_format"]

        last_error = None
        start_time = time.perf_counter()

        for attempt in range(self.max_retries):
            try:
                response = await self.client.chat.completions.create(**params)
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                # 简单的性能日志，可由子类覆盖实现更复杂的指标收集
                if hasattr(self, "_log_performance"):
                    self._log_performance(elapsed_ms, attempt + 1, None)
                return self._parse_response(response)
            except asyncio.TimeoutError:
                last_error = Exception(
                    f"{self.model} API timeout after {self.timeout}s"
                )
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2**attempt)
            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2**attempt)

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        if hasattr(self, "_log_performance"):
            self._log_performance(elapsed_ms, self.max_retries, last_error)

        raise last_error or Exception(f"{self.model} API call failed")

    def _parse_response(self, response) -> LLMResponse:
        """解析 OpenAI 兼容响应，统一映射到 LLMResponse"""
        if not response.choices:
            return LLMResponse(content="", raw_response=response)

        choice = response.choices[0]

        # 提取 tool_calls
        tool_calls = None
        if choice.finish_reason == "tool_calls" or choice.message.tool_calls:
            tool_calls = []
            for tc in choice.message.tool_calls or []:
                try:
                    args = (
                        json.loads(tc.function.arguments)
                        if isinstance(tc.function.arguments, str)
                        else tc.function.arguments
                    )
                except json.JSONDecodeError:
                    args = {}
                tool_calls.append({
                    "id": getattr(tc, "id", None) or "",
                    "name": tc.function.name,
                    "arguments": args,
                })

        # 提取 thought（reasoning_content），适用于 GLM、MiMo 等推理模型
        thought = None
        if (
            hasattr(choice.message, "reasoning_content")
            and choice.message.reasoning_content
        ):
            thought = choice.message.reasoning_content

        return LLMResponse(
            content=choice.message.content or "",
            thought=thought,
            tool_calls=tool_calls,
            raw_response=response,
        )

    async def close(self):
        """关闭连接"""
        await self.client.close()
