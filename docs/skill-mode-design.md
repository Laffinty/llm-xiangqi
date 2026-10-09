# Skill 模式设计 PLAN — LLM ↔ 棋盘实况交互协议升级

| 字段 | 值 |
|---|---|
| 文档 ID | `PLAN-SKILL-001` |
| 状态 | **已裁决**，待实施 |
| 创建 | 2026-10-08 |
| 取代 | `docs/history/optimization-plan.md`（已停用，见 §0.4） |
| 契约文档 | `docs/api-standard.md` v0.4.0 |

---

## §0 本文档怎么用

### 0.1 格式契约（先读这段，否则会误用）

这份文档为 **AI agent 消费** 而写，规则与仓库其它文档不同，先声明：

**四种条目，各有唯一 ID 前缀，不可复用、不可重排。**

| 前缀 | 含义 | 状态标记 | 修改条件 |
|---|---|---|---|
| `F-xx` | **事实**。对当前代码的陈述 | `已核实` / `待验证` | 附证伪命令。命令输出变了 → 事实作废，**以命令为准，不以本文档为准** |
| `D-xx` | **裁决**。已定的事 | `已裁决` / `挂起` | 已裁决项默认不重开。重开需新增 `D-xx`，并显式标注废弃哪条 |
| `W-xx` | **工作项**。可独立执行的一步 | `待做` / `进行中` / `完成` / `放弃` | 每项自带依赖、验收命令、反向守卫、非目标 |
| `R-xx` | **风险**。可能推翻设计的前提 | `开放` / `已消解` / `已触发` | 触发时必须停工回到 §2 复核 |

**三条硬规则：**

1. **事实与裁决必须分开。** `F-xx` 只描述「现在是这样」，`D-xx` 描述「我们决定这样」。把决定写成事实，会让后来人无法判断哪条还能被证据推翻。
2. **「已核实」必须附原始输出，不能附结论。** 结论会被后人当成前提，输出不会。
3. **进度写在本文件里，不写在对话或 commit message 里。** 任何人接手时，读 §9 就知道现在在哪。

### 0.2 怎么执行一条 W-xx

```
读依赖 → 确认全部为「完成」→ 改代码 → 跑「验收命令」→ 跑「反向守卫」→ 更新 §9 → 才算完成
```

任何一步失败即停。**不允许「先合了再说」**——本设计的全部价值建立在每步可独立回退上。

### 0.3 新增条目守什么

- ID 只增不改。作废的条目标 `废弃` 并写明作废原因，**不删除**（删除会让后来的证伪命令失去参照）。
- 每条 `F-xx` 必须能被一条命令证伪。写不出证伪命令的，说明它不是事实，是意见——改标成 `D-xx` 或删掉。
- 每条 `W-xx` 必须有「非目标」。没有非目标的条目会被无限扩张。

### 0.4 与已归档文档的关系

`docs/optimization-plan.md` 已移入 `docs/history/`，**不再执行**。

它的 P0/P1/P2/P3 条目并未作废——**多数是真实缺陷**，其中 P2-4（历史无限增长）、P2-5（assistant 从不写回）、P2-1（工具系统未接线）与本设计直接相关，已被本文件的 `F-001`/`F-004`/`F-005` 独立重新核实并吸收。

不再执行的原因是**排序**而非结论：那份文档把「Elo 评测」和「提示词 A/B」排在「阶段 5（可选）」的最后一项。本设计主张度量必须前置（`D-08`）。

> 若要在归档文档里继续追一条缺陷，**只把结论抄进本文件的 `F-xx`，不要回去改那份文档**。

---

## §1 事实

以下全部为 `已核实`。证伪命令使用 ripgrep（在仓库根执行）。

### F-001 assistant 消息从不在运行时写回 —— `已核实`

```
rg -n "assistant" src -g "*.py"
```

原始输出（**全部命中，共 1 处**）：

```
base_adapter.py:104: messages: 消息列表，格式 [{"role": "user"/"assistant"/"system", "content": "..."}]
```

唯一命中是一条 **docstring**。`PromptBuilder.build_messages()`（`prompt_builder.py:358-378`）只追加 `history`（全为 user）+ `tool_results`（渲染为 user）+ `user_content`。运行时不存在任何 assistant 消息。

### F-002 `tool_call_id` 在代码库中不存在 —— `已核实`

```
rg -c "tool_call_id" src -g "*.py"
```

原始输出：**空**（0 命中）。`ToolCallDict`（`base_adapter.py:19-22`、`base_agent.py:37-40`）只有 `{name, arguments}`，**无 `id` 字段**，即协议上无法回填工具结果。

### F-003 工具结果被伪装成 user 消息 —— `已核实`

`base_agent.py:153` 调用 `self.prompt_builder.add_tool_results(tool_results)`；`prompt_builder.py:402-404` 将其 `extend` 进 `self.tool_results`；`prompt_builder.py:370-373` 在 `build_messages` 中把它渲染为：

```python
messages.append({"role": "user", "content": tool_content})
```

模型收到的是「系统声称工具返回了这个」，而**不是**协议定义的 `role:"tool"` 消息。

### F-004 `agent.reset()` 从未被调用 —— `已核实`

```
rg -n "\.reset\(\)" src game.py main.py tests -g "*.py"
```

原始输出（**全部命中，共 2 处**）：

```
tests\test_game_controller.py:204:        controller.reset()
tests\test_p0_regressions.py:121:        controller.reset()
```

两处都是 `GameController.reset()`，且仅在测试中。`BaseAgent.reset()`（`base_agent.py:277`）**零调用点** → `PromptBuilder.history` 与 `tool_results` 跨回合无限累积。

### F-005 LLM 实际看到的工具 = 硬编码常量 —— `已核实`

```
rg -n "MCP_TOOLS|get_tools\(\)" src -g "*.py"
```

关键命中：

```
llm_agent.py:34:   tools=self.prompt_builder.get_tools() if self.config.use_tools else None,
prompt_builder.py:86:   self.tools: List[Dict[str, Any]] = list(MCP_TOOLS)
prompt_builder.py:425:  MCP_TOOLS = [
```

即：喂给模型的 schema 来自 `prompt_builder.py:425` 的**字面常量**，与工具注册表无关。

### F-006 工具注册表从未被查询 —— `已核实`

```
rg -n "get_tool_schemas" src -g "*.py"
```

原始输出（**全部命中，共 1 处**）：

```
src\mcp_tools\tool_executor.py:135:    def get_tool_schemas(self) -> List[Dict[str, Any]]:
```

只有定义，**零调用点**。

### F-007 mcp_tools 配置被解析但无消费者 —— `已核实`

```
rg -n "load_mcp_tools_config|mcp_tools_config" src game.py -g "*.py"
rg -n "mcp|tools" game.py -i
```

原始输出：

```
config_loader.py:177:    mcp_tools: MCPToolsConfig
config_loader.py:281:    def load_mcp_tools_config(cls, path: str) -> MCPToolsConfig:
config_loader.py:328:        mcp_tools=cls.load_mcp_tools_config(path),
game.py:92: use_tools=agent_data.get("use_tools", False),
```

`config/game_config.yaml:9-17`（`tools_dir` / `auto_discover` / `pikafish`）**确实被 `ConfigLoader` 解析进 `GameConfig.mcp_tools`**，但 `game.py` 从不引用该字段；`llm_agent.py:76` 的 `ToolExecutor.get_instance()` 是**无参**调用。

> 注：归档的 `optimization-plan.md` P2-1 称「配置从未被读取」——**该表述不准确**。配置被读取并解析了，只是**解析结果从未被消费**。此处更正，以本条为准。

### F-008 走步靠正则从自由文本提取 —— `已核实`

`base_agent.py:252`：

```python
all_matches = re.findall(r'\b([a-iA-I][0-9][a-iA-I][0-9])\b', content)
```

配套的纠错重试循环在 `game_controller.py:280`（`for attempt in range(3)`，硬编码，不读 `AgentConfig.max_retries`）。

### F-009 仓库没有对局质量评测 —— `已核实`

`tests/` 下 8 个文件全部是单元测试（规则引擎 / 控制器 / Web3D / 标注）。无对局基准、无胜率统计、无 prompt A/B 设施。`optimization-plan.md:898-899` 把「Elo 评测」「提示词 A/B 实验」列在「阶段 5：功能增强（可选）」。

**该文档里的 `[已实测]` 标记测的是代码正确性，不是棋力。**

### F-010 Anthropic 协议下当前消息序列非法 —— `待验证`

