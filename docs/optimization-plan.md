# LLM-Xiangqi 优化方案

> 版本: 0.1.0
> 最后更新: 2026-03-28
> 状态: 待审批

## Context

经过对项目代码的逐行审查，确认外部审计报告中存在一个真实且严重的框架级 Bug，同时报告提出的"架构优化"方向基本合理但优先级需要调整。本方案采用"先修 Bug、再测基线、后做优化"的保守策略，确保每一步改动都有数据支撑。

---

## Bug 确认：game_controller.py 结果映射错误

`src/core/game_controller.py:86-93` 中，`self.result` 的赋值完全忽略 `check_game_end()` 返回的 `reason` 字符串，仅根据 `current_color` 简单判断谁赢。

**受影响的判定**（已验证）：

| reason 字符串 | 期望结果 | 实际结果 | 状态 |
|---|---|---|---|
| `"红方长将违规"` | `BLACK_WIN` | `RED_WIN` | **反转错误** |
| `"黑方长将违规"` | `RED_WIN` | `BLACK_WIN` | **反转错误** |
| `"三次重复局面，判和"` | `DRAW` | `RED_WIN`/`BLACK_WIN` | **永远不判和** |
| 王被吃/将死/困毙 | 各自有对应胜方 | 正确 | 偶然正确 |

**根因**：当前控制器使用"当前走子方的对家赢"这个启发式规则，这只在将死/困毙时碰巧正确。长将违规方应判负而非判胜，三次重复应判和而非判胜。

---

## Phase 0：修复结果映射 Bug（P0 - 数据正确性）

**目标**：`check_game_end()` 返回的所有 reason 字符串都能正确映射到 `GameResult` 枚举值。

**修改文件**：`src/core/game_controller.py:86-93`

**当前代码**：
```python
self.result = (
    GameResult.RED_WIN
    if self.referee.board.current_color == Color.BLACK
    else GameResult.BLACK_WIN
)
```

**替换为**：基于 `reason` 字符串内容的显式映射：
- reason 包含 `"判和"` → `GameResult.DRAW`
- reason 以 `"红方长将"` 开头 → `GameResult.BLACK_WIN`（红方违规，黑方胜）
- reason 以 `"黑方长将"` 开头 → `GameResult.RED_WIN`（黑方违规，红方胜）
- reason 以 `"红方胜利"` 开头 → `GameResult.RED_WIN`
- reason 以 `"黑方胜利"` 开头 → `GameResult.BLACK_WIN`
- 兜底 fallback → 保留原 current_color 启发式（理论上不应命中）

**新增测试**：`tests/test_game_controller.py`（新文件）
- 构造重复走步序列，验证三次重复→`GameResult.DRAW`
- 验证将死/王被吃时胜方正确
- 验证 `is_game_over()` 返回的 `result_reason` 与 `result` 一致

**验收标准**：
- `pytest tests/ -v` 全部通过
- 手动构造 3 次重复局面，确认返回 `(True, GameResult.DRAW, "三次重复局面，判和")`

---

## Phase 1：手动收集基准测试数据

**目标**：用修复后的代码运行对局，建立量化基线。不修改任何源码，由用户手动执行。

**用户操作**：
- 使用当前 Prompt（`agent_default.txt`，100 分制版）和当前框架代码
- 每组模型配对运行至少 5 局对局
- 记录每局终端输出

**需记录的指标**：

| 指标 | 获取方式 |
|---|---|
| 最终结果 (`RED_WIN`/`BLACK_WIN`/`DRAW`) | `run_game()` 返回的 `result` 字段 |
| 结束原因 | `result_reason` 字段 |
| 总回合数 | `turn_count` 字段 |
| 非法走步次数 | 日志中 `"LLM幻觉非法走步"` 出现次数 |
| 格式错误次数 | 日志中 `"输出格式错误"` 出现次数 |
| 走棋历史 | `move_history` 字段，人工审阅棋力质量 |

