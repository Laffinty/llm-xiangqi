"""
WebSocket 连接管理器

管理客户端连接、消息广播和连接清理。
"""

from typing import List, Optional
from fastapi import WebSocket
from src.utils.logger import get_logger

logger = get_logger("web_3d.websocket", level="INFO")


class WebSocketManager:
    """管理 WebSocket 连接和消息广播"""

    def __init__(self):
        self.connections: List[WebSocket] = []
        self._client_info: dict = {}  # WebSocket -> client info

    async def connect(self, ws: WebSocket, client_id: Optional[str] = None) -> None:
        """接受新的 WebSocket 连接

        Args:
            ws: WebSocket 连接对象
            client_id: 可选的客户端标识
        """
        await ws.accept()
        self.connections.append(ws)
        self._client_info[ws] = {
            "client_id": client_id or f"client_{id(ws)}",
            "connected_at": self._now_ms(),
        }
        logger.info(
            f"Client connected: {self._client_info[ws]['client_id']} "
            f"(total: {len(self.connections)})"
        )

    async def disconnect(self, ws: WebSocket) -> None:
        """断开 WebSocket 连接并清理资源

        Args:
            ws: WebSocket 连接对象
        """
        if ws in self.connections:
            self.connections.remove(ws)
            client_info = self._client_info.pop(ws, {})
            logger.info(
                f"Client disconnected: {client_info.get('client_id', 'unknown')} "
                f"(total: {len(self.connections)})"
            )
        try:
            await ws.close()
        except Exception:
            pass

    async def send_to(self, ws: WebSocket, message: dict) -> bool:
        """向指定客户端发送消息

        Args:
            ws: 目标 WebSocket 连接
            message: 要发送的消息字典

        Returns:
            发送是否成功
        """
        try:
            await ws.send_json(message)
            return True
        except Exception as e:
            client_id = self._client_info.get(ws, {}).get("client_id", "unknown")
            logger.debug(f"Failed to send to {client_id}: {e}")
            await self.disconnect(ws)
            return False

    async def broadcast(self, message: dict, exclude: Optional[WebSocket] = None) -> int:
        """向所有连接广播消息

        Args:
            message: 要广播的消息字典
            exclude: 可选的要排除的 WebSocket 连接

        Returns:
            成功发送的客户端数量
        """
        disconnected = []
        sent_count = 0

        for ws in self.connections:
            if ws is exclude:
                continue
            try:
                await ws.send_json(message)
                sent_count += 1
            except Exception as e:
                client_id = self._client_info.get(ws, {}).get("client_id", "unknown")
                logger.debug(f"Broadcast failed to {client_id}: {e}")
                disconnected.append(ws)

        # 清理断开的连接
        for ws in disconnected:
            await self.disconnect(ws)

        return sent_count

    async def send_error(
        self, ws: WebSocket, code: str, message: str, details: Optional[dict] = None
    ) -> bool:
        """向客户端发送错误消息

        Args:
            ws: 目标 WebSocket 连接
            code: 错误代码
            message: 错误消息
            details: 可选的详细信息

        Returns:
            发送是否成功
        """
        error_payload = {"code": code, "message": message}
        if details:
            error_payload["details"] = details

        return await self.send_to(
            ws, {"type": "server.error", "timestamp": self._now_ms(), "payload": error_payload}
        )

    async def close_all(self) -> None:
        """关闭所有 WebSocket 连接"""
        logger.info(f"Closing all {len(self.connections)} WebSocket connections")

        # 复制列表避免遍历时修改
        connections = list(self.connections)
        for ws in connections:
            try:
                await ws.close(code=1001, reason="Server shutting down")
            except Exception:
                pass

        self.connections.clear()
        self._client_info.clear()

    def get_connection_count(self) -> int:
        """获取当前连接数"""
        return len(self.connections)

    def get_client_info(self, ws: WebSocket) -> Optional[dict]:
        """获取客户端信息"""
        return self._client_info.get(ws)

    @staticmethod
    def _now_ms() -> int:
        """获取当前时间戳（毫秒）"""
        import time

        return int(time.time() * 1000)
