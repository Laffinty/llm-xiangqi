"""
MCP工具基类

所有MCP工具都应继承此基类，实现execute方法
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from dataclasses import dataclass


@dataclass
class ToolResult:
    """工具执行结果"""

    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {"success": self.success}
        if self.data:
            result.update(self.data)
        if self.error:
            result["error"] = self.error
        return result


class BaseTool(ABC):
    """MCP工具基类"""

    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self._enabled: bool = True

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """执行工具

        Returns:
            ToolResult: 工具执行结果
        """
        pass

    @property
    def enabled(self) -> bool:
        """工具是否启用"""
        return self._enabled

    def set_enabled(self, enabled: bool):
        """设置工具启用状态"""
        self._enabled = enabled

    def get_schema(self) -> Dict[str, Any]:
        """获取工具的JSON Schema（供LLM调用）"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self._get_parameters_schema(),
            },
        }

    def _get_parameters_schema(self) -> Dict[str, Any]:
        """获取参数schema，子类可重写"""
        return {"type": "object", "properties": {}, "required": []}

    def validate_arguments(self, **kwargs) -> Optional[str]:
        """验证参数，返回错误信息或None"""
        return None
