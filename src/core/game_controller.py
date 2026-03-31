"""
游戏控制器

协调Agent和RefereeEngine的交互，管理游戏流程
"""

"""
游戏控制器

协调Agent和RefereeEngine的交互，管理游戏流程
"""

from typing import Optional, Tuple, Dict, Any
from dataclasses import dataclass
import asyncio

from .referee_engine import RefereeEngine, INITIAL_FEN, Color
from .state_serializer import (
    GameState,
    GamePhase,
    GameResult,
    MoveResult,
)
from ..utils.logger import get_logger

logger = get_logger(__name__)


# 游戏结束原因常量
class GameEndReasons:
    """游戏结束原因字符串常量"""
    # 长将判负
    RED_PERPETUAL_CHECK = "红方长将"
    BLACK_PERPETUAL_CHECK = "黑方长将"
    # 胜利
    RED_VICTORY = "红方胜利"
    BLACK_VICTORY = "黑方胜利"
    # 和棋
    DRAW = "判和"
    # 投降
    RESIGNATION_RED = "Red resigned"
    RESIGNATION_BLACK = "Black resigned"
    # 其他
    MAX_TURNS = "Maximum turns reached"
    STALEMATE = "Stalement"


@dataclass
class GameController:
    """
    游戏控制器

    职责：
    1. 回合管理
    2. 胜负判定
    3. 走棋历史
    4. 超时控制（一期暂不启用）
    """

    def __init__(
        self, referee_engine: Optional[RefereeEngine] = None, max_turns: int = 200
    ):
        self.referee = referee_engine or RefereeEngine(INITIAL_FEN)
        self.max_turns = max_turns
        self.turn_count = 0
        self.phase = GamePhase.RED_TO_MOVE
        self.result = GameResult.IN_PROGRESS
        self.result_reason: Optional[str] = None

    def get_current_state(self) -> GameState:
        """获取当前游戏状态"""
        return GameState.from_engine(self.referee)

    def get_current_turn(self) -> str:
        """获取当前回合"""
        return self.referee.get_current_turn()

    def apply_move(self, agent_name: str, iccs_move: str) -> MoveResult:
        """应用走步

        Args:
            agent_name: 执行走步的Agent名称
            iccs_move: ICCS格式走步 (如 "h2e2")

        Returns:
            MoveResult: 走步结果
        """
        if not self._validate_iccs_format(iccs_move):
            return MoveResult(success=False, error=f"Invalid ICCS format: {iccs_move}")

        if not self.referee.validate_move(iccs_move):
            legal = self.referee.get_legal_moves()
            logger.error(
                f"DEBUG: agent_name={agent_name}, iccs_move={iccs_move}, "
                f"current_turn={self.referee.get_current_turn()}, phase={self.phase}"
            )
            return MoveResult(
                success=False,
                error=f"Illegal move: {iccs_move}, "
                f"current_turn={self.referee.get_current_turn()}, "
                f"legal_moves={legal[:5]}...",
            )

        try:
            new_fen = self.referee.apply_move(iccs_move)

            self.turn_count += 1

            state = self.get_current_state()
            state.last_move = iccs_move
            state.last_move_by = agent_name

            is_over, reason = self.referee.check_game_end()
            if is_over:
                self.phase = GamePhase.GAME_OVER
                self.result = self._map_reason_to_result(reason)
                self.result_reason = reason
            else:
                if self.phase == GamePhase.RED_TO_MOVE:
                    self.phase = GamePhase.BLACK_TO_MOVE
                else:
                    self.phase = GamePhase.RED_TO_MOVE

            return MoveResult(success=True, move=iccs_move, new_fen=new_fen)

        except Exception as e:
            return MoveResult(success=False, error=str(e))

    @staticmethod
    def _map_reason_to_result(reason: str) -> GameResult:
        """将游戏结束原因字符串映射到GameResult枚举值

        Args:
            reason: check_game_end()返回的原因字符串

        Returns:
            对应的GameResult枚举值
        """
        if GameEndReasons.DRAW in reason:
            return GameResult.DRAW
        if reason.startswith(GameEndReasons.RED_PERPETUAL_CHECK):
            return GameResult.BLACK_WIN
        if reason.startswith(GameEndReasons.BLACK_PERPETUAL_CHECK):
            return GameResult.RED_WIN
        if reason.startswith(GameEndReasons.RED_VICTORY):
            return GameResult.RED_WIN
        if reason.startswith(GameEndReasons.BLACK_VICTORY):
            return GameResult.BLACK_WIN
        # Fallback: heuristic based on current turner losing
        from .referee_engine import Color
        # Should not normally reach here; kept for forward-compatibility
        return GameResult.RED_WIN  # pragma: no cover

    def _validate_iccs_format(self, move: str) -> bool:
        """验证ICCS走步格式"""
        if len(move) != 4:
            return False
        if not (move[0].isalpha() and move[2].isalpha()):
            return False
        if not (move[1].isdigit() and move[3].isdigit()):
            return False
        col1, row1 = ord(move[0].lower()) - ord("a"), int(move[1])
        col2, row2 = ord(move[2].lower()) - ord("a"), int(move[3])
        return 0 <= col1 <= 8 and 0 <= col2 <= 8 and 0 <= row1 <= 9 and 0 <= row2 <= 9

    def is_game_over(self) -> Tuple[bool, GameResult, Optional[str]]:
        """检查游戏是否结束"""
        return (self.phase == GamePhase.GAME_OVER, self.result, self.result_reason)

    def reset(self, fen: str = INITIAL_FEN) -> None:
        """重置游戏"""
        self.referee.reset(fen)
        self.turn_count = 0
        self.phase = GamePhase.RED_TO_MOVE
        self.result = GameResult.IN_PROGRESS
        self.result_reason = None

    def get_game_info(self) -> Dict[str, Any]:
        """获取游戏信息"""
        return {
            "turn_count": self.turn_count,
            "max_turns": self.max_turns,
            "phase": self.phase.value,
            "result": self.result.value,
            "result_reason": self.result_reason,
            "current_turn": self.get_current_turn(),
            "move_history": self.referee.move_history.copy(),
        }