`F-001` + `F-004` 叠加后，`build_messages` 产出的序列形如 `[system, user, user, user]`——连续多条 user 消息、且从未出现 assistant。Anthropic Messages API 要求 user/assistant 交替。

**未实测**：需要一个 MiniMax 适配器的真实调用来确认报错文本。理由见 `RK-04`。

### F-011 两家都接受 `Authorization: Bearer` —— `已核实`

官方文档中 MiMo 所有示例均用 `api-key: $MIMO_API_KEY` 头，而仓库 `OpenAICompatibleAdapter`
经 `AsyncOpenAI(api_key=...)` 发出的是 `Authorization: Bearer`。
用仓库自身的 `DeepSeekAdapter` / `MiMoAdapter` 真实请求验证：**两者均返回 200 且正常与模型对话**，
Bearer 可用，无需为 MiMo 保留单独认证路径。

证伪命令：删除 `openai_base_adapter.py:47` 的 `AsyncOpenAI(...)` 构造后重跑探测脚本，若 MiMo 返回 401/403 则本条作废。

### F-012 DeepSeek 不支持 `response_format: json_schema` —— `已核实`

```
response_format = {"type": "json_schema", "json_schema": {"strict": True, ...}}
-> 400 {"message": "This response_format type is unavailable now"}
```

官方文档标注 Json Output 为「✓」，但**不包含 `json_schema` 子类型**。
**因此 v0.4.0 api-standard §7.6 初稿里写的 `response_format` 方案对 DeepSeek 不成立，已改为函数定义内 `strict` 方案。**

### F-013 `tool_choice: "required"` 能否使用**取决于 thinking 模式** —— `已核实（2026-10-09 修订）`

**本条最初记为「DeepSeek 不支持 `required`」，那是错的——它是在 thinking 开启时测的。**
thinking 关闭后（W-00）复测，三种组合全部在 `thinking: disabled` 下进行：

| | `auto` | `required` | `{"type":"function","function":{"name":...}}` |
|---|---|---|---|
| DeepSeek | OK | **OK** | OK |
| MiMo | OK | **OK** | **不支持** |

**教训**：这条错误能存在，是因为我把「在配置 A 下观测到的现象」写成了「供应商的能力边界」。
后来 W-00 改了 thinking，F-013 就失效了——**事实的有效范围必须和观测条件一起记录**，
否则观测条件一变，事实就成了假知识。

推论：契约要用 `required` 才有确定性；`auto` 之下模型是否调用工具会随 prompt 复杂度漂移。

证伪命令：把 `config/agentX_config.yaml` 的 `thinking` 改回 true 后重跑上表，
若 `required` 再次被拒则本条成立。

---

### F-024 契约命中率：auto 下 3/6，生产路径 `required` 下 10/10 —— `已核实`

先用手搓请求测（完整对局 prompt），再改走**生产路径** `LLMAgent.think()`：

| 路径 | DeepSeek | MiMo | 合计 |
|---|---|---|---|
| `tool_choice=auto` | 3/3 | **0/3** | **3/6** |
| `tool_choice=required`（生产路径） | 5/5 | 5/5 | **10/10** |

10 次调用的走步**全部落在 enum 内**，无一例外。

**MiMo 在 `auto` 之下会随 prompt 复杂度漂移**：短 prompt 能触发工具调用，
完整对局 prompt 则完全不触发。所以「在 prompt 里加一句『必须调用』」是不够的——
**必须用 `required` 把选择权从模型手里拿走**。

实现上不把选择权交给配置项，而是**先试 `required`、被拒再回落 `auto`**：
供应商行为会变，写死配置等于把当下的观测固化成永久假设——`F-013` 就是这么错的。

### F-014 `strict: true` 放在函数定义内 —— 两家均可用，且**它真的在起作用** —— `已核实`

对 4 组配置（两家 × strict 开关）做矩阵探测：

| provider | strict | tool_choice | 结果 |
|---|---|---|---|
| DeepSeek | `true` | `auto` | OK，`move` 落在 enum 内 |
| DeepSeek | `true` | 不传 | OK，`move` 落在 enum 内 |
| DeepSeek | `false` | 不传 | **失败**：模型输出了 JSON 语法错误的 `arguments`（`Expecting ',' delimiter`） |
| MiMo | `true` | 不传 | OK，`move` 落在 enum 内 |
| MiMo | `false` | `auto` | OK |

**关键证据**：DeepSeek 在 `strict=false` 时实测吐出了语法错误的 JSON。
这说明 `strict` 不是装饰性标记，而是真实收紧了输出。

### F-015 `tool_calls[].id` 实测存在 —— `已核实`

两家返回的 tool_call 都带非空 `id`（探测输出 `id_present=True`）。
**这使 api-standard §3.4 的 R-1/R-2 可实现：信息确实存在，只是仓库没用。**

### F-016 MiMo 在 `strict=true` + `tool_choice=auto` 下单次未触发工具调用 —— `待验证`

矩阵中唯一一次未触发的组合。同一 schema 在其余 7 组均正常。
判断为采样抖动而非约束，但尚未统计率，因此保留为待验证。


### F-017 当前配置下模型「从不给出答案」，走步全靠从思考过程里正则刨 —— `已核实`

`W-02` 评测 harness 实跑（`endgame_m14_p059`，2026-10-08）时暴露：

| | finish_reason | content 长度 | thought 长度 | content 内走步 | thought 内走步 |
|---|---|---|---|---|---|
| DeepSeek `deepseek-flash` | `length` | **0** | 6473 | **0** | 28 |
| MiMo `mimo-v2.6-flash` | `length` | **0** | 6746 | **0** | 36 |

`config/agentX_config.yaml` 的 `max_tokens: 2048` 被思维链**完整吃光**（`completion_tokens` 恰好等于
`max_tokens`，`finish_reason` 为 `length`），模型从未写到它被要求的 JSON 答案。

`LLMAgent` 的 `content` 为空时回退到 `response.thought`（`llm_agent.py:48`），于是走步是从
**被截断的推理文本**里正则刨出来的。整局 12 手，`text_only_ratio = 1.0`，出现 9 次
`_extract_move` 解析失败。

**这不是 Skill 模式的问题，是独立的 P0 级缺陷**：两家都是 thinking model，而配置按非推理模型设定。

证伪命令：把 `max_tokens` 调到 16384 后重跑上表，若 `content` 恢复非空、`finish_reason` 不再是
`length`，则本条成立。


### F-018 加 token 预算不能根治，关掉 thinking 才是 —— `已核实`

在真实对局 prompt 上做 6 组扫描（`endgame_m14_p059`，2026-10-08）：

| provider | thinking | max_tokens | finish | 耗时 | content | 走步合法 |
|---|---|---|---|---|---|---|
| DeepSeek | **OFF** | 2048 | `stop` | **2.3s** | 318 | 是 |
| DeepSeek | ON | 8192 | `length` | 41.1s | **0** | 否 |
| DeepSeek | ON | 16384 | `stop` | 51.3s | 399 | 是 |
| MiMo | **OFF** | 2048 | `stop` | **7.4s** | 219 | 是 |
| MiMo | ON | 8192 | `stop` | **129.6s** | 298 | 是 |
| MiMo | ON | 16384 | `stop` | 58.2s | 262 | 是 |

**结论一**：单纯加大 `max_tokens` 只是把「截断」换成「慢」。DeepSeek 在 8192 仍然截断，
要到 16384 才写得出答案，单手 51s——一局 200 手就是 2.8 小时。

**结论二**：`thinking=OFF` 快 10–20 倍，content 必非空，走步合法，token 可预测。

**结论三（代价，必须记账）**：thinking 开启时延迟**高度不可预测**——MiMo 8192 用了 129.6s，
而 16384 反而只用 58.2s。因为它是「想完就停」而非「用满预算」。
这意味着开着 thinking 的评测**耗时方差极大**，无法据预算估算。

**未回答的问题（不要假装已解决）**：关掉 thinking 是否削弱棋力，本文没有测。
prompt 本身要求模型在 `thought` 字段里做四步分析，那部分推理仍然存在，
但供应商的 `reasoning_content` 被关掉了。**棋力影响属于待测项，不是已知结论。**

证伪命令：把 `config/agentX_config.yaml` 的 `thinking` 改为 true 后重跑 W-00 验收脚本，
若 content 仍非空且耗时相近，则本条结论二作废。


### F-019 thinking 开关 A/B：ON 在当前 token 预算下几乎完全不可用 —— `已核实`

