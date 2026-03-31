"""
外部工具示例

此目录用于存放自定义MCP工具
工具类需继承 BaseTool 并实现 execute 方法
"""

from typing import Any, Dict, Optional
import sys
import os

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from src.mcp_tools.base_tool import BaseTool, ToolResult


class ExampleTool(BaseTool):
    """示例工具 - 供开发者参考"""

    def __init__(self):
        super().__init__(
            name="example_tool",
            description="这是一个示例工具，展示如何创建自定义MCP工具",
        )

    def _get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {"input": {"type": "string", "description": "输入参数"}},
            "required": ["input"],
        }

    async def execute(self, **kwargs) -> ToolResult:
        input_value = kwargs.get("input", "")
        return ToolResult(
            success=True,
            data={"echo": input_value, "message": f"收到输入: {input_value}"},
        )

    def validate_arguments(self, **kwargs) -> Optional[str]:
        if not kwargs.get("input"):
            return "缺少必需参数: input"
        return None
