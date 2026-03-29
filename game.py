"""
LLM中国象棋对战 - 完整对战模式

使用真实LLM Agent进行对战
"""

import sys
import os

if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")
        os.system("chcp 65001 >nul 2>&1")
    except Exception:
        pass

import asyncio
import argparse
from pathlib import Path

from src.core.referee_engine import RefereeEngine, INITIAL_FEN
from src.core.game_controller import LLMAgentGameController
from src.gui.chess_gui import ChessGUI
from src.agents.llm_agent import LLMAgent
from src.web_3d import Web3DServer, make_sync_observer
from src.agents.base_agent import AgentConfig
from src.agents.prompt_builder import PromptBuilder
from src.llm_adapters.base_adapter import BaseLLMAdapter
from src.llm_adapters.deepseek_adapter import DeepSeekAdapter
from src.llm_adapters.mimo_adapter import MiMoAdapter
from src.llm_adapters.minimax_adapter import MiniMaxAdapter
from src.utils.config_loader import ConfigLoader, GUIConfig
from src.utils.logger import get_logger


ADAPTER_MAP = {
    "deepseek": DeepSeekAdapter,
    "mimo": MiMoAdapter,
    "minimax": MiniMaxAdapter,
}


logger = get_logger("game", level="INFO")


def _create_adapter(llm_config: dict) -> BaseLLMAdapter:
    """根据配置创建 LLM 适配器"""
    provider = llm_config["provider"]
    adapter_cls = ADAPTER_MAP.get(provider)
    if not adapter_cls:
        raise ValueError(
            f"Unknown LLM provider: '{provider}'. "
            f"Supported: {list(ADAPTER_MAP.keys())}"
        )
    return adapter_cls(
        api_key=llm_config["api_key"],
        model=llm_config["model"],
        base_url=llm_config["base_url"],
        timeout=llm_config.get("timeout", 30),
        max_retries=llm_config.get("max_retries", 3),
        temperature=llm_config.get("temperature", 0.7),
        max_tokens=llm_config.get("max_tokens", 2048),
    )


def _load_agent(config_file: str) -> LLMAgent:
    """从配置文件加载单个 Agent"""
    cfg = ConfigLoader.load_yaml(Path(__file__).parent / "config" / config_file)
    llm_config = cfg["llm"]
    agent_data = cfg["agent"]

    adapter = _create_adapter(llm_config)

    prompt_path = Path(__file__).parent / agent_data.get(
        "system_prompt_file", "prompts/agent_default.txt"
    )
    system_prompt = PromptBuilder.from_file(str(prompt_path)).system_prompt

    agent_cfg = AgentConfig(
        name=agent_data["name"],
        color=agent_data["color"],
        description=agent_data.get("description", ""),
        llm_adapter=adapter,
        system_prompt=system_prompt,
        max_retries=agent_data.get("max_retries", 3),
        use_tools=agent_data.get("use_tools", False),
        use_reflection=agent_data.get("use_reflection", False),
    )

    return LLMAgent(agent_cfg)


def load_agents():
    """加载Agent配置"""
    logger.info("Loading agent configurations...")

    agent1 = _load_agent("agent1_config.yaml")
    agent2 = _load_agent("agent2_config.yaml")

    logger.info(f"Agent1 (Red): {agent1.config.name} - {agent1.config.description}")
    logger.info(f"Agent2 (Black): {agent2.config.name} - {agent2.config.description}")

    return agent1, agent2


