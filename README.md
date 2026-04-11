# LLM-Xiangqi

LLM Agent 中国象棋对战框架

LLM Agent Chinese Chess Battle Framework

---

## 特性

- **多模型支持** - DeepSeek、MiMo、MiniMax 等适配器，支持 OpenAI / Anthropic 协议扩展
- **完整规则引擎** - 走法生成、将军/将杀检测、飞将、长将、三次重复等
- **走法标注** - 为合法走法添加语义标签（吃子、将军、抽将、牵制等），辅助 LLM 决策
- **纠错重试** - 非法走法自动注入纠错提示，最多重试 3 次
- **3D 可视化** - Web Three.js 可视化（默认）或 pyglet 原生 3D 界面
- **MCP 工具** - 可扩展工具系统（走法验证、局面评估、开局库）

## Features

- **Multi-LLM Support** - DeepSeek, MiMo, MiniMax adapters, extensible via OpenAI/Anthropic protocol base classes
- **Complete Rule Engine** - Move generation, check/checkmate detection, flying generals, perpetual check, threefold repetition, etc.
- **Annotated Moves** - Semantic labels for legal moves (capture, check, fork, pin, etc.) to aid LLM decisions
- **Correction Retries** - Automatic correction prompts for illegal moves, up to 3 retries
- **3D Visualization** - Web Three.js (default) or pyglet native 3D interface
- **MCP Tools** - Extensible tool system (move validation, position evaluation, opening book)

---

## 快速开始 / Quick Start

### 1. 安装 Python 依赖 / Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 2. 构建 Web 3D 前端 / Build Web 3D Frontend

默认使用 Web 3D 可视化界面，需要 Node.js 环境（建议 v18+）：

Web 3D visualization is the default interface, requiring Node.js (v18+ recommended):

```bash
cd web_3d_client
npm install
npm run build
cd ..
```

### 3. 配置 API 密钥 / Configure API Keys

默认红方使用 DeepSeek，黑方使用 MiMo：

By default, Red uses DeepSeek and Black uses MiMo:

```bash
# Linux/macOS
export DEEPSEEK_API_KEY="sk-xxx"
export MIMO_API_KEY="sk-xxx"

# Windows PowerShell
$env:DEEPSEEK_API_KEY="sk-xxx"
$env:MIMO_API_KEY="sk-xxx"

# Windows CMD
set DEEPSEEK_API_KEY=sk-xxx
set MIMO_API_KEY=sk-xxx
```

### 4. 运行 / Run

```bash
python game.py
```

程序将启动 Web 3D 服务并自动打开浏览器（默认 `http://localhost:8080`）。

The Web 3D server starts and browser opens automatically (default `http://localhost:8080`).

可选参数 / Optional arguments：

| 参数 / Arg | 说明 / Description |
|---|---|
| `--turns N` | 最大回合数 / Max turns (default 200) |
| `--config PATH` | 指定配置文件 / Custom config file |

---

## 项目结构 / Project Structure

```
llm-xiangqi/
├── config/           # 配置文件 / Configurations
│   ├── game_config.yaml      # 全局配置 / Global config
│   ├── agent1_config.yaml    # 红方配置 / Red agent config
│   └── agent2_config.yaml    # 黑方配置 / Black agent config
├── prompts/          # 系统提示词 / System prompts
├── src/
│   ├── agents/       # Agent 实现 / Agent implementations
│   ├── core/         # 规则引擎 / Rule engine
│   ├── gui/          # pyglet 原生 3D / Native 3D GUI
│   ├── llm_adapters/ # 模型适配器（可扩展）/ LLM adapters (extensible)
│   ├── mcp_tools/    # MCP 工具 / MCP tools
│   ├── utils/        # 工具函数 / Utilities
│   └── web_3d/       # Web 3D 服务 / Web 3D server
├── web_3d_client/    # Web 3D 前端 / Web 3D frontend
├── tests/            # 单元测试 / Unit tests
├── docs/             # 文档 / Documentation
├── game.py           # 主入口 / Main entry
└── main.py           # 演示入口 / Demo entry
```

---

## 配置 / Configuration

### 游戏配置 / Game Config

编辑 `config/game_config.yaml`：

Edit `config/game_config.yaml`:

```yaml
game:
  initial_fen: "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"
  max_turns: 200

gui:
  web_3d: true
  web_3d_config:
    port: 8080
    auto_open_browser: true
```

### Agent 配置 / Agent Config

编辑 `config/agent1_config.yaml` 和 `config/agent2_config.yaml`，API 密钥使用 `${ENV_VAR}` 引用环境变量：

Edit `config/agent1_config.yaml` and `config/agent2_config.yaml`. API keys use `${ENV_VAR}` to reference environment variables:

```yaml
agent:
  name: "Agent1"
  color: "Red"

llm:
  provider: "deepseek"
  model: "deepseek-chat"
  api_key: "${DEEPSEEK_API_KEY}"
  base_url: "https://api.deepseek.com"
  temperature: 0.7
```

---

## 添加新模型 / Add New Model

在 `src/llm_adapters/` 创建适配器，继承对应协议基类：

Create an adapter in `src/llm_adapters/` inheriting from the appropriate protocol base class:

```python
# OpenAI 兼容协议 / OpenAI-compatible protocol
from src.llm_adapters.openai_base_adapter import OpenAICompatibleAdapter

class MyAdapter(OpenAICompatibleAdapter):
    pass

# Anthropic 兼容协议 / Anthropic-compatible protocol
from src.llm_adapters.anthropic_base_adapter import AnthropicCompatibleAdapter

class MyAdapter(AnthropicCompatibleAdapter):
    pass
```

---

## License

[Apache 2.0](LICENSE)
