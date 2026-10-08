"""跑单局并记录指标。

原则：**不复制游戏逻辑**。这里只负责构造既有的
AgentConfig / LLMAgent / LLMAgentGameController，然后观察结果。
唯一的包装是适配器计量层，对被测代码完全透明。
"""
import time
from pathlib import Path
from typing import Dict, List, Optional

from src.core.referee_engine import RefereeEngine
from src.core.game_controller import LLMAgentGameController
from src.agents.base_agent import AgentConfig
from src.agents.llm_agent import LLMAgent
from src.agents.prompt_builder import PromptBuilder
from src.utils.config_loader import ConfigLoader

from . import providers

REPO = Path(__file__).resolve().parents[2]
AGENT_CFG = {1: "agent1_config.yaml", 2: "agent2_config.yaml"}
DEFAULT_PROMPT = "prompts/agent_default.txt"

# 评测用温度：0 以尽可能消除采样抖动。
# 这不是"现状"，因此必须写进报告——基线必须自述测的是什么。
EVAL_TEMPERATURE = 0.0


def build_agent(slot: int, adapter, color: str, name: str, temperature: float) -> LLMAgent:
    """镜像 game.py::_load_agent，仅替换 adapter 并覆盖 temperature。"""
    cfg = ConfigLoader.load_yaml(REPO / "config" / AGENT_CFG[slot])
    llm, agent_data = cfg["llm"], cfg["agent"]

    prompt_path = REPO / agent_data.get("system_prompt_file", DEFAULT_PROMPT)
    system_prompt = PromptBuilder.from_file(str(prompt_path)).system_prompt

    agent_cfg = AgentConfig(
        name=name,
        color=color,
        description=agent_data.get("description", ""),
        llm_adapter=adapter,
        system_prompt=system_prompt,
        max_retries=agent_data.get("max_retries", 3),
        use_tools=agent_data.get("use_tools", False),
        use_reflection=agent_data.get("use_reflection", False),
    )
    # AgentConfig 不带 temperature，它随 adapter 走；在 adapter 上设置
    adapter.temperature = temperature
    adapter.max_retries = 1  # 重试交给 controller，避免两层重试叠乘
    return LLMAgent(agent_cfg)


async def play_case(
    case,
    red_provider: str,
    black_provider: str,
    keys: Dict[str, str],
    max_turns: int = 60,
    timeout: int = 300,
    temperature: float = EVAL_TEMPERATURE,
    thinking: Optional[bool] = None,
) -> Dict:
    """跑一局，返回一条原始记录。

    thinking=None 表示沿用 config（providers.THINKING）。
    """
    red_adapter = providers.InstrumentedAdapter(
        providers.build_adapter(red_provider, keys[red_provider], thinking=thinking))
    black_adapter = providers.InstrumentedAdapter(
        providers.build_adapter(black_provider, keys[black_provider], thinking=thinking))

    red = build_agent(1, red_adapter, "Red", "EvalRed", temperature)
    black = build_agent(2, black_adapter, "Black", "EvalBlack", temperature)

    engine = RefereeEngine(case.fen)
    controller = LLMAgentGameController(
        red_agent=red, black_agent=black, referee_engine=engine, max_turns=max_turns)

    t0 = time.perf_counter()
    aborted = None
    try:
        result = await controller.run_game(verbose=False)
    except Exception as e:  # 单局失败不应中断整批评测
        result, aborted = {}, "%s: %s" % (type(e).__name__, str(e)[:200])
    elapsed = time.perf_counter() - t0

    try:
        await red_adapter.close()
        await black_adapter.close()
    except Exception:
        pass

    history = (result or {}).get("move_history") or []
    return {
        "case_id": case.case_id,
        "category": case.category,
        "starting_fen": case.fen,
        "red": red_provider,
        "black": black_provider,
        "aborted": aborted,
        "result": (result or {}).get("result"),
        "result_reason": (result or {}).get("result_reason"),
        "turn_count": (result or {}).get("turn_count", len(history)),
        "moves_played": len(history),
        "move_history": history,
        "elapsed_sec": round(elapsed, 2),
        "stats": {"Red": red_adapter.stats(), "Black": black_adapter.stats()},
    }


async def play_all(
    cases: List,
    matchups: List[tuple],
    keys: Dict[str, str],
    **kw,
) -> List[Dict]:
    records = []
    for case in cases:
        for red_p, black_p in matchups:
            rec = await play_case(case, red_p, black_p, keys, **kw)
            records.append(rec)
            print("  %-22s %-9s vs %-9s -> %-12s ply=%-4s %.1fs" % (
                rec["case_id"], red_p, black_p,
                rec["result"] or rec["aborted"] or "?",
                rec["turn_count"], rec["elapsed_sec"]), flush=True)
    return records