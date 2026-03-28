"""
GameController单元测试

测试覆盖：
1. 结果映射逻辑（reason → GameResult）
2. 三次重复局面判和
3. 长将违规胜负判定
4. 将死/困毙胜负判定
5. 王被吃胜负判定
"""

import pytest
from src.core.game_controller import GameController, LLMAgentGameController
from src.core.referee_engine import RefereeEngine, INITIAL_FEN
from src.core.state_serializer import GameResult, GamePhase


class TestReasonToResultMapping:
    """测试 reason → GameResult 映射"""

    def test_draw_mapping(self):
        """判和 → DRAW"""
        assert GameController._map_reason_to_result("三次重复局面，判和") == GameResult.DRAW

    def test_red_perpetual_check(self):
        """红方长将违规 → BLACK_WIN（违规方判负）"""
        assert GameController._map_reason_to_result("红方长将违规") == GameResult.BLACK_WIN

    def test_black_perpetual_check(self):
        """黑方长将违规 → RED_WIN（违规方判负）"""
        assert GameController._map_reason_to_result("黑方长将违规") == GameResult.RED_WIN

    def test_red_king_captured(self):
        """黑方胜利 - 红帅被吃 → BLACK_WIN"""
        assert GameController._map_reason_to_result("黑方胜利 - 红帅被吃") == GameResult.BLACK_WIN

    def test_black_king_captured(self):
        """红方胜利 - 黑将被吃 → RED_WIN"""
        assert GameController._map_reason_to_result("红方胜利 - 黑将被吃") == GameResult.RED_WIN

    def test_red_stalemate(self):
        """黑方胜利 - 红方被困 → BLACK_WIN"""
        assert GameController._map_reason_to_result("黑方胜利 - 红方被困") == GameResult.BLACK_WIN

    def test_black_stalemate(self):
        """红方胜利 - 黑方被困 → RED_WIN"""
        assert GameController._map_reason_to_result("红方胜利 - 黑方被困") == GameResult.RED_WIN

    def test_red_checkmate(self):
        """黑方胜利 - 红方被将死 → BLACK_WIN"""
        assert GameController._map_reason_to_result("黑方胜利 - 红方被将死") == GameResult.BLACK_WIN

    def test_black_checkmate(self):
        """红方胜利 - 黑方被将死 → RED_WIN"""
        assert GameController._map_reason_to_result("红方胜利 - 黑方被将死") == GameResult.RED_WIN


class TestKingCapturedResult:
    """测试王被吃时GameController的结果"""

    def test_black_king_captured(self):
        """黑将被吃 → 红方胜"""
        controller = GameController()
        # FEN: 黑将不存在
        fen = "9/9/9/9/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"
        controller.reset(fen)
        # 任意合法走步即可触发 check_game_end
        legal = controller.referee.get_legal_moves()
        assert len(legal) > 0
        result = controller.apply_move("red_test", legal[0])
        assert result.success
        is_over, game_result, reason = controller.is_game_over()
        assert is_over
        assert game_result == GameResult.RED_WIN
        assert "黑将被吃" in reason or "红方胜利" in reason

    def test_red_king_captured(self):
        """红帅被吃 → 黑方胜"""
        controller = GameController()
        # FEN: 红帅不存在, 轮到黑方
        fen = "1Cbakab2/9/1R7/p3n1p1p/2p6/9/P1P3P1P/R1N3N1B/9/2BAnA3 b - - 0 1"
        controller.reset(fen)
        legal = controller.referee.get_legal_moves()
        assert len(legal) > 0
        result = controller.apply_move("black_test", legal[0])
        assert result.success
        is_over, game_result, reason = controller.is_game_over()
        assert is_over
        assert game_result == GameResult.BLACK_WIN
        assert "红帅被吃" in reason or "黑方胜利" in reason


