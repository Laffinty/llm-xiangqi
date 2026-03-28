"""
Prompt构建器

构建LLM输入prompt，包含：
1. System Prompt（角色设定）
2. Game State（棋盘状态）
3. 可用的MCP工具定义
"""

from typing import List, Dict, Any, Optional
from pathlib import Path


class PromptBuilder:
    """Prompt构建器"""

    def __init__(self, system_prompt: str):
        if not system_prompt:
            raise ValueError("system_prompt is required and cannot be empty")
        self.system_prompt = system_prompt
        self.history: List[Dict[str, str]] = []
        self.tool_results: List[Dict[str, Any]] = []
        self.tools: List[Dict[str, Any]] = MCP_TOOLS

    def set_system_prompt(self, prompt: str) -> None:
        """设置System Prompt"""
        self.system_prompt = prompt

    @classmethod
    def from_file(cls, file_path: str) -> "PromptBuilder":
        """从文件加载System Prompt"""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"System prompt file not found: {file_path}")
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        if not content.strip():
            raise ValueError(f"System prompt file is empty: {file_path}")
        return cls(system_prompt=content)

    def build_game_prompt(
        self, game_state: Dict[str, Any], player_color: Optional[str] = None
    ) -> List[Dict[str, str]]:
        """构建游戏状态prompt

        Args:
            game_state: GameState字典，包含:
                - turn: 当前走子方
                - fen: FEN字符串
                - ascii_board: ASCII棋盘
                - legal_moves: 合法走步列表
                - legal_moves_count: 合法走步数量
                - game_history: 历史走步
                - last_move: 上一步走步
            player_color: Agent代表哪一方（"Red" 或 "Black"）
        """
        # 格式化System Prompt，替换{PLAYER_COLOR}
        system_prompt = self.system_prompt
        if player_color:
            system_prompt = system_prompt.replace("{PLAYER_COLOR}", player_color)
        else:
            system_prompt = system_prompt.replace(
                "{PLAYER_COLOR}", game_state.get("turn", "Unknown")
            )

        # 构建用户消息
        user_content = self._format_game_state(game_state)

        return self.build_messages(system_prompt, user_content)

    # 棋子类型中文名映射
    _PIECE_TYPE_CN = {
        "King": "将",
        "Advisor": "仕",
        "Bishop": "相",
        "Knight": "马",
        "Rook": "车",
        "Cannon": "炮",
        "Pawn": "兵",
    }

    def _format_annotation(self, ann: str) -> str:
        """将英文标注转换为中文短标签"""
        if ann.startswith("capture:"):
            piece_type = ann.split(":", 1)[1]
            return f"吃{self._PIECE_TYPE_CN.get(piece_type, piece_type)}"
        if ann == "check":
            return "将军"
        if ann == "repetition_warning":
            return "重复!"
        if ann == "development":
            return "出车"
        return ann

    def _format_game_state(self, state: Dict[str, Any]) -> str:
        """格式化游戏状态"""
        annotated_moves = state.get("annotated_moves", [])

        lines = [
            "# 当前局面",
            f"回合: {state.get('turn', 'Unknown')}",
            "",
            "## FEN",
            state.get("fen", ""),
            "",
            "## ASCII棋盘",
            state.get("ascii_board", ""),
            "",
        ]

        if annotated_moves:
            lines.append(f"## 合法走步 (共 {len(annotated_moves)} 种)")

            # 按标注类型分组
            check_capture = []
            development = []
            repetition = []
            other = []

            for entry in annotated_moves:
                move_str = entry["move"]
                anns = entry.get("annotations", [])
                if not anns:
                    other.append(move_str)
                elif "repetition_warning" in anns:
                    # 重复警告单独分组
                    label_parts = [self._format_annotation(a) for a in anns]
                    repetition.append(f"{move_str} ({', '.join(label_parts)})")
                elif "development" in anns and all(
                    a == "development" for a in anns
                ):
                    development.append(f"{move_str} (出车)")
                else:
                    # 将军/吃子组
                    label_parts = [self._format_annotation(a) for a in anns]
                    check_capture.append(
                        f"{move_str} ({', '.join(label_parts)})"
                    )

            if check_capture:
                lines.append("")
                lines.append("### 将军/吃子")
                lines.append(", ".join(check_capture))

            if development:
                lines.append("")
                lines.append("### 出子")
                lines.append(", ".join(development))

            if repetition:
                lines.append("")
                lines.append("### 重复警告")
                lines.append(", ".join(repetition))

            if other:
                lines.append("")
                lines.append("### 其他")
                for i in range(0, len(other), 10):
                    lines.append(", ".join(other[i : i + 10]))
        else:
            # 回退到无标注格式
            legal_moves = state.get("legal_moves", [])
            lines.append("## 合法走步")
            lines.append(f"共 {len(legal_moves)} 种走法:")
            if legal_moves:
                for i in range(0, len(legal_moves), 10):
                    lines.append(", ".join(legal_moves[i : i + 10]))

        if state.get("last_move"):
            lines.append("")
            lines.append("## 上一步走步")
            lines.append(
                f"{state.get('last_move')} by {state.get('last_move_by', 'Unknown')}"
            )

        game_history = state.get("game_history", [])
        if game_history:
            lines.append("")
            lines.append("## 走棋历史")
            lines.append(" ".join(game_history))

        lines.append("")
        lines.append("请根据以上局面，选择一个最优的合法走步。")

        return "\n".join(lines)

    def build_validation_prompt(
        self, game_state: Dict[str, Any]
    ) -> List[Dict[str, str]]:
        """构建验证prompt"""
        user_content = f"""验证以下走步是否合法：

当前局面：
- 回合: {game_state.get("turn", "Unknown")}
- FEN: {game_state.get("fen", "")}
- 提议走步: {game_state.get("proposed_move", "")}

请验证该走步是否合法，并给出简要解释。
"""

        return self.build_messages(self.system_prompt, user_content)

    def build_explanation_prompt(
        self, game_state: Dict[str, Any]
    ) -> List[Dict[str, str]]:
        """构建解释prompt"""
        user_content = f"""解释以下违规：

- 违规走步: {game_state.get("violated_move", "")}
- 原因: {game_state.get("violation_reason", "")}
- FEN: {game_state.get("fen", "")}

请解释为什么这个走步是违规的。
"""

        return self.build_messages(self.system_prompt, user_content)

    def build_messages(
        self, system_prompt: str, user_content: str
    ) -> List[Dict[str, str]]:
        """构建消息列表"""
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        # 添加历史消息
        messages.extend(self.history)

        # 添加工具结果
        if self.tool_results:
            tool_content = self._format_tool_results()
            messages.append({"role": "user", "content": tool_content})

        # 添加当前用户消息
        messages.append({"role": "user", "content": user_content})

        return messages

    def _format_tool_results(self) -> str:
        """格式化工具结果"""
        if not self.tool_results:
            return ""

        lines = ["# 工具调用结果"]
        for tr in self.tool_results:
            tool_name = tr.get("tool", "unknown")
            result = tr.get("result", {})
            if isinstance(result, dict):
                lines.append(f"\n## {tool_name}")
                for key, value in result.items():
                    lines.append(f"- {key}: {value}")
            else:
                lines.append(f"\n## {tool_name}: {str(result)[:200]}")

        return "\n".join(lines)

    def add_to_history(self, role: str, content: str) -> None:
        """添加到历史"""
        self.history.append({"role": role, "content": content})

    def add_tool_results(self, tool_results: List[Dict[str, Any]]) -> None:
        """添加工具调用结果"""
        self.tool_results.extend(tool_results)

    def add_reflection(self, reflection: str) -> None:
        """添加反思结果到历史"""
        self.add_to_history("user", f"反思：\n{reflection}")

    def clear_history(self) -> None:
        """清除历史"""
        self.history = []
        self.tool_results = []

    def get_tools(self) -> List[Dict[str, Any]]:
        """获取工具定义"""
        return self.tools

    def set_tools(self, tools: List[Dict[str, Any]]) -> None:
        """设置工具定义"""
        self.tools = tools


# MCP工具定义
MCP_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "evaluate_position",
            "description": "调用Pikafish引擎评估当前局面，返回评分和最佳走步推荐",
            "parameters": {
                "type": "object",
                "properties": {
                    "fen": {"type": "string", "description": "当前局面FEN"},
                    "depth": {
                        "type": "integer",
                        "description": "搜索深度(1-20)，越深越准确但越慢",
                        "default": 15,
                    },
                },
                "required": ["fen"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_opening_book",
            "description": "查询开局库中当前局面的推荐走法",
            "parameters": {
                "type": "object",
                "properties": {"fen": {"type": "string", "description": "当前局面FEN"}},
                "required": ["fen"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "validate_and_explain",
            "description": "验证走步并给出解释",
            "parameters": {
                "type": "object",
                "properties": {
                    "fen": {"type": "string", "description": "当前局面FEN"},
                    "move": {"type": "string", "description": "要验证的ICCS走步"},
                },
                "required": ["fen", "move"],
            },
        },
    },
]
