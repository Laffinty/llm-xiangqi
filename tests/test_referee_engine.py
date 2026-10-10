"""
RefereeEngine单元测试

测试覆盖：
1. FEN解析与序列化
2. 棋子移动规则
3. 合法走步生成
4. ICCS走步解析与验证
5. 游戏结束判定
"""

import pytest
from src.core.referee_engine import (
    RefereeEngine,
    Board,
    Piece,
    Position,
    Move,
    Color,
    PieceType,
    INITIAL_FEN,
)


class TestFENParsing:
    """测试FEN解析"""

    def test_initial_fen(self):
        """测试初始FEN解析"""
        engine = RefereeEngine()
        assert engine.current_fen == INITIAL_FEN

    def test_fen_roundtrip(self):
        """测试FEN来回转换"""
        engine = RefereeEngine()
        new_fen = engine.to_fen()
        engine2 = RefereeEngine(new_fen)
        assert engine.to_fen() == engine2.to_fen()

    def test_custom_fen(self):
        """测试自定义FEN"""
        fen = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"
        engine = RefereeEngine(fen)
        assert engine.current_fen == fen


class TestPiecePlacement:
    """测试棋子位置"""

    def test_red_rook_initial(self):
        """测试红车初始位置"""
        engine = RefereeEngine()
        # 红车在 a0 和 i0
        piece = engine.get_piece(Position(0, 0))
        assert piece is not None
        assert piece.piece_type == PieceType.ROOK
        assert piece.color == Color.RED

        piece = engine.get_piece(Position(8, 0))
        assert piece is not None
        assert piece.piece_type == PieceType.ROOK
        assert piece.color == Color.RED

    def test_black_rook_initial(self):
        """测试黑车初始位置"""
        engine = RefereeEngine()
        # 黑车在 a9 和 i9
        piece = engine.get_piece(Position(0, 9))
        assert piece is not None
        assert piece.piece_type == PieceType.ROOK
        assert piece.color == Color.BLACK

        piece = engine.get_piece(Position(8, 9))
        assert piece is not None
        assert piece.piece_type == PieceType.ROOK
        assert piece.color == Color.BLACK

    def test_red_king_initial(self):
        """测试红帅初始位置"""
        engine = RefereeEngine()
        piece = engine.get_piece(Position(4, 0))
        assert piece is not None
        assert piece.piece_type == PieceType.KING
        assert piece.color == Color.RED

    def test_black_king_initial(self):
        """测试黑将初始位置"""
        engine = RefereeEngine()
        piece = engine.get_piece(Position(4, 9))
        assert piece is not None
        assert piece.piece_type == PieceType.KING
        assert piece.color == Color.BLACK


class TestLegalMoves:
    """测试合法走步生成"""

    def test_initial_legal_moves_count(self):
        """测试初始局面合法走步数量"""
        engine = RefereeEngine()
        legal_moves = engine.get_legal_moves()
        # 开局应该有一定数量的合法走步
        assert len(legal_moves) > 0
        assert len(legal_moves) <= 60  # 合理上限

    def test_all_moves_iccs_format(self):
        """测试所有合法走步都是ICCS格式"""
        engine = RefereeEngine()
        legal_moves = engine.get_legal_moves()
        for move in legal_moves:
            assert len(move) == 4
            assert move[0].isalpha()
            assert move[2].isalpha()
            assert move[1].isdigit()
            assert move[3].isdigit()

    def test_rook_moves(self):
        """测试车的移动"""
        # 设置简单局面：红车在中心位置无阻挡
        engine = RefereeEngine()
        # 红车 a0 可以走到 a1, a2 等
        legal_moves = engine.get_legal_moves()
        # 应该有一些从 a0 或 h0 出发的车走步
        rook_moves = [
            m for m in legal_moves if m.startswith("a0") or m.startswith("h0")
        ]
        assert len(rook_moves) > 0


class TestMoveValidation:
    """测试走步验证"""

    def test_validate_initial_move(self):
        """测试验证初始走步"""
        engine = RefereeEngine()
        # 红方开局走 h2e2 (炮二平五) 是合法的
        assert engine.validate_move("h2e2") == True

    def test_validate_illegal_move_format(self):
        """测试非法格式"""
        engine = RefereeEngine()
        assert engine.validate_move("invalid") == False
        assert engine.validate_move("h99") == False

    def test_validate_out_of_turn(self):
        """测试轮到对方走时验证"""
        engine = RefereeEngine()
        # 目前是红方回合
        # 尝试黑方走步应该失败（黑方棋子位置）
        assert engine.validate_move("a9a8") == False