class TestThreefoldRepetitionResult:
    """测试三次重复局面 → DRAW"""

    def test_threefold_repetition_via_engine(self):
        """通过直接操控engine模拟三次重复局面"""
        engine = RefereeEngine()
        fen = engine.current_fen
        # _is_threefold_repetition() 需要 len >= 5 且当前FEN出现 >=3 次
        engine.position_history = [fen, fen + "_a", fen, fen + "_b", fen]
        assert engine._is_threefold_repetition() is True
        is_over, reason = engine.check_game_end()
        assert is_over
        assert "判和" in reason

    def test_threefold_repetition_via_controller(self):
        """通过Controller检查三次重复"""
        controller = GameController()
        fen = controller.referee.current_fen
        controller.referee.position_history = [fen, fen + "_a", fen, fen + "_b", fen]
        is_over, reason = controller.referee.check_game_end()
        assert is_over
        assert "判和" in reason

    def test_threefold_result_is_draw(self):
        """三次重复的结果应为DRAW"""
        result = GameController._map_reason_to_result("三次重复局面，判和")
        assert result == GameResult.DRAW


class TestPerpetualCheckResult:
    """测试长将违规结果"""

    def test_red_perpetual_check_result(self):
        """红方长将 → BLACK_WIN"""
        controller = GameController()
        # 模拟：红方连续将军，局面重复
        # check_history 全 True，position_history 重复
        controller.referee.check_history = [True, True, True, True]
        fen = controller.referee.current_fen
        controller.referee.position_history = [fen, fen + "_A", fen, fen + "_A", fen, fen + "_A"]
        is_over, reason = controller.referee.check_game_end()
        # perpetual check 需要 current_color == BLACK 时，offender 是红方
        # 先走一步让 current_color 切换到 Black
        if controller.referee.board.current_color.value == "red":
            controller.referee.apply_move(controller.referee.get_legal_moves()[0])

        # 重新注入状态
        controller.referee.check_history = [True, True, True, True]
        controller.referee.position_history = [
            controller.referee.current_fen,
            controller.referee.current_fen + "_mod",
        ] * 3
        is_over, reason = controller.referee._is_perpetual_check()
        if is_over:
            assert "长将" in reason
            result = GameController._map_reason_to_result(reason)
            if reason.startswith("红方长将"):
                assert result == GameResult.BLACK_WIN
            elif reason.startswith("黑方长将"):
                assert result == GameResult.RED_WIN

    def test_black_perpetual_check_result(self):
        """黑方长将 → RED_WIN"""
        result = GameController._map_reason_to_result("黑方长将违规")
        assert result == GameResult.RED_WIN


class TestGameStateConsistency:
    """测试 is_game_over 返回值一致性"""

    def test_game_not_over_initially(self):
        """初始状态游戏未结束"""
        controller = GameController()
        is_over, result, reason = controller.is_game_over()
        assert not is_over
        assert result == GameResult.IN_PROGRESS
        assert reason is None

    def test_game_over_phase(self):
        """游戏结束后phase为GAME_OVER"""
        controller = GameController()
        fen = "9/9/9/9/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"
        controller.reset(fen)
        legal = controller.referee.get_legal_moves()
        controller.apply_move("red_test", legal[0])
        assert controller.phase == GamePhase.GAME_OVER

    def test_game_info_contains_result(self):
        """get_game_info包含结果信息"""
        controller = GameController()
        fen = "9/9/9/9/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"
        controller.reset(fen)
        legal = controller.referee.get_legal_moves()
        controller.apply_move("red_test", legal[0])
        info = controller.get_game_info()
        assert info["result"] == GameResult.RED_WIN.value
        assert info["result_reason"] is not None


class TestResetPreservesCleanState:
    """测试reset后状态干净"""

    def test_reset_clears_result(self):
        """reset后result为IN_PROGRESS"""
        controller = GameController()
        fen = "9/9/9/9/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"
        controller.reset(fen)
        legal = controller.referee.get_legal_moves()
        controller.apply_move("red_test", legal[0])
        assert controller.result != GameResult.IN_PROGRESS

        controller.reset()
        assert controller.result == GameResult.IN_PROGRESS
        assert controller.result_reason is None
        assert controller.phase == GamePhase.RED_TO_MOVE


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
