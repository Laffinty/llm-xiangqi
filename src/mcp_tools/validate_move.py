"""
走步验证工具

验证走步合法性并给出解释
"""

from typing import Any, Dict, Optional

from .base_tool import BaseTool, ToolResult


class ValidateMoveTool(BaseTool):
    """走步验证工具"""

    def __init__(self, name: str = "validate_and_explain", description: str = ""):
        if not description:
            description = "验证走步并给出解释"
        super().__init__(name, description)

    def _get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "fen": {"type": "string", "description": "当前局面FEN字符串"},
                "move": {"type": "string", "description": "要验证的ICCS走步（如h2e2）"},
            },
            "required": ["fen", "move"],
        }

    async def execute(self, **kwargs) -> ToolResult:
        """执行走步验证"""
        fen = kwargs.get("fen", "")
        move = kwargs.get("move", "")

        if not fen:
            return ToolResult(success=False, error="缺少fen参数")
        if not move:
            return ToolResult(success=False, error="缺少move参数")

        try:
            from ..core.referee_engine import RefereeEngine

            engine = RefereeEngine(fen)
            is_valid = engine.validate_move(move)
            legal_moves = engine.get_legal_moves()

            if is_valid:
                return ToolResult(
                    success=True,
                    data={
                        "fen": fen,
                        "move": move,
                        "valid": True,
                        "explanation": f"走步 {move} 是合法的",
                    },
                )
            else:
                return ToolResult(
                    success=True,
                    data={
                        "fen": fen,
                        "move": move,
                        "valid": False,
                        "explanation": f"走步 {move} 是非法的",
                        "legal_moves_example": legal_moves[:10] if legal_moves else [],
                    },
                )
        except Exception as e:
            return ToolResult(success=False, error=f"验证失败: {str(e)}")

    def validate_arguments(self, **kwargs) -> Optional[str]:
        """验证参数"""
        if not kwargs.get("fen"):
            return "缺少必需参数: fen"
        if not kwargs.get("move"):
            return "缺少必需参数: move"
        return None
