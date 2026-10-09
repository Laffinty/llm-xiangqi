> # ⛔ 本文档已停用（ARCHIVED / DO NOT EXECUTE）
>
> **日期**: 2026-10-08。**状态**: 不再执行，仅作历史缺陷记录参考。
>
> ---
>
> ## 为什么停用（而不是删除）
>
> 本文档中的结论**大多数仍然成立**，停用的原因是**排序**，不是结论。
>
> 它把「Elo 评测」与「提示词 A/B 实验」排在「阶段 5：功能增强（可选）」的**最后一项**（本文档 L898-899）。
> 但我们即将重构 LLM ↔ 棋盘的交互模式——没有测量手段，就无法判断新方案到底有没有变好。
> 因此度量必须前置。裁决理由见 `docs/history/skill-mode-design.md` 裁决 `D-08`。
>
> ## 与新计划的关系
>
> | 本文档条目 | 处置 |
> |---|---|
> | P0（已修复，commit `7185695`） | 继续有效，不变 |
> | P1 / P2 / P3 缺陷 | **未作废**，仍有效；与 Skill 模式相关的已被独立重新核实并吸收 |
> | 「阶段 1-5」执行顺序 | **作废**，由新顺序 `W-02 → W-01 → W-03 → W-04 → W-05 → W-06` 取代 |
> | P2-4 / P2-5 / P2-1 | 已由 `PLAN-SKILL-001` 的 `F-004` / `F-001` / `F-005`、`F-006` 独立重新核实，并纳入 `W-01`、`W-06` |
> | P1-11（改状态但不保证还原的地雷 API） | 作为不变量 I-2 约束进入新设计 |
>
> ## 使用规则
>
> - **不得从本文档提取任务来执行。**
> - 需要继续追柠某条缺陷时，只把**结论**抄进 `docs/history/skill-mode-design.md` 的 `F-xx`（并附证伪命令），不要回来修改本文档。
> - 本文档中的 `[实测]` 标记测的是**代码正确性**，**不是棋力**。本文档从未提供任何对局质量的实测。
>
> ## 一处更正记录
>
> 本文档 P2-1 称配置「从未被读取」——**该表述不准确**。
> `ConfigLoader.load_mcp_tools_config()` 确实会解析 `game_config.yaml` 的 `mcp_tools` 段并写入 `GameConfig.mcp_tools`，
> 但没有任何消费者——即「被读取了，但解析结果从未被使用」。
> 以 `PLAN-SKILL-001` 的 `F-007` 为准。
>
> ---

# LLM-Xiangqi 代码审阅与优化方案

> 审阅日期：2026-09-27
> 审阅范围：全仓库（`src/` 2912 行可执行语句、`web_3d_client/`、`tests/` 1454 行）
> 基线提交：`4ae1878 字体`
> 方法：通读全部源码 + 实测复现 + 测试/覆盖率/性能基准

---

## 0. 体检结论（一句话）

**规则引擎（`referee_engine.py`）是这个项目最有价值的资产**——走法生成、飞将、蹩马腿、炮架判定都写得准确且有 89% 覆盖。**问题不在算法，在"接线"**：大量已写好的功能因为一两个字段名不一致、返回值缺键、模块导入顺序而**根本没被执行到**。README 里承诺的"完整规则引擎 / MCP 工具系统 / 3D 可视化"有相当一部分是**声明存在、实际失效**。

本次共确认 **43 项缺陷**，其中：

| 级别 | 数量 | 含义 | 状态 |
|---|---|---|---|
| **P0** | 5 | 阻断级：程序跑不起来，或核心功能从未生效 | ✅ **已全部修复**（`7185695`） |
| **P1** | 11 | 正确性：象棋规则判错、状态撕裂、胜负误判 | 待修 |
| **P2** | 18 | 架构：模块边界错位、"可扩展"设计名存实亡 | 待修 |
| **P3** | 9 | 工程化：覆盖率、文档漂移、安全默认值 | 待修 |

> 所有 P0/P1 结论均已在本机实测复现，非静态推测。文中标注 `[已实测]`。
>
> P0 修复说明：5 项已由 `tests/test_p0_regressions.py`（44 项回归测试）固化，测试数 115 → 159。P0-1 修复后 `pyglet>=1.5.0,<2.0` 的 pin 不再是必需品，相关清理见 **P3-9**。

---

## 1. P0 —— 阻断级缺陷（✅ 已全部修复，提交 `7185695`）

### P0-1 `import game` 直接崩溃，程序无法启动 `[已实测]`

`game.py:26` 在模块顶层 `from src.gui.chess_gui import ChessGUI`，而 `chess_gui.py:20` 是 `from pyglet.gl import glu`——该符号在 pyglet 2.x 中已移除。

```
import game -> ImportError: cannot import name 'glu' from 'pyglet.gl'
```

**关键点**：即使 `config/game_config.yaml` 里 `gui.3d: false`（默认值，走 Web 3D 路线），这个 ImportError 依然发生。原生 GUI 只是可选展示，却成了整个应用的硬依赖。

`requirements.txt` 用 `pyglet>=1.5.0,<2.0` 勉强回避了这个问题，但代价是把整个项目钉死在 2020 年的 pyglet 1.x 分支上。

**修复**：GUI 改为惰性导入。

```python
# game.py —— 顶层不再 import GUI
def _create_native_gui(fen, red_name, black_name):
    """惰性导入：仅当 gui.3d=true 时才需要 pyglet"""
    from src.gui.chess_gui import ChessGUI   # 局部导入
    return ChessGUI(fen=fen, red_agent_name=red_name, black_agent_name=black_name)
```

同步清理 `src/gui/__init__.py` 的 eager re-export，并在 `requirements.txt` 把 pyglet 拆成可选 extra：

```
# 必需
pyyaml, openai, fastapi, uvicorn[standard], websockets
# 可选：仅 gui.3d=true 时需要
pyglet>=2.0 ; extra == "native-gui"
```

---

### P0-2 LLM 永远看不到"上一步"和"当前阶段" `[已实测]`

`state_serializer.py:65` `GameState.from_engine()` 只填了 6 个字段，`phase` / `result` / `result_reason` / `last_move` / `last_move_by` 全部走 dataclass 默认值：

```
state.phase        = GamePhase.NOT_STARTED     ← 永远是 not_started
state.last_move    = None                      ← 永远是 None
state.result       = GameResult.IN_PROGRESS
```

连锁后果：

