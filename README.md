# LLM-Xiangqi / 中国象棋 LLM 对战平台

**English** | 一个基于 LLM Agent 的中国象棋对战框架，支持多模型对战、完整规则引擎、3D 可视化。

**中文** | A Chinese chess battle framework based on LLM Agent, supporting multi-model battles, complete rule engine, and 3D visualization.

---

## Features / 特性

| English | 中文 |
|---------|------|
| **Multi-Provider Support** - DeepSeek, MiniMax, MiMo adapters with unified interface | **多提供商支持** - DeepSeek、MiniMax、MiMo 适配器，统一接口 |
| **Dual Protocol** - OpenAI-compatible & Anthropic-compatible APIs | **双协议支持** - OpenAI 兼容与 Anthropic 兼容 API |
| **Complete Rule Engine** - Move validation, check/checkmate detection, game-over judgment | **完整规则引擎** - 走法验证、将军检测、胜负判定 |
| **3D Visualization** - Native pyglet GUI + Three.js Web interface | **3D 可视化** - 原生 pyglet GUI + Three.js Web 界面 |
| **MCP Tools** - Extensible tool system via MCP protocol | **MCP 工具** - 通过 MCP 协议扩展工具能力 |

---

## Quick Start / 快速开始

### 1. Install Dependencies / 安装依赖

```bash
pip install -r requirements.txt
```

### 2. Configure API Keys / 配置 API 密钥

**Environment Variables / 环境变量**

```bash
# Linux/macOS
export DEEPSEEK_API_KEY="sk-your-key"
export MIMO_API_KEY="sk-your-key"

# Windows PowerShell
$env:DEEPSEEK_API_KEY="sk-your-key"
```

**Or edit config files / 或编辑配置文件**: `config/agent1_config.yaml`, `config/agent2_config.yaml`

### 3. Run Battle / 运行对战

```bash
# Console mode / 控制台模式
python game.py

# With Web 3D visualization / Web 3D 可视化模式
# Edit config/game_config.yaml: web_3d: true
python game.py

# Demo mode / 演示模式
python main.py --mode demo
```

---

## Supported Providers / 支持的模型

| Provider | Protocol | Default Model |
|----------|----------|---------------|
| DeepSeek | OpenAI | `deepseek-chat` |
| MiMo | OpenAI | `mimo-v2-pro` |
| MiniMax | Anthropic | `MiniMax-M2.7` |

---

## Project Structure / 项目结构

```
llm-xiangqi/
├── config/              # Agent & game configs / 配置文件
├── prompts/             # System prompts / 系统提示词
├── src/
│   ├── agents/          # Agent implementations / Agent 实现
│   ├── core/            # Rule engine & controller / 核心引擎
│   ├── gui/             # Native 3D GUI / 原生 3D 界面
│   ├── llm_adapters/    # LLM provider adapters / 模型适配器
│   ├── mcp_tools/       # MCP tool system / MCP 工具系统
│   ├── utils/           # Utilities / 工具函数
│   └── web_3d/          # Web 3D server / Web 3D 服务器
├── web_3d_client/       # Three.js frontend / Web 前端
├── tests/               # Unit tests / 单元测试
├── game.py              # Battle entry / 对战入口
└── main.py              # Demo entry / 演示入口
```

---

## Web 3D Visualization / Web 3D 可视化

```bash
cd web_3d_client
npm install
npm run dev    # http://localhost:5173
```

---

## Testing / 测试

```bash
python -m pytest tests/ -v
```

---

## Documentation / 文档

- [docs/api-standard.md](docs/api-standard.md) - API specification / API 规范