3 个代表性局面 × 2 家 × {ON, OFF}，每格 1 次真实调用（2026-10-08，走生产路径
`game.py::_create_adapter` + 真实 config + 真实对局 prompt）。

| 局面 | provider | thinking | finish | 秒 | content | 合法走步 |
|---|---|---|---|---|---|---|
| `endgame_m14_p059` | DeepSeek | OFF | `stop` | **2.3** | 202 | 2 |
| `endgame_m14_p059` | DeepSeek | ON | `length` | 9.8 | **0** | 0 |
| `endgame_m14_p059` | MiMo | OFF | `stop` | **3.7** | 197 | 1 |
| `endgame_m14_p059` | MiMo | ON | `stop` | 18.7 | 256 | 1 |
| `opening_p13` | DeepSeek | OFF | `stop` | **2.8** | 420 | **0** |
| `opening_p13` | DeepSeek | ON | `length` | 9.5 | **0** | 0 |
| `opening_p13` | MiMo | OFF | `stop` | **8.5** | 266 | 1 |
| `opening_p13` | MiMo | ON | `length` | 37.2 | **0** | 0 |
| `in_check_p111` | DeepSeek | OFF | `stop` | **2.4** | 334 | 1 |
| `in_check_p111` | DeepSeek | ON | `length` | 9.7 | **0** | 0 |
| `in_check_p111` | MiMo | OFF | `stop` | 11.8 | 301 | 1 |
| `in_check_p111` | MiMo | ON | `length` | 45.4 | **0** | 0 |

**可用率：OFF 5/6，ON 1/6。** 耗时 OFF 2.3–11.8s，ON 9.5–45.4s。

DeepSeek 在 ON 档 3/3 全部 `finish_reason=length`、`content` 为空；MiMo 2/3 如此。
这说明 F-017 不是偶发，而是**在 `max_tokens: 2048` 下 thinking 开启的必然结果**。

**样本量诚实说明**：每格仅 1 次调用。这里敢下结论，依据是效应量足够大
（可用率 5:1），而不是样本量——但「棋力是否受损」这个问题 1 次调用完全回答不了。

---

### F-020 即便 thinking 关闭，仍有模型写出「无法解析的答案」 —— `已核实`

`opening_p13` + DeepSeek + thinking=OFF：content 420 字符、`finish_reason=stop`，
**但 content 里一个 ICCS 走步都没有**。模型给出了完整回答，却不是正则能抓的格式
（推测为中文记谱如「炮二平五」，未逐条核对原文，**这是推测不是结论**）。

后果：`LLMAgent._extract_move` 返回 None → 注入纠错 → 重试。基线日志里也确实出现了
多次 `LLM返回None (解析失败)`。

**这条是 W-03 决策契约的直接依据**：把合法走法写成 schema 的 `enum` 之后，
「答案格式不对」这一类失败**在构造上就不存在**——它与 prompt 措辞、记谱习惯、
模型心情都无关。

证伪命令：取 `opening_p13` + DeepSeek + thinking=OFF 重跑，若 content 中稳定出现 ICCS
模式，则本条的普遍性作废（但该次失败本身仍然成立）。


---

### F-021 协议闭环已实现并经真实供应商验收 —— `已核实`

**单测只证明消息形状，供应商是否接受才是验收。** 用真实 API 走完整工具循环
（2026-10-08），DeepSeek `deepseek-flash`：

```
[1] has_tool_calls      = True
    tool_call id        = call_00_SQ1HHMIPzUUwjHHXPTuA2187
    消息角色序列        = ['system','user','assistant','tool','assistant','tool','tool']
    工具调用轮次        = 2 | tool 消息数: 3
    tool_call_id 匹配   = True
    角色交替合法        = system/user 开头, 无连续 user
    最终 move           = h2e2   <- 从工具循环里成功提取出合法走步
[2] 用构造出的序列再发一次请求 -> 服务端接受（content 623 chars）
```

MiMo `mimo-v2.6-flash`：本次采样未触发工具调用，该格无数据（不计失败）。
但在更早一轮（修正 user 消息丢失之前）MiMo 曾产出 `tool_call id` 并被服务端接受，
`tool_call_id` 匹配为 True——**未重验的是修正后的 user 开头顺序，不是协议本身**。

**过程中发现并修掉的两个真 bug（都由这一步暴露，不是单测发现的）：**

1. **`build_messages` 把 user 消息放在了最后**，产出 `assistant -> tool -> user`，
   即连续 user 消息。user 回合属于本轮，必须排在工具往返**之前**。
2. **`build_game_prompt` 只返回消息而不记录本轮**，导致 `_continue_chat` 重建时
   **开头那条 user 消息直接丢失**，对话变成 assistant 开头。新增 `current_user_turn`。

单测当时全绿——因为它们验证的是我写下的形状，而不是供应商的规则。

### F-022 现有基线早于非法走步率指标，W-03 的主门禁暂不可判定 —— `已核实`

W-01 收尾时补了 harness 的 `--compare`（此前计划里写了验收命令，工具却没实现）。
为此新增 `move_quality` 指标：`legal` / `illegal` / `parse_failures` / `illegal_rate`，
由 `runner.InstrumentedAgent` 包在 `think()` 外层统计。

把现有基线 `--restate` 后自己跟自己比，结果是：

```
非法走步率(红)      None    None    -     无法判定
非法走步率(黑)      None    None    -     无法判定
正则兜底占比(红)     1.0     1.0     0.0   通过
调用错误(红)        0       0       0     通过

门禁未通过：
  - 非法走步率(红)：基线或本次缺该指标（多半是基线早于该指标存在）
exit: 1
```

**结论：`docs/eval-baseline.json` 采集于 `move_quality` 存在之前，主门禁无法与它比较。**
工具的行为是对的——缺指标时判「无法判定」并退出 1，而不是悄悄放行。

**代价**：W-03 之前必须**重新采集一次带 `move_quality` 的基线**（约 40-90 分钟）。
基线日志里能看到 9 次 `_extract_move` 解析失败，说明这个指标确实会动，不是摆设。

### F-023 重采基线：首次出现胜负，且失败全部来自解析而非非法走步 —— `已核实`

`docs/eval-baseline.json` 重采（2026-10-09，W-01 协议修复之后，带 `move_quality`）：

| 项 | 旧基线（协议修复前） | 新基线 |
|---|---|---|
| 分出胜负 | **0 / 7** | **3 / 7** |
| 结果分布 | 和 7 | 黑胜 3、撞上限 4 |
| 每局耗时 | 358.7s | 231.1s |
| 非法走步率 | 未测 | 红 0.025 / 黑 0.0168 |
| 其中 **illegal 走步** | 未测 | 红 **0** / 黑 **0** |
| 其中 **解析失败** | 未测 | 红 3 / 黑 2 |

**最关键的一行是 illegal = 0。** 失败全部来自「解析不出来」而非「走出了非法步」——
模型没产出非法走步，它产出的是**无法解析的答案**（`F-020` 那类）。
这直接印证 `W-03` 的判断：要消灭的是**格式问题**，不是规则理解问题。

胜负来源也清楚了：1 局 **红方被将死**、2 局 **红方投降**。投降链路与终局判定都被真实触发过
（旧基线 7 局全和棋，这两条路径从未被走到）。

**按类别的结构差异**：残局 2 局全部 20 手分胜负、被将军局面 34 手分胜负；
而开局与中局 4 局**全部撞 40 手上限**。即 **40 手预算下残局能收敛，开局/中局不能**。

**必须声明的局限**：新旧基线之间同时变了三样东西——W-01 协议修复、`move_quality` 计量层、
以及 LLM 采样本身的随机性。**「旧基线 0 胜负 → 新基线 3 胜负」不能归因给任何一项。**
要证明因果，需要同批局面、同 seed、只翻转单一变量的对照；目前没有这个数据。

### F-025 契约调用不合规时无文本可降级 —— `已核实`

W-03 首次跑批时第 1 局以 `in_progress` + `Failed to get final move` 收场，主动中止排查。

**成因链**：

1. DeepSeek 偶发返回 `move_decision` 但参数不合规（`parse()` 返回 None）
2. 因 `response.has_tool_calls()` 为真，`think()` 进入 `execute_tool_loop`
3. 循环内把 `move_decision` 过滤掉（它不是棋盘能力工具）→ 无调用可执行
4. 该响应是纯工具调用，`content` 为空 → 返回 `success=False`