1. `prompt_builder._format_game_state` 的 `## 上一步走步` 段落**永不渲染**——而 `prompts/agent_default.txt:92` 专门要求 LLM「步骤2：对手意图推测」，让它从"对方上一步"推断意图。**喂进去的数据里根本没有这一步**。
2. `GameController.apply_move` 里 `state.last_move = iccs_move`（`game_controller.py:102-104`）赋值给一个**下一行就丢弃的临时对象**——纯死代码，误导后续维护者以为它生效了。

**修复**：

```python
@classmethod
def from_engine(cls, engine, *, phase=GamePhase.NOT_STARTED,
                result=GameResult.IN_PROGRESS, result_reason=None,
                last_move=None, last_move_by=None) -> "GameState":
    ...
    return cls(..., phase=phase, result=result, result_reason=result_reason,
               last_move=last_move, last_move_by=last_move_by)
```

并在 `GameController.get_current_state()` 里把自身的 `phase`/`result` 透传进去。

---

### P0-3 终局推送给 3D 界面的永远是开局局面 `[已实测]`

`game.py:203` 与 `game.py:218`：

```python
fen=result.get("final_fen", state.fen),      # run_game 从不返回 final_fen
turn=result.get("turn", "Red"),              # run_game 从不返回 turn
```

而 `run_game()` 的实际返回值只有 5 个键：`success / turn_count / result / result_reason / move_history`。

**后果**：一整局棋下完，浏览器和原生 GUI 最后收到的 FEN 都是**开局 FEN**。棋盘不会跳到终局画面。

**修复**：`run_game()` 返回值补 `final_fen` + `turn`（或直接返回 `GameState` 对象），并加断言测试。

---

### P0-4 语义标注的棋子名全部退化成英文 `[已实测]`

`prompt_builder.py:160` 的映射表用**大写驼峰**键：

```python
_PIECE_TYPE_CN = {"King": "将", "Rook": "车", ...}
```

而 `referee_engine.py:414` 产出的是**小写** `piece_type.value`：

```
capture:rook         -> 吃rook        （应为 吃车）
capture:king         -> 吃king        （应为 吃将）
fork:cannon          -> 抽cannon      （应为 抽炮）
sacrifice:knight     -> 弃knight      （应为 弃马）
```

`.get()` 未命中就回退成原始字符串，不报错、不告警。

**这条最致命**：`prompts/agent_default.txt:64-77` 花了整整一节教 LLM 识别「抽车 / 抽马 / 抽炮」「吃车 / 吃马」这些中文标签作为**战术决策依据**，而引擎实际喂给它的是 `抽cannon` / `吃rook`。**战术标注这个核心卖点，LLM 一个字都没读懂。**

**修复**：映射表键改为小写 `piece_type.value`，并加一个覆盖全部 7 种棋子 × 全部标注前缀的参数化单测。

```python
_PIECE_TYPE_CN = {
    "king": "将", "advisor": "仕", "bishop": "相",
    "knight": "马", "rook": "车", "cannon": "炮", "pawn": "兵",
}
```

---

### P0-5 纯文本模块强依赖 HTTP SDK `[已实测]`

`src/llm_adapters/__init__.py` 顶层 re-export `openai_base_adapter`，后者 `from openai import AsyncOpenAI`。于是：

```
import src.agents.prompt_builder   ->  ModuleNotFoundError: No module named 'openai'
```

`PromptBuilder` 是一个纯字符串格式化类，零 LLM 依赖，却因为 `src/agents/__init__.py` → `base_agent.py` → `llm_adapters` 的链条被拖下水。

**后果实测**：未装 `openai` 时，`tests/test_agents.py`、`test_web_3d.py`、`test_resign.py` **三个测试模块直接无法 collect**，整个测试套件崩溃退出。

**修复**：
- `llm_adapters/__init__.py` 移除 eager import，或改用 `__getattr__` 惰性导出（PEP 562）
- 同样检查 `src/mcp_tools/__init__.py`、`src/gui/__init__.py`、`src/web_3d/__init__.py`
- 目标：`pip install pyyaml` 即可 `import src.core.referee_engine` 并跑通引擎测试

---

## 2. P1 —— 正确性缺陷

### P1-1 FEN 丢弃 halfmove / fullmove，连带 web 端回合计数恒为 1 `[已实测]`

`to_fen()` 无条件追加 `" - - 0 1"`（`referee_engine.py:352`），两个计数字段从不维护。

而 `server.py:374` 解析：

```python
turn_number = int(fen_parts[5])   # 恒等于 1
```

**后果**：Web 3D 界面的"回合数"永远是 1。WebSocket 协议字段存在但无意义。

**修复**：引擎维护 `halfmove_clock`（吃子归零、将军归零、否则 +1）与 `fullmove_number`（黑方走完 +1），`to_fen()` 真实输出。副带好处是可以实现 60 回合自然限着规则。

---

### P1-2 三次重复局面少算一次（初始局面从未入表）`[已实测]`

```python
__init__ / reset():
    self.position_history = []
    self._position_counter = {}     # 初始 FEN 不在里面
```

只有 `apply_move()` 之后才记录。初始局面在棋盘上出现过，却不计入重复计数。

**后果**：一个"初始 → 走1 → 退回 → 走1 → 退回"的过程，引擎只看到 2 次而非 3 次，**漏判和棋**。另外 `len(position_history) < 5` 这个早退阈值是任意的，会掩盖更多边界情况。

**修复**：`__init__`/`reset()` 中记录初始局面为 `position_history[0]`，删除任意阈值。

---

### P1-3 长将判负会冤枉防守方

```python
# apply_move 内
before_check = self.is_king_in_check(current_color.opposite())   # 走完后对方是否被将
current_color = current_color.opposite()
after_check  = self.is_king_in_check(current_color.opposite())   # 我方是否被将
self.check_history.append(before_check or after_check)           # 混在一起，不记是谁将的
```

`check_history` 只记录"这一手双方是否有人被将"，**丢失了谁在将军**这个关键信息。然后 `_is_perpetual_check` 靠"当前轮到谁"倒推责任人：

```python
offender = "红方" if self.board.current_color == Color.BLACK else "黑方"
```

**后果**：一段"红方连续将军，黑方连续应将"的合法变化，两边都会被标成 `True`，最终**责任被归给当前行棋方**——也就是被将死防守的一方。

**修复**：`check_history` 改为 `List[Optional[Color]]` 记录"这一手是谁在将军"。并且按规则，只有**没有被对方将军**的一方连续将军才判负：

