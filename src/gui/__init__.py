"""
pyglet 原生 3D 棋盘渲染模块。

采用 PEP 562 惰性导出：``import src.gui`` 不会导入 pyglet。
pyglet 是可选依赖（仅 ``gui.3d: true`` 时需要），
展示层缺失不应影响引擎与 Web 3D 路径的导入。
"""

from typing import TYPE_CHECKING, Any

_LAZY_EXPORTS = {
    "ChessGUI": "chess_gui",
    "CameraController": "camera_controller",
    "ChessBoardRenderer": "chess_board_renderer",
    "PieceRenderer": "piece_renderer",
}

__all__ = ["ChessGUI"]

if TYPE_CHECKING:  # pragma: no cover - 仅供类型检查器
    from .camera_controller import CameraController
    from .chess_board_renderer import ChessBoardRenderer
    from .chess_gui import ChessGUI
    from .piece_renderer import PieceRenderer


def __getattr__(name: str) -> Any:
    """按需解析导出，未安装 pyglet 时仅在实际访问时才报错。"""
    module_name = _LAZY_EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    from importlib import import_module

    module = import_module(f".{module_name}", __name__)
    value = getattr(module, name)
    globals()[name] = value
    return value


def __dir__() -> list:
    return sorted(set(globals()) | set(__all__))
