"""
Web 3D 模块测试

测试内容:
- Web3DConfig 配置加载
- Web3DServer 初始化和生命周期
- WebSocketManager 连接管理
- ObserverBridge 同步/异步桥接
- 消息广播
"""

import asyncio
import pytest
from pathlib import Path

# 确保项目根目录在路径中
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.config_loader import ConfigLoader, GUIConfig, Web3DConfig, Web3DRenderingConfig
from src.web_3d import Web3DServer, make_sync_observer, WebSocketManager
from src.web_3d.observer_bridge import ObserverBridge


class TestWeb3DConfig:
    """测试 Web 3D 配置"""

    def test_default_config(self):
        """测试默认配置"""
        config = Web3DConfig()
        assert config.host == "0.0.0.0"
        assert config.port == 8080
        assert config.auto_open_browser == True
        assert config.static_dir == "src/web_3d/static"
        assert config.rendering.shadow_map_size == 2048

    def test_load_from_yaml(self):
        """测试从 YAML 加载配置"""
        config = ConfigLoader.load_gui_config("config/game_config.yaml")
        
        assert config.web_3d == True
        assert config.web_3d_config.port == 8080
        assert config.web_3d_config.host == "0.0.0.0"
        assert config.web_3d_config.static_dir == "src/web_3d/static"

    def test_custom_config(self):
        """测试自定义配置"""
        rendering = Web3DRenderingConfig(
            shadow_map_size=4096,
            default_camera_position=[10, 15, 10],
            animation_duration=0.3
        )
        config = Web3DConfig(
            host="127.0.0.1",
            port=9090,
            auto_open_browser=False,
            static_dir="custom/static",
            rendering=rendering
        )
        
        assert config.host == "127.0.0.1"
        assert config.port == 9090
        assert config.auto_open_browser == False
        assert config.rendering.shadow_map_size == 4096


class TestWebSocketManager:
    """测试 WebSocket 管理器"""

    @pytest.fixture
    def manager(self):
        return WebSocketManager()

    @pytest.mark.asyncio
    async def test_initial_state(self, manager):
        """测试初始状态"""
        assert manager.get_connection_count() == 0
        assert manager.connections == []

    @pytest.mark.asyncio
    async def test_broadcast_no_connections(self, manager):
        """测试无连接时的广播"""
        sent = await manager.broadcast({"type": "test"})
        assert sent == 0


class TestObserverBridge:
    """测试 Observer 桥接器"""

    @pytest.mark.asyncio
    async def test_bridge_creation(self):
        """测试桥接器创建"""
        async def mock_broadcast(move, fen, is_game_over):
            pass
        
        bridge = ObserverBridge(mock_broadcast)
        assert bridge._async_broadcast == mock_broadcast

    def test_make_sync_observer_no_loop(self):
        """测试无事件循环时的 observer"""
        class MockServer:
            async def broadcast_move(self, move, fen, is_game_over):
                pass
        
        server = MockServer()
        observer = make_sync_observer(server)
        
        # 没有事件循环时不应抛出异常
        observer("h2e2", "test_fen", False)


class TestWeb3DServer:
    """测试 Web 3D 服务器"""

    @pytest.fixture
    def config(self):
        return Web3DConfig(
            host="127.0.0.1",
            port=18080,  # 使用高位端口避免冲突
            auto_open_browser=False,
            static_dir="src/web_3d/static"
        )

    def test_server_creation(self, config):
        """测试服务器创建"""
        server = Web3DServer(config)
        assert server.config == config
        assert server.ws_manager is not None
        assert server._current_state is None
        assert server._is_running == False

    def test_update_game_state(self, config):
        """测试更新游戏状态"""
        server = Web3DServer(config)
        
        server.update_game_state(
            fen="rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1",
            turn="Red",
            turn_number=1,
            move_history=[],
            legal_moves=["h2e2", "h2g2"],
            status="playing"
        )
        
        assert server._current_state is not None
        assert server._current_state["turn"] == "Red"
        assert server._current_state["turn_number"] == 1

    def test_set_game_info(self, config):
        """测试设置游戏信息"""
        server = Web3DServer(config)
        
        server.set_game_info(
            red_agent="DeepSeek",
            black_agent="GPT-4"
        )
        
        assert server._game_info["red_agent"] == "DeepSeek"
        assert server._game_info["black_agent"] == "GPT-4"


class TestIntegration:
    """集成测试"""

    @pytest.mark.asyncio
    async def test_end_to_end_state_update(self):
        """测试端到端状态更新流程"""
        from dataclasses import dataclass
        
        @dataclass
        class MockConfig:
            host: str = "127.0.0.1"
            port: int = 18081
            auto_open_browser: bool = False
            static_dir: str = "src/web_3d/static"
            rendering: Web3DRenderingConfig = None
            
            def __post_init__(self):
                if self.rendering is None:
                    self.rendering = Web3DRenderingConfig()
        
        config = MockConfig()
        server = Web3DServer(config)
        
        # 初始化状态
        server.update_game_state(
            fen="rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1",
            turn="Red",
            turn_number=1,
            move_history=[],
            status="playing"
        )
        
        assert server._current_state["turn_number"] == 1
        
        # 模拟广播走步
        await server.broadcast_move("h2e2", "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/R1BAKABNR b - - 1 1", False)
        
        # 验证状态更新
        assert "h2e2" in server._current_state["move_history"]
        assert server._current_state["turn_number"] == 1


def test_protocol_version():
    """测试协议版本"""
    from src.web_3d.server import PROTOCOL_VERSION
    assert PROTOCOL_VERSION == "1.0.0"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