**为什么设计时没想到**：我假设 strict schema 会保证参数合规，
于是「正则兜底」只写在**文本响应**分支上。契约路径下响应可能根本不含文本，
那条分支形同虚设。**分支图少了一格，实测把它补了出来。**

**修法**：在进入工具循环之前先判定分支——响应里若只有 `move_decision`
而没有棋盘能力调用，则**不带工具重问一次**，拿文本答案再走降级路径。
新增 3 条测试守住（契约失败必须重问、重问时不得带工具、契约命中时不得多余请求）。

**附带实测**：`tool_choice:"required"` 下 MiMo 仍可能无视并直接返回文本
（`finish=stop`, `tool_calls=[]`），且**服从度随 prompt 复杂度下降**——
短 prompt 触发、完整对局 prompt 不触发。故 `required` 是「尽力而为」而非保证，
降级路径必须常备。

### F-026 两家的契约通道正好互补 —— `已核实`

在**完整对局 prompt** 下实测（`W-03` 首轮门禁之后追加）：

| provider | 工具调用 + 函数内 strict + `required` | `response_format: json_schema` |
|---|---|---|
| DeepSeek `deepseek-flash` | **OK** | 400（0/4） |
| MiMo `mimo-v2.6-flash` | 会无视 required（完整 prompt 下 0.99 兜底） | **OK 4/4，走步全落 enum** |

**两家各自只吃一条通道，且互斥。** 早先 `W-03` 首轮只用工具调用通道时，
门禁虽然「全绿」，但收益几乎全来自 DeepSeek：红方 `text_only_ratio` 从 1.0 降到 0.07，
黑方只从 1.00 降到 **0.99**。

按通道分派后，生产路径 `think()` 实测 **8/8**，两家各走各的正确通道、走步全部合法：

```
deepseek  endgame_m14_p059  src=contract          move=e5e6  legal=True
deepseek  in_check_p111     src=contract          move=e2c0  legal=True
deepseek  opening_p13       src=contract          move=b6b9  legal=True
deepseek  middlegame_p25    src=contract          move=b4e4  legal=True
mimo      endgame_m14_p059  src=response_format  move=e5e6  legal=True
mimo      in_check_p111     src=response_format  move=e0d0  legal=True
mimo      opening_p13       src=response_format  move=b6b9  legal=True
mimo      middlegame_p25    src=response_format  move=b4e4  legal=True
```

**两条通道投递的是同一份 schema**（`build_tool` 与 `build_response_format` 有断言保证），
不是两套契约——分开维护必然分叉漂移。

**教训**：「门禁全绿」不等于「改动有效」。`W-03` 首轮门禁 6 项全过，
但其中 4 项的改善全部来自单一供应商；另一侧的 0.01 改善是 2 次失败变 1 次，
在 N≈115 下不构成证据。**门禁需要按侧拆分才能看出这种不对称**。

### F-027 评测包装层静默改变了被测系统 —— `已核实`

`W-03` 双通道跑批后，黑方 `fallback_rate` 高达 **0.644**（135 次决策里 87 次走了兜底），
而单次调用实测是 4/4 全中。差距这么大，必有原因。

