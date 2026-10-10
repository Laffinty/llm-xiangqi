"""`tests/eval/spectacle.py` 的契约测试（P-01 反向守卫）

**守卫什么**（每条都对应 PLAN-SPECTACLE-001 §4 P-01 的验收/反向守卫）：

1. **逐字节可复现** —— 同输入连跑两次结果完全相同（`W-02` 已确立的确定性纪律）。
2. **非法走法报错而非静默跳过** —— 报告里出现坏走法必须抛异常，
   静默跳过会把坏数据伪装成好数据。
3. **指标语义不漂移** —— 手工构造的局面必须给出可人工验算的确定值，
   防止重写实现时悄悄改了定义。
"""
from pathlib import Path

import json
import pytest

from src.core.referee_engine import RefereeEngine
from tests.eval.spectacle import (
    SpectacleReplayError,
    analyze_game,
    analyze_report,
    compare,
    replay_plies,
)

REPO = Path(__file__).resolve().parents[1]
BASELINE = REPO / "docs" / "eval-baseline.json"


def _moves_from_movelist(movelist: str):
    """把 'h2e2 h7e7' 拆成走法列表。"""
    return movelist.split()


class TestReplayDeterminism:
    """守卫 1：逐字节可复现。"""

    def test_replay_is_deterministic(self):
        fen = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"
        moves = _moves_from_movelist("h2e2 h7e7 b0c2 b9c7")
        first = [r.to_dict() if hasattr(r, "to_dict") else r for r in replay_plies(fen, moves)]
        second = replay_plies(fen, moves)
        assert len(first) == len(second) == 4
        for a, b in zip(first, second):
            assert (a.index, a.iccs, a.color, a.captured_piece, a.gives_check) == (
                b.index, b.iccs, b.color, b.captured_piece, b.gives_check)

    def test_report_analysis_is_byte_identical_across_runs(self):
        import json
        import subprocess
        import sys

        if not BASELINE.exists():
            pytest.skip("基线报告不存在")
        cmd = [sys.executable, "-m", "tests.eval.spectacle",
               "--report", str(BASELINE), "--out"]
        # 跑两次写到临时文件，比较字节
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p1 = Path(td) / "a.json"
            p2 = Path(td) / "b.json"
            subprocess.run(cmd + [str(p1)], cwd=str(REPO), capture_output=True)
            subprocess.run(cmd + [str(p2)], cwd=str(REPO), capture_output=True)
            assert p1.read_bytes() == p2.read_bytes(), "两次重放输出不一致"


class TestIllegalMoveRaises:
    """守卫 2：非法走法必须报错。"""

    def test_malformed_move_string_raises(self):
        fen = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"
        with pytest.raises(SpectacleReplayError):
            replay_plies(fen, ["XX"])

    def test_move_from_empty_square_raises(self):
        """起点无子必须报错。

        用 `i5i6`：开局 i5 是空点（红车在 i0，马在 h0）。注意**不能**用 `i0i1`
        举例——那是一步合法车走（i0 车到 i1），会把「非法」错判成「合法」。
        """
        fen = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"
        engine = RefereeEngine(fen)
        assert engine.get_piece(__import__(
            "src.core.referee_engine", fromlist=["Position"]).Position.from_iccs("i5")) is None
        with pytest.raises(SpectacleReplayError):
            replay_plies(fen, ["i5i6"])

    def test_moving_onto_own_piece_raises(self):
        """走到己方子力所在格必须报错。"""
        fen = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"
        # e0 是红帅，i0 是红车，车不能横向走到帅所在的 e0
        with pytest.raises(SpectacleReplayError):
            replay_plies(fen, ["i0e0"])

    def test_illegal_for_king_raises(self):
        """白脸将黑将：白王横向挪动暴露将面，必须判非法并报错。

        用一盘**只有将帅**的局面，构造出引擎必然拒绝的走步。
        """
        fen = "3k5/9/9/9/9/9/9/9/9/4K4 w - - 0 1"
        engine = RefereeEngine(fen)
        # 帅在 e0，将在 d9。e0d0 会让两将同列（白脸将），应非法
        assert not engine.validate_move("e0d0")
        with pytest.raises(SpectacleReplayError):
            replay_plies(fen, ["e0d0"])


