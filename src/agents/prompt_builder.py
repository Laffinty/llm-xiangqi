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

    def __init__(self, system_prompt: Optional[str] = None,
                 use_skills: bool = False):
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
        # W-05：启用后 system prompt 由 base.md + manifest + 激活正文组装
        self.use_skills = use_skills
        # 本回合激活的 skill 名，供 harness 断言用
        self.active_skills: List[str] = []
        self.history: List[Dict[str, str]] = []
        self.tool_exchanges: List[Dict[str, Any]] = []
        self.assistant_notes: List[str] = []
        # 纠错反馈并入下一条 user 消息，而不是单独追加一条（否则产生连续 user 消息）
        self.correction: Optional[str] = None
        self.current_user_turn: Optional[str] = None
        # 工具 schema 不再硬编码：以 ToolExecutor.get_tool_schemas() 为唯一事实来源
        # （F-005 / F-006）。此处仅保留可注入的列表供测试使用。
        self.tools: List[Dict[str, Any]] = []

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
        if self.use_skills:
            from ..skills.activator import compose
            composed, self.active_skills = compose(
                snapshot=game_state.get("snapshot"), player_color=player_color)
            system_prompt = composed
            self.system_prompt = composed

        user_content = self._format_game_state(game_state)
        # 记住本轮：否则 _continue_chat 重建消息时会丢掉它，对话以 assistant 开头（非法）。
        self.current_user_turn = user_content

        return self.build_messages(system_prompt, user_content)

    # 棋子类型中文名映射
    # 键必须与 RefereeEngine 产出的 PieceType.value 一致（小写），
    # 否则 capture:/fork:/sacrifice: 标注会静默退化成英文（如「吃rook」）
    _PIECE_TYPE_CN = {
        "king": "将",
        "advisor": "仕",
        "bishop": "相",
        "knight": "马",
        "rook": "车",
        "cannon": "炮",
        "pawn": "兵",
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

        lines.extend(self._format_snapshot(state.get("snapshot")))

        lines.append("")
        lines.append("请根据以上局面，选择一个最优的合法走步。")

        return "\n".join(lines)

    @staticmethod
    def _format_snapshot(snap) -> List[str]:
        """结构化局面摘要（W-04）。

        严格控制长度：这些字段每轮都进 prompt，占的是真钱。
        每行一句，不重复 ASCII 盘已有的信息，不重复列出 legal_moves（那部分
        已作为 enum 写在契约 schema 里）。
        """
        if not snap:
            return []

        out = ["", "## 局面摘要"]

        phase = {"opening": "开局", "middlegame": "中局",
                 "endgame": "残局"}.get(snap.get("board_phase"), snap.get("board_phase"))
        out.append("- 阶段: %s" % phase)

        mat = snap.get("material") or {}
        if mat:
            out.append("- 子力: 红%d 黑%d（以当前走子方视角差 %+d）" % (
                mat.get("Red", 0), mat.get("Black", 0),
                mat.get("diff_for_side_to_move", 0)))

        if snap.get("in_check"):
            out.append("- 将军: 是（%s方被将）" % snap.get("check_side"))

        detail = snap.get("last_move_detail")
        if detail and detail.get("piece"):
            bits = ["- 上一步: %s %s→%s" % (detail["piece"], detail["from"], detail["to"])]
            if detail.get("captured"):
                bits.append("吃%s" % detail["captured"])
            if detail.get("gives_check"):
                bits.append("将军")
            out.append("".join(bits))

        if snap.get("repetition_warning"):
            out.append("- 重复警告: 是（局面已出现多次，避免循环）")

        return out

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
        self,
        system_prompt: str,
        user_content: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """构建消息列表。

        协议顺序：system -> history -> 本轮 user -> 工具调用往返 -> assistant 备注。

        user_content 传 None 表示「继续上一轮」——工具循环里每一轮都追加
        一条 user 消息会产生连续 user 消息，Anthropic Messages API 直接拒绝。
        """
        messages: List[Dict[str, Any]] = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.extend(self.history)

        if user_content is None:
            user_content = self.current_user_turn

        # user turn must come BEFORE the tool exchanges: the exchanges are the
        # continuation of this very turn. Putting it last would yield
        # assistant -> tool -> user, i.e. consecutive user messages (R-3).
        if user_content is not None:
            if self.correction:
                user_content = "%s\n\n%s" % (user_content, self.correction)
            messages.append({"role": "user", "content": user_content})

        for exchange in self.tool_exchanges:
            messages.append(exchange["assistant"])
            for tr in exchange["tools"]:
                messages.append({
                    "role": "tool",
                    "tool_call_id": tr.get("id", ""),
                    "content": tr.get("content", ""),
                })

        for note in self.assistant_notes:
            messages.append({"role": "assistant", "content": note})

        return messages

    def add_tool_exchange(
        self,
        assistant_msg: Dict[str, Any],
        tool_results: List[Dict[str, Any]],
    ) -> None:
        """记录一次完整的工具调用往返。

        assistant_msg 必须是含 tool_calls 的 assistant 消息（带 id），
        tool_results 每项必须带 id —— 二者一一对应才能被供应商协议接受。
        """
        self.tool_exchanges.append({
            "assistant": assistant_msg,
            "tools": [
                {
                    "id": tr.get("id", ""),
                    "name": tr.get("tool", tr.get("name", "")),
                    "content": tr.get("content", ""),
                }
                for tr in tool_results
            ],
        })

    def add_assistant_note(self, text: str) -> None:
        """追加一条 assistant 说明（反思等）。

        必须是 assistant 而非 user —— 反思是模型自己的话，
        伪装成 user 会造成连续 user 消息。
        """
        self.assistant_notes.append(text)

    def add_to_history(self, role: str, content: str) -> None:
        """添加到历史"""
        self.history.append({"role": role, "content": content})

    def clear_history(self) -> None:
        """清除历史"""
        self.history = []
        self.tool_exchanges = []
        self.assistant_notes = []
        self.correction = None
        self.current_user_turn = None


    def get_tools(self) -> List[Dict[str, Any]]:
        """获取工具定义。

        未显式注入时从 `ToolExecutor.get_tool_schemas()` 实时取——
        那里才是工具的唯一事实来源（W-06 目标）。
        """
        if self.tools:
            return self.tools
        from ..mcp_tools.tool_executor import ToolExecutor
        return ToolExecutor.get_instance().get_tool_schemas()

    def set_tools(self, tools: List[Dict[str, Any]]) -> None:
        """显式注入工具定义（测试用）。
        不调用时 get_tools() 仍从 ToolExecutor 取。"""
        self.tools = tools