async def run_battle(agent1, agent2, max_turns: int = 100, gui_config: GUIConfig = None):
    """运行完整对局
    
    支持原生 3D GUI 和 Web 3D 两种可视化模式，通过 gui_config 配置控制。
    """
    logger.info("=" * 60)
    logger.info("LLM CHINESE CHESS BATTLE")
    logger.info("=" * 60)

    referee_engine = RefereeEngine()

    controller = LLMAgentGameController(
        red_agent=agent1,
        black_agent=agent2,
        referee_engine=referee_engine,
        max_turns=max_turns,
    )

    # GUI/Web 3D 服务器实例
    gui = None
    web_server = None

    try:
        # 根据配置决定启动哪种 GUI
        if gui_config and gui_config.enable_3d:
            # 原生 3D GUI (pyglet)
            logger.info("Native 3D GUI enabled, starting GUI...")
            red_name = f"红方:{agent1.config.llm_adapter.model}"
            black_name = f"黑方:{agent2.config.llm_adapter.model}"
            gui = ChessGUI(
                fen=INITIAL_FEN, red_agent_name=red_name, black_agent_name=black_name
            )
            gui.start()

            if not gui.wait_ready(timeout=10.0):
                logger.error("GUI initialization failed or timed out")
                return {"success": False, "error": "GUI initialization failed"}

            controller.register_observer(gui.update)

        elif gui_config and gui_config.web_3d:
            # Web 3D 服务器 (浏览器)
            logger.info(
                f"Web 3D enabled, starting server on port {gui_config.web_3d_config.port}"
            )
            web_server = Web3DServer(gui_config.web_3d_config)
            web_server.start()
            
            # 设置游戏信息
            web_server.set_game_info(
                red_agent=f"{agent1.config.name} ({agent1.config.llm_adapter.model})",
                black_agent=f"{agent2.config.name} ({agent2.config.llm_adapter.model})",
            )
            
            # 初始化游戏状态
            initial_state = controller.get_current_state()
            web_server.update_game_state(
                fen=initial_state.fen,
                turn="Red",
                turn_number=1,
                move_history=[],
                legal_moves=initial_state.legal_moves,
                players={
                    "Red": {
                        "name": agent1.config.name,
                        "model": agent1.config.llm_adapter.model,
                    },
                    "Black": {
                        "name": agent2.config.name,
                        "model": agent2.config.llm_adapter.model,
                    },
                },
                status="playing",
            )

            # 注册 Observer 桥接
            controller.register_observer(make_sync_observer(web_server))

        else:
            logger.info("GUI disabled, running in console mode")

        state = controller.get_current_state()
        logger.info(f"\nInitial Position:")
        logger.info(f"\n{state.ascii_board}")
        logger.info(f"FEN: {state.fen}")
        logger.info(f"Legal moves: {state.legal_moves_count}")

        # 运行游戏
        result = await controller.run_game(verbose=True)

        # 游戏结束后更新 Web 3D 状态
        if web_server and result:
            web_server.update_game_state(
                fen=result.get("final_fen", state.fen),
                turn=result.get("turn", "Red"),
                turn_number=result.get("turn_count", 1),
                move_history=result.get("move_history", []),
                status="finished",
                result=result.get("result"),
                result_reason=result.get("result_reason"),
            )
            # 广播游戏结束
            import asyncio
            await web_server.broadcast_move(
                "", result.get("final_fen", state.fen), is_game_over=True
            )

        # 原生 GUI 结束通知
        if gui:
            gui.update(fen=state.fen, is_game_over=True)

        logger.info("\n" + "=" * 60)
        logger.info("GAME OVER")
        logger.info("=" * 60)
        logger.info(f"Result: {result['result']}")
        logger.info(f"Reason: {result['result_reason']}")
        logger.info(f"Total turns: {result['turn_count']}")
        logger.info(f"Move history: {' '.join(result['move_history'])}")

        return result

    finally:
        # 清理资源
        if web_server:
            logger.info("Shutting down Web 3D server...")
            web_server.stop()


async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="LLM Chinese Chess Battle")
    parser.add_argument(
        "--turns", type=int, default=100, help="最大回合数 (default: 100)"
    )
    parser.add_argument(
        "--config", type=str, default="config/game_config.yaml", help="配置文件路径 (default: config/game_config.yaml)"
    )
    args = parser.parse_args()

    # 加载配置
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = Path(__file__).parent / config_path
    
    try:
        gui_config = ConfigLoader.load_gui_config(str(config_path))
        logger.info(f"Loaded config from {config_path}, 3D GUI: {'enabled' if gui_config.enable_3d else 'disabled'}")
    except Exception as e:
        logger.warning(f"Failed to load config: {e}, using defaults (3D GUI disabled)")
        gui_config = GUIConfig(enable_3d=False, web_3d=True)

    try:
        agent1, agent2 = load_agents()
        result = await run_battle(agent1, agent2, args.turns, gui_config)

    except KeyboardInterrupt:
        logger.info("\nGame interrupted by user")
    except Exception as e:
        logger.error(f"Game error: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