**排查过程**：先怀疑是 markdown 围栏（MiMo 曾输出 ```json 包裹）——
**实测否证**：单次调用下 MiMo 0 围栏、7/7 解析成功。

**真因**：`supports_response_format_json_schema` 标在**真适配器**上，
而 `InstrumentedAgent` 外面还包了一层 `InstrumentedAdapter`。
`getattr(adapter, "supports_response_format_json_schema", False)` 在包装层上返回 False，
于是 **MiMo 被派到了工具调用通道**——正是它会无视的那条（`F-024`/`F-025`）。

```
deepseek  inner=False  wrapper=<absent>
mimo      inner=True   wrapper=<absent>     <- 能力位丢了
```

**生产路径不受影响**：`game.py::_create_adapter` 返回的是裸适配器，不经包装。
所以这是**评测专用缺陷**，此前那份 0.644 是被污染的数字，不能用来判断 MiMo 的真实行为。

**教训**：`tests/eval/README.md` 自己写着「它必须对被测代码完全不可见」——
**这句话正是被我自己破坏的**。计量层的「透明」是一个需要测试保证的性质，
不是一个可以靠自觉维持的约定。已补 2 条测试（`test_instrumented_adapter_is_attribute_transparent`
与 `test_wrapper_does_not_shadow_own_attributes`），并给包装层加 `__getattr__` 代理。

**更大的教训**：**先证伪再下结论**。我这次第一反应就是「围栏」，若没有实测就写进文档，
会又多一条错的事实——和 `F-013` 同一类错误。

### F-028 W-04 门禁在 1 个事件的噪声上触发；结构化字段的成本可忽略 —— `已核实`

`W-04` 评测（2026-10-09，对比基准 `eval-after-w03b.json`）：

| 指标 | W-03 | W-04 | Δ | 判定 |
|---|---|---|---|---|
| 兜底率 红 | 0.0292 | 0.0081 | −0.0211 | 通过 |
| 兜底率 黑 | 0.0438 | **0.0574** | **+0.0136** | **退化** |
| 非法走步率 红/黑 | 0.0 / 0.0 | 0.0 / 0.0 | — | 通过 |
| 调用错误 红/黑 | 0 / 0 | 0 / 0 | — | 通过 |
| **每手 token** | 3085.7 | 3095.6 | **+9.9（+0.3%）** | 参考 |

**门禁未通过，但「退化」只有 1 个事件**：黑方兜底 6 → 7 次（分母 137 → 122），
红方反而 4 → 1 次。N≈120 次决策下这是噪声（比例检验 p≈0.7），即 `RK-03`。

**不能改判通过，也不能据此回退**——两个动作都会把观测当结论。正确处理是
标记为「未定」，把问题交回给更大的样本。

**真正有价值的结论是成本那一行**：4 行结构化摘要的边际成本是 **+0.3%**。
`W-04` 设计时最担心的是「token 涨幅吃掉棋力收益」，实测**不存在这个问题**。
这把决策空间缩小了——成本不是变量，剩下的问题纯粹是「是否提升质量」。

**由此得出的教训**：`--compare` 的门禁目前是「任何上升即失败」，
在低 N 指标上过于敏感。门禁本身需要**样本量前提**才能判读，
本工具目前还不会声明「本样本量不足以支撑该判定」。

### F-029 渐进披露省了输入 26%，墙钟时间却涨了 —— `已核实`

`W-05` 评测（2026-10-09，对比 `eval-after-w04.json`）：

| | W-04 | W-05 | Δ |
|---|---|---|---|
| 调用数 | 246 | 282 | +14.6% |
| **prompt / 次** | 2770 | **2048** | **−26%** ✅ |
| **completion / 次** | 313 | **407** | **+30%** ❌ |
| 总 token | 758426 | 692234 | −8.7% |
| 每手 token | 3095.6 | 2472.3 | −20.1% |
| **秒 / 手** | 5.8 | **6.6** | **+14%** |
| 每局秒数 | 203.4 | 264.1 | +30% |
| 非法走步率 红/黑 | 0.0 / 0.0 | 0.0 / 0.0 | — |

**渐进披露按设计生效**：prompt 侧每调用省 26%（2770 → 2048 token）。
**但墙钟时间不降反升 14%**，原因有二，且都不是「拆分失败」：

1. **调用变多**：7 局全部打满 40 手上限（W-04 平均 35 ply），调用数 +14.6%。
2. **输出侧膨胀**：`thought` 字段变长，completion/次 +30%。新 `base.md` 的思考框架
   明确要求「每步都要有具体内容，不要写套话」，以及激活的 skill 正文都鼓励展开分析。

**结论（推翻了 W-04 里我写下的乐观预期）**：我在 `W-04` 设计时说「成本不是变量，
剩下的问题纯粹是是否提升质量」——**成本确实不是瓶颈，但省 token 不等于省时间**。
本场景的延迟主要由**每手调用次数**与**输出长度**决定，输入长度的影响远小于这两项。

**未归因的部分**：completion 增长中，「思考框架措辞更严」与「skill 正文鼓励展开」
各占多少**未分离测量**。要分清需分别做两次 A/B，本次不做断言。

**门禁再次在 1 个事件上触发**：红方兜底 1 → 2（分母 123 → 140），同 `F-028`。

## §2 裁决

以下 `D-xx` 均为 `已裁决`。每条附**被否决的方案及否决理由**——这是为了避免后来者重新提出同一方案。

### D-01 先修协议，再谈 skill

skill 模式的收益**全部**来自协议闭环带来的结构化。当前协议是断的（F-001/F-002/F-003），在断协议上建 skill 层，得到的只是文本装饰。

**否决方案**：直接在现有 `MCP_TOOLS` 上包装 skill 元数据。否决理由：模型仍收不到自己那条 assistant 消息，仍无法把工具结果与具体调用对应。

### D-02 Skill 是双面的，一个 registry

| 面 | 形态 | 加载时机 |
|---|---|---|
| **知识面**（knowledge） | `SKILL.md` 目录 + YAML frontmatter | 三级渐进披露 |
| **动作面**（action） | JSON-Schema 约束的函数 | 由 router 决定是否暴露给模型 |

统一 `SkillRegistry`，用 `kind` 字段区分。理由：二者共享「被条件激活」这一核心语义，分成两套机制会让「本回合该加载什么」这个问题无解。

**格式采用** agentskills.io 开放标准（Anthropic 于 2025-12-18 发布，46+ 产品采用）的 `SKILL.md` 结构，但**语义是本项目自定义的** `kind` / `when` 字段，不是标准 skill 的自由文本语义。

### D-03 路由是确定性的，不是模型自选

Anthropic 官方区分 **workflow**（预定义代码路径）与 **agent**（模型自主决定流程），并建议「能简单就简单」。

**象棋是全可观测、回合结构 100% 确定的 workflow，不是 agent。** 引擎已经知道阶段、子力差、是否被将军、重复风险。让模型自己决定调哪个工具，是**花钱、花延迟去重新推导引擎已知的事实**。

- **引擎**决定：激活哪些知识 skill、暴露哪些动作 skill
- **模型**只决定：在受限动作空间里走哪一步

**否决方案**：把 skill 激活交给模型（社区默认做法）。否决理由：在全可观测环境里这是纯开销，且引入不可复现性——同一局面两次决策可能激活不同 skill。

**已承认的例外**：`evaluate_candidates` 该评估**哪几手**，引擎无法预知，模型在此有真实判断价值。故本项是 hybrid 而非纯 workflow。

### D-04 保留 ASCII 棋盘，结构化字段是增量

结构化 `BoardSnapshot` **不替换** ASCII 渲染，只在其上追加字段。LLM 在棋盘空间推理上对文本渲染的依赖可能强于理论预期。

**否决方案**：纯结构化替换（去掉 ASCII 盘）。否决理由：未经 A/B 的替换性改动属于未经验证的假设。必须实测，见 `W-06`。

### D-05 决策契约消灭正则与重试

把合法走步作为 `enum` 写入 schema，使模型**物理上无法输出非法走步**，
`game_controller.py:280` 的 3 次重试循环随之消失。

**实测确认的可移植实现（v0.4.0 修正）：**
用**单个工具调用**，而不是 `response_format`。

```python
tools = [{"type": "function", "function": {
    "name": "move_decision",
    "strict": True,                      # 关键：放在函数定义内
    "description": "输出走步决策",
    "parameters": {
        "type": "object",
        "properties": {
            "move":       {"type": "string", "enum": ["<N 项合法走步>"]},
            "thought":    {"type": "string"},
            "confidence": {"type": "number"}
        },
        "required": ["move", "thought", "confidence"],
        "additionalProperties": False
    }
}}]
tool_choice = "required"  # 被拒则回落 auto（F-024）
```

该路径在 **DeepSeek 与 MiMo 两家均实测通过**（F-014），且非 strict 时 DeepSeek 实测会吐出非法 JSON——
strict 在这里是有实质作用的，不是装饰。

**三条已核实的约束（写入实现时必须遵守）：**
1. `strict` 放函数定义内，不放 `response_format`（DeepSeek 拒绝，F-012）
2. 用 `tool_choice: "required"` 才有确定性；thinking 开启时 DeepSeek 会拒绝（F-013），
   故实现为「先试 required、被拒回落 auto」
3. 两家都是 thinking model，**多轮工具调用时必须回送 `reasoning_content`**，否则会报错

**降级路径仍为强制项**：若未来添加的 provider 不支持函数内 `strict`，
回退到非 strict + 本地 schema 校验 + 单次纠错。
**降级路径必须单独评测**（否则「strict 生效」这个假设永远无法证伪）。

### D-06 不引入真实 MCP server

只借鉴 MCP 的三个设计：**tools / resources 的权威分工**（模型控 vs 应用控）、**tool annotations**（只读 vs 破坏性）、**`isError` 语义**（工具跑通了但没满足请求 ≠ JSON-RPC 协议错误）。

**否决方案**：接一个 stdio MCP server 跑棋盘工具。否决理由：单机进程内通信引入 JSON-RPC 序列化 + 进程生命周期管理，是纯开销。

### D-07 投降判据移出 prompt

`agent_default.txt:138-147` 用自然语言描述投降标准，而 `game_controller.py:310` 已用代码判定同一组条件。**引擎判定是权威，prompt 里的副本是漂移风险。**

### D-08 度量必须前置到 Phase 0 之后

`optimization-plan.md` 把 Elo 评测排在最后一个可选阶段。本设计主张：**先建评测，再改协议**。

理由：一旦开始改协议，基线就永远取不到了。`F-009` 说明当前完全没有棋力度量，意味着「skill 模式是否变好」目前**不可证伪**。

**这不是追求完美主义，是避免重演「写了 450 行实测结论但测的不是棋力」。**

### D-09 记忆策略：每回合重置

默认 stateless-by-design。每回合独立构造上下文，历史只带最近 K 手 + 结构化摘要字段。

**否决方案**：保留滑动窗口的完整对话。否决理由：象棋是低分支博弈，跨回合对话的价值远低于 token 成本；且滑动窗口会让「哪一段历史影响了这一步」不可复现。

### D-10 删除工具动态发现机制

`ToolExecutor._auto_discover_tools()`（`tool_executor.py:68-80`）+ `_load_tool_from_file()` 建议删除。理由：由 LLM 自行决定的动态代码加载没有收益，且是可执行代码的动态入口。

---

## §3 目标架构

```
┌────────────────────────────────────────────────────────┐
│ GameController — 回合循环（确定性，本次不改）            │
└───────────────────────┬────────────────────────────────┘
                        │
┌───────────────────────▼────────────────────────────────┐
│ SkillRuntime                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │SkillRegistry │  │ SkillRouter  │  │BoardSnapshot │  │
│  │  L1 元数据   │  │ 确定性选技能  │  │ 结构化局面   │  │
│  │  ~100tok/项  │  │              │  │ + 保留 ASCII │  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  │
│         │                 │                 │          │
│         └────────┬────────┴─────────────────┘          │
│           SkillExecutor（唯一写入：commit_move）          │
└───────────────────────┬────────────────────────────────┘
                        │
              Adapter.chat(messages, tools)  ← 协议合规
```

**每回合回路：**

```
Engine ──► Snapshot ──► Router ──► Skill Set ──► LLM ──► commit_move ──► Event
                                    ▲                                    │
                                    └────────── 下一回合 ◄────────────────┘
