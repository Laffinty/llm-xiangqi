"""
Observer Sync/Async 桥接模块

解决 GameController 同步 Observer 回调与 WebSocket 异步广播之间的桥接问题。
"""

import asyncio
from typing import Callable, Optional
from src.utils.logger import get_logger

logger = get_logger("web_3d.observer_bridge", level="INFO")


class ObserverBridge:
    """Observer 桥接器，将同步回调转换为异步任务调度"""

    def __init__(self, async_broadcast_func: Callable):
        """
        Args:
            async_broadcast_func: 异步广播函数，接收 (move, fen, is_game_over) 参数
        """
        self._async_broadcast = async_broadcast_func
        self._event_loop: Optional[asyncio.AbstractEventLoop] = None

    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """设置事件循环引用

        Args:
            loop: 异步事件循环
        """
        self._event_loop = loop

    def __call__(self, move: str, fen: str, is_game_over: bool) -> None:
        """同步回调入口，由 GameController 调用

        Args:
            move: ICCS 格式的走法，如 "h2e2"
            fen: 移动后的 FEN 字符串
            is_game_over: 游戏是否结束
        """
        try:
            # 尝试获取当前运行的事件循环
            loop = self._event_loop or asyncio.get_running_loop()

            # 将异步广播任务调度到事件循环
            # create_task 是线程安全的，可以从任何线程调用
            loop.create_task(self._async_broadcast(move, fen, is_game_over))

        except RuntimeError as e:
            # 没有运行的事件循环
            logger.warning(
                f"No running event loop, skipping WebSocket broadcast: {e}"
            )


def make_sync_observer(web_server) -> Callable:
    """创建同步 Observer 回调，内部将 async 广播调度到事件循环

    解决问题:
    - GameController._notify_observers() 是同步调用 observer(move, fen, is_game_over)
    - Web3DServer.broadcast_move() 是 async 方法
    - 同步调用 async 函数只会返回 coroutine 对象，不会执行

    方案: 用 asyncio.create_task() 或 loop.create_task() 将 async 任务投递到事件循环

    Args:
        web_server: Web3DServer 实例，需要有 broadcast_move 异步方法

    Returns:
        同步回调函数，可直接传递给 controller.register_observer()

    Example:
        >>> web_server = Web3DServer(config)
        >>> observer = make_sync_observer(web_server)
        >>> controller.register_observer(observer)
    """

    def on_state_update(move: str, fen: str, is_game_over: bool) -> None:
        try:
            loop = asyncio.get_running_loop()
            # 使用 create_task 将异步任务调度到事件循环
            # 不等待结果，因为 Observer 回调不需要确认
            loop.create_task(web_server.broadcast_move(move, fen, is_game_over))
        except RuntimeError:
            logger.warning("No running event loop, skipping WebSocket broadcast")

    return on_state_update