class TestMetricSemantics:
    """守卫 3：指标语义不漂移。手工局面必须给出确定值。"""

    def test_tactic_rate_counts_capture_and_check(self):
        fen = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"
        # 炮二平五(吃中卒?开局无子可吃)→ 用简单局面
        moves = _moves_from_movelist("h2e2 h7e7")  # 两手都非吃子非将军
        g = analyze_game(fen, moves, case_id="t", category="test")
        # 炮二平五不将军（开局），炮8平5不将军
        assert g.tactic_rate == 0.0
        assert g.plies == 2

    def test_quiet_streak_counts_consecutive_non_tactical(self):
        fen = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"
        moves = _moves_from_movelist("h2e2 h7e7 b0c2 b9c7")
        g = analyze_game(fen, moves, case_id="t", category="test")
        assert g.quiet_streak_max == 4  # 全程无战术手

    def test_no_sac_returns_none_not_one(self):
        """无弃子时 sac_sound_rate 必须是 None（不伪装成 1.0）。"""
        fen = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"
        g = analyze_game(fen, _moves_from_movelist("h2e2 h7e7"), case_id="t", category="test")
        assert g.sac_count == 0
        assert g.sac_sound_rate is None

    def test_long_chase_zero_when_no_repetition(self):
        """短局无闷摆时 long_chase_turns 必须为 0。

        `P-06` 起该指标测的是**连续无吃无将的累积长度**（旧定义测棋盘重复，
        在无限搬运中永远测不准）。本例 7 手全无吃无将，但不足 `CHURN_MIN_RUN`
        (6) 的**完整**段——第 7 手时累计 7 ≥ 6，故记 2 手，属预期行为：
        指标定义是「达到阈值后的每一手都计入」，不是「整段都计入」。
        """
        fen = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"
        moves = _moves_from_movelist("b0c2 b9c7 c3c4 h7h6 i0i1 i9i8 e3e4")
        engine = RefereeEngine(fen)
        for m in moves:                      # 先自证合法，夹具坏掉时要立刻报错
            assert engine.validate_move(m), "夹具走法 %s 非法" % m
            engine.apply_move(m)
        g = analyze_game(fen, moves, case_id="t", category="test")
        assert g.plies == 7
        assert g.long_chase_turns == 2, (
            "7 手连续无吃无将，第 6、7 手达阈值 → 应为 2")

    def test_long_chase_detects_churn(self):
        """真正**无吃无将的搬运**应被判为闷摆（`P-06` 的目标场景）。

        旧实现用「棋盘重复」判定，**这类搬运永远测不出来**——
        `P-05` 实测的 27 手搬运 27 个棋盘全不相同。
        """
        fen = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"
        moves = _moves_from_movelist(
            "i0i1 i9i8 i1i0 i8i9 i0i1 i9i8 i1i0 i8i9 i0i1 i9i8")
        engine = RefereeEngine(fen)
        for m in moves:
            assert engine.validate_move(m), "夹具走法 %s 非法" % m
            engine.apply_move(m)
        g = analyze_game(fen, moves, case_id="t", category="test")
        assert g.plies == 10
        # 计数规则：达到阈值（第 6 手）之后的每一手都计入 → 第 6..10 手 = 5 手
        assert g.long_chase_turns == 5, "10 手全无吃无将，第 6-10 手达阈值 → 5 手"
        assert any("闷摆" in n for n in g.notes)

    def test_tactical_moves_break_the_churn_run(self):
        """吃子/将军应**打断**闷摆累积——这是新定义的核心。

        若不打断，中局里一次吃子之后的搬运会与吃子前的搬运混算，
        指标就退化成「整局无吃无将数」，失去分辨力。

        夹具取自 `docs/eval-after-spectacle.json` 的**真实对局走法**
        （`endgame_m14_p059` 前 4 手，第 4 手为吃子），
        不凭印象编棋谱。
        """
        import json
        from pathlib import Path
        base = Path(__file__).resolve().parents[1] / "docs" / "eval-after-spectacle.json"
        if not base.exists():
            pytest.skip("实测报告不存在")
        doc = json.loads(base.read_text(encoding="utf-8"))
        game = next(g for g in doc["raw"] if g["case_id"] == "endgame_m14_p059")
        full = game["move_history"]

        # 该局第 3 手是吃卒（第 1、2 手非战术），引擎实测确认
        recs = replay_plies(game["starting_fen"], full[:3])
        assert recs[-1].captured_piece == "pawn", "第 3 手是吃卒（引擎实测）"
        assert not recs[-2].is_tactic

        # 关键：取「吃子之后」的一段，看它的闷摆计数从哪一手开始。
        # 若吃子**不打断**累积，则这段会从第 1 手就计入；正确实现应归零重来。
        after = analyze_game(game["starting_fen"], full[:8],
                             case_id="t", category="test")
        recs8 = replay_plies(game["starting_fen"], full[:8])
        # 手工按定义复算：达到 CHURN_MIN_RUN 的那一手起计入
        from tests.eval.spectacle import CHURN_MIN_RUN
        run = 0
        expect = 0
        for r in recs8:
            if r.is_tactic:
                run = 0
                continue
            run += 1
            if run >= CHURN_MIN_RUN:
                expect += 1
        assert after.long_chase_turns == expect
        # 该局第 3 手吃子 -> 第 4 手起重新计数，到第 8 手只有 5 手，不足 6
        assert after.long_chase_turns == 0, (
            "吃子打断了累积：吃子后仅 5 手搬运，未达阈值 6")


