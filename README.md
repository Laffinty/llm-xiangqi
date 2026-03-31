# LLM-Xiangqi

LLM Agent 中国象棋对战框架

LLM Agent Chinese Chess Battle Framework

---

## 特性

- **多模型支持** - DeepSeek、MiMo、MiniMax 适配器
- **完整规则引擎** - 完整中国象棋规则实现
- **3D 可视化** - Web Three.js 可视化界面
- **MCP 工具** - 可扩展工具系统

## Features

- **Multi-LLM Support** - DeepSeek, MiMo, MiniMax adapters
- **Complete Rule Engine** - Full Chinese chess rules
- **3D Visualization** - Web Three.js visualization
- **MCP Tools** - Extensible tool system

---

## 快速开始 / Quick Start

### 1. 安装 Python 依赖 / Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 2. 安装并构建 Web 前端 / Setup Web Frontend

项目使用 Web 3D 可视化作为默认界面，需要 Node.js 环境（建议 v18+）。

The project uses Web 3D visualization as the default interface, requiring Node.js (v18+ recommended).

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

### 4. 运行对战 / Run Battle

```bash
python game.py
```

程序将自动打开浏览器访问 `http://localhost:8080` 查看 3D 可视化界面。

The browser will automatically open at `http://localhost:8080` for the 3D visualization.

---

## 完整部署示例 / Full Deployment Example

全新电脑从零部署：

Fresh deployment from scratch:

```bash
# 1. 获取代码 / Get the code
git clone <repository-url>
cd llm-xiangqi

# 2. Python 依赖 / Python dependencies
pip install -r requirements.txt

# 3. 前端构建 / Frontend build
cd web_3d_client
npm install
npm run build
cd ..

# 4. 设置 API 密钥 / Set API key
export DEEPSEEK_API_KEY="sk-xxx"  # 或使用其他适配器 / or use other adapters

# 5. 运行 / Run
python game.py
```

---

## 项目结构 / Project Structure

```
llm-xiangqi/
├── config/           # 配置文件 / Configurations
├── prompts/          # 系统提示词 / System prompts
├── src/
│   ├── agents/       # Agent 实现 / Agent implementations
│   ├── core/         # 规则引擎 / Rule engine
│   ├── gui/          # 原生 GUI (可选) / Native GUI (optional)
│   ├── llm_adapters/ # 模型适配器 / LLM adapters
│   ├── mcp_tools/    # MCP 工具 / MCP tools
│   └── web_3d/       # Web 服务 / Web server
├── web_3d_client/    # Web 前端 / Web frontend
├── tests/            # 单元测试 / Unit tests
├── game.py           # 主入口 / Main entry
└── main.py           # 演示入口 / Demo entry
```

---

## 配置说明 / Configuration

编辑 `config/game_config.yaml` 调整设置：

Edit `config/game_config.yaml` to adjust settings:

```yaml
# Web 3D 服务配置 / Web 3D server config
web_3d_config:
  host: "0.0.0.0"
  port: 8080
  auto_open_browser: true  # 自动打开浏览器 / Auto open browser

# Agent 配置在 / Agent configs in:
# - config/agent1_config.yaml
# - config/agent2_config.yaml
```

---

## 开发模式 / Development Mode

如需前端开发热更新 / For frontend hot-reload development:

```bash
cd web_3d_client
npm run dev
```

然后另开终端运行 / Then run in another terminal:

```bash
python game.py
```

---

## 支持的模型 / Supported Models

| 提供商 / Provider | 配置项 / Config Key | 说明 / Notes |
|------------------|--------------------|--------------|
| DeepSeek | `deepseek` | 默认推荐 / Recommended |
| MiMo | `mimo` | 小米 AI |
| MiniMax | `minimax` | MiniMax API |

在 `config/agent*.yaml` 中修改 `provider` 切换模型。

Change `provider` in `config/agent*.yaml` to switch models.
