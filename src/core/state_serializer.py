"""
状态序列化模块

将游戏状态转换为LLM友好的格式
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, TypedDict
from enum import Enum


class GamePhase(Enum):
    """游戏阶段"""
    NOT_STARTED = "not_started"
    RED_TO_MOVE = "red_to_move"
    BLACK_TO_MOVE = "black_to_move"
    GAME_OVER = "game_over"


class GameResult(Enum):
    """游戏结果"""
    RED_WIN = "red_win"
    BLACK_WIN = "black_win"
    DRAW = "draw"
    IN_PROGRESS = "in_progress"


class BoardSnapshotDict(TypedDict, total=False):
    """BoardSnapshot 结构化局面字段（W-04）"""
    board_phase: str
    material: Dict[str, Any]
    in_check: bool
    check_side: Optional[str]
    last_move_detail: Optional[Dict[str, Any]]
    repetition_warning: bool


@dataclass
class GameState:
    """游戏状态数据类

    用于在Agent、Controller和RefereeEngine之间传递状态
    """
    turn: str  # "Red" or "Black"
    fen: str
    ascii_board: str
    legal_moves: List[str]
    legal_moves_count: int
    game_history: List[str] = field(default_factory=list)
    annotated_moves: List[Dict[str, Any]] = field(default_factory=list)
    last_move: Optional[str] = None
    last_move_by: Optional[str] = None
    phase: GamePhase = GamePhase.NOT_STARTED
    result: GameResult = GameResult.IN_PROGRESS
    result_reason: Optional[str] = None
    # W-04：结构化局面字段。空旦异常，不阻断对局。
    snapshot: Optional[BoardSnapshotDict] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "turn": self.turn,
            "fen": self.fen,
            "ascii_board": self.ascii_board,
            "legal_moves": self.legal_moves,
            "legal_moves_count": self.legal_moves_count,
            "game_history": self.game_history,
            "annotated_moves": self.annotated_moves,
            "last_move": self.last_move,
            "last_move_by": self.last_move_by,
            "phase": self.phase.value,
            "result": self.result.value,
            "result_reason": self.result_reason,
            "snapshot": self.snapshot,
        }

    @classmethod
    def from_engine(
        cls,
        engine,
        *,
        phase: GamePhase = GamePhase.NOT_STARTED,
        result: GameResult = GameResult.IN_PROGRESS,
        result_reason: Optional[str] = None,
        last_move_by: Optional[str] = None,
    ) -> "GameState":
        """从RefereeEngine创建GameState

        Args:
            engine: RefereeEngine 实例
            phase: 对局阶段（由 GameController 提供，引擎本身不感知）
            result: 对局结果（由 GameController 提供）
            result_reason: 终局原因
            last_move_by: 上一步由哪个 Agent 走出（引擎不记录 Agent，需外部传入）

        Note:
            last_move 直接取自 engine.move_history（引擎是走步的唯一事实来源），
            不接受外部传入，避免与引擎状态不一致。
        """
        annotated_moves = engine.get_annotated_moves()
        move_history = engine.move_history
        snapshot = None
        try:
            from .board_snapshot import build as _build_snapshot
            snapshot = _build_snapshot(engine)
        except Exception:
            # 结构化字段是增量：它不能阻断对局。
            snapshot = None
        return cls(
            turn=engine.get_current_turn(),
            fen=engine.current_fen,
            ascii_board=engine.render_ascii_board(),
            legal_moves=[m["move"] for m in annotated_moves],
            legal_moves_count=len(annotated_moves),
            game_history=move_history.copy(),
            annotated_moves=annotated_moves,
            last_move=move_history[-1] if move_history else None,
            last_move_by=last_move_by,
            phase=phase,
            result=result,
            result_reason=result_reason,
            snapshot=snapshot,
        )


@dataclass
class MoveResult:
    """走步结果"""
    success: bool
    move: Optional[str] = None
    thought: Optional[str] = None
    error: Optional[str] = None
    new_fen: Optional[str] = None


@dataclass
class ValidationResult:
    """走步验证结果"""
    is_valid: bool
    error_message: Optional[str] = None
    explanation: Optional[str] = None