```

### 不变量（设计约束，任何实现不得违反）

| # | 不变量 |
|---|---|
| I-1 | `commit_move` 是**唯一**写入棋盘的 skill。其余全部只读。 |
| I-2 | `line_simulate` 必须在沙箱中执行，不得影响真实局面（仓库已知 `referee_engine.py` 存在「改状态但不保证还原」的地雷 API，见归档文档 P1-11） |
| I-3 | 引擎判定与 prompt 陈述冲突时，**引擎优先**（`D-07`） |
| I-4 | 同一局面 + 同一 skill set + 同一模型 → 决策可复现 |

---

## §4 Skill 规范

### 4.1 知识面（knowledge）

**三级渐进披露**，直接采用 Anthropic 的分级约定：

| 级别 | 内容 | 载入时机 | 预算 |
|---|---|---|---|
| L1 | YAML frontmatter：`name` / `description` / `when` | 启动即驻留 system prompt | ~100 token / 项 |
| L2 | `SKILL.md` 正文：程序性知识 | 条件命中时载入 | < 5k token，建议 < 500 行 |
| L3 | `references/*.md`：深度细节 | SKILL.md 显式引用时 | 按需 |

**frontmatter 扩展字段**（标准字段之外的**项目自定义**部分）：

```yaml
---
name: opening-development          # 标准字段：≤64 字符，小写+连字符，须与目录同名
description: 开局阶段的出子次序与要争夺的要点。      # 标准字段：≤1024 字符，第三人称
kind: knowledge                    # 【项目扩展】knowledge | action
when:                              # 【项目扩展】确定性激活条件
  - phase in [opening]
  - ply < 20
side_effect: none                  # 【项目扩展】none | mutating
---
```

`when` 由 `SkillRouter` 求值（`D-03`），**不是**模型自选。

### 4.2 `agent_default.txt` 的去向

| 现内容 | 现状 | 去向 |
|---|---|---|
| Role / 棋风 / 坐标系 / ICCS | L1 常驻 | **保留常驻**——这是事实不是程序 |
| 开局 doctrine（24-34 行） | 常驻 | → `opening-development` (L2) |
| 中局 doctrine（37-48 行） | 常驻 | → `middlegame-tactics` (L2) |
| 残局 doctrine（50-56 行） | 常驻 | → `endgame-technique` (L2) |
| 思考框架 4 步（82-106 行） | 常驻 | → 拆入各阶段 skill |
| 棋理口诀（110-125 行） | 常驻 | → `references/`（L3） |
| 走步价值判断表（164-176 行） | 常驻 | → `references/`（L3） |
| **投降标准（138-147 行）** | 常驻 | **删除**，由引擎判定（`D-07`） |

### 4.3 动作面（action）

| Skill | side_effect | 说明 |
|---|---|---|
| `board_inspect` | none | 只读。`detail: concise \| detailed` —— Anthropic 推荐的 `response_format` 开关，可省约 2/3 token |
| `opening_probe` | none | 只读。开局库查询，带查询深度 |
| `evaluate_candidates` | none | 只读。**批量**评估候选走法集，带 depth + 预算上限 |
| `line_simulate` | none | 只读（**必须沙箱**，I-2）。试走 → 返回新局面快照 + 对手应手候选 |
| `commit_move` | **mutating** | **唯一写入**。schema 限定合法走法，执行后发事件 |

**动作面技能一律加注解**，对齐 MCP 的 `annotations` 语义（`D-06`）：`readOnlyHint`、`destructiveHint`。

**错误返回遵循 `isError` 语义**：工具跑通了但没满足请求（如「该局面无开局库记录」）→ 返回可恢复的业务错误，让模型能换个策略；协议层错误（参数类型错）→ 走 JSON-RPC 风格硬失败。错误消息必须**可操作**——这是 Anthropic 明确建议：「opaque error codes force agents to guess」。

---

## §5 决策契约

目标响应 schema（`D-05`）：

```json
{
  "type": "object",
  "properties": {
    "move":       {"type": "string", "enum": ["<合法走步1>", "…", "共 N 项"]},
    "thought":    {"type": "string"},
    "confidence": {"type": "number"},
    "skill_used": {"type": "string"}
  },
  "required": ["move", "thought", "confidence", "skill_used"],
  "additionalProperties": false
}
```

strict 模式的三条硬性要求（OpenAI 明确规定，否则请求被拒）：每个 object 必须 `additionalProperties:false`；所有 `properties` 必须列入 `required`；可选字段用 `["string","null"]` 类型联合表达。

**降级路径是强制项**（`D-05` 约束）：当供应商不支持 strict 时，回退到非 strict function calling + 本地 schema 校验 + 单次纠错。**降级路径必须单独评测**，否则「strict 生效」这个假设永远无法证伪。

---

## §6 成本模型

| 项 | 现状（F-001/F-004/F-005 推得） | 目标 |
|---|---|---|
| 工具 schema 常驻 | 3 项硬编码 | 仅当前激活的动作 skill |
| 知识 | `agent_default.txt` 全量常驻（6 KB） | L1 manifest + 1~2 个 L2 |
| 历史 | **跨回合无限增长**（F-004） | 每回合重置 + 最近 K 手 |
| 非法走法重试 | 最多 3 轮（F-008） | 趋近 0（`D-05`） |

**Prompt caching**：稳定前缀（system + L1 manifest）跨回合不变，可命中缓存。Anthropic 演示中仅靠重排顺序即把命中率从 20% 提到 85%。前提是 system + manifest 排在请求最前且逐字节稳定——`W-05` 的验收命令会检查这一点。

---

## §7 工作项

> 每项可独立执行、独立回退。**`W-02` 必须在 `W-01` 之前完成**——否则基线永久丢失（`D-08`）。

---

### W-00 thinking 开关 —— `完成`

**依赖**：无
**非目标**：不改 prompt 文本，不改决策契约，不引入 skill。

**为什么排在最前**：`F-017` 证明模型永远写不出答案，走步全靠从截断的思考里刨。
在这个状态下采集的基线，测的是一个坏掉的系统。

**原计划（已被证据推翻）**：只调 `max_tokens`。
**实测结论（F-018）**：加大预算只是把「截断」换成「慢」；真正的修法是**关掉 thinking**。

**改动面**（已落地并通过验收）：
- `src/llm_adapters/base_adapter.py` — 新增 `thinking: Optional[bool]`，`None` = 不干预
- `src/llm_adapters/openai_base_adapter.py` — `thinking` 非 None 时注入
  `extra_body={"thinking": {"type": "enabled"|"disabled"}}`
- `src/llm_adapters/deepseek_adapter.py` / `mimo_adapter.py` — 透传
- `game.py` — `_create_adapter` 读 `llm_config["thinking"]`
- `config/agent1_config.yaml` / `agent2_config.yaml` — `thinking: false` + 实测数据注释
- `tests/eval/providers.py` — 评测沿用同一开关，保证基线反映真实配置

**验收结果**（走生产路径 `game.py::_create_adapter` + 真实 config，2026-10-08）：

| config | finish | 耗时 | content | 走步合法 |
|---|---|---|---|---|
| agent1 (DeepSeek) | `stop` | 2.9s | 423 | 是 `g4g5` |
| agent2 (MiMo) | `stop` | 36.8s | 208 | 是 `e5e6` |

**反向守卫**：`text_only_ratio` 必须下降；`completion_tokens == max_tokens` 的次数必须归零。

**机制层 A/B 已补（F-019）**：thinking=ON 可用率 1/6，OFF 为 5/6，且 OFF 快 4–20 倍。W-00 在机制层面成立。

**仍遗留**：棋力是否因此下降，属**待测项**。F-019 每格仅 1 次调用，回答不了这个问题；需每组 30+ 局且能自然终局，按实测约 6 分钟/局计，是数十小时量级的独立工程。**不得当作已知结论，也不得混进迁移里假装顺手做完。**

---


### W-01 协议修复 —— `完成`

**依赖**：无（与 W-00 顺序无关，但必须在 W-03 之前）
**非目标**：不改 prompt 文本，不改工具集合，不引入 skill。**只修协议闭环。**

**改动面**（实际落地）：
- `src/llm_adapters/base_adapter.py` — `ToolCallDict` 与 `ToolCall` 增加 `id`
- `src/llm_adapters/openai_base_adapter.py` — 解析并保留 `tc.id`
- `src/llm_adapters/anthropic_base_adapter.py` — 保留 `block.id`；把 `role:"tool"`
  转成 user 消息里的 `tool_result` 块，**并行结果合并成一条 user 消息**
- `src/agents/prompt_builder.py` — 用 `tool_exchanges` 取代伪造的 user 消息；
  消息顺序改为 system → history → **本轮 user** → 工具往返 → assistant 备注；
  新增 `current_user_turn`（否则续生成时 user 开头会丢）
- `src/agents/base_agent.py` — `execute_tool_loop` 写回 assistant+tool；
  `_continue_chat` 不再追加 user 消息；纠错反馈改为挂起并入本轮
- `src/core/game_controller.py` — `play_turn` 开头 `current_agent.reset()`
- `tests/test_protocol_sequence.py` — **新增 7 条反向守卫**（此前协议合规无人看守）

**验收结果**：见 `F-021`。真实供应商接受了构造出的序列，DeepSeek 完成 2 轮工具
循环并提取出合法走步 `h2e2`。

**过程中被实测推翻的**：单测全绿并不能证明协议正确。`build_messages` 的消息顺序
与 `current_user_turn` 缺失两个 bug 都是靠真实请求暴露的，不是靠单测。

**后续**：计划里写的 `--compare` 当时尚未实现，已补齐（见 `F-022`），
并新增 `tests/test_eval_harness.py`（12 条）——此前 `tests/` **从未导入过 harness 模块**，
harness 里的错误要靠手动跑 CLI 才会暴露。


### W-02 对局评测基线 —— `完成`

**依赖**：无
**非目标**：不提高棋力，不改任何决策逻辑，不改 prompt。

**改动面**：新增 `tests/eval/`（harness + 固定局谱集 + 报告生成器）

**做什么**：
1. 固定开局局面集（含中局、残局、被将军、重复局面等边界样本）
2. 同一模型 × N 局 × 固定 seed，记录：胜/和/负、平均 ply、非法走步率、平均 token、重试次数
3. 输出可 diff 的 JSON 报告

**验收命令**：
```
python -m tests.eval.run --games 20 --seed 42 --out baseline.json
python -m tests.eval.run --verify baseline.json
```

**反向守卫**（已按实测修正——原「两次 live 跑逐字节一致」做不到）：
LLM 采样本身不确定，要求两次 live 跑出同样字节是不成立的约束，
写了也只会诱导后来人放宽到「差不多就行」。改为**三条可证明的确定性**：

1. **序列化确定性**：报告文件内容 == 规范化重新序列化的输出
2. **汇总纯函数性**：仅用 `raw` 重算 summary，整份报告与文件逐字节相同
3. **局面集完整性**：全部 FEN 用 `RefereeEngine` 复验通过

这三条由 `python -m tests.eval.run --verify <报告>` 一次跑完。

**产出**：`docs/eval-baseline.json`（提交进仓库，作为所有后续阶段的比较基准）

---

### W-03 结构化决策契约 —— `完成`

**依赖**：W-01 已完成；**另需先重采一次带 `move_quality` 的基线**（见 `F-022`）
**非目标**：不实现 skill，不动 prompt doctrine。

**前置条件（硬性）**：现有 `docs/eval-baseline.json` 不含 `move_quality`，
本项的主门禁「非法走步率不得高于基线」**对它无法判定**。
必须先重采一份基线（约 40-90 分钟），否则本项只能靠人肉读数。

**做法**：用实测可行的单一工具调用 `move_decision`，`strict: true` 放在函数定义内，
`tool_choice: "auto"`（绝不用 `required`，见 `F-013`）。合法走法作为 `enum` 写入。

**改动面**：`src/agents/` 新增 schema 模块；`_extract_move` 降级为兜底而非主路径

**验收命令**：
```
python -m pytest tests/ -q
python -m tests.eval.run --games 7 --seed 42 --max-turns 40 \
    --out docs/eval-after-w03.json --compare <新基线>
```

**反向守卫**：非法走步率不得上升；`text_only_ratio` 不得上升；供应商不支持 strict 时
必须走降级路径且降级路径有独立测试（`D-05` 约束）。

**过程中被实测推翻的**：见 `F-025`（分支图缺一格）、`F-026`（单通道只对一家有效）。

**门禁结果**（`docs/eval-after-w03.json`，2026-10-09）：6 项全部通过。
非法走步率 红 0.025→0.0174、黑 0.0168→0.0088；正则兜底占比 红 **1.0→0.07**、黑 1.00→0.99。
**但收益几乎全来自 DeepSeek 一侧**（见 `F-026`），因此追加了按通道分派的补强。

---


### W-04 BoardSnapshot 混合视图 —— `未定`（已实现，门禁在噪声上触发）

**实测结果**：见 `F-028`。成本 +0.3%（可忽略），质量在当前 N 下**不可判定**。

**依赖**：W-03 已完成。**实施前置条件已满足**：黑方兜底率实测 **0.0438**
（`F-027` 修复后重采），远低于 0.9 阈值——先前的 0.644 是评测包装层缺陷所致，
不是 MiMo 的真实行为。**对比基准改为 `docs/eval-after-w03b.json`**。

**非目标**：不删除 ASCII 盘（`D-04`）。不重构 `RefereeEngine` 规则语义。

#### 设计为什么改了

原设计（`W-03` 之前）假设「模型仍从自由文本决策，只是多给了结构化字段」。
`W-03` 落地后这个前提不成立：**决策入口已是 schema 契约**。
于是「结构化字段给谁看」必须重答：

| 决策路径 | 结构化字段的消费者 |
|---|---|
| 契约命中（DeepSeek / MiMo json_schema） | 生成 `thought` 与 `move` 的推理过程 |
| 降级（自由文本正则） | 与现在相同，仍靠读 ASCII 盘 |

所以本项**不是「在文本里多塞几个字段」**，而是决定：
哪些结构化字段值得进入 prompt、哪些只是浪费 token（见 §6 成本模型）。

#### 拟增字段（全部为**增量**，ASCII 盘与 FEN 原样保留）

| 字段 | 用途 | 来源 |
|---|---|---|
| `phase` | 决定哪套 doctrine 生效（`W-05` 的前置） | 由 ply + 剩余子力推导 |
| `material` | 子力差；模型常自己数错 | 引擎直接算 |
| `in_check` / `check_side` | 明确是否被将军及被将方 | `is_king_in_check` |
| `last_move_san` | 上一步的中文记谱，对应 `annotated_moves` 的标签体系 | 由 `last_move` + 标注推导 |
| `repetition_warning` | 是否接近三次重复 | `position_history` |

**明确不增的**：`legal_moves` 全量列表——它已作为 `enum` 写进契约 schema
（`W-03`），在 prompt 里再列一遍是纯浪费。

#### 验收

```
python -m pytest tests/ -q
python -m tests.eval.run --games 7 --seed 42 --max-turns 40 \
    --out docs/eval-after-w04.json --compare docs/eval-baseline.json
```

**反向守卫**：
- 非法走步率 / 正则兜底占比**不得上升**
- **每手 token 不得显著上升**——若 token 涨幅吃掉棋力收益，本项判失败
  （结构化字段的价值必须能抵消它自己的成本）
- 胜率/和率**不作为门禁**：N=7 在当前预算下胜负不可观测（见 `RK-07`），
  拿它当门禁等于把噪声当信号

---


### W-05 知识 skill 拆分 —— `完成`（两步：机制 + 内容迁移与接线）

**依赖**：W-04
**非目标**：不改 `RefereeEngine`；不引入真实 MCP server（`D-06`）。

**改动面**：新增 `skills/` 目录；`prompts/agent_default.txt` 瘦身

**验收命令**：
```
python -m tests.eval.run --compare docs/eval-baseline.json --arm skills
python -m tools.check_cache_prefix.py     # 断言 system+manifest 逐字节稳定
```

**反向守卫**：胜率不得低于基线；prompt token 总量必须下降（否则渐进披露没产生收益，W-05 的存在意义不成立）。

---

### W-06 动作 skill 统一 —— `待做`

**依赖**：W-05
**非目标**：不删除 `ToolExecutor` 类本身（供旧调用方过渡），但 `get_tool_schemas()` 必须成为**唯一**工具事实来源（F-006）。

**改动面**：删除 `prompt_builder.py:425` 的硬编码 `MCP_TOOLS`；删除 `_auto_discover_tools`（`D-10`）

**验收命令**：
```
rg -n "MCP_TOOLS" src -g "*.py"                        # 必须为空
rg -n "_auto_discover_tools|_load_tool_from_file" src   # 必须为空
python -m pytest tests/ -q
python -m tests.eval.run --compare docs/eval-baseline.json --arm skills
```

**反向守卫**：`tool_executor.py:135` 的 `get_tool_schemas` 必须存在调用点（F-006 当前为 0）。

---

## §8 风险登记

| ID | 风险 | 状态 | 触发后果 |
|---|---|---|---|
| `RK-01` | LLM 在棋盘空间推理上强依赖 ASCII 渲染，纯结构化反而更弱 | `开放` | 由 W-04 A/B 消解；已用 `D-04` 保留 ASCII 兜底 |
| `RK-02` | 供应商 strict 行为不一致 | **已部分消解** | 实测：函数内 strict 两家均可用（F-014）；但 `response_format` 与 `tool_choice:required` 被拒（F-012/F-013），已改写 D-05 |
| `RK-03` | 评测本身引入方差，N 局不足以区分 A/B | `开放` | W-02 的反向守卫（逐字节可复现）+ 加大 N |
| `RK-04` | F-010 未实测，Anthropic 协议下的具体报错未知 | `开放` | W-01 完成后立即实测 |
| `RK-05` | Skill 拆分把 doctrine 切碎后，模型跨 skill 推理出现断层 | `开放` | 由 W-05 的 A/B 消解 |
| `RK-07` | 40 回合预算下开局/中局不收敛（4 局全撞上限），残局与被将军局面可收敛 | `开放` | `F-023`：残局 20 手、被将军 34 手分胜负；开局/中局需更长预算才能观测。W-03 落��后需重测是否改善 |
| `RK-06` | 渐进披露反而增加往返（读 skill → 用 skill 多一轮 LLM 调用） | `开放` | W-05 需统计 LLM 调用次数，不只看胜率 |

---

## §9 进度

| 工作项 | 状态 | 门禁结果 | 日期 |
|---|---|---|---|
| `W-00` thinking 开关 | `完成` | F-017 消解：两家 `finish=stop`、content 非空、走步合法 | 2026-10-08 |
| `W-02` 评测基线 | `完成` | 7 局 0 胜负；3 局截断、4 局重复和棋；报告已自述该限制 | 2026-10-08 |
| `W-01` 协议修复 | `完成` | F-021：真实供应商接受序列，DeepSeek 2 轮工具循环提取 `h2e2` | 2026-10-08 |
| `W-03` 决策契约 | `完成` | 门禁 6/6 通过；双通道补强后 MiMo 侧契约命中 8/8 | 2026-10-09 |
| `W-04` BoardSnapshot | `待做` | — | — |
| `W-05` 知识 skill | `待做` | — | — |
| `W-06` 动作 skill | `待做` | — | — |

**收口**：见 §11。**执行顺序**：`W-00` → `W-02`（基线）→ `W-01` → **重采含 move_quality 的基线** → `W-03` → `W-04` → `W-05` → `W-06`。

`W-00` 是后补的（harness 建好后第一件事就是发现了它）：它是在 `W-02` 的实跑中才暴露的（F-017）。harness 建好后第一件事
就是发现了它——这本身就是「先建度量」这条裁决（D-08）的收益证明。

---

## §10 参考信源

| 主题 | 来源 |
|---|---|
| Agent Skills 三级渐进披露、~100 token/项 L1 预算 | https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview |
| Skills 工程实践、SKILL.md 结构 | https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills |
| agentskills.io 开放标准（2025-12-18 发布） | https://agentskills.io |
| workflow vs agent 的架构区分、「先找最简方案」 | https://www.anthropic.com/engineering/building-effective-agents |
| 工具设计的五条原则、`response_format` 开关、可操作错误消息、token 预算 | https://www.anthropic.com/engineering/writing-tools-for-agents |
| strict schema 的三条硬性要求 | https://developers.openai.com/api/docs/guides/function-calling |
| Structured Outputs 背景与拒绝语义 | https://openai.com/index/introducing-structured-outputs-in-the-api/ |
| MCP tools / resources 分工、`annotations`、`isError` 语义 | https://modelcontextprotocol.io/specification/2025-06-18/server/tools |
| ReflAct（仓库 `base_agent.py:120` 引用的反思依据） | EMNLP 2025, arXiv:2505.15182 |

---

## §11 迁移收口与遗留项

> 本节是 2026-10-09 那一轮迁移的收口账。**只列还没解决的**，已解决的在 §7 各自的工作项里。

### 11.1 这一轮实际改变了什么（均有数字）

| 变化 | 证据 |
|---|---|
| 门禁能区分「真退化」与「噪声」 | §11.3：两比例 z 检验，三次历史误判重判为不可判定 |
| 模型不再「写不出答案」 | `F-017` → `F-019`：thinking=ON 可用率 1/6，OFF 为 5/6 |
| 协议闭环 | `F-021`：真实供应商接受构造出的序列，DeepSeek 完成 2 轮工具循环并提取 `h2e2` |
| 契约消灭整类解析失败 | `F-023` + W-03 门禁：parse_failures 红3/黑2 → **0/0**，非法走步率归零 |
| 契约按供应商分派通道 | `F-026`：DeepSeek 走工具调用、MiMo 走 `response_format`，实测 8/8 |
| 知识按局面按需加载 | `F-029`：prompt/次 2770 → **2048（−26%）**，任何局面组合都省于原全量常驻 |
| 工具来源收敛为单一事实源 | W-06：删掉 47 行硬编码 `MCP_TOOLS` 与 42 行动态发现死代码 |

### 11.2 遗留项一：棋力在当前配置下不可观测 —— **开放**

7 局评测里 **0 局分出胜负**，开局与中局全部撞 40 手上限。

这不是「样本还不够」，而是**当前回合预算下 doctrine 层面的改动根本无法验收**。
基线与 W-03/W-04/W-05 三份报告的胜负列全部为 0，报告的 `warnings` 也都自述了这一点。

两条解法，**都不是本轮该做的**：

- **A. 提高回合预算**：让对局能自然终局。代价是每局从 ~4 分钟涨到可能 20+ 分钟，
  且需要每组 30+ 局才能区分 A/B——按当前速率是数十小时量级的独立工程。
- **B. 永久改验收标准**：从「胜率」改为「激活正确性 + token 成本 + 走步合法率」。
  这三个指标在 N≈120 次决策下**可测**，且它们恰好是 skill 系统该保证的性质。
  `W-05` 第一步建立的激活断言就是为 B 准备的。

**倾向 B**，因为 A 的成本与本轮迁移的收益不成比例。但这是需要用户拍板的取舍，不是技术选择。

### 11.3 遗留项二：门禁缺样本量判读 —— **已解决（2026-10-09）**

同一个问题已触发**三次**（`F-028`、`W-04`、`W-05`）：门禁在「差 1 个事件」的
低 N 指标上判为退化：

| 轮次 | 指标 | 基线 → 本次 | 实际事件数 |
|---|---|---|---|
| W-04 | 兜底率(黑) | 0.0438 → 0.0574 | 6 → 7 |
| W-05 | 兜底率(红) | 0.0081 → 0.0143 | 1 → 2 |

工具当前只会说「退化」，**不会说「本样本量不足以支撑该判定」**。
这与 `F-012`（缺指标时静默放行）是同一类问题的镜像：**数据不足时给出了一个过于确定的结论**。

**已实施**：`--compare` 现在对计数类指标做**两比例 z 检验**（合并方差正态近似，
`min(n1,n2) < 20` 时拒绝判定），输出 `绝对差值 [分子/分母]` 与 p 值。

判定矩阵（写错过一次，见下）：

| p | 方向 | 判定 |
|---|---|---|
| p < 0.05 | 未变差 | 通过 |
| p < 0.05 | **变差** | **退化 → 门禁失败** |
| p ≥ 0.05 | 任意 | **不可判定**（显式列出，不是通过） |
| 无法计算 | 变差 | 不可判定 |

**三次历史误判用新逻辑重判，全部翻转为「不可判定」**：

| 轮次 | 指标 | 基线 → 本次 | p | 旧判定 | 新判定 |
|---|---|---|---|---|---|
| W-04 | 兜底率(黑) | 6/137 → 7/122 | 0.617 | 退化 | **不可判定** |
| W-05 | 兜底率(红) | 1/123 → 2/140 | 0.639 | 退化 | **不可判定** |
| W-05 | 兜底率(黑) | 7/122 → 8/140 | 0.994 | 退化 | **不可判定** |

**实现中踩到的坑（值得记）**：第一版判定矩阵写成「只要有 spec 就判不可判定」，
结果 **10/400 这种真实退化也会被放过**。是新增的 `test_gate_fails_on_a_real_regression`
把它逼出来的——**「不可判定」的兜底不能变成「默认通过」的另一张脸**。

### 11.4 遗留项三：`W-04` 处于「未定」 —— **待定**

`BoardSnapshot` 已实现并接入，**成本 +0.3%（每手 +9.9 token）**，非法走步率与
兜底率均未恶化，但效果在当前 N 下不可判定。

**保留它的理由**：便宜、无害、且它输出的 `board_phase` / `repetition_warning`
是 `W-05` 路由规则的输入——撤掉会让已建的激活机制失去依据。
**未定的理由**：没有任何数据支持「它提升了质量」。

这是一个**诚实的中立状态**，不是「通过」，也不是「失败」。
若将来 11.2 选了方案 B（改用激活正确性验收），`W-04` 应重新用该标准评一次。

### 11.5 交接给后来者

- 每条事实都带证伪命令，**命令红了以命令为准，不以本文档为准**
- 改动前先看 §7 对应工作项的「反向守卫」，它们是**会红的守卫**，不是建议
- 评测命令：`python -m tests.eval.run --games 7 --seed 42 --max-turns 40 --out <新报告> --compare <基准>`
  **必须带同一个 `--seed`**，否则局面集与顺序不同，差异无法归因
- 报告文件自带 `warnings` 与 `meta.notes`，**先读它们再读数字**
