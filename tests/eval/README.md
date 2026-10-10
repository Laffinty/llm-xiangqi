# tests/eval — 对局评测 harness（`W-02`）

为 Skill 模式重构建立**可复现的棋力基线**。本 harness 的存在理由见
`docs/history/skill-mode-design.md` 裁决 `D-08`：度量必须先于重构，否则「变好了没」无法证伪。

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

# 5. 跑局后与基线对比（门禁）
python -m tests.eval.run --games 7 --seed 42 --max-turns 40 \
    --out docs/eval-after-w03.json --compare docs/eval-baseline.json
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

**文件必须是 UTF-8**（`providers.py` 按 `utf-8-sig` 读）。GBK 文件会解析失败或
静默解析出错误的 provider 标记。用记事本另存为时留意编码。

**密钥冲突会直接中止**（2026-10-10 实测）：若环境变量里有一把失效的
`MIMO_API_KEY`，而密钥文件里是有效的，`load_keys` 抛 `KeyConflict` 并**不发任何请求**。
这不是 bug——「默认优先级」正是静默用错 key 的成因。清掉环境变量或改文件：

```powershell
$env:MIMO_API_KEY=''      # 清掉冲突项，再跑
python -m tests.eval.run --probe --api-file <路径>
```

`--probe` 会真实发一次请求验连通性，且**要求两家密钥齐备**——
只配一家会以 `MissingKey` 退出。

**密钥文件不要放进仓库**。`.gitignore` 已覆盖 `api.txt` / `TEST_API.txt` /
`*_API.txt`（2026-10-10 补上——原先只有 `.env`，而本项目的密钥文件正是
`TEST_API.txt` 这种命名，不补的话一次 `git add .` 就会把 key 提交出去，
且**git 历史里删不掉**）。

### 局面集

| 文件 | 来源 | 用途 |
|---|---|---|
| `tests/eval/cases.json` | 引擎实走生成的**冻结集** | 所有已有基线用它，作为对比的控制变量 |
| `tests/eval/cases_real.json` | 2026-10-10 真实对局（13 手红方将死胜） | 更贴近真实分布；用 `--cases-file` 选择 |

**`--compare` 必须两侧用同一套局面集**，否则差异无法归因。报告的 `meta.cases_file`
会记录实际使用的那套。

`cases_real.json` 只收录「轮到红方且有合法走步」的局面：`GameController` 硬编码
`phase=RED_TO_MOVE`，黑方走棋的局面会把该走法派给错误的 Agent；
终局（0 合法走步）保留在 `source_game` 里而不是 `cases`。

---

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

## 观感性门禁（`python -m tests.eval.spectacle`）

上面那组是**合法性**门禁。本项目另有一组**观感性**门禁，用独立命令：

```bash
# 纯离线重放，不调 API —— raw 里已有 starting_fen + move_history
python -m tests.eval.spectacle --report docs/eval-after-spectacle.json

# 与基线对比并判定
python -m tests.eval.spectacle --report <本次报告> --compare docs/eval-baseline.json
```

**为什么不并入 `run.py --compare`**：观感性指标全部由「起始局面 + 走法序列」重放得出，
与 LLM 无关，因此可以脱离跑局单独执行。已跑过的历史报告随时能补算，
不必为加几个指标重跑一次对局（那要花 API 额度）。

| 指标 | 方向 | 含义 |
|---|---|---|
| `mean_tactic_rate` | 不得下降（且 ≤ 0.45） | 吃子或将军的着法占比 |
| `mean_move_repeat_rate` | 不得上升 | 同一方重复走同一手的比例 |
| `mean_sac_sound_rate` | 不得下降 | 弃子中「没白送」的比例 |
| `mean_quiet_streak_max` | 不得上升 | 最长连续无吃无将手数 |
| `total_long_chase_turns` | 不得上升 | 进入重复循环后的回合数 |

**阈值不是拍的**：`tactic_rate` 上限 0.45 来自 6 份历史报告的实测分布
（`docs/plan/entertainment-quality-plan.md` §3.4）。初稿的 0.55 在全部实测数据上
**永不触发**，等于装饰性守卫，已被实测推翻。

判定规则与上面同源：**基线缺该指标（含 `None`，如无弃子时 `sac_sound_rate`）
一律判「无法判定」，退出码 1，绝不显示成「通过」。**

---

## 已知问题

首轮实跑发现：当前 `max_tokens: 2048` 会被思维链吃光，模型**从未写出答案**，
走步全靠从截断的思考文本里正则刨。详见 `docs/history/skill-mode-design.md` 事实 `F-017`
与工作项 `W-00`。基线采集应在 `W-00` 之后进行，否则 before 本身是坏的。
评测报告的角色与当前基准见 `docs/open-questions.md`；本轮迁移的证据链在 `docs/history/skill-mode-design.md`。

## 门禁（`--compare`）

`--compare` 会跑局后逐项对比基线，按固定方向判定。方向写死在 `run.py:GATES`，
不要在调用处临时改。

| 指标 | 方向 | 含义 |
|---|---|---|
| `move_quality.*.illegal_rate` | 不得上升 | 非法走步 + 解析失败占比 |
| `sides.*.text_only_ratio` | 不得上升 | 走正则兜底路径的回合占比 |
| `sides.*.errors` | 不得上升 | 调用错误数 |

代销与速度只展示不能门禁——它们是取舍，不是回归。

**基线缺某个指标时，门禁判为「无法判定」并令退出码为 1**——
不会把「没测过」显示成「通过」。这是这个工具最不应该犯的错。

另：报告格式演进后旧报告可用 `--restate` 重算，无需重跑对局。
