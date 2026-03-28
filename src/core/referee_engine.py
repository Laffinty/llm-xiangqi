"""
RefereeEngine - 中国象棋裁判引擎

核心职责：
1. FEN解析与序列化
2. 所有棋子走法规则（车马炮将相仕兵）
3. legal_moves生成器
4. ICCS走步解析与验证
5. 游戏结束判定

设计原则：LLM无状态（Stateless），引擎强状态（Stateful）
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Set, Dict, Any
from enum import Enum
import re


# 初始局面FEN
INITIAL_FEN = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"

# 棋子符号映射
PIECE_NAMES = {
    "K": "将",
    "k": "帅",
    "A": "仕",
    "a": "士",
    "B": "相",
    "b": "象",
    "N": "马",
    "n": "马",
    "R": "车",
    "r": "车",
    "C": "炮",
    "c": "炮",
    "P": "兵",
    "p": "卒",
}


# 棋子颜色
class Color(Enum):
    RED = "red"
    BLACK = "black"

    def opposite(self) -> Color:
        return Color.BLACK if self == Color.RED else Color.RED


# 棋子类型
class PieceType(Enum):
    KING = "king"  # 将/帅
    ADVISOR = "advisor"  # 仕/士
    BISHOP = "bishop"  # 相/象
    KNIGHT = "knight"  # 马
    ROOK = "rook"  # 车
    CANNON = "cannon"  # 炮
    PAWN = "pawn"  # 兵/卒


@dataclass
class Piece:
    """棋子"""

    piece_type: PieceType
    color: Color

    def __str__(self) -> str:
        char = self.piece_type.name[0] if self.piece_type != PieceType.ADVISOR else "A"
        if self.piece_type == PieceType.KING:
            char = "K" if self.color == Color.RED else "k"
        elif self.piece_type == PieceType.ADVISOR:
            char = "A" if self.color == Color.RED else "a"
        elif self.piece_type == PieceType.BISHOP:
            char = "B" if self.color == Color.RED else "b"
        elif self.piece_type == PieceType.KNIGHT:
            char = "N" if self.color == Color.RED else "n"
        elif self.piece_type == PieceType.ROOK:
            char = "R" if self.color == Color.RED else "r"
        elif self.piece_type == PieceType.CANNON:
            char = "C" if self.color == Color.RED else "c"
        elif self.piece_type == PieceType.PAWN:
            char = "P" if self.color == Color.RED else "p"
        return char

    @staticmethod
    def from_char(c: str) -> Optional["Piece"]:
        """从字符创建棋子"""
        piece_map = {
            "K": (PieceType.KING, Color.RED),
            "k": (PieceType.KING, Color.BLACK),
            "A": (PieceType.ADVISOR, Color.RED),
            "a": (PieceType.ADVISOR, Color.BLACK),
            "B": (PieceType.BISHOP, Color.RED),
            "b": (PieceType.BISHOP, Color.BLACK),
            "N": (PieceType.KNIGHT, Color.RED),
            "n": (PieceType.KNIGHT, Color.BLACK),
            "R": (PieceType.ROOK, Color.RED),
            "r": (PieceType.ROOK, Color.BLACK),
            "C": (PieceType.CANNON, Color.RED),
            "c": (PieceType.CANNON, Color.BLACK),
            "P": (PieceType.PAWN, Color.RED),
            "p": (PieceType.PAWN, Color.BLACK),
        }
        if c in piece_map:
            pt, color = piece_map[c]
            return Piece(pt, color)
        return None


@dataclass
class Position:
    """棋盘位置"""

    col: int  # 0-8 (a-i)
    row: int  # 0-9 (0-9)

    def __str__(self) -> str:
        return f"{chr(ord('a') + self.col)}{self.row}"

    @staticmethod
    def from_iccs(s: str) -> "Position":
        """从ICCS坐标创建位置 (如 'h2' -> Position(7, 2))"""
        if len(s) != 2:
            raise ValueError(f"Invalid ICCS position: {s}")
        col = ord(s[0].lower()) - ord("a")
        row = int(s[1])
        if not (0 <= col <= 8 and 0 <= row <= 9):
            raise ValueError(f"Invalid ICCS position: {s}")
        return Position(col, row)

    def to_iccs(self) -> str:
        return f"{chr(ord('a') + self.col)}{self.row}"


@dataclass
class Move:
    """走步"""

    from_pos: Position
    to_pos: Position

    def __str__(self) -> str:
        return f"{self.from_pos}{self.to_pos}"

    @staticmethod
    def from_iccs(s: str) -> "Move":
        """从ICCS字符串创建走步 (如 'h2e2')"""
        if len(s) != 4:
            raise ValueError(f"Invalid ICCS move: {s}")
        return Move(Position.from_iccs(s[:2]), Position.from_iccs(s[2:]))

    def to_iccs(self) -> str:
        return f"{self.from_pos}{self.to_pos}"


class Board:
    """棋盘状态 (10行 x 9列)"""

    def __init__(self):
        # 棋盘：board[row][col]，row 0是黑方底（红方视角的9），row 9是红方底（红方视角的0）
        # 红方在下方(0-4行)，黑方在上方(5-9行)
        self.grid: List[List[Optional[Piece]]] = [[None] * 9 for _ in range(10)]
        self.current_color: Color = Color.RED

    def get_piece(self, pos: Position) -> Optional[Piece]:
        """获取指定位置的棋子"""
        if not self._is_valid_pos(pos):
            return None
        return self.grid[pos.row][pos.col]

    def set_piece(self, pos: Position, piece: Optional[Piece]) -> None:
        """设置指定位置的棋子"""
        if self._is_valid_pos(pos):
            self.grid[pos.row][pos.col] = piece

    def remove_piece(self, pos: Position) -> Optional[Piece]:
        """移除指定位置的棋子"""
        piece = self.get_piece(pos)
        self.set_piece(pos, None)
        return piece

    def _is_valid_pos(self, pos: Position) -> bool:
        """检查位置是否在棋盘内"""
        return 0 <= pos.col <= 8 and 0 <= pos.row <= 9

    def copy(self) -> "Board":
        """深拷贝棋盘"""
        new_board = Board()
        new_board.current_color = self.current_color
        for r in range(10):
            for c in range(9):
                new_board.grid[r][c] = self.grid[r][c]
        return new_board


class RefereeEngine:
    """
    裁判引擎 - 绝对信任的裁判

    核心原则：
    - LLM无状态，引擎强状态
    - 绝不依赖LLM依靠上下文历史推演当前棋盘
    - 每次请求必须注入全量状态
    """

    def __init__(self, fen: str = INITIAL_FEN):
        self.current_fen: str = fen
        self.move_history: List[str] = []
        self.board = Board()
        self._parse_fen(fen)
        self.position_history: List[str] = []
        self.check_history: List[bool] = []

    def _parse_fen(self, fen: str) -> None:
        """解析FEN字符串并设置棋盘"""
        parts = fen.split()
        if len(parts) < 1:
            raise ValueError(f"Invalid FEN: {fen}")

        # 重要：先清空整个棋盘，避免残留棋子导致状态泄漏
        for r in range(10):
            for c in range(9):
                self.board.grid[r][c] = None

        # 解析棋盘位置
        rows = parts[0].split("/")
        if len(rows) != 10:
            raise ValueError(f"FEN must have 10 rows, got {len(rows)}")

        for r, row_str in enumerate(rows):
            c = 0
            for char in row_str:
                if char.isdigit():
                    c += int(char)
                else:
                    piece = Piece.from_char(char)
                    if piece:
                        self.board.grid[9 - r][c] = piece  # FEN row 0是黑方底
                        c += 1

        # 解析轮到哪方走
        if len(parts) >= 2:
            self.board.current_color = Color.RED if parts[1] == "w" else Color.BLACK

    def to_fen(self) -> str:
        """将当前棋盘状态转换为FEN字符串"""
        # 棋盘部分
        fen_rows = []
        for r in range(9, -1, -1):
            row_str = ""
            empty = 0
            for c in range(9):
                piece = self.board.grid[r][c]
                if piece is None:
                    empty += 1
                else:
                    if empty > 0:
                        row_str += str(empty)
                        empty = 0
                    row_str += str(piece)
            if empty > 0:
                row_str += str(empty)
            fen_rows.append(row_str)

        fen = "/".join(fen_rows)

        # 轮到哪方
        fen += " "
        fen += "w" if self.board.current_color == Color.RED else "b"

        # 后续字段（简化处理）
        fen += " - - 0 1"

        return fen

    def get_legal_moves(self) -> List[str]:
        """获取所有合法走步（ICCS格式）"""
        legal_moves = []
        for r in range(10):
            for c in range(9):
                piece = self.board.grid[r][c]
                if piece and piece.color == self.board.current_color:
                    pos = Position(c, r)
                    for target in self._get_piece_moves(pos, piece):
                        move = Move(pos, target)
                        if self._is_move_legal(move, piece):
                            legal_moves.append(move.to_iccs())
        return legal_moves

    def get_annotated_moves(self) -> List[Dict[str, Any]]:
        """获取带语义标注的合法走步列表

        Returns:
            [{"move": "h2e2", "annotations": ["capture:Pawn", "check"]}, ...]
        """
        annotated = []
        for r in range(10):
            for c in range(9):
                piece = self.board.grid[r][c]
                if piece and piece.color == self.board.current_color:
                    pos = Position(c, r)
                    for target in self._get_piece_moves(pos, piece):
                        move = Move(pos, target)
                        if self._is_move_legal(move, piece):
                            annotations = self._annotate_move(move, piece)
                            annotated.append({
                                "move": move.to_iccs(),
                                "annotations": annotations,
                            })
        return annotated

    def _annotate_move(self, move: Move, piece: Piece) -> List[str]:
        """为单步走步生成语义标注

        检测四类标注：
        - capture:{piece_type}: 吃子
        - check: 将军
        - repetition_warning: 走后局面已出现≥2次
        - development: 车从底线出发
        """
        annotations = []

        # 1. 吃子检测（无需模拟走步）
        target_piece = self.board.get_piece(move.to_pos)
        if target_piece and target_piece.color != piece.color:
            annotations.append(f"capture:{target_piece.piece_type.value}")

        # 2. 出子标记（无需模拟走步）
        if piece.piece_type == PieceType.ROOK:
            if (piece.color == Color.RED and move.from_pos.row == 0 and move.to_pos.row > 0) or \
               (piece.color == Color.BLACK and move.from_pos.row == 9 and move.to_pos.row < 9):
                annotations.append("development")

        # 3-4. 将军检测和重复警告（需要模拟走步）
        saved_from = self.board.remove_piece(move.from_pos)
        saved_to = self.board.get_piece(move.to_pos)
        self.board.set_piece(move.to_pos, piece)

        # 将军检测：走步后对方王是否被将军
        if self.is_king_in_check(piece.color.opposite()):
            annotations.append("check")

        # 重复警告：模拟走后局面在 history 中已出现≥2次
        # 将军时不标重复警告，避免误导 LLM 避免唯一正确的将军走步
        temp_fen = self.to_fen()
        if self.position_history.count(temp_fen) >= 2:
            if "check" not in annotations:
                annotations.append("repetition_warning")

        # 恢复棋盘状态
        self.board.set_piece(move.from_pos, saved_from)
        self.board.set_piece(move.to_pos, saved_to)

        return annotations

    def _get_piece_moves(self, pos: Position, piece: Piece) -> List[Position]:
        """获取指定棋子的所有移动目标（不考虑将军检查）"""
        moves = []

        if piece.piece_type == PieceType.KING:
            moves = self._get_king_moves(pos, piece.color)
        elif piece.piece_type == PieceType.ADVISOR:
            moves = self._get_advisor_moves(pos, piece.color)
        elif piece.piece_type == PieceType.BISHOP:
            moves = self._get_bishop_moves(pos, piece.color)
        elif piece.piece_type == PieceType.KNIGHT:
            moves = self._get_knight_moves(pos, piece.color)
        elif piece.piece_type == PieceType.ROOK:
            moves = self._get_rook_moves(pos, piece.color)
        elif piece.piece_type == PieceType.CANNON:
            moves = self._get_cannon_moves(pos, piece.color)
        elif piece.piece_type == PieceType.PAWN:
            moves = self._get_pawn_moves(pos, piece.color)

        return moves

    def _get_king_moves(self, pos: Position, color: Color) -> List[Position]:
        """将帅的移动"""
        moves = []
        # 九宫内移动
        if color == Color.RED:
            # 红帅在 0-4 行，九宫范围：列 3-5，行 0-2
            for dc, dr in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                new_pos = Position(pos.col + dc, pos.row + dr)
                if 3 <= new_pos.col <= 5 and 0 <= new_pos.row <= 2:
                    moves.append(new_pos)
        else:
            # 黑将 在 5-9 行，九宫范围：列 3-5，行 7-9
            for dc, dr in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                new_pos = Position(pos.col + dc, pos.row + dr)
                if 3 <= new_pos.col <= 5 and 7 <= new_pos.row <= 9:
                    moves.append(new_pos)
        return moves

    def _get_advisor_moves(self, pos: Position, color: Color) -> List[Position]:
        """仕/士的移动"""
        moves = []
        if color == Color.RED:
            # 红仕在九宫的4个斜线位置：(3,0),(5,0),(4,1),(3,2),(5,2)
            for dc, dr in [(1, 1), (1, -1), (-1, 1), (-1, -1)]:
                new_pos = Position(pos.col + dc, pos.row + dr)
                if 3 <= new_pos.col <= 5 and 0 <= new_pos.row <= 2:
                    moves.append(new_pos)
        else:
            # 黑士在九宫的4个斜线位置：(3,7),(5,7),(4,8),(3,9),(5,9)
            for dc, dr in [(1, 1), (1, -1), (-1, 1), (-1, -1)]:
                new_pos = Position(pos.col + dc, pos.row + dr)
                if 3 <= new_pos.col <= 5 and 7 <= new_pos.row <= 9:
                    moves.append(new_pos)
        return moves

    def _get_bishop_moves(self, pos: Position, color: Color) -> List[Position]:
        """相/象的移动"""
        moves = []
        # 相走"田"字
        for dc, dr in [(2, 2), (2, -2), (-2, 2), (-2, -2)]:
            new_pos = Position(pos.col + dc, pos.row + dr)
            # 检查象眼（中间位置）
            eye_pos = Position(pos.col + dc // 2, pos.row + dr // 2)
            if (
                self._is_valid_bishop_pos(new_pos, color)
                and self.get_piece(eye_pos) is None
            ):
                moves.append(new_pos)
        return moves

    def _is_valid_bishop_pos(self, pos: Position, color: Color) -> bool:
        """检查相/象位置是否合法"""
        if not (0 <= pos.col <= 8 and 0 <= pos.row <= 9):
            return False
        if color == Color.RED:
            return 0 <= pos.row <= 4  # 红相只能在0-4行
        else:
            return 5 <= pos.row <= 9  # 黑象只能在5-9行

    def _get_knight_moves(self, pos: Position, color: Color) -> List[Position]:
        """马的移动

        马走"日"字：先走直线1步（蹩马腿），再走拐角1步
        """
        moves = []
        knight_offsets = [
            ((-1, 0), (-2, -1)),  # 左2上1: leg在(-1,0), target在(-2,-1)
            ((-1, 0), (-2, 1)),  # 左2下1: leg在(-1,0), target在(-2,1)
            ((1, 0), (2, -1)),  # 右2上1: leg在(1,0), target在(2,-1)
            ((1, 0), (2, 1)),  # 右2下1: leg在(1,0), target在(2,1)
            ((0, -1), (-1, -2)),  # 上2左1: leg在(0,-1), target在(-1,-2)
            ((0, -1), (1, -2)),  # 上2右1: leg在(0,-1), target在(1,-2)
            ((0, 1), (-1, 2)),  # 下2左1: leg在(0,1), target在(-1,2)
            ((0, 1), (1, 2)),  # 下2右1: leg在(0,1), target在(1,2)
        ]
        for (leg_dc, leg_dr), (target_dc, target_dr) in knight_offsets:
            leg_pos = Position(pos.col + leg_dc, pos.row + leg_dr)
            target_pos = Position(pos.col + target_dc, pos.row + target_dr)
            # 检查蹩马腿和目标位置
            if self._is_valid_pos(target_pos) and self.get_piece(leg_pos) is None:
                moves.append(target_pos)
        return moves

    def _get_rook_moves(self, pos: Position, color: Color) -> List[Position]:
        """车的移动"""
        moves = []
        for dc, dr in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
            for i in range(1, 10):
                new_pos = Position(pos.col + dc * i, pos.row + dr * i)
                if not self._is_valid_pos(new_pos):
                    break
                moves.append(new_pos)
                if self.get_piece(new_pos) is not None:
                    break
        return moves

    def _get_cannon_moves(self, pos: Position, color: Color) -> List[Position]:
        """炮的移动

        中国象棋炮规则:
        - 非捕获: 任意距离直线移动,路径必须全部为空
        - 捕获: 恰好1个炮架 + 目标必须是敌方棋子
        """
        moves = []
        for dc, dr in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
            screen_count = 0
            for i in range(1, 10):
                new_pos = Position(pos.col + dc * i, pos.row + dr * i)
                if not self._is_valid_pos(new_pos):
                    break
                piece = self.get_piece(new_pos)

                if piece is None:
                    # 空格: 非捕获时 count=0 才可移动, 捕获时 count=1 才可
                    if screen_count == 0:
                        moves.append(new_pos)
                    # screen_count > 0 时不能继续移动(已被阻挡)
                else:
                    # 有棋子: 判断是炮架(screen)还是捕获目标
                    if screen_count == 0:
                        # 第一个棋子是炮架,继续寻找目标
                        screen_count = 1
                    else:
                        # screen_count == 1, 这是第二个棋子:可能是捕获目标
                        if piece.color != color:
                            # 恰好1个炮架 + 目标是敌人 -> 合法捕获
                            moves.append(new_pos)
                        break  # 无论是否捕获,遇子停止
        return moves

    def _get_pawn_moves(self, pos: Position, color: Color) -> List[Position]:
        """兵/卒的移动

        中国象棋规则:
        - 红方在底部(0-4行)，面向顶部(9行方向)
        - 黑方在顶部(5-9行)，面向底部(0行方向)
        - 红兵前进: row + 1 (朝向黑方)
        - 黑卒前进: row - 1 (朝向红方)
        - 过河(进入对方区域)后可以左右移动
        """
        moves = []
        if color == Color.RED:
            # 红兵：未过河只能前进，过河可以左右
            # 红方在底部(0-4行)，过河意味着进入黑方区域(row >= 5)
            if pos.row >= 5:
                # 已过河，可以左右移动
                for dc in [-1, 1]:
                    new_pos = Position(pos.col + dc, pos.row)
                    if self._is_valid_pos(new_pos):
                        moves.append(new_pos)
            # 前进(朝向黑方 = row + 1)
            new_pos = Position(pos.col, pos.row + 1)
            if self._is_valid_pos(new_pos):
                moves.append(new_pos)
        else:
            # 黑卒：未过河只能前进，过河可以左右
            # 黑方在顶部(5-9行)，过河意味着进入红方区域(row <= 4)
            if pos.row <= 4:
                # 已过河，可以左右移动
                for dc in [-1, 1]:
                    new_pos = Position(pos.col + dc, pos.row)
                    if self._is_valid_pos(new_pos):
                        moves.append(new_pos)
            # 前进(朝向红方 = row - 1)
            new_pos = Position(pos.col, pos.row - 1)
            if self._is_valid_pos(new_pos):
                moves.append(new_pos)
        return moves

    def _is_valid_pos(self, pos: Position) -> bool:
        return 0 <= pos.col <= 8 and 0 <= pos.row <= 9

    def get_piece(self, pos: Position) -> Optional[Piece]:
        return self.board.get_piece(pos)

    def _is_kings_facing(self) -> bool:
        """检查将帅是否对面（飞将）

        中国象棋规则：将帅不能在同一列上直接对面（无棋子阻挡）

        Returns:
            True 表示将帅对面（非法状态），False 表示合法
        """
        red_king_pos = None
        black_king_pos = None

        for r in range(10):
            for c in range(9):
                piece = self.board.grid[r][c]
                if piece and piece.piece_type == PieceType.KING:
                    if piece.color == Color.RED:
                        red_king_pos = Position(c, r)
                    else:
                        black_king_pos = Position(c, r)

        if not red_king_pos or not black_king_pos:
            return False

        if red_king_pos.col != black_king_pos.col:
            return False

        col = red_king_pos.col
        min_row = min(red_king_pos.row, black_king_pos.row)
        max_row = max(red_king_pos.row, black_king_pos.row)

        for r in range(min_row + 1, max_row):
            if self.board.grid[r][col] is not None:
                return False

        return True

    def _is_move_legal(self, move: Move, piece: Piece) -> bool:
        """检查走步是否合法（考虑将军检查和飞将规则）"""
        target_piece = self.get_piece(move.to_pos)

        if target_piece and target_piece.color == piece.color:
            return False

        original = self.remove_piece(move.from_pos)
        self.set_piece(move.to_pos, piece)

        in_check = self.is_king_in_check(piece.color)

        kings_facing = self._is_kings_facing()

        self.set_piece(move.from_pos, original)
        self.set_piece(move.to_pos, target_piece)

        return not in_check and not kings_facing

    def remove_piece(self, pos: Position) -> Optional[Piece]:
        return self.board.remove_piece(pos)

    def set_piece(self, pos: Position, piece: Optional[Piece]) -> None:
        self.board.set_piece(pos, piece)

    def validate_move(self, iccs_move: str, fen: str = None) -> bool:
        """校验走步合法性"""
        try:
            move = Move.from_iccs(iccs_move)
        except ValueError:
            return False

        # 检查起点是否有己方棋子
        piece = self.get_piece(move.from_pos)
        if piece is None or piece.color != self.board.current_color:
            return False

        # 检查目标位置是否在合法移动中
        legal_moves = self.get_legal_moves()
        return iccs_move in legal_moves

    def apply_move(self, iccs_move: str) -> str:
        """执行走步，返回新FEN"""
        if not self.validate_move(iccs_move):
            raise ValueError(f"Invalid move: {iccs_move}")

        move = Move.from_iccs(iccs_move)
        piece = self.remove_piece(move.from_pos)
        captured = self.remove_piece(move.to_pos)
        self.set_piece(move.to_pos, piece)

        before_check = self.is_king_in_check(self.board.current_color.opposite())

        self.board.current_color = self.board.current_color.opposite()

        self.current_fen = self.to_fen()
        self.move_history.append(iccs_move)

        self.position_history.append(self.current_fen)

        after_check = self.is_king_in_check(self.board.current_color.opposite())
        self.check_history.append(before_check or after_check)

        return self.current_fen

    def _is_perpetual_check(self) -> Tuple[bool, str]:
        """检查是否出现长将

        中国象棋规则：
        - 连续将军超过一定次数且局面重复，判负
        - 这里的实现：连续4次将军且局面重复2次以上

        Returns:
            (is_perpetual, reason)
        """
        if len(self.check_history) < 4:
            return False, ""

        recent_checks = self.check_history[-4:]
        if not all(recent_checks):
            return False, ""

        if len(self.position_history) >= 4:
            recent_positions = self.position_history[-4:]
            unique_positions = len(set(recent_positions))
            if unique_positions <= 2:
                offender = "红方" if self.board.current_color == Color.BLACK else "黑方"
                return True, f"{offender}长将违规"

        return False, ""

    def _is_threefold_repetition(self) -> bool:
        """检查是否出现三次重复局面

        中国象棋规则：相同局面出现三次，可以判和

        Returns:
            True 表示出现三次重复局面
        """
        if len(self.position_history) < 5:
            return False

        current_pos = self.position_history[-1] if self.position_history else ""
        if not current_pos:
            return False

        count = self.position_history.count(current_pos)
        return count >= 3

    def _find_king_position(self, color: Color) -> Optional[Position]:
        """查找指定颜色王的位置"""
        for r in range(10):
            for c in range(9):
                piece = self.board.grid[r][c]
                if (
                    piece
                    and piece.piece_type == PieceType.KING
                    and piece.color == color
                ):
                    return Position(c, r)
        return None

    def check_game_end(self) -> Tuple[bool, str]:
        """检查游戏是否结束

        检查顺序：
        1. 长将违规
        2. 三次重复局面判和
        3. 王被吃（直接判定输）
        4. 将死/困毙

        Returns:
            (is_ended, reason)
        """
        is_perpetual, reason = self._is_perpetual_check()
        if is_perpetual:
            return True, reason

        if self._is_threefold_repetition():
            return True, "三次重复局面，判和"

        red_king_pos = self._find_king_position(Color.RED)
        black_king_pos = self._find_king_position(Color.BLACK)

        if red_king_pos is None:
            return True, "黑方胜利 - 红帅被吃"
        if black_king_pos is None:
            return True, "红方胜利 - 黑将被吃"

        red_in_check = self.is_king_in_check(Color.RED)
        black_in_check = self.is_king_in_check(Color.BLACK)

        legal_moves = self.get_legal_moves()

        if len(legal_moves) == 0:
            if self.board.current_color == Color.RED:
                return True, "黑方胜利 - 红方被困"
            else:
                return True, "红方胜利 - 黑方被困"

        if red_in_check and len(self._get_legal_moves_for_color(Color.RED)) == 0:
            return True, "黑方胜利 - 红方被将死"
        if black_in_check and len(self._get_legal_moves_for_color(Color.BLACK)) == 0:
            return True, "红方胜利 - 黑方被将死"

        return False, ""

    def is_king_in_check(self, color: Color) -> bool:
        """检查指定颜色的王是否被将军

        注意：调用此方法前应确保王存在，否则返回False
        """
        king_pos = self._find_king_position(color)
        if not king_pos:
            return False

        # 检查是否有对方棋子能吃到王
        enemy_color = color.opposite()
        for r in range(10):
            for c in range(9):
                piece = self.board.grid[r][c]
                if piece and piece.color == enemy_color:
                    # 检查这个棋子能否吃到王的位置
                    target_pos = king_pos
                    from_pos = Position(c, r)
                    if from_pos != target_pos:  # 避免自检
                        # 简单检查：王被将军通常是对方直接威胁
                        # 更准确的检查需要考虑蹩马腿等
                        moves = self._get_piece_moves(from_pos, piece)
                        if target_pos in moves:
                            # 进一步验证（考虑将军检查）
                            if self._can_piece_attack_target(
                                from_pos, target_pos, piece
                            ):
                                return True
        return False

    def _can_piece_attack_target(
        self, from_pos: Position, to_pos: Position, piece: Piece
    ) -> bool:
        """检查棋子能否真正攻击目标（考虑蹩马腿、炮架等）"""
        if piece.piece_type == PieceType.KNIGHT:
            # 检查蹩马腿
            knight_offsets = [
                ((-1, 0), (-1, -1)),
                ((-1, 0), (-1, 1)),
                ((1, 0), (1, -1)),
                ((1, 0), (1, 1)),
                ((0, -1), (-1, -1)),
                ((0, -1), (1, -1)),
                ((0, 1), (-1, 1)),
                ((0, 1), (1, 1)),
            ]
            for (leg_dc, leg_dr), (target_dc, target_dr) in knight_offsets:
                if (
                    from_pos.col + target_dc == to_pos.col
                    and from_pos.row + target_dr == to_pos.row
                ):
                    leg_pos = Position(from_pos.col + leg_dc, from_pos.row + leg_dr)
                    if self.get_piece(leg_pos) is not None:
                        return False
                    return True
            return False
        elif piece.piece_type == PieceType.CANNON:
            # 检查炮的路径
            if from_pos.col == to_pos.col or from_pos.row == to_pos.row:
                count = 0
                dc = (to_pos.col - from_pos.col) // max(
                    abs(to_pos.col - from_pos.col), 1
                )
                dr = (to_pos.row - from_pos.row) // max(
                    abs(to_pos.row - from_pos.row), 1
                )
                current = Position(from_pos.col + dc, from_pos.row + dr)
                while current != to_pos:
                    if self.get_piece(current) is not None:
                        count += 1
                    current = Position(current.col + dc, current.row + dr)
                return count == 1  # 正好一个炮架
            return False
        elif piece.piece_type == PieceType.BISHOP:
            # 检查象眼
            if (
                abs(to_pos.col - from_pos.col) == 2
                and abs(to_pos.row - from_pos.row) == 2
            ):
                eye_pos = Position(
                    (from_pos.col + to_pos.col) // 2, (from_pos.row + to_pos.row) // 2
                )
                if self.get_piece(eye_pos) is not None:
                    return False
            return True
        else:
            # 其他棋子直接检查
            return to_pos in self._get_piece_moves(from_pos, piece)

    def _get_legal_moves_for_color(self, color: Color) -> List[str]:
        """获取指定颜色的所有合法走步"""
        original_color = self.board.current_color
        self.board.current_color = color
        moves = self.get_legal_moves()
        self.board.current_color = original_color
        return moves

    def get_current_turn(self) -> str:
        """获取当前回合"""
        return "Red" if self.board.current_color == Color.RED else "Black"

    def render_ascii_board(self, fen: str = None) -> str:
        """渲染ASCII棋盘"""
        if fen:
            self._parse_fen(fen)

        lines = [
            "    a   b   c   d   e   f   g   h   i",
            "  +---+---+---+---+---+---+---+---+---+",
        ]

        for r in range(9, -1, -1):
            row_str = f"{r} |"
            for c in range(9):
                piece = self.board.grid[r][c]
                if piece:
                    # 转换大小写：红方用大写，黑方用小写
                    char = str(piece)
                    if piece.color == Color.BLACK:
                        char = char.lower()
                    else:
                        char = char.upper()
                    row_str += f" {char} |"
                else:
                    row_str += "   |"
            lines.append(row_str)
            lines.append("  +---+---+---+---+---+---+---+---+---+")

        lines.append("    a   b   c   d   e   f   g   h   i")

        return "\n".join(lines)

    def serialize_for_llm(self, include_scores: bool = False) -> dict:
        """序列化为LLM输入格式

        Args:
            include_scores: 是否包含Pikafish评分排序（一期暂不支持）

        Returns:
            LLM友好的游戏状态字典
        """
        legal_moves = self.get_legal_moves()

        return {
            "turn": self.get_current_turn(),
            "fen": self.current_fen,
            "ascii_board": self.render_ascii_board(),
            "legal_moves": legal_moves,
            "legal_moves_count": len(legal_moves),
            "game_history": self.move_history.copy(),
            "last_move": self.move_history[-1] if self.move_history else None,
        }

    def reset(self, fen: str = INITIAL_FEN) -> None:
        """重置游戏到初始状态"""
        self.current_fen = fen
        self.move_history = []
        self.board = Board()
        self._parse_fen(fen)
        self.position_history = []
        self.check_history = []


# 示例用法
if __name__ == "__main__":
    engine = RefereeEngine()
    print("Initial FEN:", engine.current_fen)
    print("\nASCII Board:")
    print(engine.render_ascii_board())
    print("\nLegal Moves:", engine.get_legal_moves()[:5], "...")
    print("Legal Moves Count:", len(engine.get_legal_moves()))