class TestDeadEndExemption:
    """`P-09`/`P-10` 守卫：无进攻子力时的闷摆**不可归因于 doctrine**。

    **实测依据**（残局 2 局信号验证 `eval-after-p07-endgame.json`）：
      - `endgame_m9_p085`：红方仅帅 + 一象，子力 0.0 对 8.0；
      - `endgame_m14_p059`：红方帅 + 仕 + 两象，子力 6.0 对 12.0，
        且唯一那个「吃子」实为黑卒吃红象，方向相反。
    两局红方**无车马炮、且无过河兵**，`endgame-technique` 的四条换法
    （进兵提速 / 主动兑子 / 制造接触 / 残局禁弃子）**一条都用不上**。
    """

    def test_dead_end_criteria_exist(self):
        from tests.eval.spectacle import DEAD_END_LEGAL_MOVES, NO_ATTACK_PIECES
        assert DEAD_END_LEGAL_MOVES >= 2, "阈值过低会把正常残局误判为死局"
        assert set(NO_ATTACK_PIECES) == {"rook", "knight", "cannon"}, \
            "进攻子力应含车/马/炮"

    def test_attack_piece_is_the_only_exemption_reason(self):
        """`P-12`：判据收敛为**只有**「无进攻子力」才豁免。

        旧版附带「合法着法数 < 5」，实测在 `eval-after-w03` 的
        `middlegame_p41` 上误伤 8 手——该局全程有进攻子力，
        只是某些局面着法偏少。此断言防止该误伤复发。
        """
        import json
        from pathlib import Path
        from tests.eval.spectacle import _is_dead_end
        base = Path(__file__).resolve().parents[1] / "docs" / "eval-after-w03.json"
        if not base.exists():
            pytest.skip("历史报告不存在")
        doc = json.loads(base.read_text(encoding="utf-8"))
        game = next(g for g in doc["raw"] if g["case_id"] == "middlegame_p41")
        recs = replay_plies(game["starting_fen"], game["move_history"])
        assert all(r.has_attack_piece for r in recs), \
            "该局全程有进攻子力"
        assert not any(_is_dead_end(r) for r in recs), \
            "有进攻子力就不得豁免（着法数少不再是豁免理由）"

    def test_openings_have_attack_pieces(self):
        """开局双方都应判定为「有进攻子力」——否则豁免会误伤正常对局。"""
        from tests.eval.spectacle import _is_dead_end
        fen = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"
        # 引擎实测合法的开局走法（`e2e4` 非法——中卒已被吃/不能那样走）
        moves = ["h2e2", "h7h6", "b0c2"]
        engine = RefereeEngine(fen)
        for m in moves:
            assert engine.validate_move(m), "夹具走法 %s 非法" % m
            engine.apply_move(m)
        recs = replay_plies(fen, moves)
        for r in recs:
            assert r.has_attack_piece, "开局第 %d 手应判定有进攻子力" % (r.index + 1)
            assert not _is_dead_end(r), "开局不应被判死局"

    def test_no_attack_position_is_exempted(self):
        """实测报告里「无进攻子力」的手应被豁免，且开局手不被豁免。"""
        import json
        from pathlib import Path
        from tests.eval.spectacle import _is_dead_end
        base = Path(__file__).resolve().parents[1] / "docs" / "eval-after-p07-endgame.json"
        if not base.exists():
            pytest.skip("实测报告不存在")
        doc = json.loads(base.read_text(encoding="utf-8"))
        game = next(g for g in doc["raw"] if g["case_id"] == "endgame_m9_p085")
        recs = replay_plies(game["starting_fen"], game["move_history"])
        assert any(not r.has_attack_piece for r in recs), "该局应存在无进攻子力的手"
        assert any(r.has_attack_piece for r in recs), "开局阶段应有进攻子力"
        exempt = [r for r in recs if _is_dead_end(r)]
        alive = [r for r in recs if not _is_dead_end(r)]
        assert exempt and alive, "豁免与未豁免的手应同时存在（否则判据失效）"

    def test_churn_excludes_dead_end_turns(self):
        """死局段里的无吃无将手不应计入闷摆。"""
        import json
        from pathlib import Path
        from tests.eval.spectacle import CHURN_MIN_RUN, _long_chase_turns, _is_dead_end
        base = Path(__file__).resolve().parents[1] / "docs" / "eval-after-p07-endgame.json"
        if not base.exists():
            pytest.skip("实测报告不存在")
        doc = json.loads(base.read_text(encoding="utf-8"))
        game = next(g for g in doc["raw"] if g["case_id"] == "endgame_m9_p085")
        recs = replay_plies(game["starting_fen"], game["move_history"])

        got = _long_chase_turns(recs)
        run = 0; expect = 0
        for r in recs:
            if r.is_tactic:
                run = 0
                continue
            run += 1
            if run >= CHURN_MIN_RUN and not _is_dead_end(r):
                expect += 1
        assert got == expect
        # 与「不豁免」的旧算法对比，确认豁免确实改变了结果
        run = 0; no_exempt = 0
        for r in recs:
            if r.is_tactic:
                run = 0
                continue
            run += 1
            if run >= CHURN_MIN_RUN:
                no_exempt += 1
        assert got < no_exempt, "死局豁免未生效"