```python
class RepetitionTracker:
    """规则正确的重复/长将追踪"""
    # 长将：连续 N 手同一方将军，且该方在序列中从未被对方将军
    # 长捉：双方均无将军但连续重复 N 次
```

---

### P1-4 三次重复无条件自动判和 `[已实测]`

`_is_threefold_repetition()` 一旦命中，`check_game_end()` 直接返回 `判和`。但中国象棋规则中：

- 三次重复是**由某方提出**（"应将"），不是自动和棋
- 若重复局面中**一方处于被将军状态**，则该方必须变招，否则**判负**而非判和
- 完全缺失：60 回合自然限着、双方均无进攻的"自然限着"和棋

**修复**：把"自动判和"改为"记录待提议"，由 controller 决定是否裁决；并实现被将状态的特殊判定。

---

### P1-5 `_map_reason_to_result` 抛异常时状态被撕裂 `[已实测]`

```python
# GameController._map_reason_to_result
if GameEndReasons.DRAW in reason: return GameResult.DRAW
if reason.startswith(RED_PERPETUAL_CHECK): ...
raise ValueError(f"Unknown game end reason: {reason}")
```

实测 `"Maximum turns reached"` 和 `"Stalemate"` 都抛 `ValueError`。而 `apply_move` 的结构是：

```python
new_fen = self.referee.apply_move(iccs_move)   # ← 引擎上已经生效
self.turn_count += 1
is_over, reason = self.referee.check_game_end()
self.result = self._map_reason_to_result(reason)   # ← 此处抛异常
except Exception as e:
    return MoveResult(success=False, error=str(e))  # ← 报告"失败"
```

**后果**：棋盘已变、`turn_count` 已加，却告诉调用方"这步失败了"。引擎与 controller 状态不一致。

目前 `check_game_end()` 恰好不产生这两个字符串，属**埋雷**——任何人日后新增一种终局原因就会踩中。

**修复**：
1. 终局原因改为强类型枚举（`GameEndReason`），从根上消除字符串匹配
2. `apply_move` 改为"先计算后提交"（copy-on-write），异常时不污染状态
3. 补全 `MAX_TURNS` / `STALEMATE` / 投降 的映射

---

### P1-6 `phase` 硬编码红方先走，与 FEN 矛盾 `[已实测]`

```python
GameController.__init__:  self.phase = GamePhase.RED_TO_MOVE
GameController.reset():   self.phase = GamePhase.RED_TO_MOVE
```

两处都硬编码，不读 FEN 的 side-to-move。实测载入黑方先走的 FEN：

```
engine.get_current_turn() = Black
controller.phase          = RED_TO_MOVE     ← 矛盾
```

`config/game_config.yaml` 的 `initial_fen` 目前也没被使用（`game.py:119` 硬编码 `RefereeEngine()`），一旦启用自定义开局就会立刻暴露。

**修复**：`phase` 从 `referee.get_current_turn()` 推导，构造与 `reset()` 都走同一路径。

---

### P1-7 回合超时后 `run_game` 返回 `in_progress` `[已实测]`

```python
except asyncio.TimeoutError:
    logger.error(f"Turn timed out after {self.turn_timeout}s")
    break          # ← 不设 phase / result
```

`run_game` 返回 `result: "in_progress"`，与"和棋"无法区分。调用方和上层日志会认为对局还在进行。

**修复**：超时应是一个明确的终局（判负或判和，取决于规则取向），至少要有 `GameEndReasons.TIMEOUT`。

---

### P1-8 引擎评估分数未转换视角，量纲混用

`evaluate_position.py`：

- UCI 的 `score` 是**行棋方视角**。红方调用时引擎返回的是"红方视角"，黑方调用时是"黑方视角"——但两者都用同一个 key `evaluation` 返回给 LLM，**没有标注是谁的视角**。
- `score cp` 被 `/100.0` 转成"兵"，`score mate` 被映射成 `±100.0`——**两种不同量纲塞进同一个字段**。
- 匹配 `f"depth {depth}"` 是精确字符串匹配。引擎实际输出的 `info` 行深度格式多变，匹配不到就返回 `evaluation: None`，LLM 拿到空评估却不知道为什么。

**修复**：返回中显式带 `side_to_move` 与 `evaluation_red` / `evaluation_black`；解析改为"取最后一条 info 行"而非精确匹配深度。

---

### P1-9 引擎子进程超时后成为孤儿进程

```python
stdout, stderr = await asyncio.wait_for(process.communicate(...), timeout=60)
```

超时后 `wait_for` 取消的是 `communicate()`，**`process` 本身没被 kill**，引擎进程继续跑。且 `_run_engine_analysis` 内部超时 60s，工具循环最多 3 轮 → 最坏 180s，**远超 `turn_timeout=120s`**。

**修复**：`except asyncio.TimeoutError: process.kill(); await process.wait()`，并把引擎超时纳入统一的回合预算。

---

### P1-10 开局库数据自相矛盾 + 存在永不命中的死键 `[已实测]`

```python
COMMON_OPENINGS = {
    "rnbakabnr/.../RNBAKABNR": {
        "recommended_moves": [..., {"move": "c3c4", "name": "仙人指路"}, ...]},   # c3c4
    "rnbakabnr/.../RNBAKABNR w - - 0 1": {
        "recommended_moves": [..., {"move": "g3g4", "name": "仙人指路"}, ...]},   # g3g4
}
```

- **同一个开局名"仙人指路"给了两个互相矛盾的走法**（实测两条记录都合法，但棋理上只有一个对）
- **第二个键含空格，永远匹配不到**——`execute()` 里 `base_fen = fen.split()[0]` 已经截断到空格前
- `load_book()` 从未被 `ToolExecutor` 调用，外部开局库功能形同虚设；`_loaded` 字段只写不读

**修复**：合并为单条记录，键统一用棋盘部分；`ToolExecutor` 注册时调用 `load_book(config.tools_dir)`。

---

### P1-11 两个"改状态但不保证还原"的地雷 API

```python
# referee_engine.py:1098 —— docstring 自认会改状态
def render_ascii_board(self, fen: str = None) -> str:
    if fen:
        self._parse_fen(fen)      # ← 直接覆盖整个棋盘
    return self._build_ascii_board()

# referee_engine.py:1086 —— 临时改色，无 try/finally
def _get_legal_moves_for_color(self, color):
    original = self.board.current_color
    self.board.current_color = color
    moves = self.get_legal_moves()      # ← 若抛异常，current_color 残留
    self.board.current_color = original
    return moves
```

