# LLM-Xiangqi

LLM Agent 中国象棋对战框架

LLM Agent Chinese Chess Battle Framework

---

## 特性

- **多模型支持** - DeepSeek、MiMo、MiniMax 适配器
- **完整规则引擎** - 完整中国象棋规则实现
- **3D 可视化** - 原生 pyglet GUI + Web Three.js
- **MCP 工具** - 可扩展工具系统

## Features

- **Multi-LLM Support** - DeepSeek, MiMo, MiniMax adapters
- **Complete Rule Engine** - Full Chinese chess rules
- **3D Visualization** - Native pyglet GUI + Web Three.js
- **MCP Tools** - Extensible tool system

---

## 快速开始

```bash
pip install -r requirements.txt
```

设置 API 密钥：

```bash
export DEEPSEEK_API_KEY="sk-xxx"  # Linux/macOS
$env:DEEPSEEK_API_KEY="sk-xxx"    # Windows PowerShell
```

运行对战：

```bash
python game.py
```

## Quick Start

```bash
pip install -r requirements.txt
```

Set API key:

```bash
export DEEPSEEK_API_KEY="sk-xxx"  # Linux/macOS
$env:DEEPSEEK_API_KEY="sk-xxx"    # Windows PowerShell
```

Run battle:

```bash
python game.py
```

---

## 项目结构

```
llm-xiangqi/
├── config/           # 配置文件
├── prompts/          # 系统提示词
├── src/
│   ├── agents/       # Agent 实现
│   ├── core/         # 规则引擎
│   ├── gui/          # 原生 3D GUI
│   ├── llm_adapters/ # 模型适配器
│   ├── mcp_tools/    # MCP 工具
│   └── web_3d/       # Web 服务
├── web_3d_client/    # Web 前端
├── tests/            # 单元测试
├── game.py           # 主入口
└── main.py           # 演示入口
```

## Project Structure

```
llm-xiangqi/
├── config/           # Configurations
├── prompts/          # System prompts
├── src/
│   ├── agents/       # Agent implementations
│   ├── core/         # Rule engine
│   ├── gui/          # Native 3D GUI
│   ├── llm_adapters/ # LLM adapters
│   ├── mcp_tools/    # MCP tools
│   └── web_3d/       # Web server
├── web_3d_client/    # Web frontend
├── tests/            # Unit tests
├── game.py           # Main entry
└── main.py           # Demo entry
```

---

## Web 3D 可视化

### 环境准备

进入前端目录并安装依赖：

```bash
cd web_3d_client
npm install
```

### 编译构建

构建前端静态文件（输出到 `src/web_3d/static/`）：

```bash
npm run build
```

### 运行

返回项目根目录，通过 `game.py` 运行（Web 3D 模式）：

```bash
cd ..
python game.py
```

或者使用完整命令：

```bash
cd web_3d_client && npm install && npm run build && cd .. && python game.py
```

浏览器将自动打开（默认端口 8080），也可手动访问 http://localhost:8080

### 配置

编辑 `config/game_config.yaml` 调整 Web 3D 设置：

```yaml
gui:
  3d: false        # 原生 3D GUI (pyglet)
  web_3d: true     # Web 3D 可视化

  web_3d_config:
    host: "0.0.0.0"
    port: 8080
    auto_open_browser: true
```

### 开发模式（可选）

如需前端开发实时热更新：

```bash
cd web_3d_client
npm run dev
```

---

## Web 3D Visualization

### Setup

Install dependencies:

```bash
cd web_3d_client
npm install
```

### Build

Build static files (output to `src/web_3d/static/`):

```bash
npm run build
```

### Run

Return to project root and run via `game.py`:

```bash
cd ..
python game.py
```

Or in one command:

```bash
cd web_3d_client && npm install && npm run build && cd .. && python game.py
```

Browser will auto-open (default port 8080), or manually visit http://localhost:8080

### Configuration

Edit `config/game_config.yaml` to adjust Web 3D settings:

```yaml
gui:
  3d: false        # Native 3D GUI (pyglet)
  web_3d: true     # Web 3D visualization

  web_3d_config:
    host: "0.0.0.0"
    port: 8080
    auto_open_browser: true
```

### Development Mode (Optional)

For frontend hot-reload development:

```bash
cd web_3d_client
npm run dev
```