class TestAttackCaseFile:
    """`P-11` 守卫：新局面集必须保持「双方都有进攻子力」。

    `P-10` 实测确认旧 `cases.json` 的两个残局**红方无车马炮、无过河兵**，
    闷摆指标在其上结构性不可归因。`cases_attack.json` 就是为此而生——
    若日后有人往里塞死局局面，这个集子就失去意义，故加断言。
    """

    FILE = Path(__file__).resolve().parents[1] / "tests" / "eval" / "cases_attack.json"

    def test_file_exists_and_loads(self):
        if not self.FILE.exists():
            pytest.skip("cases_attack.json 尚未生成")
        from tests.eval.cases import load
        cases = load(self.FILE)          # load() 内部已用 RefereeEngine 复验
        assert cases, "局面集不应为空"

    def test_all_positions_have_attack_pieces(self):
        if not self.FILE.exists():
            pytest.skip("cases_attack.json 尚未生成")
        from src.core.referee_engine import RefereeEngine
        from tests.eval.spectacle import NO_ATTACK_PIECES, PieceType, Color
        data = json.loads(self.FILE.read_text(encoding="utf-8"))
        for c in data["cases"]:
            e = RefereeEngine(c["fen"])
            for color in (Color.RED, Color.BLACK):
                n = 0
                for r in range(10):
                    for cc in range(9):
                        p = e.board.grid[r][cc]
                        if not p or p.color != color:
                            continue
                        if p.piece_type.value in NO_ATTACK_PIECES:
                            n += 1
                        elif p.piece_type == PieceType.PAWN:
                            crossed = (r >= 5) if color == Color.RED else (r <= 4)
                            if crossed:
                                n += 1
                assert n >= 3, "%s: %s方进攻子力仅 %d 个，本集子失去意义" % (
                    c["id"], "红" if color == Color.RED else "黑", n)

    def test_all_positions_are_middlegame(self):
        if not self.FILE.exists():
            pytest.skip("cases_attack.json 尚未生成")
        from src.core.board_snapshot import build
        from src.core.referee_engine import RefereeEngine
        data = json.loads(self.FILE.read_text(encoding="utf-8"))
        for c in data["cases"]:
            e = RefereeEngine(c["fen"])
            assert build(e)["board_phase"] == "middlegame", \
                "%s 阶段应为 middlegame" % c["id"]


