"""
Web 3D 可视化模块

提供基于 Web 技术的 3D 中国象棋对战可视化平台。
"""

from src.web_3d.server import Web3DServer
from src.web_3d.observer_bridge import ObserverBridge, make_sync_observer
from src.web_3d.websocket_manager import WebSocketManager

__all__ = [
    "Web3DServer",
    "ObserverBridge",
    "make_sync_observer",
    "WebSocketManager",
]
