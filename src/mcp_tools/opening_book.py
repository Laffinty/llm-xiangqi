"""
开局库查询工具

提供象棋开局知识库查询功能
"""

from typing import Any, Dict, Optional
import json
from pathlib import Path

from .base_tool import BaseTool, ToolResult


class OpeningBookTool(BaseTool):
    """开局库查询工具"""

    INITIAL_FEN = (
        "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"
    )

    COMMON_OPENINGS: Dict[str, Dict[str, Any]] = {
        "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR": {
            "name": "初始局面",
            "recommended_moves": [
                {"move": "c3c4", "name": "仙人指路", "score": 0.5},
                {"move": "h2e2", "name": "中炮", "score": 0.6},
                {"move": "b2c2", "name": "过宫炮", "score": 0.4},
                {"move": "a3a4", "name": "边兵", "score": 0.2},
            ],
        },
        "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1": {
            "name": "初始局面（红先）",
            "recommended_moves": [
                {"move": "h2e2", "name": "中炮开局", "score": 0.6},
                {"move": "g3g4", "name": "仙人指路", "score": 0.5},
                {"move": "b2c2", "name": "过宫炮", "score": 0.4},
            ],
        },
    }

    def __init__(self, name: str = "query_opening_book", description: str = ""):
        if not description:
            description = "查询开局库中当前局面的推荐走法"
        super().__init__(name, description)
        self._book_data: Dict[str, Any] = {}
        self._loaded = False

    def _get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "fen": {"type": "string", "description": "当前局面FEN字符串"}
            },
            "required": ["fen"],
        }

    def load_book(self, path: Optional[str] = None) -> bool:
        """加载开局库数据文件

        Returns:
            True if loaded successfully, False if loading failed
        """
        if path is None:
            self._loaded = True
            return True

        book_path = Path(path)
        if not book_path.exists():
            self._loaded = True
            return True

        try:
            with open(book_path, "r", encoding="utf-8") as f:
                self._book_data = json.load(f)
            self._loaded = True
            return True
        except (json.JSONDecodeError, OSError) as e:
            self._loaded = False
            return False

    async def execute(self, **kwargs) -> ToolResult:
        """执行开局库查询"""
        fen = kwargs.get("fen", "")
        if not fen:
            return ToolResult(success=False, error="缺少fen参数")

        base_fen = fen.split()[0] if " " in fen else fen

        opening_info = self.COMMON_OPENINGS.get(base_fen)
        if opening_info:
            return ToolResult(
                success=True,
                data={
                    "fen": fen,
                    "opening_name": opening_info["name"],
                    "moves": opening_info["recommended_moves"],
                    "source": "builtin",
                },
            )

        if self._book_data:
            book_entry = self._book_data.get(base_fen)
            if book_entry:
                return ToolResult(
                    success=True,
                    data={
                        "fen": fen,
                        "moves": book_entry.get("moves", []),
                        "source": "external",
                    },
                )

        return ToolResult(
            success=True,
            data={
                "fen": fen,
                "moves": [],
                "message": "当前局面不在开局库中",
                "source": "none",
            },
        )

    def validate_arguments(self, **kwargs) -> Optional[str]:
        """验证参数"""
        if not kwargs.get("fen"):
            return "缺少必需参数: fen"
        return None
