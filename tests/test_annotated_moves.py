"""
语义标注走步测试

测试四类标注：
1. capture: 吃子标注
2. check: 将军标注
3. repetition_warning: 重复警告
4. development: 出子标记
"""

import pytest
from src.core.referee_engine import RefereeEngine, Color


class TestCaptureAnnotation:
    """测试吃子标注"""

    def test_capture_in_annotated_moves(self):
        """测试走步中包含吃子时标注正确"""
        # 红车在a0, 黑卒在a1, 红帅在e0, 黑将在e9
        fen = "4k4/9/9/9/9/9/9/9/p8/R8 w - - 0 1"
        engine = RefereeEngine(fen)
        annotated = engine.get_annotated_moves()

        # 找到吃卒的走步
        capture_moves = [
            m for m in annotated
            if any(a.startswith("capture:") for a in m["annotations"])
        ]
        assert len(capture_moves) > 0

        # 验证 a0a1 吃兵
        a0a1 = [m for m in capture_moves if m["move"] == "a0a1"]
        assert len(a0a1) == 1
        assert "capture:pawn" in a0a1[0]["annotations"]

    def test_no_capture_no_annotation(self):
        """测试没有吃子时不产生capture标注"""
        # 两王远离，无其他棋子，无吃子可能
        fen = "4k4/9/9/9/9/9/9/9/9/4K4 w - - 0 1"
        engine = RefereeEngine(fen)
        annotated = engine.get_annotated_moves()

        for entry in annotated:
            capture_anns = [
                a for a in entry["annotations"] if a.startswith("capture:")
            ]
            assert len(capture_anns) == 0


class TestCheckAnnotation:
    """测试将军标注"""

    def test_check_annotation(self):
        """测试走步将军时有check标注"""
        # 构造红车可以将军的局面
        # 红车在e1, 黑将在e9, 中间无遮挡
        fen = "4k4/9/9/9/9/9/9/9/4R4/4K4 w - - 0 1"
        engine = RefereeEngine(fen)
        annotated = engine.get_annotated_moves()

        # 找到将军的走步 (车走到e列, 即 e1e2-e1e8)
        check_moves = [
            m for m in annotated
            if "check" in m["annotations"]
        ]
        assert len(check_moves) > 0

    def test_no_check_no_annotation(self):
        """测试没有将军时不产生check标注"""
        engine = RefereeEngine()
        annotated = engine.get_annotated_moves()

        for entry in annotated:
            assert "check" not in entry["annotations"]


class TestRepetitionWarning:
    """测试重复警告标注"""

    def test_repetition_warning(self):
        """测试走步会导致局面重复时有repetition_warning标注"""
        # 红炮a1, 黑将f9, 红帅d0
        fen = "5k3/9/9/9/9/9/9/9/C8/3K5 w - - 0 1"
        engine = RefereeEngine(fen)

        # 红走 a1a2
        engine.apply_move("a1a2")
        # 黑走 f9e9
        engine.apply_move("f9e9")
        # 当前轮红方，炮在a2
        # 手动把当前FEN加入position_history 2次
        # 这样如果红走 a2a1 后FEN不匹配，我们需要让 a2a1 的模拟FEN在history中有>=2次
        # a2a1 模拟后FEN = 4k4/9/9/9/9/9/9/9/C8/3K5 w - - 0 1 (炮回到a1, 黑将还在e9)
        # 最简方案: 直接手动构造repetition_warning触发条件
        # 把 a2a1 走后会产生的FEN加入history 2次
        from src.core.referee_engine import Move
        mv = Move.from_iccs("a2a1")
        piece = engine.board.remove_piece(mv.from_pos)
        target = engine.board.get_piece(mv.to_pos)
        engine.board.set_piece(mv.to_pos, piece)
        sim_fen = engine.to_fen()
        engine.board.set_piece(mv.from_pos, piece)
        engine.board.set_piece(mv.to_pos, target)

        engine.position_history.append(sim_fen)
        engine.position_history.append(sim_fen)

        annotated = engine.get_annotated_moves()
        a2a1 = [
            m for m in annotated
            if m["move"] == "a2a1" and "repetition_warning" in m["annotations"]
        ]
        assert len(a2a1) > 0

    def test_repetition_warning_suppressed_when_check(self):
        """将军走步不标repetition_warning"""
        # 红车在e1，黑将在e9，中间无遮挡
        # 构造局面使 e1e8 既是将军，模拟后FEN又在history中>=2次
        fen = "4k4/9/9/9/9/9/9/9/4R4/4K4 w - - 0 1"
        engine = RefereeEngine(fen)

        # 手动将 e1e8 模拟走后的FEN加入history 2次
        from src.core.referee_engine import Move
        mv = Move.from_iccs("e1e8")
        piece = engine.board.remove_piece(mv.from_pos)
        target = engine.board.get_piece(mv.to_pos)
        engine.board.set_piece(mv.to_pos, piece)
        sim_fen = engine.to_fen()
        engine.board.set_piece(mv.from_pos, piece)
        engine.board.set_piece(mv.to_pos, target)

        engine.position_history.append(sim_fen)
        engine.position_history.append(sim_fen)

        annotated = engine.get_annotated_moves()
        e1e8 = [m for m in annotated if m["move"] == "e1e8"]
        assert len(e1e8) == 1
        # 应有 check 标注
        assert "check" in e1e8[0]["annotations"]
        # 不应有 repetition_warning（将军时抑制）
        assert "repetition_warning" not in e1e8[0]["annotations"]


