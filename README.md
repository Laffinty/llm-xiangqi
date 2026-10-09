# LLM-Xiangqi

LLM Agent 中国象棋对战框架

---

## 特性

- **多模型支持** — DeepSeek、MiMo、MiniMax，OpenAI 与 Anthropic 双协议适配
- **完整规则引擎** — 走法生成、将军/将杀检测、飞将、长将、三次重复局面
- **走步标注** — 每个合法走法附战术标签（吃子 / 将军 / 捉双 / 牵制 / 弃子 / 过河），辅助模型判断
- **决策契约** — 合法走法以 `enum` 写入 strict schema，模型在结构上无法输出非法走步
- **Skill 模式** — 棋艺知识按局面拆成 `SKILL.md`，按需加载而非全量常驻（任何局面组合的常驻开销都低于拆分前）
- **结构化局面** — 阶段 / 子力差 / 将军 / 重复预警由引擎直接给出，模型不必自己数
- **评测 harness** — 冻结局面集 + 门禁对比，把「改动有没有变好」变成可判定的问题
- **3D 可视化** — Web Three.js（默认）或 pyglet 原生界面

### Features

- **Multi-LLM Support** — DeepSeek, MiMo, MiniMax; OpenAI- and Anthropic-protocol adapters
- **Complete Rule Engine** — move generation, check/checkmate, flying generals, perpetual check, threefold repetition
- **Annotated Moves** — tactical labels per legal move to assist model judgement
- **Decision Contract** — legal moves written as an `enum` in a strict schema; structurally impossible to emit an illegal move
- **Skill Mode** — chess knowledge split into `SKILL.md` by phase and loaded on demand
- **Structured Position** — phase / material / check / repetition provided by the engine
- **Evaluation Harness** — frozen case set with gated comparison

---

## 快速开始 / Quick Start

### 1. 安装 Python 依赖

```bash
pip install -r requirements.txt
```

### 2. 构建 Web 3D 前端

```bash
cd web_3d_client
npm install
npm run build
cd ..
```

### 3. 配置 API 密钥

```bash
# Linux/macOS
export DEEPSEEK_API_KEY="sk-xxx"
export MIMO_API_KEY="sk-xxx"

# Windows PowerShell
$env:DEEPSEEK_API_KEY="sk-xxx"
$env:MIMO_API_KEY="sk-xxx"
```

### 4. 运行

```bash
python game.py
```

程序会启动 Web 3D 服务并自动打开浏览器（默认 `http://localhost:8080`）。

| 参数 | 说明 |
|---|---|
| `--turns N` | 最大回合数（默认 100） |
| `--config PATH` | 指定配置文件 |

---

## 架构

每回合的回路：

```
RefereeEngine ──► BoardSnapshot ──► SkillRouter ──► system prompt + 决策契约
      │                                                          │
      │                                                          ▼
      └─────────────── 事件 ◄── GameController ◄── move_decision ◄── LLM
```

- **`BoardSnapshot`** — 结构化局面（阶段 / 子力 / 将军 / 上一步 / 重复预警）
- **`SkillRouter`** — 由局面特征**确定性**决定激活哪些 knowledge skill，不由模型自选
- **决策契约** — 合法走法作为 `enum` 写进 schema，走步由结构保证而非正则兜底
- **`ToolExecutor`** — 棋盘能力工具的唯一事实来源

通信契约见 `docs/api-standard.md`。待解决问题见 `docs/open-questions.md`；
本轮迁移的计划、裁决与证据已归档至 `docs/history/`。

---

## 项目结构

```
llm-xiangqi/
├── config/           # 配置文件
│   ├── game_config.yaml
│   ├── agent1_config.yaml
│   └── agent2_config.yaml
├── prompts/
│   ├── base.md       # 常驻基础层（角色 / 坐标系 / 禁止事项）
│   └── agent_default.txt   # 未启用 skill 时的旧式全量 prompt
├── skills/           # 知识 skill，按局面激活
│   ├── opening-development/SKILL.md
│   ├── middlegame-tactics/SKILL.md
│   ├── endgame-technique/SKILL.md
│   ├── check-defense/SKILL.md
│   └── repetition-management/SKILL.md
├── src/
│   ├── agents/       # Agent 与决策契约
│   ├── core/         # 规则引擎 / 控制器 / 状态序列化
│   ├── skills/       # Skill 注册表与路由器
│   ├── llm_adapters/ # 模型适配器（可扩展）
│   ├── mcp_tools/    # 棋盘能力工具
│   ├── gui/          # pyglet 原生 3D
│   ├── web_3d/       # Web 3D 服务
│   └── utils/
├── tests/
│   └── eval/         # 对局评测 harness
├── docs/             # 设计文档与评测报告
├── game.py           # 主入口
└── main.py           # 演示入口
```

---

## 配置

### Agent 配置 / Agent Config

`config/agent1_config.yaml`、`config/agent2_config.yaml`：

```yaml
agent:
  name: "Agent1"
  color: "Red"
  system_prompt_file: "prompts/agent_default.txt"
  max_retries: 3
  use_tools: false          # 是否暴露棋盘能力工具
  decision_contract: true   # 合法走法写入 strict schema 的 enum
  skills: true              # 按局面加载 SKILL.md 而非全量常驻

llm:
  provider: "deepseek"
  model: "deepseek-flash"
  api_key: "${DEEPSEEK_API_KEY}"
  base_url: "https://api.deepseek.com"
  temperature: 0.7
  max_tokens: 2048
  thinking: false           # 深度求是 thinking model，开启会吃光 max_tokens
  timeout: 30
```

**关于 `thinking`**：两家默认模型都是 thinking model。开启思维链会消耗 `max_tokens` 预算导致 `content` 为空、走步只能从截断的思考中提取。实测关闭后 2–7 秒/手且走步必合法，开启则 40–130 秒/手且可能截断。

### 评测 / Evaluation

```bash
# 采集基线
python -m tests.eval.run --games 7 --seed 42 --max-turns 40 --out docs/eval-baseline.json

# 改动后与基线对比（门禁自动判定）
python -m tests.eval.run --games 7 --seed 42 --max-turns 40 \
    --out docs/eval-after.json --compare docs/eval-baseline.json

# 复验报告自洽性 / 复验连通性
python -m tests.eval.run --verify docs/eval-baseline.json
python -m tests.eval.run --probe --api-file C:\path\to\keys.txt
```

门禁覆盖：非法走步率、正则兜底率、调用错误、**激活一致性**（每回合实际激活的 skill 必须等于局面蕴含的应激活）与**空激活率上限**。

计数类指标做两比例 z 检验，差异与噪声不可区分时判「不可判定」而非「退化」；指标缺失时门禁判失败——无法评估不等于通过。

---

## 添加新模型 / Adding a Model

在 `src/llm_adapters/` 继承对应协议基类：

```python
# OpenAI 兼容协议
from src.llm_adapters.openai_base_adapter import OpenAICompatibleAdapter

class MyAdapter(OpenAICompatibleAdapter):
    pass

# Anthropic 兼容协议
from src.llm_adapters.anthropic_base_adapter import AnthropicCompatibleAdapter

class MyAdapter(AnthropicCompatibleAdapter):
    pass
```

若新供应商的**结构化输出能力**与既有两家不同（是否支持函数内 `strict`、是否支持 `response_format: json_schema`、`tool_choice` 限制），在适配器上标注能力位并在 `src/agents/llm_agent.py` 的 `_chat()` 中分派契约通道。既有实测：DeepSeek 仅支持函数内 `strict`，MiMo 两者皆支持。

---

## License

[Apache 2.0](LICENSE)
