"""
Prompt构建器

构建LLM输入prompt，包含：
1. System Prompt（角色设定）
2. Game State（棋盘状态）
3. 可用的MCP工具定义
"""

from typing import List, Dict, Any, Optional, TypedDict, Literal
from pathlib import Path


# 类型定义
class AnnotatedMoveDict(TypedDict):
    """带标注的走步字典"""

    move: str
    annotations: List[str]


class GameStateDict(TypedDict, total=False):
    """游戏状态字典类型"""

    turn: Literal["Red", "Black"]
    fen: str
    ascii_board: str
    legal_moves: List[str]
    legal_moves_count: int
    game_history: List[str]
    last_move: Optional[str]
    last_move_by: Optional[str]
    phase: str
    result: str
    result_reason: Optional[str]
    annotated_moves: List[AnnotatedMoveDict]
    proposed_move: Optional[str]
    violated_move: Optional[str]
    violation_reason: Optional[str]


class PromptBuilder:
    """Prompt构建器

    支持从文件或字符串加载system prompt，提供向后兼容的无参构造函数。

    Examples:
        >>> # 从字符串创建（推荐）
        >>> builder = PromptBuilder("你是一位象棋大师...")
        >>>
        >>> # 从文件创建（推荐）
        >>> builder = PromptBuilder.from_file("prompts/agent_default.txt")
        >>>
        >>> # 无参创建（向后兼容，加载默认prompt）
        >>> builder = PromptBuilder()
    """

    DEFAULT_PROMPT_FILE = "prompts/agent_default.txt"
    _FALLBACK_PROMPT = (
        "你是中国象棋AI助手。根据当前局面选择最优走步。"
        '必须输出JSON格式: {"thought": "你的分析", "move": "h2e2"}'
    )

    def __init__(self, system_prompt: Optional[str] = None):
        """
        初始化PromptBuilder

        Args:
            system_prompt: System prompt字符串。若为None，则加载默认prompt文件。

        Raises:
            ValueError: 当system_prompt为空字符串或默认prompt文件不存在时
        """
        if system_prompt is None:
            system_prompt = self._load_default_prompt()

        if not system_prompt or not system_prompt.strip():
            raise ValueError(
                "system_prompt is required and cannot be empty. "
                f"Ensure {self.DEFAULT_PROMPT_FILE} exists or provide a valid prompt."
            )

        self.system_prompt = system_prompt
        self.history: List[Dict[str, str]] = []
        self.tool_results: List[Dict[str, Any]] = []
        self.tools: List[Dict[str, Any]] = list(MCP_TOOLS)

    @classmethod
    def _load_default_prompt(cls) -> str:
        """
        加载默认system prompt

        按优先级尝试：
        1. DEFAULT_PROMPT_FILE 文件内容
        2. _FALLBACK_PROMPT 内置回退prompt

        Returns:
            默认system prompt字符串
        """
        try:
            # 尝试从项目根目录开始查找
            path = Path(__file__).parent.parent.parent / cls.DEFAULT_PROMPT_FILE
            if path.exists():
                content = path.read_text(encoding="utf-8")
                if content.strip():
                    return content
        except (OSError, UnicodeDecodeError):
            pass

        # 使用内置回退prompt
        return cls._FALLBACK_PROMPT

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
        self, game_state: GameStateDict, player_color: Optional[str] = None
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
        # 新增：位置标注
        if ann == "cross_river":
            return "过河"
        if ann == "central_file":
            return "占中"
        if ann == "flank":
            return "占肋"
        # 新增：战术标注
        if ann == "pin":
            return "牵制"
        if ann.startswith("fork:"):
            piece_type = ann.split(":", 1)[1]
            return f"抽{self._PIECE_TYPE_CN.get(piece_type, piece_type)}"
        if ann.startswith("sacrifice:"):
            piece_type = ann.split(":", 1)[1]
            return f"弃{self._PIECE_TYPE_CN.get(piece_type, piece_type)}"
        return ann

    def _format_game_state(self, state: GameStateDict) -> str:
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

            # 按标注类型分组（新增战术组和位置组）
            tactical = []  # 战术组合：捉双、牵制、弃子
            positional = []  # 战略位置：过河、占中、占肋
            check_capture = []  # 将军/吃子
            development = []  # 出子
            repetition = []  # 重复警告
            other = []  # 其他

            for entry in annotated_moves:
                move_str = entry["move"]
                anns = entry.get("annotations", [])

                # 分类判断
                is_tactical = any(
                    a in ["pin"] or a.startswith(("fork:", "sacrifice:")) for a in anns
                )
                is_positional = any(
                    a in ["cross_river", "central_file", "flank"] for a in anns
                )
                is_check_capture = any(
                    a in ["check"] or a.startswith("capture:") for a in anns
                )

                if not anns:
                    other.append(move_str)
                elif "repetition_warning" in anns:
                    # 重复警告单独分组
                    label_parts = [self._format_annotation(a) for a in anns]
                    repetition.append(f"{move_str} ({', '.join(label_parts)})")
                elif is_tactical:
                    # 战术组合组（优先级最高）
                    label_parts = [self._format_annotation(a) for a in anns]
                    tactical.append(f"{move_str} ({', '.join(label_parts)})")
                elif is_positional:
                    # 战略位置组
                    label_parts = [self._format_annotation(a) for a in anns]
                    positional.append(f"{move_str} ({', '.join(label_parts)})")
                elif "development" in anns and len(anns) == 1:
                    # 纯出子走步
                    development.append(f"{move_str} (出车)")
                elif is_check_capture:
                    # 将军/吃子组
                    label_parts = [self._format_annotation(a) for a in anns]
                    check_capture.append(f"{move_str} ({', '.join(label_parts)})")
                else:
                    # 混合标注放入其他
                    label_parts = [self._format_annotation(a) for a in anns]
                    other.append(f"{move_str} ({', '.join(label_parts)})")

            # 按优先级展示
            if tactical:
                lines.append("")
                lines.append("### 战术组合 ⭐")
                lines.append(", ".join(tactical))

            if positional:
                lines.append("")
                lines.append("### 战略位置")
                lines.append(", ".join(positional))

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
        self, game_state: GameStateDict
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
        self, game_state: GameStateDict
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
