"""观感性指标重放器（P-01，`PLAN-SPECTACLE-001` §4）

**为什么是重放而不是重跑**：`docs/eval-*.json` 的 `raw[i]` 已含 `starting_fen` 与完整
`move_history`（`PLAN-SPECTACLE-001` `E-03`）。因此全部观感性指标可由二者**纯离线重放**得出，
不消耗任何 API——这是「度量必须前置」（`PLAN-SKILL-001` `D-08`）在本项目里能落地的唯一形式。

**为什么必须用 `RefereeEngine` 而不是自己解析走法**：判定规则一旦有两套，
指标就与生产行为脱钩，之后任何 A/B 都无法归因。所有吃子/将军/弃子/长打判定
一律委托给 `src/core/referee_engine.py`——与对局时同一份代码。

**确定性**：`W-02` 已确立「逐字节可复现」纪律。本模块是**纯函数**：给定同一份报告，
两次调用结果完全相同。不读时钟、不读环境变量、不排序不稳定容器之外的东西。
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.core.referee_engine import (  # noqa: E402
    Color,
    PieceType,
    Position,
    RefereeEngine,
)


class SpectacleReplayError(ValueError):
    """重放失败。

    **刻意不吞异常**：报告里若含非法走法，那本身就是需要暴露的缺陷。
    静默跳过会让指标看起来正常，从而把坏数据伪装成好数据。
    """


# 与 `endgame-technique/SKILL.md` 的残局换算表同源，保持两处一致。
PIECE_VALUE: Dict[str, float] = {
    "rook": 9.0,
    "knight": 4.5,
    "cannon": 4.5,
    "pawn": 2.0,
    "bishop": 2.0,
    "advisor": 2.0,
    "king": 0.0,
}

# 弃子「成立」的观察窗口：弃子后 N 个己方回合内被吃，判为不成立。
# 与 §7 盲区 2 一致——这是粗糙代理，不是引擎认可。
SAC_LOOKAHEAD_PLIES = 4

# 闷摆段的最小长度（`P-06`）。连续无吃无将达到此长度即计入闷摆回合。
# 依据：实测 6 份报告的最长连续段为 10/20/19/20/23/25，取 6 留出余量。
CHURN_MIN_RUN = 6


@dataclass(frozen=True)
class PlyRecord:
    """单手棋的客观事实。只记录可重放验证的量，不含任何评价性判断。"""

    index: int
    iccs: str
    color: str                       # "Red" / "Black"
    moved_piece: str                 # 棋子类型英文名，如 "rook"
    captured_piece: Optional[str]    # 吃掉的棋子类型；未吃子为 None
    captured_value: float            # 吃掉子力的价值；未吃子为 0.0
    gives_check: bool                # 走后是否将军对方
    in_check_before: bool            # 走这步之前己方是否被将（被迫应将的判据）
    is_sacrifice: bool               # 引擎 `_detect_sacrifice` 判定：主动把车/马/炮置于可吃
    under_threat: bool               # 走完之后己方该子是否可被对方直接吃掉
    material_after: Dict[str, float]  # 走完这步后双方的子力价值
    board_key: str                   # 局面棋盘部分（FEN 第一段），用于重复判定
    legal_moves_before: int = 0      # 走这步**之前**，走子方的合法着法数（死局判据）

    @property
    def is_tactic(self) -> bool:
        """战术手：吃子或将军。"""
        return bool(self.captured_piece) or self.gives_check


@dataclass
class GameSpectacle:
    """单局的观感性指标。字段与 `PLAN-SPECTACLE-001` §3.1 一一对应。"""

    case_id: str
    category: str
    plies: int = 0
    tactic_rate: float = 0.0
    quiet_streak_max: int = 0
    move_repeat_rate: float = 0.0
    sac_count: int = 0
    sac_sound_rate: Optional[float] = None   # 无弃子时为 None，不伪装成 1.0
    style_drift_count: int = 0
    long_chase_turns: int = 0
    per_color: Dict[str, Dict[str, float]] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "category": self.category,
            "plies": self.plies,
            "tactic_rate": self.tactic_rate,
            "quiet_streak_max": self.quiet_streak_max,
            "move_repeat_rate": self.move_repeat_rate,
            "sac_count": self.sac_count,
            "sac_sound_rate": self.sac_sound_rate,
            "style_drift_count": self.style_drift_count,
            "long_chase_turns": self.long_chase_turns,
            "per_color": self.per_color,
            "notes": self.notes,
        }


def _color_name(color: Color) -> str:
    return "Red" if color == Color.RED else "Black"


def _material_value(engine: RefereeEngine) -> Dict[str, float]:
    """按棋子价值表统计双方总子力价值。"""
    total = {"Red": 0.0, "Black": 0.0}
    for row in engine.board.grid:
        for piece in row:
            if piece is None:
                continue
            key = "Red" if piece.color == Color.RED else "Black"
            total[key] += PIECE_VALUE.get(piece.piece_type.value, 0.0)
    return total


def _board_key(fen: str) -> str:
    """局面棋盘部分。重复局面按棋盘判定，与走子方无关。"""
    return fen.split()[0] if " " in fen else fen


def replay_plies(starting_fen: str, moves: Sequence[str]) -> List[PlyRecord]:
    """重放整局，返回逐手客观事实。

    **非法走步直接抛 `SpectacleReplayError`**，不做跳过、不做截断。
    报告里出现非法走法说明该局记录本身有问题，静默吞掉会让指标失真。
    """
    engine = RefereeEngine(starting_fen)
    records: List[PlyRecord] = []

    for i, iccs in enumerate(moves):
        if not isinstance(iccs, str) or len(iccs) != 4:
            raise SpectacleReplayError(
                "第 %d 手走法格式非法: %r" % (i, iccs))

        mover_color = engine.get_current_turn()
        in_check_before = engine.is_king_in_check(
            Color.RED if mover_color == "Red" else Color.BLACK)
        # 走子方此刻的可选着法数：用于判定「死局」——
        # 着法极少时无内容可走是**局面决定的**，不能归因于 doctrine（`P-09`）。
        legal_before = len(engine.get_legal_moves())

        move = None
        try:
            move = __import__("src.core.referee_engine", fromlist=["Move"]).Move.from_iccs(iccs)
        except Exception as exc:  # pragma: no cover - 格式分支已被上面拦掉
            raise SpectacleReplayError("第 %d 手无法解析: %r (%s)" % (i, iccs, exc))

        moved_piece = engine.get_piece(move.from_pos)
        if moved_piece is None:
            raise SpectacleReplayError(
                "第 %d 手 %s：起点 %s 无子" % (i, iccs, move.from_pos))

        captured_piece = engine.get_piece(move.to_pos)
        if captured_piece is not None and captured_piece.color == moved_piece.color:
            raise SpectacleReplayError(
                "第 %d 手 %s：目标 %s 是己方子力" % (i, iccs, move.to_pos))

        # 弃子判定复用引擎生产逻辑（含「模拟对方能否吃掉该子」），
        # 在走子**之前**求值，此时棋盘仍是走子前的状态。
        sacrifice_piece_type = engine._detect_sacrifice(
            move, moved_piece, None)

        if not engine.validate_move(iccs):
            raise SpectacleReplayError("第 %d 手 %s：引擎判定为非法走步" % (i, iccs))

        fen_after = engine.apply_move(iccs)
        opponent = Color.RED if moved_piece.color == Color.RED else Color.BLACK
        gives_check = engine.is_king_in_check(opponent)

        # 「走完后己方该子是否可被直接吃掉」——弃子是否「成立」的即时信号。
        landing = engine.get_piece(move.to_pos)
        under_threat = False
        if landing is not None:
            enemy_color = landing.color.opposite()
            for r in range(10):
                for c in range(9):
                    p = engine.board.grid[r][c]
                    if p and p.color == enemy_color:
                        if move.to_pos in engine._get_piece_moves(Position(c, r), p):
                            under_threat = True
                            break
                if under_threat:
                    break

        records.append(PlyRecord(
            index=i,
            iccs=iccs,
            color=_color_name(moved_piece.color),
            moved_piece=moved_piece.piece_type.value,
            captured_piece=(captured_piece.piece_type.value
                            if captured_piece else None),
            captured_value=(PIECE_VALUE.get(captured_piece.piece_type.value, 0.0)
                            if captured_piece else 0.0),
            gives_check=bool(gives_check),
            in_check_before=bool(in_check_before),
            is_sacrifice=bool(sacrifice_piece_type),
            under_threat=under_threat,
            material_after=_material_value(engine),
            board_key=_board_key(fen_after),
            legal_moves_before=legal_before,
        ))

    return records


def _quiet_streak_max(records: Sequence[PlyRecord]) -> int:
    """最长连续「无吃子无将军」手数。"""
    best = cur = 0
    for r in records:
        if r.is_tactic:
            cur = 0
        else:
            cur += 1
            best = max(best, cur)
    return best


def _move_repeat_rate(records: Sequence[PlyRecord]) -> float:
    """同一方重复走**同一手**的比例（来回搬运同一条路线也算）。

    只统计本方各自的走法集合；双方走同名子力不算重复。
    """
    seen: Dict[str, set] = {"Red": set(), "Black": set()}
    repeats = 0
    for r in records:
        if r.iccs in seen[r.color]:
            repeats += 1
        else:
            seen[r.color].add(r.iccs)
    return repeats / len(records) if records else 0.0


def _is_sacrifice_candidate(r: PlyRecord) -> bool:
    """按 `E-08` 第 3 条过滤：被迫应将时的弃子不算「主动弃子」。

    国际象棋 brilliant move 的判定明确区分「主动选择」与「被迫」——
    被迫弃子只算 Good，不算 Brilliant。同一条判据在这里同样成立。
    """
    return r.is_sacrifice and not r.in_check_before


def _sac_sound_rate(records: Sequence[PlyRecord]) -> Optional[float]:
    """弃子中「N 步内该子未被直接吃掉」的比例。

    **这是粗糙代理**（§7 盲区 2）：无引擎评估，无法判断「弃后是否划算」，
    只能判断「弃的子是否立刻就没了」。无弃子时返回 None——不伪装成 1.0。
    """
    idx_by_ply = {r.index: i for i, r in enumerate(records)}
    cand = [(i, r) for i, r in enumerate(records) if _is_sacrifice_candidate(r)]
    if not cand:
        return None

    sound = 0
    for i, r in cand:
        # 在其后 SAC_LOOKAHEAD_PLIES 步内，己方是否丢了与被弃子等值的子力。
        # 这是「没白送」的最低限度判据，不是「弃得妙」。
        end = idx_by_ply[r.index] + 1 + SAC_LOOKAHEAD_PLIES
        window = records[idx_by_ply[r.index] + 1:end]
        lost = sum(x.captured_value for x in window if x.color == r.color)
        sac_value = PIECE_VALUE.get(r.moved_piece, 0.0)
        if lost < sac_value:
            sound += 1
    return sound / len(cand)


def _style_drift_count(records: Sequence[PlyRecord]) -> int:
    """棋风目标在局中切换的次数（攻/守相位切换）。

    代理指标：把每一手归到「攻」（吃子或将军）或「守」（其余）两个相位，
    统计同一方相位切换的次数。

    **已知盲区**（§7 盲区 1）：本指标只测「个体是否摇摆」，
    **测不出双方是否同质**。双方用同一段棋风文字时各自都不漂移，指标为 0，
    但棋局依然无趣。真正的解法是 `P-04`（棋风硬绑定），当前挂起。
    """
    drift = 0
    last_phase: Dict[str, Optional[bool]] = {"Red": None, "Black": None}
    for r in records:
        phase = r.is_tactic          # True = 攻，False = 守
        if last_phase[r.color] is not None and last_phase[r.color] != phase:
            drift += 1
        last_phase[r.color] = phase
    return drift


def _long_chase_turns(records: Sequence[PlyRecord]) -> int:
    """**闷摆回合数**：连续无吃无将且长度达阈值的手数合计（`P-06` 重写）。

    **为什么重写**：旧定义以「棋盘出现第 2 次」判重复。
    `P-05` 实测发现它在无限搬运中**永远测不准**——搬运时棋盘不断微变，
    27 手搬运的 27 个棋盘全不相同，被判成「长打 27 回合」，
    而真正该测的「闷摆」反而漏掉。

    **新定义**：把每一段「连续无吃无将」中**长度 >= CHURN_MIN_RUN 的部分**
    累加。这直接对应 doctrine 的判据（`repetition-management` /
    `middlegame-tactics`：「连续两手无吃无将即已在闷摆」），指标与条文同源。

    **阈值 6 的依据**（实测 6 份报告的最长连续段）：
    基线 10；W-03/W-03b/W-04/W-05/W-05b 分别为 20/19/20/23/25。
    取 6 能捕获劣化后的长段，又不会把开局正常的 4-5 手铺垫误判为闷摆。
    """
    total = 0
    run = 0
    for r in records:
        if r.is_tactic:
            run = 0
            continue
        run += 1
        # 死局豁免（`P-09`）：走子方可选着法极少时，「没内容可走」是**局面
        # 决定的**，不是 doctrine 没起作用。实测 `endgame_m9_p085` 到第 11 手时
        # 红方只剩 3 子、合法着法 4 个——此时任何走法都只能调度同一个象。
        # 把它计入闷摆，等于因为**局面本身无解**而惩罚 doctrine。
        if run >= CHURN_MIN_RUN and not _is_dead_end(r):
            total += 1
    return total


# 走子方合法着法数低于此值即视为「死局」，闷摆不可归因于 doctrine（`P-09`）。
# 依据实测：正常残局仍有 5-9 个着法可选，而死局局面低至 1-4 个。
DEAD_END_LEGAL_MOVES = 5


def _is_dead_end(rec: PlyRecord) -> bool:
    """该手是否发生在「可选着法极少」的死局中。"""
    return 0 < rec.legal_moves_before < DEAD_END_LEGAL_MOVES


def analyze_game(starting_fen: str,
                 moves: Sequence[str],
                 case_id: str = "?",
                 category: str = "?") -> GameSpectacle:
    """重放一局并计算 §3.1 的七个指标。"""
    records = replay_plies(starting_fen, moves)
    result = GameSpectacle(case_id=case_id, category=category, plies=len(records))

    if not records:
        result.notes.append("空对局：无走法记录")
        return result

    tactics = sum(1 for r in records if r.is_tactic)
    result.tactic_rate = tactics / len(records)
    result.quiet_streak_max = _quiet_streak_max(records)
    result.move_repeat_rate = _move_repeat_rate(records)
    result.sac_count = sum(1 for r in records if _is_sacrifice_candidate(r))
    result.sac_sound_rate = _sac_sound_rate(records)
    result.style_drift_count = _style_drift_count(records)
    result.long_chase_turns = _long_chase_turns(records)

    for color in ("Red", "Black"):
        own = [r for r in records if r.color == color]
        if not own:
            result.per_color[color] = {
                "plies": 0, "tactic_rate": None, "quiet_streak_max": 0,
                "move_repeat_rate": None, "sac_count": 0,
                "material_end": 0.0,
            }
            continue
        own_tactics = sum(1 for r in own if r.is_tactic)
        result.per_color[color] = {
            "plies": len(own),
            "tactic_rate": own_tactics / len(own),
            "quiet_streak_max": _quiet_streak_max(own),
            "move_repeat_rate": _move_repeat_rate(own),
            "sac_count": sum(1 for r in own if _is_sacrifice_candidate(r)),
            "material_end": own[-1].material_after[color],
        }

    if result.long_chase_turns:
        # 找第一段闷摆的起点，只为提示文案定位；计数由 _long_chase_turns 负责
        first = None
        run = 0
        for r in records:
            if r.is_tactic:
                run = 0
                continue
            run += 1
            if run >= CHURN_MIN_RUN and first is None:
                first = r.index - run + 1
        result.notes.append(
            "第 %s 手起出现闷摆（连续无吃无将 ≥%d 手），全程累计 %d 手"
            % (first if first is not None else "?", CHURN_MIN_RUN,
               result.long_chase_turns))
    if result.tactic_rate > 0.45:
        result.notes.append(
            "tactic_rate=%.3f 超过 0.45：疑似互将军形成噪音，非「更精彩」"
            % result.tactic_rate)
    if result.sac_sound_rate is not None and result.sac_sound_rate < 0.5:
        result.notes.append(
            "sac_count=%d 但 sac_sound_rate=%.2f：弃子多于得子，疑似为观赏而弃"
            % (result.sac_count, result.sac_sound_rate))
    return result


def analyze_report(raw_games: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """对一份报告的 `raw` 数组逐局重放，返回可 JSON 序列化的汇总。"""
    games: List[GameSpectacle] = []
    errors: List[Dict[str, str]] = []

    for g in raw_games:
        try:
            games.append(analyze_game(
                starting_fen=g["starting_fen"],
                moves=g.get("move_history") or [],
                case_id=g.get("case_id", "?"),
                category=g.get("category", "?"),
            ))
        except SpectacleReplayError as exc:
            errors.append({
                "case_id": g.get("case_id", "?"),
                "error": str(exc),
            })

    def _mean(values: List[float]) -> Optional[float]:
        return sum(values) / len(values) if values else None

    tactic = _mean([g.tactic_rate for g in games])
    repeat = _mean([g.move_repeat_rate for g in games])
    sound_vals = [g.sac_sound_rate for g in games if g.sac_sound_rate is not None]
    sound = _mean(sound_vals) if sound_vals else None

    return {
        "schema": "llm-xiangqi/spectacle@1",
        "games": [g.to_dict() for g in games],
        "summary": {
            "games": len(games),
            "replay_errors": len(errors),
            "mean_tactic_rate": tactic,
            "mean_quiet_streak_max": _mean([float(g.quiet_streak_max) for g in games]),
            "mean_move_repeat_rate": repeat,
            "total_sac_count": sum(g.sac_count for g in games),
            "mean_sac_sound_rate": sound,
            "mean_style_drift_count": _mean([float(g.style_drift_count) for g in games]),
            "total_long_chase_turns": sum(g.long_chase_turns for g in games),
        },
        "errors": errors,
    }


def _dig(doc: Dict[str, Any], path: str) -> Optional[float]:
    cur: Any = doc
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur if isinstance(cur, (int, float)) and not isinstance(cur, bool) else None


# 门禁方向与 `PLAN-SPECTACLE-001` §3.1 一致。
# 「up」在此处的语义是「不低于基线的合理下限」，不是「越高越好」——
# 上限由 OVERRIDES 单独约束，见 §3.3 判读规则第 2 条。
SPECTACLE_GATES: List[Tuple[str, str, str]] = [
    ("summary.mean_tactic_rate", "战术密度", "up"),
    ("summary.mean_move_repeat_rate", "走法重复率", "down"),
    ("summary.mean_sac_sound_rate", "弃子成立率", "up"),
    ("summary.mean_quiet_streak_max", "最长静默", "down"),
    ("summary.total_long_chase_turns", "闷摆回合", "down"),
]

# §3.3 第 2 条：tactic_rate 不是越高越好，超过上限判「过火」。
# 上限 0.45 来自实测分布（§3.4）：6 份历史报告落在 0.308~0.336，
# 该值距实测最高点留 +34% 余量，足以容纳真实改善，同时远低于 0.55
# ——后者在全部实测数据上永远不会触发，等于没有守卫。
OVERRIDES: List[Tuple[str, str, float, str]] = [
    ("summary.mean_tactic_rate", "战术密度上限", 0.45,
     "超过上限判为互将军噪音，不判为改善"),
]


def compare(base: Dict[str, Any], cur: Dict[str, Any]) -> Tuple[List[Tuple[str, str, str]], bool]:
    """逐项对比并按门禁方向判定。

    两条不可退让的原则（与 `run.py:141` 一致）：
      1. 基线缺该指标 → 判「无法判定」，**绝不显示成通过**；
      2. 基线缺 `sac_sound_rate`（无弃子时为 None）同样判「无法判定」。

    返回 (逐项结果, 是否全部通过)。
    """
    rows: List[Tuple[str, str, str]] = []
    ok_all = True

    for path, name, direction in SPECTACLE_GATES:
        b, c = _dig(base, path), _dig(cur, path)
        if b is None or c is None:
            rows.append((name, "无法判定", "基线或本次缺该指标（多半是无弃子/无数据）"))
            ok_all = False
            continue
        if direction == "up":
            ok = c >= b
            rows.append((name, "通过" if ok else "退化",
                         "%.4f -> %.4f（要求不下降）" % (b, c)))
        else:
            ok = c <= b
            rows.append((name, "通过" if ok else "退化",
                         "%.4f -> %.4f（要求不上升）" % (b, c)))
        ok_all = ok_all and ok

    for path, name, cap, why in OVERRIDES:
        c = _dig(cur, path)
        if c is None:
            rows.append((name, "无法判定", "本次缺该指标"))
            ok_all = False
            continue
        if c > cap:
            rows.append((name, "退化", "%.4f > 上限 %.2f，%s" % (c, cap, why)))
            ok_all = False
        else:
            rows.append((name, "通过", "%.4f <= 上限 %.2f" % (c, cap)))

    return rows, ok_all


def _print_summary(doc: Dict[str, Any]) -> None:
    s = doc["summary"]
    print("局面数 %d（重放失败 %d）" % (s["games"], s["replay_errors"]))
    for g in doc["games"]:
        print("")
        print("[%s] %s  %d 手" % (g["category"], g["case_id"], g["plies"]))
        print("  战术密度      %.3f" % g["tactic_rate"])
        print("  最长静默      %d 手" % g["quiet_streak_max"])
        print("  走法重复率    %.3f" % g["move_repeat_rate"])
        print("  弃子          %d 次（成立率 %s）" % (
            g["sac_count"],
            "n/a" if g["sac_sound_rate"] is None else "%.2f" % g["sac_sound_rate"]))
        print("  棋风摇摆      %d 次" % g["style_drift_count"])
        print("  闷摆回合      %d" % g["long_chase_turns"])
        for note in g["notes"]:
            print("  ! %s" % note)
    print("")
    print("---- 汇总 ----")
    print("mean_tactic_rate        %s" % s["mean_tactic_rate"])
    print("mean_quiet_streak_max   %s" % s["mean_quiet_streak_max"])
    print("mean_move_repeat_rate   %s" % s["mean_move_repeat_rate"])
    print("total_sac_count         %s" % s["total_sac_count"])
    print("mean_sac_sound_rate     %s" % s["mean_sac_sound_rate"])
    print("mean_style_drift_count  %s" % s["mean_style_drift_count"])
    print("total_long_chase_turns  %s" % s["total_long_chase_turns"])
    for e in doc["errors"]:
        print("重放失败 [%s]: %s" % (e["case_id"], e["error"]))


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m tests.eval.spectacle")
    ap.add_argument("--report", required=True,
                    help="eval 报告 JSON（含 raw 数组）")
    ap.add_argument("--compare", metavar="BASELINE", default=None,
                    help="与基线报告逐项对比并按门禁方向判定")
    ap.add_argument("--out", default=None, help="把观感性汇总写到该文件")
    args = ap.parse_args(argv)

    path = Path(args.report)
    if not path.exists():
        print("找不到报告: %s" % path)
        return 2
    doc = json.loads(path.read_text(encoding="utf-8"))

    raw = doc.get("raw")
    if not isinstance(raw, list) or not raw:
        print("报告 %s 无 raw 数组，无法重放" % path)
        return 2

    result = analyze_report(raw)
    _print_summary(result)

    if args.out:
        Path(args.out).write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")
        print("")
        print("已写出 %s" % args.out)

    if args.compare:
        base_path = Path(args.compare)
        if not base_path.exists():
            print("找不到基线: %s" % base_path)
            return 2
        base_doc = json.loads(base_path.read_text(encoding="utf-8"))
        base_raw = base_doc.get("raw")
        if not isinstance(base_raw, list) or not base_raw:
            print("基线 %s 无 raw 数组，无法重放" % base_path)
            return 2

        rows, ok = compare(analyze_report(base_raw), result)
        print("")
        print("---- 观感性门禁 ----")
        for name, verdict, detail in rows:
            print("%-14s %-10s %s" % (name, verdict, detail))
        if not ok:
            print("观感性门禁未全部通过")
            return 1
        print("观感性门禁全部通过")

    return 0


if __name__ == "__main__":
    sys.exit(main())