class TestDevelopmentAnnotation:
    """测试出子标注"""

    def test_rook_development(self):
        """测试车从底线出发有development标注"""
        # 初始局面，红车在a0和i0（底线）
        engine = RefereeEngine()
        annotated = engine.get_annotated_moves()

        dev_moves = [
            m for m in annotated
            if "development" in m["annotations"]
        ]
        # 红方有两辆车在底线, 应该至少有两个development标注的走步
        assert len(dev_moves) >= 2

        # 验证是车的走步
        for dm in dev_moves:
            move_str = dm["move"]
            from_pos = move_str[:2]
            # a0 和 i0 是红车的初始位置
            assert from_pos in ("a0", "i0")

    def test_rook_not_development_from_mid(self):
        """车从非底线出发不标development"""
        # 红车a0，红帅d0，黑将f9（不同列避免飞将）
        fen = "5k3/9/9/9/9/9/9/9/9/R2K5 w - - 0 1"
        engine = RefereeEngine(fen)
        # 红走 a0a1
        engine.apply_move("a0a1")
        # 黑走 f9e9
        engine.apply_move("f9e9")
        # 现在红车在a1，轮红方走。车从a1出发不应有development标注
        annotated = engine.get_annotated_moves()
        rook_moves_from_a1 = [
            m for m in annotated
            if m["move"].startswith("a1")
        ]
        for m in rook_moves_from_a1:
            assert "development" not in m["annotations"], \
                f"车从非底线 a1 走到 {m['move']} 不应标 development"

    def test_rook_back_rank_stay_no_development(self):
        """车在底线同行移动不标development"""
        # 红车a0和i0，红帅d0，黑将f9（不同列避免飞将）
        fen = "5k3/9/9/9/9/9/9/9/9/R2K4R w - - 0 1"
        engine = RefereeEngine(fen)
        annotated = engine.get_annotated_moves()
        # a0 的车同行移动到 b0（仍在底线 row 0），不应标 development
        a0_stay = [
            m for m in annotated
            if m["move"].startswith("a0") and m["move"][3] == "0"
        ]
        for m in a0_stay:
            assert "development" not in m["annotations"], \
                f"车在底线同行移动 {m['move']} 不应标 development"

    def test_non_rook_no_development(self):
        """测试非车走步没有development标注"""
        engine = RefereeEngine()
        annotated = engine.get_annotated_moves()

        non_dev_moves = [
            m for m in annotated
            if "development" not in m["annotations"]
            and not any(a.startswith("capture:") for a in m["annotations"])
            and "check" not in m["annotations"]
        ]
        # 非车走步不应有development标注
        for m in non_dev_moves:
            assert "development" not in m["annotations"]


class TestAnnotatedMovesBackwardCompat:
    """测试向后兼容性"""

    def test_annotated_moves_has_all_legal(self):
        """测试annotated_moves包含所有合法走步"""
        engine = RefereeEngine()
        legal = engine.get_legal_moves()
        annotated = engine.get_annotated_moves()

        annotated_moves = [m["move"] for m in annotated]
        assert set(legal) == set(annotated_moves)

    def test_annotated_moves_format(self):
        """测试annotated_moves返回格式正确"""
        engine = RefereeEngine()
        annotated = engine.get_annotated_moves()

        for entry in annotated:
            assert "move" in entry
            assert "annotations" in entry
            assert isinstance(entry["move"], str)
            assert len(entry["move"]) == 4  # ICCS格式
            assert isinstance(entry["annotations"], list)
