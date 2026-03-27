"""
Agent模块集成测试

测试Agent和Adapter的基本功能
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock

from src.llm_adapters.base_adapter import LLMResponse, BaseLLMAdapter
from src.llm_adapters.deepseek_adapter import DeepSeekAdapter
from src.agents.prompt_builder import PromptBuilder, MCP_TOOLS
from src.agents.base_agent import BaseAgent, AgentConfig, AgentResult, AgentStatus
from src.core.referee_engine import RefereeEngine


class TestPromptBuilder:
    """测试PromptBuilder"""

    def test_default_system_prompt(self):
        """测试默认System Prompt"""
        builder = PromptBuilder()
        assert len(builder.system_prompt) > 0
        assert "ICCS" in builder.system_prompt

    def test_build_game_prompt(self):
        """测试构建游戏prompt"""
        builder = PromptBuilder()

        game_state = {
            "turn": "Red",
            "fen": "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1",
            "ascii_board": "    a   b   c\n0 | R | N | B |",
            "legal_moves": ["a0a1", "a0a2", "b0a1"],
            "legal_moves_count": 3,
            "game_history": [],
            "last_move": None
        }

        messages = builder.build_game_prompt(game_state)
        assert len(messages) >= 2  # system + user
        assert any("Red" in m.get("content", "") for m in messages)

    def test_build_validation_prompt(self):
        """测试构建验证prompt"""
        builder = PromptBuilder()

        game_state = {
            "turn": "Red",
            "fen": "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1",
            "proposed_move": "h2e2",
            "action": "validate_only"
        }

        messages = builder.build_validation_prompt(game_state)
        assert len(messages) >= 2
        assert any("h2e2" in m.get("content", "") for m in messages)


class TestMCPTools:
    """测试MCP工具定义"""

    def test_tools_defined(self):
        """测试工具已定义"""
        assert len(MCP_TOOLS) > 0

    def test_evaluate_position_schema(self):
        """测试evaluate_position工具schema"""
        tool = next((t for t in MCP_TOOLS if t["function"]["name"] == "evaluate_position"), None)
        assert tool is not None
        assert "fen" in tool["function"]["parameters"]["properties"]


class TestBaseAgent:
    """测试BaseAgent"""

    def test_extract_move(self):
        """测试从内容中提取走步"""
        # 创建mock adapter
        mock_adapter = MagicMock()
        mock_adapter.chat = AsyncMock()

        config = AgentConfig(
            name="TestAgent",
            color="Red",
            description="Test",
            llm_adapter=mock_adapter,
            system_prompt="Test prompt"
        )

        class TestAgent(BaseAgent):
            async def think(self, game_state):
                pass

        agent = TestAgent(config)

        # 测试提取
        content = "我选择走 h2e2 这步棋。"
        move = agent._extract_move(content)
        assert move == "h2e2"

        # 测试无法提取
        content = "我不知道该走什么"
        move = agent._extract_move(content)
        assert move is None


class TestRefereeEngine:
    """测试RefereeEngine（确保集成兼容）"""

    def test_engine_state_for_agent(self):
        """测试引擎状态可以用于Agent"""
        engine = RefereeEngine()
        state = engine.serialize_for_llm()

        assert "turn" in state
        assert "fen" in state
        assert "ascii_board" in state
        assert "legal_moves" in state
        assert len(state["legal_moves"]) > 0

    def test_validate_and_apply(self):
        """测试验证和应用走步"""
        engine = RefereeEngine()

        # 记录原始FEN
        original_fen = engine.current_fen

        # 验证红方开局走步
        assert engine.validate_move("h2e2") == True

        # 应用走步
        new_fen = engine.apply_move("h2e2")

        # 验证FEN已更新
        assert new_fen != original_fen
        assert new_fen == engine.current_fen  # apply_move会更新内部FEN

        # 验证回合已切换
        assert engine.board.current_color.value == "black"


class TestLLMResponse:
    """测试LLM响应结构"""

    def test_response_without_tools(self):
        """测试无工具调用的响应"""
        response = LLMResponse(content="Hello")
        assert response.has_tool_calls() == False

    def test_response_with_tools(self):
        """测试有工具调用的响应"""
        response = LLMResponse(
            content="",
            tool_calls=[{"name": "test", "arguments": {}}]
        )
        assert response.has_tool_calls() == True


class TestAgentIntegration:
    """测试Agent集成（使用mock）"""

    @pytest.mark.asyncio
    async def test_agent_think_with_mock(self):
        """测试Agent思考（使用mock）"""
        # 创建mock adapter
        mock_adapter = MagicMock()
        mock_response = LLMResponse(
            content='{"thought": "Test", "move": "h2e2"}'
        )
        mock_adapter.chat = AsyncMock(return_value=mock_response)

        # 创建Agent
        config = AgentConfig(
            name="TestAgent",
            color="Red",
            description="Test",
            llm_adapter=mock_adapter,
            system_prompt="Test"
        )

        class TestAgent(BaseAgent):
            async def think(self, game_state):
                self.status = AgentStatus.THINKING
                messages = self.prompt_builder.build_game_prompt(game_state)
                response = await self.config.llm_adapter.chat(messages)
                move = self._extract_move(response.content)
                self.status = AgentStatus.IDLE
                return AgentResult(success=True, move=move, thought="Test")

        agent = TestAgent(config)

        # 执行思考
        game_state = {
            "turn": "Red",
            "fen": "test",
            "ascii_board": "test",
            "legal_moves": ["h2e2"],
            "legal_moves_count": 1,
            "game_history": []
        }

        result = await agent.think(game_state)

        assert result.success == True
        assert result.move == "h2e2"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
