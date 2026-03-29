"""
配置加载模块

支持YAML配置文件和环境变量引用
"""

import os
import yaml
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from pathlib import Path


@dataclass
class LLMConfig:
    """LLM配置"""

    provider: str
    model: str
    api_key: str
    base_url: str
    temperature: float = 0.7
    max_tokens: int = 2048
    timeout: int = 30


@dataclass
class AgentConfig:
    """Agent配置"""

    name: str
    color: str
    description: str
    llm: LLMConfig
    system_prompt_file: str
    max_retries: int = 3
    retry_delay: int = 2
    use_tools: bool = True
    use_reflection: bool = False


@dataclass
class RefereeConfig:
    """裁判配置"""

    name: str
    role: str
    description: str
    llm: LLMConfig
    system_prompt_file: str
    validate_all_moves: bool = True
    explain_violations: bool = True


@dataclass
class MCPToolsConfig:
    """MCP工具配置"""

    enabled: bool = True
    tools_dir: str = "data/opening_books"


@dataclass
class TimeControlConfig:
    """时限配置"""

    enabled: bool = False
    seconds_per_turn: int = 60


@dataclass
class GameConfig:
    """游戏全局配置"""

    initial_fen: str = (
        "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"
    )
    time_control: TimeControlConfig = field(default_factory=TimeControlConfig)
    max_turns: int = 200


@dataclass
class LoggingConfig:
    """日志配置"""

    level: str = "INFO"
    file: str = "logs/game.log"
    console: bool = True


@dataclass
class Web3DRenderingConfig:
    """Web 3D 渲染配置"""

    shadow_map_size: int = 2048
    default_camera_position: list = field(default_factory=lambda: [8, 12, 12])
    animation_duration: float = 0.5


@dataclass
class Web3DConfig:
    """Web 3D 配置"""

    host: str = "0.0.0.0"
    port: int = 8080
    auto_open_browser: bool = True
    static_dir: str = "src/web_3d/static"
    rendering: Web3DRenderingConfig = field(default_factory=Web3DRenderingConfig)


@dataclass
class GUIConfig:
    """GUI配置"""

    enable_3d: bool = False
    web_3d: bool = True
    web_3d_config: Web3DConfig = field(default_factory=Web3DConfig)


@dataclass
class AppConfig:
    """应用完整配置"""

    game: GameConfig
    mcp_tools: MCPToolsConfig
    logging: LoggingConfig
    gui: GUIConfig


class ConfigLoader:
    """配置加载器"""

    @staticmethod
    def _resolve_env_vars(value: Any) -> Any:
        """解析环境变量引用 ${VAR_NAME}"""
        if isinstance(value, str):
            if value.startswith("${") and value.endswith("}"):
                env_var = value[2:-1]
                return os.environ.get(env_var, "")
            if value.startswith("${") and ":" in value:
                inner = value[2:-1]
                var_name, default = inner.split(":", 1)
                return os.environ.get(var_name, default)
        return value

    @staticmethod
    def _resolve_dict_env_vars(d: Dict[str, Any]) -> Dict[str, Any]:
        """递归解析字典中的环境变量"""
        result = {}
        for key, value in d.items():
            if isinstance(value, dict):
                result[key] = ConfigLoader._resolve_dict_env_vars(value)
            else:
                result[key] = ConfigLoader._resolve_env_vars(value)
        return result

    @classmethod
    def load_yaml(cls, path) -> Dict[str, Any]:
        """加载YAML配置文件"""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        with open(path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        return cls._resolve_dict_env_vars(config or {})

    @classmethod
    def load_agent_config(cls, path: str) -> AgentConfig:
        """加载Agent配置"""
        data = cls.load_yaml(path)
        llm_data = data.get("llm", {})
        agent_data = data.get("agent", {})

        llm = LLMConfig(
            provider=llm_data.get("provider", ""),
            model=llm_data.get("model", ""),
            api_key=llm_data.get("api_key", ""),
            base_url=llm_data.get("base_url", ""),
            temperature=llm_data.get("temperature", 0.7),
            max_tokens=llm_data.get("max_tokens", 2048),
            timeout=llm_data.get("timeout", 30),
        )

        return AgentConfig(
            name=agent_data.get("name", ""),
            color=agent_data.get("color", ""),
            description=agent_data.get("description", ""),
            llm=llm,
            system_prompt_file=agent_data.get("system_prompt_file", ""),
            max_retries=agent_data.get("max_retries", 3),
            retry_delay=agent_data.get("retry_delay", 2),
            use_tools=agent_data.get("use_tools", True),
            use_reflection=agent_data.get("use_reflection", False),
        )

    @classmethod
    def load_game_config(cls, path: str) -> GameConfig:
        """加载游戏配置"""
        data = cls.load_yaml(path)
        game_data = data.get("game", {})

        tc_data = game_data.get("time_control", {})
        time_control = TimeControlConfig(
            enabled=tc_data.get("enabled", False),
            seconds_per_turn=tc_data.get("seconds_per_turn", 60),
        )

        return GameConfig(
            initial_fen=game_data.get("initial_fen", ""),
            time_control=time_control,
            max_turns=game_data.get("max_turns", 200),
        )

    @classmethod
    def load_logging_config(cls, path: str) -> LoggingConfig:
        """加载日志配置"""
        data = cls.load_yaml(path)
        logging_data = data.get("logging", {})

        return LoggingConfig(
            level=logging_data.get("level", "INFO"),
            file=logging_data.get("file", "logs/game.log"),
            console=logging_data.get("console", True),
        )

    @classmethod
    def load_mcp_tools_config(cls, path: str) -> MCPToolsConfig:
        """加载MCP工具配置"""
        data = cls.load_yaml(path)
        mcp_data = data.get("mcp_tools", {})

        return MCPToolsConfig(
            enabled=mcp_data.get("enabled", True),
            tools_dir=mcp_data.get("tools_dir", "data/opening_books"),
        )

    @classmethod
    def load_gui_config(cls, path: str) -> GUIConfig:
        """加载GUI配置"""
        data = cls.load_yaml(path)
        gui_data = data.get("gui", {})

        # 加载 web_3d_config
        web_3d_config_data = gui_data.get("web_3d_config", {})
        rendering_data = web_3d_config_data.get("rendering", {})

        rendering_config = Web3DRenderingConfig(
            shadow_map_size=rendering_data.get("shadow_map_size", 2048),
            default_camera_position=rendering_data.get(
                "default_camera_position", [8, 12, 12]
            ),
            animation_duration=rendering_data.get("animation_duration", 0.5),
        )

        web_3d_config = Web3DConfig(
            host=web_3d_config_data.get("host", "0.0.0.0"),
            port=web_3d_config_data.get("port", 8080),
            auto_open_browser=web_3d_config_data.get("auto_open_browser", True),
            static_dir=web_3d_config_data.get("static_dir", "src/web_3d/static"),
            rendering=rendering_config,
        )

        return GUIConfig(
            enable_3d=gui_data.get("3d", False),
            web_3d=gui_data.get("web_3d", True),
            web_3d_config=web_3d_config,
        )

    @classmethod
    def load_app_config(cls, path: str) -> AppConfig:
        """加载完整的应用配置"""
        return AppConfig(
            game=cls.load_game_config(path),
            mcp_tools=cls.load_mcp_tools_config(path),
            logging=cls.load_logging_config(path),
            gui=cls.load_gui_config(path),
        )