前者是"看起来像纯函数、实际是 mutator"；后者在异常路径下会留下脏状态。

**修复**：`render_ascii_board` 删除 `fen` 参数（保留纯 `render_ascii_board_readonly`）；`_get_legal_moves_for_color` 加 `try/finally`。

---

## 3. P2 —— 架构问题

### P2-1 MCP 工具系统完全没接线 `[已实测]`

README 和 `agent_default.txt` 都把"MCP 工具"当卖点，但实际是**两套互不相干的实现**：

| | 来源 | 状态 |
|---|---|---|
| LLM 实际看到的工具 | `prompt_builder.py` 里的 `MCP_TOOLS` 硬编码常量 | 生效 |
| 工具执行与注册 | `ToolExecutor` + `BaseTool` + `tools/` 动态发现 | **形同虚设** |

```python
# llm_agent.py —— 喂给 LLM 的是硬编码常量，不是注册表
tools=self.prompt_builder.get_tools()

# tool_executor.py —— get_tool_schemas() 从来没被调用过
```

而且 `ToolExecutor.get_instance()` **无参调用** → `config.get("tools_dir")` 为 `None` → `_auto_discover_tools()` 直接 return。**动态工具发现是永不执行的死代码。**

`config/game_config.yaml` 里明明配了 `tools_dir: "src/mcp_tools/tools"` 和 `auto_discover: true`——**配置从未被读取**。

**修复**：

```python
# LLMAgent 改为从注册表取
def get_tools(self):
    return ToolExecutor.get_instance().get_tool_schemas()

# game.py 启动时注入配置
ToolExecutor.get_instance(MCPToolsConfigDTO.from_yaml(...).to_dict())

# register_tool 去重，避免 schema 重复
def register_tool(self, tool: BaseTool):
    if tool.name in self._tools:
        return
    self._tools[tool.name] = tool
    self._tool_schemas.append(tool.get_schema())
```

---

### P2-2 `ToolExecutor` 全局单例不可注入

单例 + `reset_instance()` 是测试专用后门。生产代码无法为红黑双方配置不同工具集（黑方可能不需要 `evaluate_position`）。

**修复**：改为由 `AgentConfig` 持有 `tool_executor` 实例依赖注入，保留单例仅作为默认工厂。

---

### P2-3 工具结果在多轮循环中重复累加 `[已实测]`

```python
# base_agent.py: execute_tool_loop
tool_results = []
for iteration in range(3):
    for tool_call in current_response.tool_calls:
        tool_results.append({...})          # 累加进同一个 list
    self.prompt_builder.add_tool_results(tool_results)   # ← 传入已累加的 list
```

`add_tool_results` 内部是 `self.tool_results.extend(tool_results)`。实测 3 轮循环后累积 **6 条**（期望 3）——每次都把上一轮已包含的内容再塞一遍。

**修复**：`add_tool_results` 传入本轮新增的增量切片，或直接改为赋值覆盖。

---

### P2-4 Agent 对话历史跨回合无限增长 `[已实测]`

`PromptBuilder.history` 和 `tool_results` 只在 `clear_history()` 时清空，而 **`run_game` / `play_turn` 从不调用 `agent.reset()`**（实测调用次数 0）。

**后果**：200 回合的对局里，每个 Agent 的 prompt 会累积 200 轮纠错反馈 + 工具结果。token 成本失控，最终必然触顶或严重拖慢。这是"跑几局之后就废了"的典型根因。

**修复**：
- 明确记忆策略：象棋是低分支博弈，建议**每回合重置历史**（stateless-by-design，与 `referee_engine.py:11` 的设计原则本来就一致——"LLM 无状态，引擎强状态"）
- 若确实需要记忆，改为滑动窗口（保留最近 N 手）+ 独立的 `game_memory` 摘要字段

---

### P2-5 "多轮对话"是假的

`build_messages` 产出的消息序列是 `[system, ...history(全是user), tool_results(user), user_content(user)]`——**从不写回 assistant 回复**。

后果：
- 纠错反馈会形成**连续多条 user 消息**（OpenAI 容忍，Anthropic 会报错）
- LLM 看不到自己上一轮说了什么，所谓"对话"只是单向的追加日志

**修复**：每次 `chat()` 后把 `assistant` 消息写回历史。

---

### P2-6 `AgentConfig` 的重试配置是摆设 `[已实测]`

```python
@dataclass
class AgentConfig:
    max_retries: int = 3      # 声明了
    retry_delay: int = 2      # 声明了
```

`game_controller.play_turn` 里是 `for attempt in range(3)` **硬编码**。实测 `game_controller.py` 中 `max_retries` / `retry_delay` 出现次数均为 0。

**修复**：改用 `self.current_agent.config.max_retries`，并真正使用 `retry_delay`。

---

### P2-7 `AgentStatus` 状态机是死代码

```python
self.status = AgentStatus.THINKING
try:
    ...
except Exception:
    self.status = AgentStatus.ERROR      # ← 立刻被 finally 覆盖
finally:
    self.status = AgentStatus.IDLE       # ← 无论如何都变 IDLE
```

`THINKING` 和 `ERROR` 刚被赋值就无条件改写，`get_status()` 永远只能返回 `IDLE` 或 `DONE`（而 `DONE` 从未被设置）。

**修复**：`finally` 里恢复上一个状态而非硬置 `IDLE`；或直接删除这个未被使用的状态机。

---

### P2-8 `config_loader.py` 的校验层被整体绕过

`config_loader.py` 定义了 7 个带 `__post_init__` 校验的 dataclass（`LLMConfig` / `AgentConfigDTO` / `GameConfig` / `LoggingConfig` ...），但 `game.py:68` 的 `_load_agent` **手搓 dict 读取**：

```python
cfg = ConfigLoader.load_yaml(...)
llm_config = cfg["llm"]              # 绕过 LLMConfig 校验
adapter = _create_adapter(llm_config)
```

**后果**：`temperature` 越界、`timeout` 为负、provider 拼错——全部不会在启动时报错，而是延后到 LLM 调用时才炸。

同时 `RefereeConfig` 和 `TimeControlConfig` 定义了但**完全无人使用**（`turn_timeout=120` 硬编码在 `LLMAgentGameController.__init__`）。

**修复**：`game.py` 改用 `ConfigLoader.load_agent_config()`，删除 `game.py` 内的手搓读取；废弃未使用的 DTO 或补齐其消费方。

---

### P2-9 `${VAR:default}` 语法是死代码 `[已实测]`