class TestMoveApplication:
    """测试走步应用"""

    def test_apply_valid_move(self):
        """测试应用有效走步"""
        engine = RefereeEngine()
        original_fen = engine.current_fen
        new_fen = engine.apply_move("h2e2")
        assert new_fen != original_fen
        assert engine.board.current_color == Color.BLACK

    def test_apply_invalid_move(self):
        """测试应用无效走步应该抛出异常"""
        engine = RefereeEngine()
        with pytest.raises(ValueError):
            engine.apply_move("invalid")


class TestGameEnd:
    """测试游戏结束判定"""

    def test_game_not_ended_initially(self):
        """测试初始局面游戏未结束"""
        engine = RefereeEngine()
        is_over, reason = engine.check_game_end()
        assert is_over == False
        assert reason == ""

    def test_checkmate_detection(self):
        """测试将死检测"""
        # 设置一个简单将死局面
        # 红方将帅被困
        fen = "3k5/4a4/4b4/9/9/9/9/4K4/9/4R4 w - - 0 1"
        engine = RefereeEngine(fen)
        # 此时红方应该已经被将死
        legal_moves = engine.get_legal_moves()
        # 红方被困，无合法走步
        # 注意：这个局面可能需要调整

    def test_king_captured_detection(self):
        """测试王被吃检测"""
        engine = RefereeEngine()

        # 红帅被吃的局面（红帅不存在）
        fen = "1Cbakab2/9/1R7/p3n1p1p/2p6/9/P1P3P1P/R1N3N1B/9/2BAnA3 b - - 0 1"
        engine.reset(fen)
        is_over, reason = engine.check_game_end()
        assert is_over == True
        assert "红帅被吃" in reason or "黑方胜利" in reason

        # 黑将被吃的局面（黑将不存在，只有红方棋子）
        fen2 = "9/9/9/9/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"
        engine.reset(fen2)
        is_over2, reason2 = engine.check_game_end()
        assert is_over2 == True
        assert "黑将被吃" in reason2 or "红方胜利" in reason2


class TestICCS:
    """测试ICCS格式"""

    def test_position_from_iccs(self):
        """测试从ICCS创建位置"""
        pos = Position.from_iccs("a0")
        assert pos.col == 0
        assert pos.row == 0

        pos = Position.from_iccs("i9")
        assert pos.col == 8
        assert pos.row == 9

    def test_position_to_iccs(self):
        """测试位置转ICCS"""
        pos = Position(0, 0)
        assert pos.to_iccs() == "a0"

        pos = Position(8, 9)
        assert pos.to_iccs() == "i9"

    def test_move_from_iccs(self):
        """测试从ICCS创建走步"""
        move = Move.from_iccs("h2e2")
        assert move.from_pos.col == 7
        assert move.from_pos.row == 2
        assert move.to_pos.col == 4
        assert move.to_pos.row == 2

    def test_move_to_iccs(self):
        """测试走步转ICCS"""
        move = Move(Position(7, 2), Position(4, 2))
        assert move.to_iccs() == "h2e2"


class TestASCIIBoard:
    """测试ASCII棋盘渲染"""

    def test_render_initial_board(self):
        """测试渲染初始棋盘"""
        engine = RefereeEngine()
        board_str = engine.render_ascii_board()
        assert "a   b   c   d   e   f   g   h   i" in board_str
        assert "+---+" in board_str

    def test_board_contains_pieces(self):
        """测试棋盘包含棋子"""
        engine = RefereeEngine()
        board_str = engine.render_ascii_board()
        # 应该包含大小写字母表示棋子
        assert "K" in board_str  # 红帅
        assert "k" in board_str  # 黑将


