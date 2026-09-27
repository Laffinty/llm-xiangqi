"""
Web 3D 可视化模块（FastAPI + WebSocket）。

采用 PEP 562 惰性导出：``import src.web_3d`` 不会连带导入 fastapi / uvicorn。
这样控制台（--mode demo）与引擎测试在缺少 Web 依赖时仍可运行。
"""

from typing import TYPE_CHECKING, Any

_LAZY_EXPORTS = {
    "Web3DServer": "server",
    "ObserverBridge": "observer_bridge",
    "make_sync_observer": "observer_bridge",
    "WebSocketManager": "websocket_manager",
}

__all__ = [
    "Web3DServer",
    "ObserverBridge",
    "make_sync_observer",
    "WebSocketManager",
]

if TYPE_CHECKING:  # pragma: no cover - 仅供类型检查器
    from src.web_3d.observer_bridge import ObserverBridge, make_sync_observer
    from src.web_3d.server import Web3DServer
    from src.web_3d.websocket_manager import WebSocketManager


def __getattr__(name: str) -> Any:
    """按需解析导出，避免模块级导入 fastapi。"""
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
