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

## 支持模型

| 提供商 | 默认模型 |
|--------|----------|
| DeepSeek | deepseek-chat |
| MiMo | mimo-v2-pro |
| MiniMax | MiniMax-M2.7 |

## Supported Models

| Provider | Default Model |
|----------|---------------|
| DeepSeek | deepseek-chat |
| MiMo | mimo-v2-pro |
| MiniMax | MiniMax-M2.7 |

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

## Web 可视化

```bash
cd web_3d_client && npm install && npm run dev
```

访问 http://localhost:5173

## Web 3D

```bash
cd web_3d_client && npm install && npm run dev
```

Access at http://localhost:5173

---

## 测试

```bash
python -m pytest tests/ -v
```

## Testing

```bash
python -m pytest tests/ -v
```

---

## 许可证

Apache 2.0

## License

Apache 2.0
