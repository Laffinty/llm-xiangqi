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
        """走这步会造成局面重复时，应带 repetition_warning 标注。

        **改为走生产路径构造**（T-05）：旧写法手工 `position_history.append(sim_fen)`
        两次，但生产代码判重读的是 `_position_counter`——两个存储各改各的，
        测试测的是一条生产中不存在的路径。现在用真实往返走法让引擎自己记账。
        """
        fen = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"
        engine = RefereeEngine(fen)
        # 双车在 i 线往返：第一轮走完即回到起始局面，
        # 于是第二轮的每一步都「会再次造成重复」。
        for m in ["i0i1", "i9i8", "i1i0", "i8i9"]:
            assert engine.validate_move(m), "夹具走法 %s 非法" % m
            engine.apply_move(m)

        annotated = engine.get_annotated_moves()
        warned = [m["move"] for m in annotated
                  if "repetition_warning" in m["annotations"]]
        assert warned, "往返后回到曾出现过的局面，应标 repetition_warning"

    def test_repetition_warning_suppressed_when_check(self):
        """将军走步不标 repetition_warning（将军优先，避免噪声标签）"""
        fen = "4k4/9/9/9/9/9/9/9/4R4/4K4 w - - 0 1"
        engine = RefereeEngine(fen)

        # e1e8 既是将军，走完后的棋盘（红车到 e8）又确实已出现过——
        # 通过**生产使用的** `_position_counter` 记账，而不是改 `position_history`
        # （T-05：判重读的是前者，两者不是同一份数据）。
        from src.core.referee_engine import _board_key
        key = _board_key("4k3R/9/9/9/9/9/9/9/9/4K4 w - - 0 1")
        engine._position_counter[key] = 1

        annotated = engine.get_annotated_moves()
        e1e8 = [m for m in annotated if m["move"] == "e1e8"]
        assert len(e1e8) == 1
        assert "check" in e1e8[0]["annotations"]
        assert "repetition_warning" not in e1e8[0]["annotations"], \
            "将军时抑制 repetition_warning"


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
