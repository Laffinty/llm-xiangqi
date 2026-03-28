"""
投降机制测试

测试 LLM 返回 jxjx 时能否正确触发投降，判定对方胜利。
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.agents.base_agent import AgentResult, AgentConfig, AgentStatus
from src.agents.llm_agent import LLMAgent
from src.llm_adapters.base_adapter import LLMResponse
from src.core.game_controller import LLMAgentGameController
from src.core.state_serializer import GameResult, GamePhase


def _make_agent(name, color, response_content):
    """创建一个返回指定内容的 mock LLM Agent"""
    mock_adapter = MagicMock()
    mock_response = LLMResponse(content=response_content)
    mock_adapter.chat = AsyncMock(return_value=mock_response)

    config = AgentConfig(
        name=name,
        color=color,
        description=f"Test {name}",
        llm_adapter=mock_adapter,
        system_prompt="Test prompt",
    )
    return LLMAgent(config)


class TestExtractMoveDetectsJxjx:
    """测试 _extract_move 能检测到 jxjx"""

    def test_jxjx_detected(self):
        """包含 jxjx 的内容应返回 'jxjx'"""
        agent = _make_agent("test", "Red", "")
        result = agent._extract_move('{"thought": "认输", "move": "jxjx"}')
        assert result == "jxjx"

    def test_jxjx_case_insensitive(self):
        """大小写不敏感"""
        agent = _make_agent("test", "Red", "")
        assert agent._extract_move('"move": "JXJX"') == "jxjx"
        assert agent._extract_move('"move": "JxJx"') == "jxjx"

    def test_normal_move_not_matched(self):
        """正常走步不应被误判为 jxjx"""
        agent = _make_agent("test", "Red", "")
        result = agent._extract_move(
            '{"move": "h2e2"}',
            legal_moves=["h2e2"]
        )
        assert result == "h2e2"


class TestAgentResultResign:
    """测试 LLMAgent.think() 返回 resign=True"""

    @pytest.mark.asyncio
    async def test_jxjx_returns_resign(self):
        """LLM 返回 jxjx 时 AgentResult 应有 resign=True"""
        agent = _make_agent("RedAgent", "Red", '{"thought": "没法下了", "move": "jxjx"}')
        game_state = {
            "turn": "Red",
            "fen": "test",
            "ascii_board": "test",
            "legal_moves": ["a0a1", "h2e2"],
        }
        result = await agent.think(game_state)
        assert result.success
        assert result.move == "jxjx"
        assert result.resign is True

    @pytest.mark.asyncio
    async def test_normal_move_no_resign(self):
        """正常走步 resign 应为 False"""
        agent = _make_agent("RedAgent", "Red", '{"thought": "走车", "move": "h2e2"}')
        game_state = {
            "turn": "Red",
            "fen": "test",
            "ascii_board": "test",
            "legal_moves": ["h2e2"],
        }
        result = await agent.think(game_state)
        assert result.success
        assert result.move == "h2e2"
        assert result.resign is False


class TestResignInGameController:
    """测试投降在 GameController 层的完整流程"""

    @pytest.mark.asyncio
    async def test_red_resigns_black_wins(self):
        """红方投降 → 黑方胜利（子力不足时）"""
        # 红方只有 2 个非将棋子（帅e0 + 车a0），黑将e9
        fen = "4k4/9/9/9/9/9/9/9/9/R3K4 w - - 0 1"
        from src.core.referee_engine import RefereeEngine
        engine = RefereeEngine(fen)

        red_agent = _make_agent("RedBot", "Red", '{"thought": "子力悬殊，认输", "move": "jxjx"}')
        black_agent = _make_agent("BlackBot", "Black", '{"thought": "正常", "move": "e9e8"}')

        controller = LLMAgentGameController(
            red_agent=red_agent, black_agent=black_agent, referee_engine=engine
        )
        result = await controller.play_turn()

        assert result.success
        assert "投降" in result.thought

        is_over, game_result, reason = controller.is_game_over()
        assert is_over
        assert game_result == GameResult.BLACK_WIN
        assert "Red resigned" in reason

    @pytest.mark.asyncio
    async def test_black_resigns_red_wins(self):
        """黑方投降 → 红方胜利（子力不足时）"""
        # 红车a0，红帅d0，黑将f9（不同列避免飞将）
        fen = "5k3/9/9/9/9/9/9/9/9/R2K5 w - - 0 1"
        from src.core.referee_engine import RefereeEngine
        engine = RefereeEngine(fen)

        red_agent = _make_agent("RedBot", "Red", '{"thought": "正常", "move": "a0a1"}')
        black_agent = _make_agent("BlackBot", "Black", '{"thought": "认输", "move": "jxjx"}')

        controller = LLMAgentGameController(
            red_agent=red_agent, black_agent=black_agent, referee_engine=engine
        )

        # 红方先走一步正常走步
        await controller.play_turn()
        assert controller.phase == GamePhase.BLACK_TO_MOVE

        # 黑方投降（黑方 0 个非将棋子，允许投降）
        result = await controller.play_turn()
        assert result.success
        assert "投降" in result.thought

        is_over, game_result, reason = controller.is_game_over()
        assert is_over
        assert game_result == GameResult.RED_WIN
        assert "Black resigned" in reason


class TestResignationGuard:
    """测试投降门槛：子力充足时拒绝投降"""

    @pytest.mark.asyncio
    async def test_resign_rejected_when_enough_pieces(self):
        """子力充足(>=3非将棋子)时投降被拒绝，触发重试"""
        # 第一次返回 jxjx（投降被拒绝），第二次返回合法走步
        mock_adapter = MagicMock()
        mock_adapter.chat = AsyncMock(
            side_effect=[
                LLMResponse(content='{"thought": "算了", "move": "jxjx"}'),
                LLMResponse(content='{"thought": "走车", "move": "a0a1"}'),
            ]
        )
        config = AgentConfig(
            name="RedBot",
            color="Red",
            description="Test",
            llm_adapter=mock_adapter,
            system_prompt="Test",
        )
        red_agent = LLMAgent(config)
        black_agent = _make_agent("BlackBot", "Black", '{"thought": "正常", "move": "a9a8"}')

        controller = LLMAgentGameController(red_agent=red_agent, black_agent=black_agent)
        # 初始局面红方有 16 个非将棋子，投降应被拒绝
        result = await controller.play_turn()

        # 投降被拒绝后重试，应返回正常走步结果
        assert result.success
        assert result.move == "a0a1"
        # 游戏不应结束
        is_over, _, _ = controller.is_game_over()
        assert not is_over

    @pytest.mark.asyncio
    async def test_resign_accepted_when_few_pieces(self):
        """子力不足(<=2非将棋子)时投降被接受"""
        # 构造一个红方只有 2 个非将棋子的局面
        # 红帅e0 + 红车a0 + 红兵a3，黑将e9
        fen = "4k4/9/9/9/9/9/9/9/9/R3K4 w - - 0 1"
        from src.core.referee_engine import RefereeEngine
        engine = RefereeEngine(fen)

        red_agent = _make_agent("RedBot", "Red", '{"thought": "没法下了", "move": "jxjx"}')
        black_agent = _make_agent("BlackBot", "Black", '{"thought": "正常", "move": "e9e8"}')

        controller = LLMAgentGameController(
            red_agent=red_agent, black_agent=black_agent, referee_engine=engine
        )
        result = await controller.play_turn()

        assert result.success
        assert "投降" in result.thought

        is_over, game_result, reason = controller.is_game_over()
        assert is_over
        assert game_result == GameResult.BLACK_WIN
        assert "Red resigned" in reason


class TestResignOnRetry:
    """测试纠错重试时投降"""

    @pytest.mark.asyncio
    async def test_resign_after_illegal_move(self):
        """第一次非法走步后，纠错重试时投降"""
        # 构造红方只有 2 个非将棋子的局面（允许投降）
        fen = "4k4/9/9/9/9/9/9/9/9/R3K4 w - - 0 1"
        from src.core.referee_engine import RefereeEngine
        engine = RefereeEngine(fen)

        # 第一次返回非法走步，第二次返回 jxjx
        mock_adapter = MagicMock()
        mock_adapter.chat = AsyncMock(
            side_effect=[
                LLMResponse(content='{"thought": "走一步", "move": "z9z9"}'),  # 非法
                LLMResponse(content='{"thought": "认输", "move": "jxjx"}'),    # 投降
            ]
        )

        config = AgentConfig(
            name="RedBot",
            color="Red",
            description="Test",
            llm_adapter=mock_adapter,
            system_prompt="Test",
        )
        red_agent = LLMAgent(config)
        black_agent = _make_agent("BlackBot", "Black", '{"thought": "正常", "move": "e9e8"}')

        controller = LLMAgentGameController(
            red_agent=red_agent, black_agent=black_agent, referee_engine=engine
        )
        result = await controller.play_turn()

        assert result.success
        assert "投降" in result.thought

        is_over, game_result, reason = controller.is_game_over()
        assert is_over
        assert game_result == GameResult.BLACK_WIN


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
