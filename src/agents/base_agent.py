"""
Agent基类

定义所有对战Agent的通用接口和功能
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import json
from typing import Optional, List, Dict, Any, TypedDict, Literal
from enum import Enum

from ..llm_adapters.base_adapter import BaseLLMAdapter, LLMResponse
from .prompt_builder import PromptBuilder
from .decision_contract import DECISION_TOOL_NAME
from . import decision_contract
from ..utils.logger import get_logger


# 类型定义
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
    annotated_moves: List[Dict[str, Any]]
    proposed_move: Optional[str]
    violated_move: Optional[str]
    violation_reason: Optional[str]


class ToolCallDict(TypedDict):
    """工具调用字典类型"""
    name: str
    arguments: Dict[str, Any]


class ToolResultDict(TypedDict):
    """工具结果字典类型"""
    tool: str
    arguments: Dict[str, Any]
    result: Any


class AgentStatus(Enum):
    """Agent状态"""
    IDLE = "idle"
    THINKING = "thinking"
    WAITING_TOOL = "waiting_tool"
    DONE = "done"
    ERROR = "error"


@dataclass
class AgentConfig:
    """Agent配置"""
    name: str
    color: str
    description: str
    llm_adapter: BaseLLMAdapter
    system_prompt: str
    max_retries: int = 3
    retry_delay: int = 2
    use_tools: bool = True
    use_reflection: bool = False  # ReflAct式反思，默认关闭节省token
    # W-03 决策契约：合法走步以 enum 写入 schema。
    # 默认关闭 —— 开启会改变行为，必须显式开启。
    use_decision_contract: bool = False
    # W-05：启用后 system prompt 由 base.md + skill manifest + 激活正文组装，
    # 而不是 agent_default.txt 全量常驻。默认关：未迁移时保持旧行为。
    use_skills: bool = False


@dataclass
class AgentResult:
    """Agent决策结果"""
    success: bool
    move: Optional[str] = None
    thought: Optional[str] = None
    error: Optional[str] = None
    resign: bool = False  # LLM是否主动投降
    tool_results: List[Dict] = field(default_factory=list)


class BaseAgent(ABC):
    """对战Agent基类"""

    def __init__(self, config: AgentConfig):
        self.config = config
        self.prompt_builder = PromptBuilder(config.system_prompt,
                                           use_skills=getattr(config, "use_skills", False))
        self.status = AgentStatus.IDLE
        self.last_response: Optional[LLMResponse] = None
        # 本回合的合法走步：续生成时仍需它构造决策契约的 enum
        self._last_legal_moves: List[str] = []

    @abstractmethod
    async def think(self, game_state: GameStateDict) -> AgentResult:
        """思考并返回走步

        Args:
            game_state: 当前游戏状态

        Returns:
            AgentResult: 决策结果
        """
        pass

    def _tools_for_turn(self, legal_moves: List[str]) -> Optional[List[Dict[str, Any]]]:
        """本回合要暴露给模型的工具列表。

        决策契约工具（答案出口）与棋盘能力工具（查询）是两回事，
        但可以同时暴露。契约开启但局面无合法走步时不给契约工具——
        此时应由引擎判定终局，不该让模型去编一个走法。
        """
        tools: List[Dict[str, Any]] = []
        if self.config.use_decision_contract:
            tool = decision_contract.build_tool(legal_moves)
            if tool:
                tools.append(tool)
        if self.config.use_tools:
            tools.extend(self.prompt_builder.get_tools())
        return tools or None


    MAX_TOOL_ITERATIONS = 3

    async def execute_tool_loop(
        self,
        initial_response: LLMResponse,
        tool_executor,
        game_state: GameStateDict
    ) -> AgentResult:
        """工具调用循环，直到得到最终走步。

        协议闭环（R-1 / R-2）：
          1. 模型请求工具调用
          2. 执行工具
          3. **把 assistant(tool_calls) 与 role:"tool" 结果原样写回**
          4. 继续生成（不追加新的 user 消息）

        第 4 步的「不追加」不是省事：每轮追加一条 user 消息会产生连续
        user 消息，Anthropic Messages API 直接拒绝。
        """
        current_response = initial_response
        tool_results: List[Dict[str, Any]] = []

        for _ in range(self.MAX_TOOL_ITERATIONS):
            if not current_response.has_tool_calls():
                break
            # move_decision 是答案出口而非棋盘能力，不得尝试执行它
            current_response.tool_calls = [
                tc for tc in current_response.tool_calls
                if tc.get("name") != DECISION_TOOL_NAME
            ]
            if not current_response.tool_calls:
                break

            assistant_msg = {
                "role": "assistant",
                "content": current_response.content or None,
                "tool_calls": [
                    {
                        "id": tc.get("id", ""),
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": json.dumps(
                                tc["arguments"], ensure_ascii=False
                            ),
                        },
                    }
                    for tc in current_response.tool_calls
                ],
            }

            round_results: List[Dict[str, Any]] = []
            for tc in current_response.tool_calls:
                result = await tool_executor.execute(tc["name"], tc["arguments"])
                round_results.append({
                    "tool": tc["name"],
                    "id": tc.get("id", ""),
                    "arguments": tc["arguments"],
                    "result": result,
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                })
            tool_results.extend(round_results)

            self.prompt_builder.add_tool_exchange(assistant_msg, round_results)

            if self.config.use_reflection and round_results:
                reflection = await self._reflect_on_tools(round_results)
                if reflection:
                    self.prompt_builder.add_assistant_note(reflection)

            current_response = await self._continue_chat()

        if current_response.content:
            move = self._extract_move(
                current_response.content,
                legal_moves=game_state.get('legal_moves', [])
            )
            return AgentResult(
                success=True,
                move=move,
                thought=current_response.thought or current_response.content[:500],
                tool_results=tool_results
            )

        return AgentResult(success=False, error="Failed to get final move")

    async def _continue_chat(self) -> LLMResponse:
        """继续生成，不追加新的 user 消息。

        上一轮的工具结果本身就是上下文的一部分；再加一条 user 会造成
        连续 user 消息（R-3）。
        """
        messages = self.prompt_builder.build_messages(
            self.config.system_prompt,
            user_content=None,
        )

        return await self.config.llm_adapter.chat(
            messages,
            tools=self._tools_for_turn(self._last_legal_moves or []),
        )

    async def _reflect_on_tools(self, tool_results: List[Dict[str, Any]]) -> Optional[str]:
        """对工具调用结果进行反思（ReflAct风格）

        反思问题：
        1. 工具评分是否可靠？是否有异常？
        2. 是否有遗漏的战略因素？
        3. 最终走步是否确认？
        """
        reflection_prompt = f"""基于以下工具调用结果，请反思：