**建议统计表格式**：

| 局次 | 红方模型 | 黑方模型 | 结果 | 原因 | 回合数 | 非法走步 | 格式错误 | 棋力评价 |
|---|---|---|---|---|---|---|---|---|
| 1 | deepseek-chat | mimo-v2-flash | ? | ? | ? | ? | ? | 手动 |

**验收标准**：
- 至少 5 局完整对局数据
- 计算非法走步率 = 重试次数 / (总回合数 + 重试次数)
- 基线数据文档化

**依赖**：Phase 0 完成。

---

## Phase 2：精简 Prompt

**目标**：移除 100 分制启发式打分系统，简化输出格式，释放 LLM 注意力。

**修改文件**：`prompts/agent_default.txt`

**核心改动**：
- 保留：角色定义（冷酷象棋杀手）、坐标系参考、关键战术原则（出车优先、防飞炮）
- 移除：40+30+20+10 分制打分体系、4 步 JSON 输出结构（`1_development_status` ~ `4_final_decision`）
- 新增输出格式：`{"thought": "简短思考过程", "move": "4字符ICCS走步"}`
- 战术原则以简洁列表替代打分规则

**修改文件**：`src/agents/prompt_builder.py`（可选，视 Phase 1 数据决定）
- 如果非法走步率偏高，可考虑在 `_format_game_state()` 中按棋子类型分组合法走步

**验收标准**：
- 运行相同数量的对局
- 非法走步率不显著上升
- 棋力评价不低于基线
- 每轮 token 消耗应下降（更短 Prompt + 更短输出 JSON）

**依赖**：Phase 1 基线数据。

---

## Phase 3：框架侧语义标注

**目标**：在 `get_legal_moves()` 层面为合法走步附加"吃子"、"将军"、"重复警告"、"出子"语义标签，让 LLM 无需自行推断战术含义。

### 3.1 设计决策

采用 **Option A**：在 `RefereeEngine` 中新增 `get_annotated_moves() -> List[dict]` 方法，保留原 `get_legal_moves()` 不变以向后兼容。返回格式示例：
```python
{"move": "h2e2", "annotations": ["capture:Pawn", "check"]}
{"move": "a0a1", "annotations": ["development"]}
{"move": "b2e2", "annotations": []}
```

### 3.2 修改文件清单

**`src/core/referee_engine.py`**（新增 ~60 行）：
- `get_annotated_moves()`：遍历合法走步，对每步调用 `_annotate_move()`
- `_annotate_move(move, piece) -> List[str]`：检测四类标注
  - **吃子检测**：`move.to_pos` 有敌方棋子 → `capture:{piece_type}`
  - **将军检测**：模拟走步后调用 `is_king_in_check()` → `check`
  - **重复警告**：模拟走步后生成 FEN，查 `position_history`，若已出现 ≥2 次 → `repetition_warning`
  - **出子标记**：车从底线（红方 row=0 / 黑方 row=9）出发 → `development`

**`src/core/state_serializer.py`**（小改）：
- `GameState` 新增字段：`annotated_moves: List[Dict[str, Any]] = field(default_factory=list)`
- `GameState.from_engine()` 中调用 `engine.get_annotated_moves()` 填充新字段
- `legal_moves` 保留为 `List[str]`（从 annotated_moves 提取），向后兼容
- `to_dict()` 输出中包含 `annotated_moves`

**`src/agents/prompt_builder.py`**（中改）：
- `_format_game_state()` 检查是否存在 `annotated_moves`：
  - 有：按标注格式化，如 `h2e2 (吃兵, 将军)`，可按标注类型分组展示
  - 无：回退当前逗号分隔格式

### 3.3 性能影响评估

`_annotate_move()` 对每步执行一次棋盘模拟 + 检测恢复。典型局面 30-50 步合法走步，每次模拟约 O(90) 操作，总计 < 10ms。与 LLM API 延迟（秒级）相比可忽略。

