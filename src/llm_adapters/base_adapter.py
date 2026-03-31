"""
LLM适配器基类

统一接口，支持多LLM后端（DeepSeek、MiniMax等）
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, TypedDict


# 类型定义
class MessageDict(TypedDict):
    """消息字典类型"""
    role: str
    content: str


class ToolCallDict(TypedDict):
    """工具调用字典类型"""
    name: str
    arguments: Dict[str, Any]


@dataclass
class LLMResponse:
    """LLM响应结构"""
    content: str
    thought: Optional[str] = None
    tool_calls: Optional[List[ToolCallDict]] = None
    raw_response: Optional[Any] = None

    def has_tool_calls(self) -> bool:
        """检查是否有工具调用"""
        return self.tool_calls is not None and len(self.tool_calls) > 0


@dataclass
class ToolCall:
    """工具调用结构"""
    name: str
    arguments: Dict[str, Any]


class BaseLLMAdapter(ABC):
    """LLM适配器基类
    
    支持异步上下文管理器语法：
        async with DeepSeekAdapter(...) as adapter:
            response = await adapter.chat(...)
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
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max_retries
        self.temperature = temperature
        self.max_tokens = max_tokens
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口，确保资源被释放"""
        await self.close()
    
    def _mask_api_key(self, key: str) -> str:
        """API Key脱敏显示
        
        用于日志记录，避免泄露完整API Key。
        
        Args:
            key: 原始API Key
            
        Returns:
            脱敏后的API Key，如 "sk-ab...xyz"
        """
        if not key or len(key) <= 8:
            return "***"
        return f"{key[:4]}...{key[-4:]}"

    @abstractmethod
    async def chat(
        self,
        messages: List[MessageDict],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs: Any
    ) -> LLMResponse:
        """发送聊天请求

        Args:
            messages: 消息列表，格式 [{"role": "user"/"assistant"/"system", "content": "..."}]
            tools: 可选的tools定义列表
            **kwargs: 其他参数如temperature, max_tokens等

        Returns:
            LLMResponse: LLM响应
        """
        pass

    @abstractmethod
    async def close(self):
        """关闭连接/清理资源"""
        pass

    def build_messages(
        self,
        system_prompt: str,
        user_content: str,
        history: Optional[List[MessageDict]] = None
    ) -> List[MessageDict]:
        """构建消息列表

        Args:
            system_prompt: 系统提示
            user_content: 用户消息内容
            history: 可选的对话历史

        Returns:
            格式化的消息列表
        """
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        if history:
            messages.extend(history)

        messages.append({"role": "user", "content": user_content})

        return messages
