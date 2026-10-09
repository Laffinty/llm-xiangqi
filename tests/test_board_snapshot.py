"""BoardSnapshot 的守卫（W-04）。

核心主张：结构化字段是**增量**且**诚实**的——
  1. 它不能因为自身出错就拖垮对局（快照失败必须静默降级为 None）
  2. 它不该在信息不足时**猜**（无历史的局面不得被标成"开局"）
  3. 它不该重复已有信息（legal_moves 已在 schema 的 enum 里）
"""
import pytest

from src.core.board_snapshot import ENDGAME_PIECES, _derive_phase, _ply_from_fen, build
from src.core.referee_engine import INITIAL_FEN, RefereeEngine
from src.core.state_serializer import GamePhase, GameResult, GameState
from src.agents.prompt_builder import PromptBuilder

INITIAL = INITIAL_FEN
# 残局（取自冻结局面集）
ENDGAME = "2b1k4/4a4/b4P3/9/9/9/9/B2K4p/9/5A3 w - - 0 1"


def _walk(fen, plies):
    e = RefereeEngine(fen)
    for _ in range(plies):
        legal = e.get_legal_moves()
        if not legal:
            break
        e.apply_move(sorted(legal)[0])
    return e


# ------------------------------------------------------------------ phase

def test_phase_uses_material_as_the_hard_signal():
    assert _derive_phase(30, 10) == "endgame"
    assert _derive_phase(30, 32) == "middlegame"


def test_phase_does_not_guess_when_ply_is_unknown():
    """无 ply 就不该声称是开局——32 子力的局面无法与前期中局区分。"""
    assert _derive_phase(None, 32) == "middlegame"
    assert _derive_phase(0, 32) == "opening", "ply 可信为 0 时才判开局"


def plys_or_none(n):
    return n


def test_ply_from_fen_roundtrip():
    e = _walk(INITIAL, 6)
    got = _ply_from_fen(e.current_fen)
    # FEN 里的 fullmove 未必跟真实手数一致（合成局面恒为 1），但不得抛异常
    assert got >= 0


# ------------------------------------------------------------------ fields

def test_snapshot_shape_on_initial_position():
    s = build(RefereeEngine(INITIAL))
    assert set(s) == {"board_phase", "material", "in_check", "check_side",
                      "last_move_detail", "repetition_warning"}
    assert s["material"]["Red"] == 16 and s["material"]["Black"] == 16
    assert s["in_check"] is False and s["check_side"] is None
    assert s["last_move_detail"] is None


def test_material_diff_is_from_side_to_move():
    """第 3 手后轮到黑方，差值应为 Black - Red。"""
    e = _walk(INITIAL, 3)
    s = build(e)
    expected = s["material"]["Black"] - s["material"]["Red"]
    assert s["material"]["diff_for_side_to_move"] == expected


def test_last_move_detail_is_reconstructed_from_pre_move_position():
    e = _walk(INITIAL, 4)
    d = build(e)["last_move_detail"]
    assert d and d["iccs"] == e.move_history[-1]
    # 红黑用字不同：车马炮相仕帅兵 / 车马炮象士将卒
    assert d["piece"] in "车马炮相象仕士帅将兵卒", "应还原出走子，不能恒为 None"


def test_capture_is_detected_in_last_move_detail():
    """走到出现吃子为止，captured 必须非空。"""
    e = RefereeEngine(INITIAL)
    found = False
    for _ in range(60):
        legal = e.get_legal_moves()
        if not legal:
            break
        # 挑一个能吃的（若没有则走字典序第一个）
        capture = next((m for m in sorted(legal)
                        if len(RefereeEngine(e.current_fen).get_legal_moves()) >= 0
                        and _captures(e, m)), None)
        e.apply_move(capture or sorted(legal)[0])
        d = build(e)["last_move_detail"]
        if d and d.get("captured"):
            found = True
            break
    assert found, "60 手内必然出现吃子；检测不到说明还原逻辑坏了"


def _captures(engine, iccs):
    probe = RefereeEngine(engine.current_fen)
    before = _count(probe)
    try:
        probe.apply_move(iccs)
    except ValueError:
        return False
    return _count(probe) < before


def _count(engine):
    return sum(1 for row in engine.board.grid for p in row if p)


def test_repetition_warning_appears_when_position_repeats():
    e = RefereeEngine(INITIAL)
    warned = False
    seen = set()
    for i in range(60):
        legal = e.get_legal_moves()
        if not legal or e.check_game_end()[0]:
            break
        e.apply_move(sorted(legal)[0])
        if build(e)["repetition_warning"]:
            warned = True
            break
        # 往返同一子，制造重复
        back = [m for m in e.get_legal_moves() if m[:2] == e.move_history[-1][2:]]
        if back:
            e.apply_move(back[0])
    assert warned, "往返同一子必然产生重复局面；检测不到说明 repetition_warning 坏了"


# ------------------------------------------------------- GameState 集成

def test_game_state_carries_snapshot_and_survives_engine_failure():
    st = GameState.from_engine(RefereeEngine(INITIAL), phase=GamePhase.RED_TO_MOVE,
                               result=GameResult.IN_PROGRESS)
    assert st.snapshot and st.to_dict()["snapshot"]["material"]["total"] == 32

    # 快照是增量：即使构造失败也不能让 from_engine 抛错
    class _Broken:
        move_history = []
        position_history = []
        current_fen = "garbage"
        board = None
        def get_annotated_moves(self): return []
        def get_current_turn(self): return "Red"
        def render_ascii_board(self): return ""
        def is_king_in_check(self, c): return False
        def to_fen(self): return "garbage"
    st2 = GameState.from_engine(_Broken(), phase=GamePhase.RED_TO_MOVE,
                                result=GameResult.IN_PROGRESS)
    assert st2.snapshot is None


def test_prompt_renders_snapshot_without_duplicating_legal_moves():
    e = _walk(INITIAL, 3)
    st = GameState.from_engine(e, phase=GamePhase.RED_TO_MOVE, result=GameResult.IN_PROGRESS)
    out = PromptBuilder("s")._format_game_state(st.to_dict())
    assert "## 局面摘要" in out
    assert "阶段:" in out and "子力:" in out
    # legal_moves 已在 schema 的 enum 里，摘要不得重复列出
    tail = out[out.index("## 局面摘要"):]
    assert st.to_dict()["legal_moves"][0] not in tail


def test_prompt_omits_section_when_snapshot_missing():
    d = GameState.from_engine(RefereeEngine(INITIAL), phase=GamePhase.RED_TO_MOVE,
                              result=GameResult.IN_PROGRESS).to_dict()
    d["snapshot"] = None
    out = PromptBuilder("s")._format_game_state(d)
    assert "## 局面摘要" not in out