**验收标准**：
- 现有测试全部通过
- 新增 `test_annotated_moves.py`：验证吃子/将军/重复/出子四类标注
- 运行对局，日志中可见带标注的合法走步输出
- 无性能退化

**依赖**：Phase 0。Phase 1-2 推荐但非必须。

---

## Phase 4：基于语义标注重写 Prompt

**目标**：利用 Phase 3 的标注信息重写 Prompt，让 LLM 直接看到战术后果。

**修改文件**：`prompts/agent_default.txt`

**关键指导规则**：
- 看到 `capture:Rook` / `capture:Knight` / `capture:Cannon` → 优先吃
- 看到 `check` → 优先将军（配合吃子更优先）
- 看到 `repetition_warning` → 禁止选择（除非是唯一合法步）
- 开局阶段优先选带 `development` 标注的走步
- 无战术机会时，优先推进车马向敌方半场

**修改文件**：`src/agents/prompt_builder.py`

`_format_game_state()` 中按标注类型分组合法走步：
```
## 合法走步 (共 34 种)

### 将军/吃子
h2e2 (吃兵, 将军), a0a9 (吃车)

### 出子
a0a1 (出车), i0i1 (出车)

### 其他
b2e2, c3c4, ...
```

**验收标准**：
- 运行相同数量的对局
- 非法走步率不高于 Phase 2
- 战略质量提升：LLM 更一致地执行吃子、将军、出子
- 与 Phase 1 基线对比所有指标

**依赖**：Phase 2（精简 Prompt）+ Phase 3（语义标注）。

---

## Phase 5：对比验证

**目标**：控制变量实验，对比各阶段效果，选出最终配置。

**测试矩阵**：

| 配置 | Prompt | 语义标注 | 说明 |
|---|---|---|---|
| A | 原版（100分制） | 无 | Phase 1 基线 |
| B | 精简版 | 无 | Phase 2 |
| C | 原版 | 有 | Phase 3 + 原 Prompt |
| D | 精简版 | 有 | Phase 3 + Phase 4（完整方案） |

每组至少 5 局。通过切换 `prompts/` 目录下的 prompt 文件和 `GameState.from_engine()` 中是否调用 `get_annotated_moves()` 实现配置切换。

**对比指标**：非法走步率、格式错误率、结果分布、平均回合数、token 消耗、人工棋力评价。

**验收标准**：
- 所有配置能稳定完成对局（无崩溃、无死循环）
- 至少 2 项指标上选出明确优胜配置
- 确定最终上线配置

**依赖**：所有前置阶段完成。

---

## 文件修改汇总

| 文件 | Phase | 改动内容 |
|---|---|---|
| `src/core/game_controller.py` | 0 | 修复结果映射逻辑（86-93行） |
| `tests/test_game_controller.py` | 0 | 新增：结果映射单元测试 |
| `src/core/referee_engine.py` | 3 | 新增 `get_annotated_moves()`、`_annotate_move()` |
| `src/core/state_serializer.py` | 3 | `GameState` 新增 `annotated_moves` 字段 |
| `src/agents/prompt_builder.py` | 2-4 | `_format_game_state()` 支持标注格式化和分组 |
| `prompts/agent_default.txt` | 2, 4 | 两轮重写：精简版 → 标注感知版 |

## 关键决策点

1. **Phase 1 vs Phase 2 顺序**：Phase 1 基线数据必须在 Phase 2 之前收集，否则无法评估精简 Prompt 的效果
2. **Phase 3 是否依赖 Phase 2**：不严格依赖。语义标注是框架特性，独立于 Prompt 设计
3. **Phase 4 是否执行**：取决于 Phase 2 + Phase 3 各自的独立效果，如果单独某一阶段已达到满意效果，Phase 4 可能不需要
4. **模型选择**：Phase 1-5 应使用相同的模型配对，以控制变量
