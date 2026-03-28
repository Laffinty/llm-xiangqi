"""
Agent基类

定义所有对战Agent的通用接口和功能
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from enum import Enum

from ..llm_adapters.base_adapter import BaseLLMAdapter, LLMResponse
from .prompt_builder import PromptBuilder
from ..utils.logger import get_logger


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
        self.prompt_builder = PromptBuilder(config.system_prompt)
        self.status = AgentStatus.IDLE
        self.last_response: Optional[LLMResponse] = None

    @abstractmethod
    async def think(self, game_state: Dict[str, Any]) -> AgentResult:
        """思考并返回走步

        Args:
            game_state: 当前游戏状态

        Returns:
            AgentResult: 决策结果
        """
        pass

    async def execute_tool_loop(
        self,
        initial_response: LLMResponse,
        tool_executor,
        game_state: Dict[str, Any]
    ) -> AgentResult:
        """执行工具调用循环直到得到最终走步

        工具调用循环：
        1. LLM请求工具调用
        2. 执行工具（evaluate_position等）
        3. 追加结果到历史
        4. LLM反思（ReflAct风格，可选）
        5. 重复直到得到最终走步

        ReflAct研究表明：反思步骤可提升27.7%准确率

        Args:
            initial_response: LLM初始响应
            tool_executor: 工具执行器
            game_state: 游戏状态（用于走步验证）

        Returns:
            AgentResult: 最终决策结果
        """
        current_response = initial_response
        tool_results = []
        legal_moves = game_state.get('legal_moves', [])
        game_history = game_state.get('game_history', [])

        # 最多3轮工具调用
        for iteration in range(3):
            if not current_response.has_tool_calls():
                break

            # 执行所有工具调用
            for tool_call in current_response.tool_calls:
                result = await tool_executor.execute(
                    tool_call["name"],
                    tool_call["arguments"]
                )
                tool_results.append({
                    "tool": tool_call["name"],
                    "arguments": tool_call["arguments"],
                    "result": result
                })

            # 将工具结果追加到消息历史
            self.prompt_builder.add_tool_results(tool_results)

            # 可选：ReflAct式反思
            if self.config.use_reflection and tool_results:
                reflection_response = await self._reflect_on_tools(tool_results)
                if reflection_response:
                    self.prompt_builder.add_reflection(reflection_response)

            # 继续生成
            current_response = await self._continue_chat()

        # 最终决策
        if current_response.content:
            move = self._extract_move(
                current_response.content,
                legal_moves=legal_moves
            )
            return AgentResult(
                success=True,
                move=move,
                thought=current_response.thought or current_response.content[:500],
                tool_results=tool_results
            )

        return AgentResult(success=False, error="Failed to get final move")

    async def _continue_chat(self) -> LLMResponse:
        """继续聊天（工具调用后）"""
        messages = self.prompt_builder.build_messages(
            self.config.system_prompt,
            "基于工具调用结果，请继续你的决策。"
        )

        return await self.config.llm_adapter.chat(
            messages,
            tools=self.prompt_builder.get_tools() if self.config.use_tools else None
        )

    async def _reflect_on_tools(self, tool_results: List[Dict]) -> Optional[str]:
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

    def _format_tool_results(self, tool_results: List[Dict]) -> str:
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
        legal_moves: List[str] = None
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

    def add_correction_feedback(self, error_msg: str, legal_moves: List[str] = None) -> None:
        """添加纠正性反馈到prompt历史，强制LLM修正错误

        Args:
            error_msg: 错误信息
            legal_moves: 可选的合法走步列表
        """
        correction_prompt = f"""【系统纠错】你的上一次输出存在问题：

错误类型：{error_msg}

请严格按照以下格式重新输出JSON（不要输出任何其他内容）：
{{
  "thought": "你的思考过程",
  "move": "从legal_moves中选择的4字符ICCS走步"
}}
"""
        if legal_moves:
            correction_prompt += f"\n当前合法走步列表：{legal_moves[:20]}{'...' if len(legal_moves) > 20 else ''}"

        correction_prompt += '\n\n如果局面确实无法挽救，你可以输出 {"thought": "认输原因", "move": "jxjx"} 来认输。'

        # 添加到历史，LLM下次思考时会看到
        self.prompt_builder.add_to_history("user", correction_prompt)