```python
if value.startswith("${") and value.endswith("}"):   # 先匹配
    env_var = value[2:-1]
    return os.environ.get(env_var, "")
if value.startswith("${") and ":" in value:          # 永远到不了
    var_name, default = inner.split(":", 1)
    return os.environ.get(var_name, default)
```

`"${DEMO_A:fb}"` 也以 `}` 结尾，被第一个分支截获。实测：

```
'${DEMO_A}'     -> ''
'${DEMO_A:fb}' -> ''      ← 应为 'fb'
```

**分支顺序颠倒**。修好之后还有第二个问题：变量缺失时**静默返回 `""`**，空 API key 会被送进 OpenAI SDK，报错点远离根因。

**修复**：先匹配带 `:` 的分支；缺失变量时抛带变量名的明确异常（`${VAR:?message}` 风格）。

---

### P2-10 `LoggingConfig.VALID_LEVELS` 污染 dataclass 签名 `[已实测]`

```python
@dataclass
class LoggingConfig:
    VALID_LEVELS = {"DEBUG", "INFO", ...}   # 有注解 → 被当作字段
```

实测 `dataclasses.fields()` 返回 `['level', 'file', 'console']`——这个无注解的赋值**没有**进入 fields（侥幸正确），但它确实出现在实例上并被 `__post_init__` 读取。属于"碰巧没坏"的脆弱写法。

**修复**：显式标注 `ClassVar[Set[str]]`。

---

### P2-11 环境变量解析不递归进 list

`_resolve_dict_env_vars` 只递归 `dict`，`list` 直接原样返回。`default_camera_position: [8, 12, 12]` 里的值永远不会被解析。行为不一致。

---

### P2-12 `referee_engine.py` 是 1200 行的上帝模块

单文件同时承担 9 类职责：

| 职责 | 行数 | 备注 |
|---|---|---|
| 数据类型（Color / PieceType / Piece / Position / Move / Board） | 1-204 | |
| FEN 解析与序列化 | 205-354 | |
| 走法生成（7 种棋子） | 580-768 | 质量最好 |
| 合法性 / 飞将 | 812-834 | |
| 将军检测 | 997-1084 | |
| 战术标注（吃子/牵制/捉双/弃子…） | 370-578 | 性能热点 |
| 重复 / 长将 / 终局判定 | 887-995 | |
| ASCII 渲染 | 1098-1159 | |
| LLM 序列化 | 1161-1180 | 与 `state_serializer.py` 职责重叠 |

**`serialize_for_llm()` 与 `state_serializer.GameState.from_engine()` 是两套并行的状态序列化实现**，前者是死代码。

同时 `get_legal_moves()` 和 `get_annotated_moves()` 是**完全重复的双层嵌套循环**（`356-368` vs `370-392`）。

**修复拆分**：

```
src/core/
├── types.py          # Color / PieceType / Piece / Position / Move
├── board.py          # Board + FEN 解析/序列化
├── movegen.py        # 7 种棋子走法生成（纯函数，输入 Board 输出 List[Position]）
├── rules.py          # 合法性 / 飞将 / 将军检测
├── annotations.py    # 战术标注（可选，性能敏感）
├── repetition.py     # 重复 / 长将 / 终局判定（强类型枚举）
└── engine.py         # RefereeEngine 门面，只做编排
```

用 `functools.lru_cache` 缓存合法走步，避免重复计算。

---

### P2-13 战术标注性能：15× 开销，每回合调用 3 次 `[已实测]`

```
初始局面:   get_legal_moves 0.0042s  →  get_annotated_moves 0.0642s  (15.3×)
中局局面:   get_legal_moves 0.0039s  →  get_annotated_moves 0.0580s  (15.0×)
```

热点在三个 O(90×N) 暴力模拟，且**对每个合法走步都跑一遍**：

- `_detect_pin`：遍历 90 格 × 每个敌子做一次 `is_king_in_check`（内含 90 格 × 走法生成）
- `_detect_fork`：生成走法 + 遍历
- `_detect_sacrifice`：遍历所有敌子 + 各自走法

而 `GameController.get_current_state()` 每次都调 `get_annotated_moves()`，`play_turn` + `run_game` 每回合共调 3 次 → **每 ply 约 0.17 秒纯 CPU**，且随局面开放程度增长。

**修复**：
1. 合并 `get_legal_moves` / `get_annotated_moves` 为单一生成器，标注做成可选参数
2. `get_current_state()` 缓存，`apply_move` 后失效
3. pin 检测复用"攻击表"：先算一次全部敌子的攻击格集合，避免反复 `is_king_in_check`
4. `run_game` 里的 `state` 复用（第 423 行）而非重新生成

---

### P2-14 `Board.grid` 公开可变，抽象泄漏

`GameController._count_non_king_pieces` 直接遍历 `self.referee.board.grid[r][col]`。任何调用方都能绕过 `get_piece`/`set_piece` 直接改棋盘，`copy()` / `copy.deepcopy()` 两种拷贝方式并存。

**修复**：`grid` 私有化，暴露只读 `pieces()` 迭代器或 `__getitem__`。

---

### P2-15 observer 桥接：`ObserverBridge` 类是死代码

`observer_bridge.py` 定义了完整的 `ObserverBridge` 类（40 行），**从未被使用**。`make_sync_observer()` 用闭包把同样的逻辑重写了一遍（且只用了 `__call__` 里那部分）。

另外 fire-and-forget 的 `create_task` 没有背压：若广播慢于走棋，任务会堆积；`run_game` 返回后 `web_server.stop()` 可能发生在最后几次广播完成之前，**终局消息丢失**。

**修复**：删除 `ObserverBridge` 类；`make_sync_observer` 暴露 `pending_tasks`，在 `run_battle` 的 `finally` 里 `await asyncio.gather(*pending)` 再停服。

---

### P2-16 Adapter 注册硬编码 + 连接泄漏

```python
# game.py:39 —— 加一个新模型必须改主入口文件
ADAPTER_MAP = {"deepseek": ..., "mimo": ..., "minimax": ...}
```

README 却教用户"在 `src/llm_adapters/` 创建适配器"——但创建完还得回来改 `game.py`，且 `openai_base_adapter` / `anthropic_base_adapter` 两个基类没有注册入口（`anthropic` 适配器无任何 provider 使用它）。

更严重的是：`BaseLLMAdapter` 实现了 `__aenter__` / `__aexit__` / `close()`，但 **`game.py` 从不调用它们**（实测 `game.py` 中 `.close(` 出现 0 次）。两个 `AsyncOpenAI` 客户端的连接池在进程退出时不会优雅释放。

