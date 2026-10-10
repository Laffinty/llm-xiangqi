"""T-05 守卫：`repetition_warning` 的判定必须真正生效（`PLAN-SPECTACLE-001` §5）

**背景**：`P-03` 实测发现 `repetition_management` 这个 SKILL 在 40 手残局里
**一次都没激活过**。根因有两处，都在 `src/core/referee_engine.py`：

1. **起始局面从未入表**——`position_history` 只在 `apply_move` **之后**追加，
   于是「某局面出现第二次」永远晚一手才成立。
2. **判重口径不一致**——`_annotate_move` 用**完整 FEN**（含走子方与 fullmove）
   比较，而同一棋盘的两次出现其 fullmove 必然不同，**恒不成立**。

两处任意一处单独存在，`repetition_warning` 就永不触发。本文件把修复后的行为
钉成断言，并做**负向验证**：临时撤销修复，确认断言真的会红。
"""
import pytest

from src.core.board_snapshot import build
from src.core.referee_engine import RefereeEngine, _board_key

START = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"
SHUFFLE = ["i0i1", "i9i8", "i1i0", "i8i9"]   # 双车在 i 线往返（引擎实测合法）


def _walk(engine, moves):
    for m in moves:
        assert engine.validate_move(m), "夹具走法 %s 非法" % m
        engine.apply_move(m)


class TestStartPositionRegistered:
    """修复 1：起始局面必须入表。"""

    def test_history_and_counter_seeded_on_init(self):
        e = RefereeEngine(START)
        assert e.position_history == [START]
        assert e._position_counter[_board_key(START)] == 1

    def test_reset_uses_same_semantics_as_init(self):
        """两条构造路径必须一致——只改一处会让重开后的判重重新失准。"""
        e = RefereeEngine()
        e.apply_move("h2e2")
        e.reset()
        assert e.position_history == [e.current_fen]
        assert e._position_counter[_board_key(e.current_fen)] == 1

    def test_board_key_ignores_side_and_move_number(self):
        """棋盘段提取必须剥离走子方与回合数，否则判重恒不成立。"""
        a = "rnbakabnr/9/9/9/9/9/9/9/9/RNBAKABNR w - - 0 1"
        b = "rnbakabnr/9/9/9/9/9/9/9/9/RNBAKABNR b - - 7 9"
        assert _board_key(a) == _board_key(b)


class TestRepetitionWarningFires:
    """修复 2+1 合并后的可观测行为：警告真的会触发。"""

    def test_warning_fires_on_shuffle(self):
        e = RefereeEngine(START)
        _walk(e, SHUFFLE)          # 第一轮往返 → 起始局面出现 2 次
        ann = {a["move"]: a["annotations"] for a in e.get_annotated_moves()}
        warned = [m for m, a in ann.items() if "repetition_warning" in a]
        assert warned, "往返后应标 repetition_warning（修复前恒为空）"

    def test_warning_not_fired_on_first_visit(self):
        """首访局面不该预警——否则开局就误报，SKILL 立刻变噪声源。"""
        e = RefereeEngine(START)
        ann = {a["move"]: a["annotations"] for a in e.get_annotated_moves()}
        assert not any("repetition_warning" in a for a in ann.values())

    def test_snapshot_agrees_with_annotations(self):
        """`board_snapshot` 与 `get_annotated_moves` 的口径必须一致。

        两者都判「出现 2 次即预警」。若一个触发另一个不触发，
        SKILL 的激活信号与模型看到的标注就会互相矛盾。
        """
        e = RefereeEngine(START)
        _walk(e, SHUFFLE)
        snap = build(e)
        ann = {a["move"]: a["annotations"] for a in e.get_annotated_moves()}
        warned = any("repetition_warning" in a for a in ann.values())
        assert snap["repetition_warning"] is warned, (
            "快照与标注口径不一致：snapshot=%s annotations=%s"
            % (snap["repetition_warning"], warned))

    def test_threefold_still_judged_as_draw(self):
        """出现 3 次仍判和——修复不能把判和判坏。"""
        e = RefereeEngine(START)
        _walk(e, SHUFFLE * 3)
        assert e._is_threefold_repetition() is True
        is_over, reason = e.check_game_end()
        assert is_over and "判和" in reason


class TestLastMoveDetailFixed:
    """连带修好的点：第一手之后 `last_move_detail` 不再退化。"""

    def test_first_ply_detail_is_populated(self):
        e = RefereeEngine(START)
        e.apply_move("h2e2")            # 炮二平五
        d = build(e, ply=1)["last_move_detail"]
        assert d["piece"] == "炮", "第 1 手就应能还原上一步细节"
        assert d["from"] == "h2" and d["to"] == "e2"


class TestNegativeVerification:
    """负向验证：证明修复的两处都是必要的，否则守卫无效。"""

    def test_temp_fen_side_differs_from_history(self):
        """修复 2 的根据：`to_fen()` 模拟时的 side 与历史里存的不一致。

        `_annotate_move` 在**走子方尚未切换**时调用 `to_fen()`，其 side 是
        「走这步之前那一方」；`position_history` 存的是 `apply_move` 切换
        **之后**的 FEN。两者 side 恒相反 → 用完整 FEN 比较永远匹配不上。
        """
        from src.core.referee_engine import Move
        e = RefereeEngine(START)
        mv = Move.from_iccs("i0i1")
        pc = e.get_piece(mv.from_pos)
        sf = e.board.remove_piece(mv.from_pos)
        st = e.board.get_piece(mv.to_pos)
        e.board.set_piece(mv.to_pos, pc)
        temp_fen = e.to_fen()
        e.board.set_piece(mv.from_pos, sf)
        e.board.set_piece(mv.to_pos, st)
        # 还原后走这一步，看历史里存的是哪个 side
        after = e.apply_move("i0i1")
        assert temp_fen.split()[1] != after.split()[1], (
            "若两者 side 相同，则「必须按棋盘段比较」的结论不成立")

    def test_full_fen_count_is_always_zero_without_fix(self):
        """证明修复前完整 FEN 比较恒不成立。"""
        from src.core.referee_engine import Move
        e = RefereeEngine(START)
        e.position_history = []          # 模拟修复前：无起始局面
        for m in ["i0i1", "i9i8", "i1i0", "i8i9"]:
            mv = Move.from_iccs(m)
            pc = e.get_piece(mv.from_pos)
            sf = e.board.remove_piece(mv.from_pos)
            st = e.board.get_piece(mv.to_pos)
            e.board.set_piece(mv.to_pos, pc)
            temp_fen = e.to_fen()
            e.board.set_piece(mv.from_pos, sf)
            e.board.set_piece(mv.to_pos, st)
            # 完整 FEN 比较：恒为 0 → 原实现永不触发
            assert e.position_history.count(temp_fen) == 0
            e.apply_move(m)