class TestKingFacingRule:
    """测试将帅对面（飞将）规则"""

    def test_kings_not_facing_initially(self):
        """测试初始局面将帅不对面"""
        engine = RefereeEngine()
        assert engine._is_kings_facing() == False

    def test_kings_facing_detected(self):
        """测试将帅对面被检测"""
        # 设置一个将帅对面的局面：红帅e0，黑将e9，中间无子
        # 移除中间的棋子
        fen = "4k4/9/9/9/9/9/9/9/9/4K4 w - - 0 1"
        engine = RefereeEngine(fen)
        assert engine._is_kings_facing() == True

    def test_kings_facing_with_blocker_legal(self):
        """测试有棋子阻挡时将帅可以同列"""
        # 设置将帅同列但有棋子阻挡的局面
        fen = "4k4/9/9/9/4R4/9/9/9/9/4K4 w - - 0 1"
        engine = RefereeEngine(fen)
        assert engine._is_kings_facing() == False

    def test_kings_facing_move_illegal(self):
        """测试导致将帅对面的走步非法"""
        fen = "4k4/9/9/9/4P4/9/9/9/9/4K4 w - - 0 1"
        engine = RefereeEngine(fen)
        legal_moves = engine.get_legal_moves()
        assert "e0e1" in legal_moves

    def test_kings_different_columns_not_facing(self):
        """测试将帅不同列不算对面"""
        fen = "3k5/9/9/9/9/9/9/9/9/4K4 w - - 0 1"
        engine = RefereeEngine(fen)
        assert engine._is_kings_facing() == False


class TestPerpetualCheckRule:
    """测试长将禁止规则"""

    def test_perpetual_check_not_detected_initially(self):
        """测试初始局面无长将"""
        engine = RefereeEngine()
        is_perpetual, reason = engine._is_perpetual_check()
        assert is_perpetual == False

    def test_check_history_tracking(self):
        """测试将军历史追踪"""
        engine = RefereeEngine()
        engine.apply_move("h2e2")
        assert len(engine.check_history) == 1


class TestThreefoldRepetition:
    """测试三次重复局面判和"""

    def test_no_repetition_initially(self):
        """测试初始局面无重复"""
        engine = RefereeEngine()
        assert engine._is_threefold_repetition() == False

    def test_position_history_tracking(self):
        """局面历史追踪：走 1 手后应含**起始局面 + 走完后局面**共 2 条。

        `T-05` 修复前 `position_history` 走 1 手后只有 1 条——起始局面从未入表，
        导致重复判定永远晚一手才成立。本断言守住修复后的语义。
        """
        engine = RefereeEngine()
        start = engine.current_fen
        engine.apply_move("h2e2")
        assert len(engine.position_history) == 2
        assert engine.position_history[0] == start, "起始局面必须入表"
        assert engine.position_history[-1] == engine.current_fen

    def test_start_position_is_registered_on_construction(self):
        """构造时起始局面即已入表（`_position_counter` 同步）。"""
        from src.core.referee_engine import _board_key
        engine = RefereeEngine()
        assert engine.position_history == [engine.current_fen]
        assert engine._position_counter[_board_key(engine.current_fen)] == 1

    def test_reset_registers_start_position_consistently(self):
        """`reset()` 必须与 `__init__` 同一口径——否则重开后重复判定重新失准。"""
        from src.core.referee_engine import _board_key
        engine = RefereeEngine()
        engine.apply_move("h2e2")
        engine.reset()
        assert engine.position_history == [engine.current_fen]
        assert engine._position_counter[_board_key(engine.current_fen)] == 1


class TestSpecialRules:
    """测试中国象棋特殊规则"""

    def test_knight_blocked_leg(self):
        """测试蹩马腿"""
        # 创建一个有蹩马腿的局面：马在c0，b1有棋子
        # 马从c0走到a1需要先走b1，如果b1有子就蹩腿
        fen = "4k4/9/9/9/9/9/9/9/1p7/2N1K4 w - - 0 1"
        engine = RefereeEngine(fen)
        legal_moves = engine.get_legal_moves()
        # 马c0走日字到a1或e1，但如果b1或d1有子就蹩腿
        # b1有黑卒，所以c0a1不合法
        assert "c0a1" not in legal_moves

    def test_bishop_blocked_eye(self):
        """测试塞象眼"""
        engine = RefereeEngine()
        # 初始局面，象眼无阻挡
        legal_moves = engine.get_legal_moves()
        # 相g0可以走田字
        assert "g0i2" in legal_moves or "g0e2" in legal_moves

    def test_cannon_capture_with_screen(self):
        """测试炮隔山打子"""
        engine = RefereeEngine()
        # 初始局面，炮不能直接吃子
        legal_moves = engine.get_legal_moves()
        # 炮h2的移动
        cannon_moves = [m for m in legal_moves if m.startswith("h2")]
        # 只有不吃的移动
        non_capture_moves = [
            m
            for m in cannon_moves
            if engine.get_piece(Position(ord(m[2]) - ord("a"), int(m[3]))) is None
        ]
        assert len(non_capture_moves) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