**修复**：
- adapter 自注册：`BaseLLMAdapter.__init_subclass__` 写入全局 `PROVIDER_REGISTRY`
- 打包或退出时 `await adapter.close()`（用 `try/finally` 或 `AsyncExitStack`）

---

### P2-17 Web 3D 细节问题

| 问题 | 位置 |
|---|---|
| `WebSocketManager._client_info` 私有属性被外部直接读写 | `server.py:164` |
| `set_game_info` 在 `update_game_state` 之前调用，导致 `players` 分支不生效（靠后续调用兜住） | `game.py:159` vs `166` |
| `_broadcast_move_event` 里 `fen_parts[1]` 无长度检查 | `server.py:373` |
| `start()` 在线程真正绑定端口前就置 `_is_running=True`，浏览器仅靠 `sleep(1.5)` 等待 | `server.py:264, 291` |
| `threading.Lock` 在 async 代码中做同步阻塞 | `server.py:338` |
| 协议版本不匹配直接拒绝连接，前端无法降级 | `server.py:186` |

---

### P2-18 构建产物提交进 git

```
src/web_3d/static/assets/css/main-C3VHkqfH.css
src/web_3d/static/assets/js/main-C-aHVLbI.js
```

vite 产物（hash 文件名）与 `web_3d_client/` 源码**双份真相**，无 CI 构建校验。改前端源码后忘记重新 build 就会用旧产物，且 diff 完全不可读。

**修复**：`src/web_3d/static/` 加入 `.gitignore`；`static_dir` 改为指向 `web_3d_client/dist`；或加 CI job 校验构建产物与源码同步。

---

## 4. P3 —— 工程化与体验

### P3-1 覆盖率 47%，关键路径零覆盖 `[已实测]`

```
TOTAL                          2912   1530    47%

src\mcp_tools\tool_executor.py  108    108     0%   ← 工具系统完全未测
src\mcp_tools\evaluate_position  98     98     0%
src\mcp_tools\opening_book.py    48     48     0%
src\mcp_tools\base_tool.py       34     34     0%
src\gui\*.py                          590     0%   ← GUI 全部未测
src\llm_adapters\openai_base_adapter  55  45    18%   ← 唯一的 LLM 出网路径
src\web_3d\server.py             181    107    41%
```

**`run_game`（`game_controller.py:359-434`）覆盖率为 0**——主对局循环、投降判定、胜负收敛、超时处理，全部无测试。`referee_engine.py` 虽然 89%，但 `check_game_end` 的将死/困毙分支（983-993）、长将（902/911）、三次重复（932）恰好都在未覆盖行里。

**修复优先级**：
1. `run_game` 端到端测试（用 FakeAgent，注入固定走步序列，覆盖将死/超时/投降/最大回合）
2. `mcp_tools` 全量单测（纯函数，好写）
3. adapter 协议契约测试（mock HTTP，验证重试/超时/响应解析）

### P3-2 无 CI、无 Lint、无类型检查

无 `.github/workflows/`，无 `ruff` / `black` / `pyright` 配置。`.gitignore` 里预留了 `.ruff_cache/` 但没有配置文件。80 个测试只能靠人手动跑。

**修复**：加 CI（`pytest + ruff + pyright`），并在 `pyproject.toml` 集中声明。

### P3-3 README 与实际行为不符

| README 声明 | 实际 |
|---|---|
| `--turns N` default 200 | `argparse` 默认 **100**（`game.py:244`） |
| `game_config.yaml` 的 `max_turns: 200` | **从不生效**，只读 CLI 参数 |
| `game_config.yaml` 的 `initial_fen` | **从不生效**，`RefereeEngine()` 硬编码 |
| "完整规则引擎…长将、三次重复" | 存在 P1-3 / P1-4 判定错误 |
| "MCP 工具 - 可扩展工具系统" | 见 P2-1，动态发现永不执行 |
| 只提 `game.py` 为入口 | `main.py` 是另一个入口，`--mode game` 未实现 |

**修复**：以配置为唯一事实来源（README → P2-8），并加"文档与实现一致性"检查项。

### P3-4 默认 `host: "0.0.0.0"` 对全网暴露

`Web3DConfig.host` 默认 `0.0.0.0`，配合 `auto_open_browser: true`。该服务暴露一个**可改变对局状态**的 WebSocket（虽然当前只广播，但协议预留了 `client.*` 消息类型）。同时无 CORS、无鉴权、无速率限制。

**修复**：默认改 `127.0.0.1`，暴露到局域网需显式配置。

### P3-5 走步提取过于脆弱

```python
all_matches = re.findall(r'\b([a-iA-I][0-9][a-iA-I][0-9])\b', content)
```

对**整段 content** 做正则。LLM 在 `thought` 里写"考虑从 h2 走到 e2 再到 h0"就会误抓。且 prompt 明确要求输出 JSON——**为什么不先 `json.loads` 再取 `move` 字段**，再回退到正则？

匹配不到时返回 `None`，LLM 实际输出的内容被完全丢弃，用户只看到"格式错误"。

**修复**：三级解析——`json.loads(content)` → 提取 code fence 内的 JSON → 正则兜底，并把原始输出摘要记入日志。

### P3-6 Adapter 重试策略对不可重试错误也重试

```python
except Exception as e:              # 401 / 400 / 404 也重试
    last_error = e
    await asyncio.sleep(2**attempt)
```

API key 错误会白白等 3 秒再失败。另外 `except asyncio.TimeoutError` 分支实际捕获不到 openai SDK 的 `APITimeoutError`（它继承自 `APIError` 而非 `asyncio.TimeoutError`），会落到通用分支。

**修复**：区分可重试（429 / 5xx / 网络）与不可重试（4xx）；读取 `Retry-After` 头。

### P3-7 两个入口职责重叠

`game.py`（真实对战）和 `main.py`（demo，`--mode game` 未实现）并存。`main.py` 的 demo 直接调 `controller.apply_move("DemoAgent", "h2e2")` 绕过回合管理。

**修复**：合并为单一 CLI，`main.py` 保留为 `--mode demo` 子命令。

### P3-8 `main.py` demo 第二步走步非法 `[已实测]`

`main.py:56` 演示黑方走 `i7e7`，但黑炮在 **h7** 而非 i7：

```
Move failed: Illegal move: i7e7, current_turn=Black, legal_moves=['a6a5', 'c6c5', ...]
```

