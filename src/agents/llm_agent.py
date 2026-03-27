"""
通用 LLM Agent

适配所有 LLM 适配器（DeepSeek、MiMo 等），消除 agent_deepseek / agent_glm / agent_minimax 的重复代码。
"""

from typing import Dict, Any

from .base_agent import BaseAgent, AgentResult, AgentStatus


class LLMAgent(BaseAgent):
    """通用 LLM Agent，通过注入的 adapter 适配任意 LLM 后端"""

    async def think(self, game_state: Dict[str, Any]) -> AgentResult:
        """思考走步

        Args:
            game_state: 当前游戏状态

        Returns:
            AgentResult: 决策结果
        """
        self.status = AgentStatus.THINKING

        try:
            messages = self.prompt_builder.build_game_prompt(
                game_state,
                player_color=self.config.color
            )

            response = await self.config.llm_adapter.chat(
                messages,
                tools=self.prompt_builder.get_tools() if self.config.use_tools else None,
            )

            self.last_response = response

            if response.has_tool_calls():
                tool_executor = self._get_tool_executor()
                return await self.execute_tool_loop(response, tool_executor, game_state)

            move = self._extract_move(
                response.content,
                legal_moves=game_state.get('legal_moves', [])
            )
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