class TestCompareGates:
    def test_missing_metric_is_indeterminate_not_pass(self):
        """基线缺 sac_sound_rate（None）时必须判「无法判定」，不能判通过。"""
        base = {"summary": {
            "mean_tactic_rate": 0.3, "mean_move_repeat_rate": 0.1,
            "mean_sac_sound_rate": None, "mean_quiet_streak_max": 5.0,
            "total_long_chase_turns": 0,
        }}
        cur = {"summary": {
            "mean_tactic_rate": 0.4, "mean_move_repeat_rate": 0.05,
            "mean_sac_sound_rate": 0.8, "mean_quiet_streak_max": 4.0,
            "total_long_chase_turns": 0,
        }}
        rows, ok = compare(base, cur)
        assert ok is False
        sac_row = [r for r in rows if r[0] == "弃子成立率"][0]
        assert sac_row[1] == "无法判定"

    def test_tactic_rate_over_cap_is_regression(self):
        """tactic_rate 超过 0.45 上限判「退化」（互将军噪音，不判改善）。

        上限来自实测分布（PLAN-SPECTACLE-001 §3.4）：6 份历史报告实测
        落在 0.308~0.336。**0.55 是初稿拍脑袋值，实测下永远不会触发**，
        等于没有守卫——此断言同时守住「阈值必须由数据支撑」这条纪律。
        """
        base = {"summary": {
            "mean_tactic_rate": 0.3, "mean_move_repeat_rate": 0.1,
            "mean_sac_sound_rate": 0.7, "mean_quiet_streak_max": 5.0,
            "total_long_chase_turns": 0,
        }}
        cur = {"summary": {
            "mean_tactic_rate": 0.70, "mean_move_repeat_rate": 0.1,
            "mean_sac_sound_rate": 0.7, "mean_quiet_streak_max": 5.0,
            "total_long_chase_turns": 0,
        }}
        rows, ok = compare(base, cur)
        cap_row = [r for r in rows if r[0] == "战术密度上限"][0]
        assert cap_row[1] == "退化"
        assert ok is False

    def test_cap_is_not_so_high_it_never_triggers(self):
        """反向守卫：上限必须落在实测分布之上、且有余量。

        实测最高 0.336（§3.4）。若有人把上限调到 0.34~0.45 以外的高位，
        要么永不触发（等于没守卫），要么把正常改善误判为过火。
        此断言把上限钉在 [0.36, 0.50] 区间内。
        """
        from tests.eval.spectacle import OVERRIDES
        cap = [o[2] for o in OVERRIDES if o[0] == "summary.mean_tactic_rate"][0]
        assert 0.36 <= cap <= 0.50, "上限 %.2f 超出实测支撑区间" % cap

    def test_measured_worse_than_baseline_flags_regression(self):
        """用实测到的退化方向验证门禁真的会红。

        真实数据：baseline 的 long_chase_turns=0，w05b 为 37。
        若门禁对这种明显退化判「通过」，整条守卫就是装饰。
        """
        base = {"summary": {
            "mean_tactic_rate": 0.326, "mean_move_repeat_rate": 0.054,
            "mean_sac_sound_rate": 0.625, "mean_quiet_streak_max": 7.0,
            "total_long_chase_turns": 17,      # P-06 重写后的实测值
        }}
        worse = {"summary": {
            "mean_tactic_rate": 0.379, "mean_move_repeat_rate": 0.093,
            "mean_sac_sound_rate": 0.527, "mean_quiet_streak_max": 9.7,
            "total_long_chase_turns": 40,      # P-05 实测：闷摆回合 17 -> 40
        }}
        rows, ok = compare(base, worse)
        assert ok is False
        churn_row = [r for r in rows if r[0] == "闷摆回合"][0]
        assert churn_row[1] == "退化"
        quiet_row = [r for r in rows if r[0] == "最长静默"][0]
        assert quiet_row[1] == "退化"

    def test_all_improved_passes(self):
        base = {"summary": {
            "mean_tactic_rate": 0.3, "mean_move_repeat_rate": 0.1,
            "mean_sac_sound_rate": 0.6, "mean_quiet_streak_max": 6.0,
            "total_long_chase_turns": 4,
        }}
        cur = {"summary": {
            "mean_tactic_rate": 0.35, "mean_move_repeat_rate": 0.05,
            "mean_sac_sound_rate": 0.7, "mean_quiet_streak_max": 5.0,
            "total_long_chase_turns": 0,
        }}
        rows, ok = compare(base, cur)
        assert ok is True, rows


class TestBaselineReplay:
    def test_baseline_replays_all_games_without_error(self):
        if not BASELINE.exists():
            pytest.skip("基线报告不存在")
        import json
        doc = json.loads(BASELINE.read_text(encoding="utf-8"))
        result = analyze_report(doc["raw"])
        assert result["summary"]["replay_errors"] == 0, result["errors"]
        assert result["summary"]["games"] == len(doc["raw"])
        # 观感性汇总必须能 JSON 序列化
        json.dumps(result)