# LLM-Xiangqi

LLM Agent 中国象棋对战框架

LLM Agent Chinese Chess Battle Framework

---

## 特性

- **多模型支持** - DeepSeek、MiMo、MiniMax 等 LLM 适配器，可扩展任意模型
- **完整规则引擎** - 完整中国象棋规则实现
- **3D 可视化** - Web Three.js 可视化界面
- **MCP 工具** - 可扩展工具系统

## Features

- **Multi-LLM Support** - DeepSeek, MiMo, MiniMax and other LLM adapters, extensible to any model
- **Complete Rule Engine** - Full Chinese chess rules
- **3D Visualization** - Web Three.js visualization
- **MCP Tools** - Extensible tool system

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

### 3. 配置 API 密钥 / Configure API Key

```bash
# Linux/macOS
export DEEPSEEK_API_KEY="sk-xxx"

# Windows PowerShell
$env:DEEPSEEK_API_KEY="sk-xxx"

# Windows CMD
set DEEPSEEK_API_KEY=sk-xxx
```

### 4. 运行 / Run

```bash
python game.py
```

程序将启动 Web 3D 服务并自动打开浏览器（默认 `http://localhost:8080`）。

The Web 3D server starts and browser opens automatically (default `http://localhost:8080`).

---

## 项目结构 / Project Structure

```
llm-xiangqi/
├── config/           # 配置文件 / Configurations
├── prompts/          # 系统提示词 / System prompts
├── src/
│   ├── agents/       # Agent 实现 / Agent implementations
│   ├── core/         # 规则引擎 / Rule engine
│   ├── llm_adapters/ # 模型适配器（可扩展）/ LLM adapters (extensible)
│   ├── mcp_tools/    # MCP 工具 / MCP tools
│   └── web_3d/       # Web 3D 服务 / Web 3D server
├── web_3d_client/    # Web 3D 前端 / Web 3D frontend
├── tests/            # 单元测试 / Unit tests
├── game.py           # 主入口 / Main entry
└── main.py           # 演示入口 / Demo entry
```

---

## 配置 / Configuration

编辑 `config/game_config.yaml`：

Edit `config/game_config.yaml`:

```yaml
gui:
  web_3d: true               # 启用 Web 3D / Enable Web 3D
  web_3d_config:
    port: 8080               # 服务端口 / Server port
    auto_open_browser: true  # 自动打开浏览器 / Auto open browser
```

---

## 添加新模型 / Add New Model

在 `src/llm_adapters/` 创建适配器，继承 `BaseLLMAdapter`：

Create an adapter in `src/llm_adapters/` inheriting from `BaseLLMAdapter`:

```python
from src.llm_adapters.base_adapter import BaseLLMAdapter

class MyAdapter(BaseLLMAdapter):
    async def chat(self, prompt: str) -> str:
        # 实现模型调用 / Implement model call
        pass
```
