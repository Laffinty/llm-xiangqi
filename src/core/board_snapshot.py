"""BoardSnapshot —— 局面视图的结构化字段（W-04）。

**为什么不删 ASCII 盘**：`D-04`。结构化字段是**增量**，用于替模型省掉
「自己数子力 / 自己判断是否被将军」这类容易出错的推导，而不是替换它读盘的方式。

**为什么不做中文记谱（SAN）**：记谱的档位方向依赖走子方向，规则繁琐且易错；
而 FEN + 走棋历史本来就在 prompt 里，模型读得到。改为给出事实性的
`last_move_detail`，信息量更大而出错面更小。

字段全部从引擎推导，**不接受外部传入**——引擎是唯一事实来源。
"""
from typing import Any, Dict, List, Optional

from .referee_engine import Color, Piece, PieceType, Position, RefereeEngine

FILES = "abcdefghi"

# 剩余总子力低于此值视为残局
ENDGAME_PIECES = 16
# 开局按手数界定
OPENING_PLIES = 12


def _ply_from_fen(fen: str) -> int:
    """从 FEN 的 fullmove 字段推已走手数。

    不能用 `len(move_history)`：从中局局面 FEN 起手的对局走棋历史为空，
    会把所有中局/残局都判成“开局”。
    """
    try:
        parts = fen.split()
        fullmove = int(parts[5])
        side = parts[1]
    except (IndexError, ValueError):
        return 0
    return (fullmove - 1) * 2 + (1 if side.lower().startswith("b") else 0)


def _count_material(engine: RefereeEngine) -> Dict[str, int]:
    counts = {"Red": 0, "Black": 0}
    for row in engine.board.grid:
        for piece in row:
            if piece:
                key = "Red" if piece.color == Color.RED else "Black"
                counts[key] += 1
    return counts


def _piece_at(engine: RefereeEngine, pos) -> Optional[Piece]:
    try:
        col = FILES.index(pos[0]) if isinstance(pos, str) else pos[0]
        row = int(pos[1]) if isinstance(pos, str) else pos[1]
    except (ValueError, IndexError):
        return None
    if not (0 <= col <= 8 and 0 <= row <= 9):
        return None
    return engine.board.get_piece(Position(col, row))


# 红黑用字不同：仕/士、相/象、帅/将、兵/卒
_CN = {
    (PieceType.KING, True): "帅", (PieceType.KING, False): "将",
    (PieceType.ADVISOR, True): "仕", (PieceType.ADVISOR, False): "士",
    (PieceType.BISHOP, True): "相", (PieceType.BISHOP, False): "象",
    (PieceType.KNIGHT, True): "马", (PieceType.KNIGHT, False): "马",
    (PieceType.ROOK, True): "车", (PieceType.ROOK, False): "车",
    (PieceType.CANNON, True): "炮", (PieceType.CANNON, False): "炮",
    (PieceType.PAWN, True): "兵", (PieceType.PAWN, False): "卒",
}


def _piece_cn(piece) -> Optional[str]:
    if piece is None:
        return None
    return _CN.get((piece.piece_type, piece.color == Color.RED))


def _derive_phase(ply: Optional[int], total_pieces: int) -> str:
    """阶段判定。

    **可靠性分层**：子力是硬信号（直接数子）；ply 只在可信时用。
    一个没有历史的局面（如从 FEN 直接起手的评测局面）无法区分「开局」与
    「未吃子的前期中局」，此时只给中性值——**不猜**。
    """
    if total_pieces <= ENDGAME_PIECES:
        return "endgame"
    if ply is not None and ply <= OPENING_PLIES and total_pieces >= 28:
        return "opening"
    return "middlegame"


    """阶段判定。刻意保守：宁可把中局叫残局，也别过早丢掉中局 doctrine。"""
    if total_pieces <= ENDGAME_PIECES:
        return "endgame"
    if ply <= OPENING_PLIES:
        return "opening"
    return "middlegame"


def _last_move_detail(engine: RefereeEngine) -> Optional[Dict[str, Any]]:
    """从上一步之前的局面还原「谁走了什么、吃了谁、是否将军」。

    用 `position_history[-2]`（走子前的 FEN）重建，避免用当前局面推断——
    当前局面上起点格必然是空的。
    """
    if not engine.move_history:
        return None
    iccs = engine.move_history[-1]
    if len(iccs) != 4:
        return None

    prev_fen = None
    if len(engine.position_history) >= 2:
        prev_fen = engine.position_history[-2]
    if prev_fen is None:
        return {"iccs": iccs, "piece": None, "captured": None, "gives_check": None}

    try:
        prev = RefereeEngine(prev_fen)
    except Exception:
        return {"iccs": iccs, "piece": None, "captured": None, "gives_check": None}

    src, dst = iccs[:2], iccs[2:]
    piece = _piece_at(prev, src)
    captured = _piece_at(prev, dst)

    # 走完这一步后，对方是否被将军——当前局面即可判定（这就是最后一步）
    mover = _piece_at(prev, src)
    opponent = Color.BLACK if (mover and mover.color == Color.RED) else Color.RED
    try:
        gives_check = engine.is_king_in_check(opponent)
    except Exception:
        gives_check = None

    return {
        "iccs": iccs,
        "piece": _piece_cn(piece),
        "from": src,
        "to": dst,
        "captured": _piece_cn(captured),
        "gives_check": gives_check,
    }


def build(engine: RefereeEngine, *, ply: Optional[int] = None) -> Dict[str, Any]:
    """构造 BoardSnapshot 字段集合。"""
    material = _count_material(engine)
    total = material["Red"] + material["Black"]
    # ply 只在可信时使用：走棋历史非空，或 FEN 的 fullmove 大于 1
    if ply is None:
        ply = len(engine.move_history)
        if ply == 0:
            from_fen = _ply_from_fen(engine.current_fen)
            ply = from_fen if from_fen > 0 else None

    current_turn = engine.get_current_turn()
    try:
        red_in_check = engine.is_king_in_check(Color.RED)
        black_in_check = engine.is_king_in_check(Color.BLACK)
    except Exception:
        red_in_check = black_in_check = False

    check_side = None
    if red_in_check:
        check_side = "Red"
    elif black_in_check:
        check_side = "Black"

    try:
        occurrences = engine.position_history.count(engine.current_fen)
    except Exception:
        occurrences = 0

    return {
        "board_phase": _derive_phase(ply, total),
        "material": {
            "Red": material["Red"],
            "Black": material["Black"],
            "total": total,
            # 以当前走子方视角表示，避免模型自己换算
            "diff_for_side_to_move": (
                material["Red"] - material["Black"]
                if current_turn.lower().startswith("r")
                else material["Black"] - material["Red"]
            ),
        },
        "in_check": check_side is not None,
        "check_side": check_side,
        "last_move_detail": _last_move_detail(engine),
        # 出现 2 次即预警（第 3 次就要判和）
        "repetition_warning": occurrences >= 2,
    }
