# tests/eval — 对局评测 harness（`W-02`）

为 Skill 模式重构建立**可复现的棋力基线**。本 harness 的存在理由见
`docs/skill-mode-design.md` 裁决 `D-08`：度量必须先于重构，否则「变好了没」无法证伪。

## 原则

- **只观察，不介入。** 复用现有的 `LLMAgent` / `LLMAgentGameController`，不复制游戏逻辑。
  唯一的包装是 `InstrumentedAdapter` 计量层，对被测代码完全透明。
- **不改决策逻辑。** 本目录不修改 `src/` 下任何文件。
- **密钥不入库。** 只从环境变量或 `--api-file` 读取；`--api-file` 与环境变量冲突时**直接报错**，
  不做静默优先级（本机就踩过：环境变量里存着一把失效的旧 key）。

## 用法

```bash
# 1. 只复验冻结局面集（离线，无需密钥）
python -m tests.eval.run --cases-only

# 2. 复验两家连通性
python -m tests.eval.run --probe --api-file C:\path\to\TEST_API.txt

# 3. 跑基线
python -m tests.eval.run --games 7 --seed 42 --max-turns 40 --out docs/eval-baseline.json

# 3b. thinking 开关 A/B（回答「关掉 thinking 是否削弱棋力」）
python -m tests.eval.run --games 7 --seed 42 --max-turns 40 \
    --thinking true --out docs/eval-thinking-on.json

# 4. 复验报告自洽性
python -m tests.eval.run --verify docs/eval-baseline.json
```

常用开关：`--both-sides`（正反两个方向）、`--only-category endgame in_check`、
`--thinking true|false`（覆盖 config，用于 A/B）。

**A/B 必须用同一个 `--seed`**：局面顺序由 seed 派生，两次跑的局面集与顺序完全一致，
差异才归因于被测变量。

**git 状态在开跑前采集**：报告里的 `commit` / `dirty` 若在跑完之后才取，
期间发生的任何提交都会让报告声称自己来自一个它没跑过的 commit。基线必须自述。

密钥文件格式（每行一条，`【name】...sk-xxx`）：

```
【Mimo】只能用mimo-v2.6-flash，KEY是sk-xxxx
【deepseek】只能用deepseek-flash，KEY是sk-yyyy
```

## 确定性

**LLM 采样本身不确定，两次 live 跑不可能逐字节一致。**
因此 harness 只保证三条**可证明**的确定性，`--verify` 一次跑完：

1. 序列化确定性 —— 文件内容 == 规范化重新序列化的输出
2. 汇总纯函数性 —— 仅用 `raw` 重算 summary，整份报告与文件逐字节相同
3. 局面集完整性 —— 全部 FEN 用 `RefereeEngine` 复验通过

评测温度固定为 `0.0`（**不是仓库默认的 0.7**），并写入报告 `meta`。
基线必须自述测的是什么。

## 指标含义

| 指标 | 含义 |
|---|---|
| `text_only_ratio` | 纯文本回合占比。走的是正则提取路径，是**非法走步/重试的先行指标**。Skill 模式落地后应显著下降 |
| `content_only_turns` | 模型返回纯文本而非工具调用的次数 |
| `mean_tokens_per_turn` | 每手平均 token 总量 |

## 局面集

`cases.json` 由引擎实走生成（**禁止手改**），加载时用 `RefereeEngine` 复验：
每个 FEN 都必须存在、与记录的合法走步数一致、且轮到红方走棋
（`GameController` 硬编码 `phase=RED_TO_MOVE`，这是既有行为，见归档文档 P1-6）。

覆盖：开局 / 中局 / 被将军（仅 5 个合法应手）/ 残局。

**已知缺口**：重复局面（长将/三次重复）场景未覆盖。

## 已知问题

首轮实跑发现：当前 `max_tokens: 2048` 会被思维链吃光，模型**从未写出答案**，
走步全靠从截断的思考文本里正则刨。详见 `docs/skill-mode-design.md` 事实 `F-017`
与工作项 `W-00`。基线采集应在 `W-00` 之后进行，否则 before 本身是坏的。