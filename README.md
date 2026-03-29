# LLM-Xiangqi / 中国象棋 LLM 对战框架

[English](#english) | [中文](#中文)

---

<a name="中文"></a>
## 中文

基于 LLM Agent 的中国象棋对战框架，支持多种 LLM 提供者（DeepSeek、GLM、MiniMax、MiMo 等）。框架内置完整的象棋规则引擎、3D 可视化界面以及灵活的多 Agent 对战架构，可用于 AI 对战、研究 LLM 推理能力、评估不同模型在棋类任务中的表现。

### 统一 API 架构

本项目采用分层解耦架构，通过统一的通信契约确保任意 LLM 后端均可无缝接入：

```
┌──────────────────────────────────────────────────────────────┐
│                        主程序 (game.py)                       │
│                                                              │
│  ┌──────────────┐    ┌──────────┐    ┌───────────────────┐  │
│  │GameController │───│ LLMAgent │───│  PromptBuilder     │  │
│  └──────┬───────┘    └────┬─────┘    └───────────────────┘  │
│         │                 │                                  │
│         │           ┌─────┴──────┐                           │
│         │           │  Agent API │  ← Agent层统一接口         │
│         │           └─────┬──────┘                           │
│         │                 │                                  │
│  ┌──────┴───────┐  ┌─────┴──────────┐   ┌────────────────┐ │
│  │ RefereeEngine │  │ BaseLLMAdapter │───│   MCP Tools    │ │
│  └──────────────┘  └─────┬──────────┘   └────────────────┘ │
│                          │                                  │
│          ┌───────────────┴───────────────┐                  │
│  ┌───────┴──────────┐        ┌───────────┴──────────┐      │
│  │OpenAICompatible  │        │AnthropicCompatible   │      │
│  │Adapter (base)    │        │Adapter (base)        │      │
│  └───────┬──────────┘        └───────────┬──────────┘      │
│      ┌───┴───┐                      ┌────┴────┐            │
│  ┌───┴───┐┌───┴───┐            ┌────┴───┐     │            │
│  │DeepSeek││ MiMo  │            │MiniMax │     │            │
│  │Adapter ││Adapter│            │Adapter │     │            │
│  └───┬────┘└───┬───┘            └───┬────┘     │            │
└─────┼─────────┼────────────────────┼──────────┼────────────┘
      │         │                    │          │
  OpenAI API  OpenAI API        Anthropic API (SDK)
```

### 适配器继承层级

```
BaseLLMAdapter (ABC)
  ├── OpenAICompatibleAdapter
  │     ├── DeepSeekAdapter
  │     └── MiMoAdapter
  └── AnthropicCompatibleAdapter
        └── MiniMaxAdapter
```

**设计原则**: 协议级公共逻辑（消息格式转换、重试策略、响应解析）由协议基类实现；具体适配器只需覆盖默认的 `model` 和 `base_url`。

### 核心数据结构

| 数据结构 | 说明 |
|---------|------|
| `GameState` | 游戏状态，包含 FEN、合法走步列表、历史记录等 |
| `AgentResult` | Agent 决策结果，包含走步、思考过程、工具调用结果 |
| `LLMResponse` | LLM 响应，统一封装 `content`、`thought`、`tool_calls` |
| `MoveResult` | 走步执行结果 |

### 支持的 LLM Provider

| provider | 适配器类 | 协议 | 默认模型 |
|----------|---------|------|---------|
| `deepseek` | `DeepSeekAdapter` | OpenAI | `deepseek-chat` |
| `mimo` | `MiMoAdapter` | OpenAI | `mimo-v2-pro` |
| `minimax` | `MiniMaxAdapter` | Anthropic | `MiniMax-M2.7` |

### 快速开始

#### 1. 安装依赖

```bash
pip install -r requirements.txt
```

#### 2. 配置 API Keys

**方式一：环境变量（推荐，更安全）**

```bash
# Linux/macOS
export DEEPSEEK_API_KEY="sk-xxx"
export MIMO_API_KEY="sk-xxx"

# Windows PowerShell
$env:DEEPSEEK_API_KEY="sk-xxx"
$env:MIMO_API_KEY="sk-xxx"
```

**方式二：本地配置文件（不被 Git 追踪）**

创建 `config/agent1_config.local.yaml` 或编辑原配置：

```yaml
llm:
  provider: "deepseek"
  model: "deepseek-chat"
  api_key: "${DEEPSEEK_API_KEY}"  # 或硬编码 "sk-xxx"
  base_url: "https://api.deepseek.com"
  temperature: 0.7
  max_tokens: 2048
```

配置文件：
- `config/agent1_config.yaml` - 红方 Agent
- `config/agent2_config.yaml` - 黑方 Agent

#### 3. 运行对战

```bash
python game.py
python game.py --turns 200  # 指定最大回合数
```

### 接入新 LLM 适配器

只需 3 步即可接入新的 LLM 后端：

**1. 判断协议类型并创建适配器：**

```python
# OpenAI 兼容协议（推荐）
from src.llm_adapters.openai_base_adapter import OpenAICompatibleAdapter

class NewLLMAdapter(OpenAICompatibleAdapter):
    def __init__(self, api_key, model="default-model",
                 base_url="https://api.newllm.com/v1", **kwargs):
        super().__init__(api_key=api_key, model=model, base_url=base_url, **kwargs)
```

**2. 注册到 `game.py`：**

```python
ADAPTER_MAP = {
    "deepseek": DeepSeekAdapter,
    "mimo":     MiMoAdapter,
    "minimax":  MiniMaxAdapter,
    "new_llm":  NewLLMAdapter,  # 新增
}
```

**3. 配置文件中指定：**

```yaml
llm:
  provider: "new_llm"
  model: "model-name"
  api_key: "sk-xxx"
  base_url: "https://api.example.com"
```

### 项目结构

```
llm-xiangqi/
├── config/                    # 配置文件
├── prompts/                   # System prompts
├── src/
│   ├── agents/                # Agent 实现
│   ├── core/                  # 核心引擎 (裁判、状态、控制器)
│   ├── gui/                   # 3D 可视化界面 (pyglet)
│   ├── llm_adapters/          # LLM 适配器 (统一 API)
│   ├── mcp_tools/             # MCP Tools
│   └── utils/                 # 工具函数
├── web_3d_client/             # Web 3D 可视化界面 (Three.js)
│   ├── src/                   # 前端源码
│   └── index.html             # 入口页面
├── docs/
│   └── api-standard.md        # API 详细文档
├── tests/
├── game.py                    # 游戏对战入口
└── main.py                    # 主入口
```

### 功能特性

- **模块化 Agent 架构**：统一的 `LLMAgent` 类 + 可插拔适配器
- **双协议支持**：OpenAI 兼容协议 + Anthropic 兼容协议
- **完整的中国象棋规则引擎**：棋子移动验证、将军/应将检测、胜负判定
- **3D 可视化**：基于 pyglet/OpenGL 的实时渲染
- **Web 3D 可视化**：基于 Three.js 的网页端 3D 界面
- **MCP Tools 集成**：支持通过 MCP 协议扩展 Agent 工具能力

### Web 3D 可视化界面

项目包含基于 Three.js 的 Web 3D 可视化界面：

```bash
cd web_3d_client
npm install
npm run dev          # 启动开发服务器
npm run build        # 构建生产版本
```

访问 http://localhost:5173/ 查看 3D 棋盘。

---

<a name="english"></a>
## English

A Chinese Chess (Xiangqi) framework based on LLM Agents, supporting multiple LLM providers (DeepSeek, GLM, MiniMax, MiMo, etc.). The framework includes a complete chess rules engine, 3D visualization, and a flexible multi-agent battle architecture, suitable for AI battles, LLM reasoning research, and model evaluation.

### Unified API Architecture

The project adopts a layered decoupled architecture with a unified communication contract ensuring seamless integration of any LLM backend:

```
┌──────────────────────────────────────────────────────────────┐
│                        Main Program (game.py)                 │
│                                                              │
│  ┌──────────────┐    ┌──────────┐    ┌───────────────────┐  │
│  │GameController │───│ LLMAgent │───│  PromptBuilder     │  │
│  └──────┬───────┘    └────┬─────┘    └───────────────────┘  │
│         │                 │                                  │
│         │           ┌─────┴──────┐                           │
│         │           │  Agent API │  ← Unified Agent Interface│
│         │           └─────┬──────┘                           │
│         │                 │                                  │
│  ┌──────┴───────┐  ┌─────┴──────────┐   ┌────────────────┐ │
│  │ RefereeEngine │  │ BaseLLMAdapter │───│   MCP Tools    │ │
│  └──────────────┘  └─────┬──────────┘   └────────────────┘ │
│                          │                                  │
│          ┌───────────────┴───────────────┐                  │
│  ┌───────┴──────────┐        ┌───────────┴──────────┐      │
│  │OpenAICompatible  │        │AnthropicCompatible   │      │
│  │Adapter (base)    │        │Adapter (base)        │      │
│  └───────┬──────────┘        └───────────┬──────────┘      │
│      ┌───┴───┐                      ┌────┴────┐            │
│  ┌───┴───┐┌───┴───┐            ┌────┴───┐     │            │
│  │DeepSeek││ MiMo  │            │MiniMax │     │            │
│  │Adapter ││Adapter│            │Adapter │     │            │
│  └───┬────┘└───┬───┘            └───┬────┘     │            │
└─────┼─────────┼────────────────────┼──────────┼────────────┘
      │         │                    │          │
  OpenAI API  OpenAI API        Anthropic API (SDK)
```

### Adapter Inheritance Hierarchy

```
BaseLLMAdapter (ABC)
  ├── OpenAICompatibleAdapter
  │     ├── DeepSeekAdapter
  │     └── MiMoAdapter
  └── AnthropicCompatibleAdapter
        └── MiniMaxAdapter
```

**Design Principle**: Protocol-level common logic (message format conversion, retry strategy, response parsing) is implemented by protocol base classes; specific adapters only need to override default `model` and `base_url`.

### Core Data Structures

| Data Structure | Description |
|----------------|-------------|
| `GameState` | Game state containing FEN, legal moves list, history, etc. |
| `AgentResult` | Agent decision result with move, thought process, tool results |
| `LLMResponse` | LLM response, unified wrapper for `content`, `thought`, `tool_calls` |
| `MoveResult` | Move execution result |

### Supported LLM Providers

| provider | Adapter Class | Protocol | Default Model |
|----------|--------------|----------|---------------|
| `deepseek` | `DeepSeekAdapter` | OpenAI | `deepseek-chat` |
| `mimo` | `MiMoAdapter` | OpenAI | `mimo-v2-pro` |
| `minimax` | `MiniMaxAdapter` | Anthropic | `MiniMax-M2.7` |

### Quick Start

#### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

#### 2. Configure API Keys

**Option 1: Environment Variables (Recommended, Safer)**

```bash
# Linux/macOS
export DEEPSEEK_API_KEY="sk-xxx"
export MIMO_API_KEY="sk-xxx"

# Windows PowerShell
$env:DEEPSEEK_API_KEY="sk-xxx"
$env:MIMO_API_KEY="sk-xxx"
```

**Option 2: Local Config File (Not tracked by Git)**

Create `config/agent1_config.local.yaml` or edit the original config:

```yaml
llm:
  provider: "deepseek"
  model: "deepseek-chat"
  api_key: "${DEEPSEEK_API_KEY}"  # or hardcode "sk-xxx"
  base_url: "https://api.deepseek.com"
  temperature: 0.7
  max_tokens: 2048
```

Config files:
- `config/agent1_config.yaml` - Red Agent
- `config/agent2_config.yaml` - Black Agent

#### 3. Run Battle

```bash
python game.py
python game.py --turns 200  # Specify max turns
```

### Adding New LLM Adapter

Only 3 steps to integrate a new LLM backend:

**1. Determine protocol type and create adapter:**

```python
# OpenAI-compatible protocol (recommended)
from src.llm_adapters.openai_base_adapter import OpenAICompatibleAdapter

class NewLLMAdapter(OpenAICompatibleAdapter):
    def __init__(self, api_key, model="default-model",
                 base_url="https://api.newllm.com/v1", **kwargs):
        super().__init__(api_key=api_key, model=model, base_url=base_url, **kwargs)
```

**2. Register in `game.py`:**

```python
ADAPTER_MAP = {
    "deepseek": DeepSeekAdapter,
    "mimo":     MiMoAdapter,
    "minimax":  MiniMaxAdapter,
    "new_llm":  NewLLMAdapter,  # Added
}
```

**3. Specify in config file:**

```yaml
llm:
  provider: "new_llm"
  model: "model-name"
  api_key: "sk-xxx"
  base_url: "https://api.example.com"
```

### Project Structure

```
llm-xiangqi/
├── config/                    # Configuration files
├── prompts/                   # System prompts
├── src/
│   ├── agents/                # Agent implementations
│   ├── core/                  # Core engine (referee, state, controller)
│   ├── gui/                   # 3D visualization (pyglet)
│   ├── llm_adapters/          # LLM adapters (unified API)
│   ├── mcp_tools/             # MCP Tools
│   └── utils/                 # Utilities
├── web_3d_client/             # Web 3D visualization (Three.js)
│   ├── src/                   # Frontend source code
│   └── index.html             # Entry page
├── docs/
│   └── api-standard.md        # Detailed API documentation
├── tests/
├── game.py                    # Game entry point
└── main.py                    # Main entry
```

### Features

- **Modular Agent Architecture**: Unified `LLMAgent` class + pluggable adapters
- **Dual Protocol Support**: OpenAI-compatible + Anthropic-compatible protocols
- **Complete Chinese Chess Rules Engine**: Move validation, check detection, win/loss determination
- **3D Visualization**: Real-time rendering based on pyglet/OpenGL
- **Web 3D Visualization**: Web-based 3D interface powered by Three.js
- **MCP Tools Integration**: Extend Agent capabilities via MCP protocol

### Web 3D Visualization

The project includes a Web 3D visualization interface based on Three.js:

```bash
cd web_3d_client
npm install
npm run dev          # Start development server
npm run build        # Build production version
```

Visit http://localhost:5173/ to view the 3D chessboard.

---

## API Documentation / API 文档

For detailed API specifications, see [docs/api-standard.md](docs/api-standard.md).

详细 API 规范请参阅 [docs/api-standard.md](docs/api-standard.md)。
