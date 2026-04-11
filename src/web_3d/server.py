"""
Web 3D 服务器模块

基于 FastAPI 的 Web 服务器，提供 WebSocket 通信和静态文件服务。
在独立线程中运行 uvicorn，与主事件循环隔离。
"""

import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from src.utils.logger import get_logger
from src.web_3d.websocket_manager import WebSocketManager

logger = get_logger("web_3d.server", level="INFO")

# 协议版本
PROTOCOL_VERSION = "1.0.0"


def _now_ms() -> int:
    """获取当前时间戳（毫秒）"""
    return int(time.time() * 1000)


class Web3DServer:
    """Web 3D 服务器，在独立线程中运行 uvicorn

    特性:
    - FastAPI Web 框架
    - WebSocket 实时通信
    - 静态文件服务 (HTML/JS/CSS)
    - 独立线程运行，不阻塞主事件循环
    - 自动浏览器打开
    """

    def __init__(self, config):
        """
        Args:
            config: Web3DConfig 配置对象
        """
        self.config = config
        self.app = self._create_app()
        self.server: Optional[Any] = None  # uvicorn.Server
        self.ws_manager = WebSocketManager()
        self._state_lock = threading.Lock()
        self._current_state: Optional[dict] = None
        self._game_info: dict = {}
        self._server_thread: Optional[threading.Thread] = None
        self._is_running = False

        # 延迟导入 uvicorn，避免事件循环问题
        try:
            import uvicorn

            self._uvicorn = uvicorn
        except ImportError:
            logger.error("uvicorn not installed, Web 3D server cannot start")
            self._uvicorn = None

    def _create_app(self) -> FastAPI:
        """创建 FastAPI 应用实例"""

        @asynccontextmanager
        async def lifespan(app: FastAPI):
            """应用生命周期管理"""
            logger.info("Web 3D server starting up")
            yield
            logger.info("Web 3D server shutting down")
            await self.ws_manager.close_all()

        app = FastAPI(
            title="LLM Xiangqi Web 3D",
            description="Web 3D visualization for LLM Chinese Chess",
            version=PROTOCOL_VERSION,
            lifespan=lifespan,
        )

        # WebSocket 端点
        @app.websocket("/ws")
        async def websocket_endpoint(ws: WebSocket):
            """WebSocket 连接处理"""
            client_id = None
            try:
                # 等待第一条消息获取 client_id
                # 先接受连接，然后在消息循环中处理
                await self.ws_manager.connect(ws, client_id=None)

                while True:
                    try:
                        data = await ws.receive_json()
                        await self._handle_message(ws, data)
                    except Exception as e:
                        logger.debug(f"WebSocket receive error: {e}")
                        break

            except WebSocketDisconnect:
                logger.debug("Client disconnected")
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
            finally:
                await self.ws_manager.disconnect(ws)

        # 健康检查端点
        @app.get("/health")
        async def health_check():
            return {
                "status": "healthy",
                "protocol_version": PROTOCOL_VERSION,
                "connections": self.ws_manager.get_connection_count(),
            }

        # 挂载静态文件目录
        static_dir = Path(self.config.static_dir)
        if static_dir.exists():
            app.mount(
                "/",
                StaticFiles(directory=str(static_dir), html=True),
                name="static",
            )
        else:
            logger.warning(f"Static directory not found: {static_dir}")

            # 创建一个简单的占位响应
            @app.get("/")
            async def root():
                return {
                    "message": "Web 3D Server running",
                    "status": "static files not found",
                    "static_dir": str(static_dir),
                }

        return app

    async def _handle_message(self, ws: WebSocket, data: dict) -> None:
        """处理客户端消息

        Args:
            ws: WebSocket 连接
            data: 收到的消息字典
        """
        if not isinstance(data, dict):
            await self.ws_manager.send_error(
                ws, "INVALID_MESSAGE", "Message must be a JSON object"
            )
            return

        msg_type = data.get("type")
        if not msg_type or not isinstance(msg_type, str):
            await self.ws_manager.send_error(
                ws, "MISSING_TYPE", "Message must contain a 'type' field"
            )
            return

        client_id = data.get("client_id")

        # 更新客户端信息
        if client_id and self.ws_manager.get_client_info(ws):
            self.ws_manager._client_info[ws]["client_id"] = client_id

        if msg_type == "client.ready":
            await self._handle_client_ready(ws, data)

        elif msg_type == "client.ping":
            await self._handle_ping(ws, data)

        else:
            logger.warning(f"Unknown message type: {msg_type}")
            await self.ws_manager.send_error(
                ws, "UNKNOWN_MESSAGE_TYPE", f"Unknown message type: {msg_type}"
            )

    async def _handle_client_ready(self, ws: WebSocket, data: dict) -> None:
        """处理客户端就绪消息

        发送当前游戏状态给新连接的客户端。
        """
        client_version = data.get("protocol_version", "0.0.0")

        # 协议版本检查
        if client_version != PROTOCOL_VERSION:
            await self.ws_manager.send_error(
                ws,
                "PROTOCOL_VERSION_MISMATCH",
                f"Protocol version mismatch: client={client_version}, server={PROTOCOL_VERSION}",
                {"expected": PROTOCOL_VERSION, "received": client_version},
            )
            return

        # 发送当前游戏状态
        with self._state_lock:
            current_state = self._current_state
        if current_state:
            await self.ws_manager.send_to(
                ws,
                {
                    "type": "game.init",
                    "timestamp": _now_ms(),
                    "payload": current_state,
                },
            )
            logger.debug(f"Sent game.init to client")
        else:
            # 游戏尚未开始，发送空状态
            await self.ws_manager.send_to(
                ws,
                {
                    "type": "game.init",
                    "timestamp": _now_ms(),
                    "payload": {
                        "status": "waiting",
                        "message": "Game not started yet",
                    },
                },
            )

    async def _handle_ping(self, ws: WebSocket, data: dict) -> None:
        """处理心跳 ping"""
        ping_id = data.get("payload", {}).get("id") if data.get("payload") else None

        await self.ws_manager.send_to(
            ws,
            {
                "type": "server.pong",
                "timestamp": _now_ms(),
                "payload": {"id": ping_id},
            },
        )

    def start(self) -> None:
        """在独立线程中启动 uvicorn 服务器

        使用 threading 而非 asyncio.create_task()，因为:
        1. asyncio.run() 的事件循环尚未启动时不能调用 create_task
        2. uvicorn 内部有自己的事件循环，放在独立线程更安全
        """
        if self._is_running:
            logger.warning("Server already running")
            return

        if self._uvicorn is None:
            raise RuntimeError("uvicorn not installed")

        config = self._uvicorn.Config(
            self.app,
            host=self.config.host,
            port=self.config.port,
            log_level="info",
            access_log=False,  # 减少日志噪音
        )
        self.server = self._uvicorn.Server(config)

        # 在独立线程中运行服务器
        self._server_thread = threading.Thread(
            target=self._run_server,
            daemon=True,
            name="Web3DServer",
        )
        self._is_running = True
        self._server_thread.start()

        logger.info(
            f"Web 3D Server starting on http://{self.config.host}:{self.config.port}"
        )

        # 自动打开浏览器
        if self.config.auto_open_browser:
            self._open_browser()

    def _run_server(self) -> None:
        """在独立线程中运行 uvicorn"""
        try:
            self.server.run()
        except Exception as e:
            logger.error(f"Server error: {e}")
        finally:
            self._is_running = False

    def _open_browser(self) -> None:
        """自动打开浏览器"""
        import webbrowser

        url = f"http://localhost:{self.config.port}"

        # 延迟打开，给服务器启动时间
        def open_delayed():
            import time

            time.sleep(1.5)  # 等待服务器启动
            try:
                webbrowser.open(url)
                logger.info(f"Opened browser: {url}")
            except Exception as e:
                logger.warning(f"Failed to open browser: {e}")

        thread = threading.Thread(target=open_delayed, daemon=True)
        thread.start()

    def stop(self) -> None:
        """停止服务器"""
        if not self._is_running or not self.server:
            return

        logger.info("Stopping Web 3D Server...")
        self._is_running = False

        # 触发服务器退出
        self.server.should_exit = True

        # 等待线程结束
        if self._server_thread and self._server_thread.is_alive():
            self._server_thread.join(timeout=5.0)

        logger.info("Web 3D Server stopped")

    def update_game_state(
        self,
        fen: str,
        turn: str,
        turn_number: int,
        move_history: list,
        legal_moves: Optional[list] = None,
        players: Optional[dict] = None,
        last_move: Optional[dict] = None,
        status: str = "playing",
        result: Optional[str] = None,
        result_reason: Optional[str] = None,
    ) -> None:
        """更新当前游戏状态

        在收到走步通知时更新内部状态，供新连接的客户端获取。
        """
        with self._state_lock:
            self._current_state = {
                "fen": fen,
                "turn": turn,
                "turn_number": turn_number,
                "move_history": move_history,
                "legal_moves": legal_moves or [],
                "players": players or {},
                "last_move": last_move,
                "status": status,
                "result": result,
                "result_reason": result_reason,
            }

    async def broadcast_move(self, move: str, fen: str, is_game_over: bool) -> None:
        """广播走步事件

        由 Observer 桥接调用，将走步信息广播给所有连接的客户端。

        Args:
            move: ICCS 格式的走法，如 "h2e2"
            fen: 移动后的 FEN 字符串
            is_game_over: 游戏是否结束
        """
        if is_game_over:
            await self._broadcast_game_over(fen)
        else:
            await self._broadcast_move_event(move, fen)

    async def _broadcast_move_event(self, move: str, fen: str) -> None:
        """广播移动事件"""
        from_pos, to_pos = move[:2], move[2:]

        # 解析 FEN 获取当前回合信息
        fen_parts = fen.split()
        turn = "Red" if fen_parts[1] == "w" else "Black"
        turn_number = int(fen_parts[5]) if len(fen_parts) > 5 else 1

        # 更新内部状态
        with self._state_lock:
            if self._current_state:
                self._current_state["fen"] = fen
                self._current_state["turn"] = turn
                self._current_state["turn_number"] = turn_number
                if move:
                    self._current_state.setdefault("move_history", []).append(move)
                self._current_state["last_move"] = {
                    "from_pos": from_pos,
                    "to_pos": to_pos,
                    "move": move,
                }

        message = {
            "type": "game.move",
            "timestamp": _now_ms(),
            "payload": {
                "move": move,
                "from_pos": from_pos,
                "to_pos": to_pos,
                "fen_after": fen,
                "turn": turn,
                "turn_number": turn_number,
            },
        }

        sent = await self.ws_manager.broadcast(message)
        logger.debug(f"Broadcasted move {move} to {sent} clients")

    async def _broadcast_game_over(self, fen: str) -> None:
        """广播游戏结束事件"""
        result = "unknown"
        result_reason = ""

        with self._state_lock:
            if self._current_state:
                result = self._current_state.get("result", "unknown")
                result_reason = self._current_state.get("result_reason", "")
                self._current_state["status"] = "finished"
                self._current_state["fen"] = fen

        message = {
            "type": "game.game_over",
            "timestamp": _now_ms(),
            "payload": {
                "result": result,
                "result_reason": result_reason,
                "fen": fen,
            },
        }

        sent = await self.ws_manager.broadcast(message)
        logger.info(f"Broadcasted game over to {sent} clients")

    def set_game_info(self, red_agent: str, black_agent: str) -> None:
        """设置游戏参与者信息"""
        with self._state_lock:
            self._game_info = {
                "red_agent": red_agent,
                "black_agent": black_agent,
            }
            if self._current_state:
                self._current_state["players"] = {
                    "Red": {"name": red_agent, "model": red_agent},
                    "Black": {"name": black_agent, "model": black_agent},
                }

    def is_running(self) -> bool:
        """检查服务器是否正在运行"""
        return (
            self._is_running and self._server_thread and self._server_thread.is_alive()
        )