**定级依据**：属于 P3 而非 P0。`python main.py --mode demo` **能正常跑完并 `EXIT=0`**，只是第二步打出 error 日志（实测）。既不是"程序跑不起来"，demo 也不是核心功能（核心是对战流程 `game.py`），第一步 `h2e2` 正常。属于演示数据笔误。

**修复**：`i7e7` → `h7e7`。顺带把这两步改成走 `GameController.play_turn()`，与 P3-7 一并处理。

### P3-9 `pyglet` 版本 pin 已成维护债

```text
pyglet>=1.5.0,<2.0
```

这个 pin 原本是为了绕开 P0-1（`pyglet.gl.glu` 在 2.x 被移除）。**P0-1 修复后**，`game.py` 已改为分支内惰性导入 GUI，pyglet 2.x 可正常运行（实测环境 2.1.16 下 `import game` 通过）。

**定级依据**：属于 P3 而非 P0。当前 pin 反而**让** pyglet 1.5（含 `glu`）被装上，GUI 路径功能正常——没有任何东西被阻断。

**代价**：把整个项目钉死在 2020 年的 pyglet 1.x 分支上（1.5.x 早已停止维护），且与 P3-2 的依赖整理割裂。

**修复**：随 P3-2 一并把 pyglet 拆为可选 extra：

```text
# 必需
pyyaml, openai, fastapi, uvicorn[standard], websockets, pytest, pytest-asyncio
# 可选：仅 gui.3d=true 时需要
pyglet>=2.0 ; extra == "native-gui"
```

同时需为 `chess_gui.py:20` 的 `from pyglet.gl import glu` 提供 pyglet 2.x 兼容写法（2.x 需 `from pyglet.gl import *` 并自行取 `gluBegin/gluPerspective`，或改用自实现的透视投影矩阵）。

---

## 5. 建议的目标架构

```
llm-xiangqi/
├── pyproject.toml              # 统一依赖/lint/类型/pytest 配置
├── src/
│   ├── core/                   # 纯规则层，零外部依赖，零 I/O
│   │   ├── types.py            #   Color/Piece/Position/Move
│   │   ├── board.py            #   Board + FEN
│   │   ├── movegen.py          #   走法生成（纯函数）
│   │   ├── rules.py            #   合法性/将军/飞将
│   │   ├── annotations.py      #   战术标注（可选、性能敏感）
│   │   ├── repetition.py       #   重复/长将（强类型 GameEndReason）
│   │   └── engine.py           #   RefereeEngine 门面
│   ├── agents/
│   │   ├── base.py             #   Agent 协议 + 记忆策略（每回合重置）
│   │   ├── llm.py              #   LLMAgent
│   │   ├── prompt.py           #   PromptBuilder（从 ToolRegistry 取 schema）
│   │   └── parse.py            #   走步解析：JSON → fence → regex 三级
│   ├── llm/
│   │   ├── base.py             #   BaseLLMAdapter（自注册 + 生命周期）
│   │   ├── openai_compat.py    #   OpenAI 协议基类
│   │   └── providers/          #   deepseek/ mimo/ minimax/ …
│   ├── tools/
│   │   ├── registry.py         #   ToolRegistry（唯一事实来源）
│   │   ├── base.py
│   │   └── builtin/            #   opening_book/ evaluate_position/ validate_move
│   ├── config/                 #   带校验的 DTO，__post_init__ 保证启动即失败
│   ├── web/                    #   FastAPI + WS（惰性导入）
│   └── observability/          #   日志/指标/对局回放
├── web_3d_client/              # 前端源码
├── tests/
│   ├── unit/  integration/  contract/  perft/
└── docs/
```

**三条硬性依赖规则**：

1. `src/core/**` 不 import 任何第三方包——规则引擎必须能在裸 Python 上跑（便于 perft 与规则校验）
2. 所有 `__init__.py` 移除 eager re-export，或统一用 PEP 562 `__getattr__` 惰性导出
3. 展示层（`gui/`、`web/`）惰性导入，缺失时降级而非崩溃

---

## 6. 分阶段路线图

### 阶段 0：止血（约 1 天，纯 bugfix，不改架构）—— ✅ **P0 部分已完成**（`7185695`）

| # | 动作 | 对应 | 状态 |
|---|---|---|---|
| 0.1 | GUI 惰性导入，`import game` 恢复可用 | P0-1 | ✅ |
| 0.2 | `_PIECE_TYPE_CN` 键改小写 | P0-4 | ✅ |
| 0.3 | `GameState.from_engine` 接收并透传 phase/last_move | P0-2 | ✅ |
| 0.4 | `run_game()` 返回 `final_fen` + `turn` | P0-3 | ✅ |
| 0.5 | 清理各 `__init__.py` eager import | P0-5 | ✅ |
| 0.6 | 初始局面入 `position_history` | P1-2 | 待做 |
| 0.7 | `to_fen()` 维护 halfmove/fullmove | P1-1 | 待做 |
| 0.8 | `phase` 从 FEN 推导 | P1-6 | 待做 |
| 0.9 | 超时收敛为明确终局 | P1-7 | 待做 |
| 0.10 | 补全 `_map_reason_to_result` 全部分支 | P1-5 | 待做 |

> 0.1-0.5 已由 `tests/test_p0_regressions.py`（44 项）固化，测试 115 → 159。
> 0.6-0.10 属 P1，建议与**阶段 1** 一并处理。

### 阶段 1：正确性（约 3-5 天）

- 重写长将/重复判定：`RepetitionTracker` + 强类型 `GameEndReason`（P1-3、P1-4、P1-5）
- `evaluate_position` 视角转换 + 量纲分离 + 子进程 kill（P1-8、P1-9）
- 修开局库数据矛盾与死键，接上 `load_book`（P1-10）
- 收敛 `render_ascii_board` / `_get_legal_moves_for_color` 的状态副作用（P1-11）
- adapter 错误分类重试（P3-6）
- 走步解析改三级 + JSON 优先（P3-5）

### 阶段 2：架构（约 1-2 周）

- `ToolRegistry` 成为工具唯一事实来源，`ToolExecutor` 改依赖注入（P2-1、P2-2）
- Agent 记忆策略：每回合重置历史，写回 assistant 消息（P2-4、P2-5）
- 激活 `max_retries` / `retry_delay`，清理 `AgentStatus`（P2-6、P2-7）
- `game.py` 改用 `ConfigLoader` 校验层（P2-8）
- 修 `${VAR:default}` + 缺失变量显式报错（P2-9、P2-10、P2-11）
- adapter 自注册 + 生命周期管理（P2-16）
- 清理 observer 桥接死代码 + 终局广播 await（P2-15）