class LLMAgentGameController(GameController):
    """
    LLM Agent游戏控制器

    支持LLM Agent对战的完整流程管理
    """

    def __init__(
        self,
        red_agent=None,
        black_agent=None,
        referee_engine: Optional[RefereeEngine] = None,
        max_turns: int = 200,
    ):
        super().__init__(referee_engine, max_turns)
        self.red_agent = red_agent
        self.black_agent = black_agent
        self.current_agent = None
        self._observers: list = []

    def _count_non_king_pieces(self, color: str) -> int:
        """计算指定颜色的非将/帅棋子数量"""
        from .referee_engine import PieceType, Color

        c = Color(color.lower())
        count = 0
        for r in range(10):
            for col in range(9):
                piece = self.referee.board.grid[r][col]
                if piece and piece.color == c and piece.piece_type != PieceType.KING:
                    count += 1
        return count

    def register_observer(self, callback):
        """注册观察者

        Args:
            callback: 回调函数，签名为 callback(move: str, fen: str, is_game_over: bool)
        """
        if callback not in self._observers:
            self._observers.append(callback)

    def unregister_observer(self, callback):
        """注销观察者"""
        if callback in self._observers:
            self._observers.remove(callback)

    def _notify_observers(self, move: str, fen: str, is_game_over: bool):
        """通知所有观察者"""
        for observer in self._observers:
            try:
                observer(move, fen, is_game_over)
            except Exception as e:
                logger.error(f"Observer notification failed: {e}")

    def apply_move(self, agent_name: str, iccs_move: str) -> MoveResult:
        """应用走步（带观察者通知）"""
        result = super().apply_move(agent_name, iccs_move)
        if result.success:
            is_over = self.phase == GamePhase.GAME_OVER
            self._notify_observers(result.move, result.new_fen, is_over)
        return result

    async def play_turn(self) -> MoveResult:
        """执行当前回合

        Returns:
            MoveResult: 走步结果
        """
        if self.phase == GamePhase.GAME_OVER:
            return MoveResult(success=False, error="Game is over")

        if self.phase == GamePhase.RED_TO_MOVE:
            self.current_agent = self.red_agent
        else:
            self.current_agent = self.black_agent

        if self.current_agent is None:
            return MoveResult(success=False, error="No agent for current turn")

        legal_moves = self.referee.get_legal_moves()
        last_error_msg = None

        for attempt in range(3):
            state = self.get_current_state()

            if attempt > 0 and last_error_msg:
                self.current_agent.add_correction_feedback(last_error_msg, legal_moves)

            result = await self.current_agent.think(state.to_dict())

            if not result.success:
                return MoveResult(success=False, error=result.error)

            # 投降检测
            if result.resign or result.move == "jxjx":
                from .referee_engine import Color
                agent_name = self.current_agent.config.name
                resigner_color = self.current_agent.config.color
                resigner_color_enum = Color(resigner_color.lower())

                # 计算子力
                non_king = self._count_non_king_pieces(resigner_color)
                # 检查是否被将军
                in_check = self.referee.is_king_in_check(resigner_color_enum)
                # 检查是否有合法走步（被困毙）
                has_legal_moves = len(legal_moves) > 0

                # 投降条件（满足任一即可）：
                # 1. 子力严重不足（<=1个非将棋子）
                # 2. 子力不足（<=4个非将棋子）且被将军
                # 3. 无合法走步（被困毙）
                can_resign = (
                    non_king <= 1  # 子力严重不足
                    or (non_king <= 4 and in_check)  # 子力不足且被将军
                    or not has_legal_moves  # 被困毙
                )

                if not can_resign:
                    reason = []
                    if non_king > 4:
                        reason.append(f"子力充足({non_king}个非将棋子)")
                    elif not in_check:
                        reason.append("未被将军")
                    logger.warning(
                        f"{agent_name} {'且'.join(reason)}时尝试投降，拒绝并继续纠错"
                    )
                    last_error_msg = "当前局面不允许投降：子力尚充足或未被将军。请从合法走步中选择一个。"
                    continue

                logger.info(f"{agent_name} 投降认输，原因: {result.thought}")
                if self.phase == GamePhase.RED_TO_MOVE:
                    self.result = GameResult.BLACK_WIN
                    self.result_reason = f"{GameEndReasons.RESIGNATION_RED}: {result.thought}"
                else:
                    self.result = GameResult.RED_WIN
                    self.result_reason = f"{GameEndReasons.RESIGNATION_BLACK}: {result.thought}"
                self.phase = GamePhase.GAME_OVER
                return MoveResult(success=True, error=None, thought=f"投降认输: {result.thought}")

            if result.move and result.move in legal_moves:
                move_result = self.apply_move(
                    self.current_agent.config.name, result.move
                )
                if move_result.success:
                    move_result.thought = result.thought
                return move_result
            else:
                if result.move is None:
                    last_error_msg = "输出格式错误：未能在响应中找到有效的ICCS走步。请严格按照JSON格式输出，包含move字段，值为4字符的ICCS坐标（如h2e2）。"
                    logger.warning(f"LLM返回None (解析失败), attempt {attempt + 1}/3")
                else:
                    last_error_msg = f"你的走步 '{result.move}' 不在合法列表中。合法走步共{len(legal_moves)}种，请务必从以下列表中选择一个：{legal_moves[:10]}..."
                    logger.warning(
                        f"LLM幻觉非法走步: {result.move}, attempt {attempt + 1}/3"
                    )

        return MoveResult(success=False, error=f"LLM连续3次产生非法走步，已放弃")

    async def run_game(self, verbose: bool = True) -> Dict[str, Any]:
        """运行完整游戏

        Args:
            verbose: 是否输出详细信息

        Returns:
            游戏结果信息
        """


        if verbose:
            logger.info("=" * 60)
            logger.info("LLM Chinese Chess Game Started")
            logger.info("=" * 60)
            state = self.get_current_state()
            logger.info(f"\nInitial Board:\n{state.ascii_board}")
            red_model = (
                self.red_agent.config.llm_adapter.model if self.red_agent else "None"
            )
            black_model = (
                self.black_agent.config.llm_adapter.model
                if self.black_agent
                else "None"
            )
            logger.info(
                f"Red Agent: {self.red_agent.config.name if self.red_agent else 'None'}:{red_model}"
            )
            logger.info(
                f"Black Agent: {self.black_agent.config.name if self.black_agent else 'None'}:{black_model}"
            )

        while self.phase != GamePhase.GAME_OVER:
            if self.turn_count >= self.max_turns:
                self.phase = GamePhase.GAME_OVER
                self.result = GameResult.DRAW
                self.result_reason = GameEndReasons.MAX_TURNS
                break

            move_result = await self.play_turn()

            if not move_result.success:
                logger.error(f"Move failed: {move_result.error}")
                break

            if self.phase == GamePhase.BLACK_TO_MOVE:
                move_by = self.red_agent.config.name if self.red_agent else "Red"
                move_model = (
                    self.red_agent.config.llm_adapter.model
                    if self.red_agent
                    else "Unknown"
                )
                move_color = "Red"
            else:
                move_by = self.black_agent.config.name if self.black_agent else "Black"
                move_model = (
                    self.black_agent.config.llm_adapter.model
                    if self.black_agent
                    else "Unknown"
                )
                move_color = "Black"

            if verbose:
                logger.info(
                    f"\n{move_by}:{move_model} ({move_color}) moved: {move_result.move}"
                )
                if move_result.thought:
                    logger.info(f"Thought: {move_result.thought.replace(chr(10), ' ')}")

            state = self.get_current_state()
            if verbose:
                logger.info(f"Board:\n{state.ascii_board}")

            is_over, result, reason = self.is_game_over()
            if is_over:
                if verbose:
                    logger.info(f"\nGame Over: {reason}")
                    logger.info(f"Result: {result}")
                break

        return {
            "success": True,
            "turn_count": self.turn_count,
            "result": self.result.value,
            "result_reason": self.result_reason,
            "move_history": self.referee.move_history.copy(),
        }
