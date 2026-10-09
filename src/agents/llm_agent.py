"""
通用 LLM Agent

适配所有 LLM 适配器（DeepSeek、MiMo 等），消除 agent_deepseek / agent_glm / agent_minimax 的重复代码。
"""

from typing import Any, Dict, List, Optional

from . import decision_contract
from .base_agent import BaseAgent, AgentResult, AgentStatus


class LLMAgent(BaseAgent):
    """通用 LLM Agent，通过注入的 adapter 适配任意 LLM 后端"""

    async def _chat(self, messages, tools):
        """发一次请求，必要时在 tool_choice 上自动降级。

        F-013 修订：`tool_choice: "required"` 被拒是 **thinking 模式特有**的现象。
        thinking 关闭后（W-00）两家都支持 `required`。用 `required` 才能让契约
        确定生效——`auto` 之下 MiMo 是否调用工具会随 prompt 复杂度漂移（实测 0/3）。

        这里不把选择权交给配置，而是**先试 required、被拒再回落 auto**：
        供应商行为会变，写死配置等于把当下的观测固化成永久假设。
        """
        if not tools:
            return await self.config.llm_adapter.chat(messages, tools=None)

        names = {t.get("function", {}).get("name") for t in tools}
        # 只有一个工具时可以用 required 强制；混有棋盘能力工具时不行，
        # 否则会逼模型去调 board_inspect 而不是回答问题。
        forced = len(names) == 1

        try:
            return await self.config.llm_adapter.chat(
                messages, tools=tools,
                tool_choice="required" if forced else "auto")
        except Exception as e:
            if not forced or "tool_choice" not in str(e):
                raise
            return await self.config.llm_adapter.chat(
                messages, tools=tools, tool_choice="auto")

    async def think(self, game_state: Dict[str, Any]) -> AgentResult:
        """思考走步

        决策顺序（W-03）：
          1. 先看是否走了决策契约（move_decision + strict enum）—— 命中即结束
          2. 否则若有棋盘工具调用，走工具循环（W-01 的协议闭环）
          3. 否则降级：从自由文本里正则提取并校验

        第 3 步是降级路径，不是主路径。它保留是因为 `tool_choice` 只能是 auto
        （见 F-013），供应商**不保证**一定会调用工具。
        """
        self.status = AgentStatus.THINKING

        try:
            messages = self.prompt_builder.build_game_prompt(
                game_state,
                player_color=self.config.color
            )
            legal_moves = game_state.get('legal_moves', []) or []
            self._last_legal_moves = legal_moves
            tools = self._tools_for_turn(legal_moves)

            response = await self._chat(messages, tools)
            self.last_response = response

            # ---- 1. 决策契约 ----
            if self.config.use_decision_contract:
                decision = decision_contract.parse(response, legal_moves)
                if decision:
                    return AgentResult(
                        success=True,
                        move=decision["move"],
                        thought=decision["thought"] or (response.content or "")[:500],
                        tool_results=[{"tool": decision_contract.DECISION_TOOL_NAME,
                                       "arguments": {"move": decision["move"]},
                                       "result": {"source": "contract",
                                                  "confidence": decision["confidence"]}}],
                    )

            # ---- 2. 棋盘工具循环（move_decision 不是棋盘工具，不进这里）----
            if response.has_tool_calls():
                tool_executor = self._get_tool_executor()
                return await self.execute_tool_loop(response, tool_executor, game_state)

            # ---- 3. 降级：自由文本正则 ----
            move = self._extract_move(response.content, legal_moves=legal_moves)
            if move is None and response.thought:
                move = self._extract_move(response.thought, legal_moves=legal_moves)

            if move == "jxjx":
                return AgentResult(
                    success=True,
                    move="jxjx",
                    thought=response.thought or (response.content[:500] if response.content else ""),
                    resign=True,
                )

            # 降级路径也要校验：正则可能抓到"看起来合法"但不在枚举内的走步
            if move is not None and move != "jxjx":
                err = decision_contract.validate_free_text(move, legal_moves)
                if err is not None:
                    move = None

            return AgentResult(
                success=True,
                move=move,
                thought=response.thought or (response.content[:500] if response.content else ""),
            )

        except Exception as e:
            self.status = AgentStatus.ERROR
            return AgentResult(success=False, error=str(e))

        finally:
            self.status = AgentStatus.IDLE

    def _get_tool_executor(self):
        """获取工具执行器（单例）"""
        from ..mcp_tools.tool_executor import ToolExecutor
        return ToolExecutor.get_instance()