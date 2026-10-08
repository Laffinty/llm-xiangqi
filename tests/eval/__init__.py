"""LLM-Xiangqi 对局评测 harness（W-02）。

用途：在**不改动任何决策逻辑**的前提下，为 Skill 模式重构建立可复现的棋力基线。

设计约束：
- 只观察，不介入。复用现有的 LLMAgent / LLMAgentGameController，评测不复制游戏逻辑。
- 密钥只从环境变量或 --api-file 读取，任何情况下都不写入仓库。
- 汇总层必须是原始记录的纯函数，因此 --verify 能逐字节复算。

命令：
    python -m tests.eval.run --games 20 --seed 42 --out docs/eval-baseline.json
    python -m tests.eval.run --verify docs/eval-baseline.json
    python -m tests.eval.run --probe
"""

__all__ = ["cases", "providers", "runner", "report"]