工具结果：
{self._format_tool_results(tool_results)}

请回答：
1. 这些评估是否可靠？有无异常值？
2. 是否遗漏了重要的战略考量？
3. 你最终选择哪个走步？
"""

        try:
            reflection_response = await self.config.llm_adapter.chat([
                {"role": "user", "content": reflection_prompt}
            ])
            return reflection_response.content if reflection_response.content else None
        except Exception:
            return None


    def _format_tool_results(self, tool_results: List[ToolResultDict]) -> str:
        """格式化工具结果用于反思prompt"""
        formatted = []
        for tr in tool_results:
            tool_name = tr.get("tool", "unknown")
            result = tr.get("result", {})
            if isinstance(result, dict):
                formatted.append(f"- {tool_name}: score={result.get('score', 'N/A')}")
            else:
                formatted.append(f"- {tool_name}: {str(result)[:100]}")
        return "\n".join(formatted)

    def _extract_move(
        self,
        content: str,
        legal_moves: Optional[List[str]] = None
    ) -> Optional[str]:
        """从响应内容中提取走步

        匹配ICCS格式走步：4字符，字母+数字交替
        验证：
        1. 首先提取所有可能的走步
        2. 优先选择在legal_moves中的走步
        3. 如果匹配失败，记录详细错误信息
        """
        import re
        logger = get_logger("agent", level="WARNING")

        # 检测投降指令 jxjx
        if re.search(r'\bjxjx\b', content, re.IGNORECASE):
            logger.info("_extract_move: 检测到投降指令 jxjx")
            return "jxjx"

        # 找到所有4字符的ICCS走步（大小写不敏感）
        all_matches = re.findall(r'\b([a-iA-I][0-9][a-iA-I][0-9])\b', content)

        if not all_matches:
            # 记录详细错误信息用于调试
            logger.warning(f"_extract_move: 未找到ICCS走步模式，内容前200字符: {content[:200]}")
            return None

        # 如果提供了legal_moves，优先选择合法走步（转换为小写比较）
        if legal_moves is not None:
            valid_candidates = [m for m in all_matches if m.lower() in legal_moves]
            if valid_candidates:
                return valid_candidates[0].lower()
            else:
                # 所有匹配都不在合法列表中
                logger.warning(f"_extract_move: 所有匹配都不在legal_moves中: {all_matches}")
                # 返回None，让调用方触发重试
                return None

        # 回退：返回第一个匹配（转为小写）
        return all_matches[0].lower() if all_matches else None

    def get_status(self) -> AgentStatus:
        """获取当前状态"""
        return self.status

    def reset(self) -> None:
        """重置Agent状态"""
        self.status = AgentStatus.IDLE
        self.prompt_builder.clear_history()
        self.last_response = None

    def add_correction_feedback(
        self,
        error_msg: str,
        legal_moves: Optional[List[str]] = None
    ) -> None:
        """登记纠错反馈，并入下一条 user 消息。

        不能直接 append 一条 user 消息 —— 连续 user 消息在 Anthropic
        Messages API 下非法（R-3）。改为挂起，由 PromptBuilder 在构造
        本轮 user 内容时合并进去。
        """
        parts = ["【系统纠错】你的上一次输出存在问题：", "", "错误类型：%s" % error_msg]
        if legal_moves:
            parts.append("当前合法走步列表：%s%s" % (
                legal_moves[:20], "..." if len(legal_moves) > 20 else ""))
        parts.append(
            "\n请严格按照以下格式重新输出JSON（不要输出任何其他内容）：\n"
            '{"thought": "你的思考过程", "move": "从legal_moves中选择的4字符ICCS走步"}'
        )
        parts.append(
            '\n如果局面确实无法挽救，你可以输出 {"thought": "认输原因", "move": "jxjx"} 来认输。'
        )
        self.prompt_builder.correction = "\n\n".join(parts)
