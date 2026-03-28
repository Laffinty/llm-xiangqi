"""
状态序列化模块

将游戏状态转换为LLM友好的格式
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
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
            "result_reason": self.result_reason
        }

    @classmethod
    def from_engine(cls, engine) -> "GameState":
        """从RefereeEngine创建GameState"""
        annotated_moves = engine.get_annotated_moves()
        return cls(
            turn=engine.get_current_turn(),
            fen=engine.current_fen,
            ascii_board=engine.render_ascii_board(),
            legal_moves=[m["move"] for m in annotated_moves],
            legal_moves_count=len(annotated_moves),
            game_history=engine.move_history.copy(),
            annotated_moves=annotated_moves,
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