### 阶段 3：性能与拆分（约 1 周）

- 合并 `get_legal_moves` / `get_annotated_moves` 为单一生成器（P2-12）
- `get_current_state()` 缓存 + 攻击表复用，目标消除 15× 开销（P2-13）
- 拆分 `referee_engine.py`，删除 `serialize_for_llm` 死代码（P2-12）
- `Board.grid` 私有化（P2-14）

### 阶段 4：工程化（约 3-5 天）

- CI：`pytest + ruff + pyright`（P3-2）
- 补 `run_game` / `mcp_tools` / adapter 契约测试，目标覆盖率 ≥ 80%（P3-1）
- 引入 **perft** 测试（以初始局面为基准校验走法生成正确性）——这是规则引擎唯一可靠的自动化验证手段
- 配置文件成为唯一事实来源，同步修正 README（P3-3）
- 构建产物移出 git（P2-18）
- 合并 `main.py` / `game.py` 入口，顺带修 demo 走步（P3-7、P3-8）
- 依赖整理：`pyglet` 拆为 `[native-gui]` 可选 extra + 兼容 2.x（P3-9、P3-2）
- `host` 默认改 `127.0.0.1`（P3-4）

### 阶段 5：功能增强（可选）

- **人类对弈模式**：目前只能 LLM vs LLM，无法人机对战
- **对局回放/导出**：SGF 格式
- **多 Agent 锦标赛**：批量跑不同模型组合并对比
- **Elo 评测**：复用已有 MCP 工具 + perft 做基准
- **提示词 A/B 实验**：同一模型不同 prompt 的胜率对比

---

## 7. 附录：缺陷速查表

| ID | 级别 | 摘要 | 位置 |
|---|---|---|---|
| P0-1 | P0 ✅已修 | `import game` 因 pyglet 崩溃 `[实测]` | `game.py:26` |
| P0-2 | P0 ✅已修 | `phase`/`last_move` 恒为缺省 `[实测]` | `state_serializer.py:65` |
| P0-3 | P0 ✅已修 | 终局推送开局 FEN `[实测]` | `game.py:203,218` |
| P0-4 | P0 ✅已修 | 标注棋子名退化英文 `[实测]` | `prompt_builder.py:160` |
| P0-5 | P0 ✅已修 | 纯文本模块依赖 `openai` `[实测]` | `llm_adapters/__init__.py` |
| P1-1 | P1 | FEN 丢弃 halfmove/fullmove `[实测]` | `referee_engine.py:352` |
| P1-2 | P1 | 三次重复漏算初始局面 `[实测]` | `referee_engine.py:216` |
| P1-3 | P1 | 长将判负冤枉防守方 | `referee_engine.py:883` |
| P1-4 | P1 | 三次重复无条件自动判和 | `referee_engine.py:969` |
| P1-5 | P1 | 终局原因未映射导致状态撕裂 `[实测]` | `game_controller.py:142` |
| P1-6 | P1 | `phase` 硬编码 `[实测]` | `game_controller.py:59,163` |
| P1-7 | P1 | 超时后返回 `in_progress` `[实测]` | `game_controller.py:391` |
| P1-8 | P1 | 引擎评分未转视角、量纲混用 | `evaluate_position.py:127` |
| P1-9 | P1 | 引擎子进程超时成为孤儿 | `evaluate_position.py:115` |
| P1-10 | P1 | 开局库矛盾 + 死键 `[实测]` | `opening_book.py:21` |
| P1-11 | P1 | 两个改状态的地雷 API | `referee_engine.py:1086,1098` |
| P2-1 | P2 | MCP 工具系统未接线 `[实测]` | `llm_agent.py:34` |
| P2-2 | P2 | `ToolExecutor` 全局单例 | `tool_executor.py:30` |
| P2-3 | P2 | 工具结果重复累加 `[实测]` | `base_agent.py:153` |
| P2-4 | P2 | 对话历史跨回合无限增长 `[实测]` | `game_controller.py` |
| P2-5 | P2 | 从不写回 assistant 消息 | `prompt_builder.py:356` |
| P2-6 | P2 | `max_retries`/`retry_delay` 是摆设 `[实测]` | `game_controller.py:266` |
| P2-7 | P2 | `AgentStatus` 死状态机 | `llm_agent.py:24,71` |
| P2-8 | P2 | 配置校验层被绕过 | `game.py:68` |
| P2-9 | P2 | `${VAR:default}` 死代码 `[实测]` | `config_loader.py:192` |
| P2-10 | P2 | `VALID_LEVELS` 污染 dataclass `[实测]` | `config_loader.py:130` |
| P2-11 | P2 | 环境变量不递归进 list | `config_loader.py:199` |
| P2-12 | P2 | 1200 行上帝模块 + 双份序列化 | `referee_engine.py` |
| P2-13 | P2 | 标注 15× 开销，每回合 3 次 `[实测]` | `referee_engine.py:370` |
| P2-14 | P2 | `Board.grid` 可变外泄 | `referee_engine.py:172` |
| P2-15 | P2 | `ObserverBridge` 死代码 + 广播丢失 | `observer_bridge.py:14` |
| P2-16 | P2 | adapter 硬编码 + 连接泄漏 `[实测]` | `game.py:39` |
| P2-17 | P2 | Web 3D 封装/竞态/私有属性 | `server.py` |
| P2-18 | P2 | 构建产物入库 | `src/web_3d/static/assets` |
| P3-1 | P3 | 覆盖率 47%，主循环 0% `[实测]` | `tests/` |
| P3-2 | P3 | 无 CI / Lint / 类型检查 / 依赖整理 | — |
| P3-3 | P3 | README 与实现不符 | `README.md:84` |
| P3-4 | P3 | 默认 `0.0.0.0` 全网暴露 | `config_loader.py:156` |
| P3-5 | P3 | 走步正则提取脆弱 | `base_agent.py:252` |
| P3-6 | P3 | 不可重试错误也重试 | `openai_base_adapter.py:86` |
| P3-7 | P3 | 两个入口职责重叠 | `main.py` / `game.py` |
| P3-8 | P3 | demo 第二步走步非法 `[实测]` | `main.py:56` |
| P3-9 | P3 | `pyglet` pin 已成维护债（P0-1 后） | `requirements.txt` |
