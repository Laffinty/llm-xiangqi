# LLM-Xiangqi / 中国象棋 LLM 对战框架

基于 LLM Agent 的中国象棋对战框架，支持多种 LLM 提供者（DeepSeek、MiniMax、MiMo 等）。内置完整的象棋规则引擎、3D 可视化界面以及灵活的多 Agent 对战架构。

---

## 特性

- **模块化 Agent 架构**：统一的 `LLMAgent` 类 + 可插拔适配器
- **双协议支持**：OpenAI 兼容 + Anthropic 兼容协议
- **完整的规则引擎**：棋子移动验证、将军/应将检测、胜负判定
- **3D 可视化**：pyglet/OpenGL 原生界面 + Three.js Web 界面
- **MCP Tools**：支持通过 MCP 协议扩展 Agent 工具能力

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 API Keys

**推荐：使用环境变量**

```bash
# Linux/macOS
export DEEPSEEK_API_KEY="sk-your-key"
export MIMO_API_KEY="sk-your-key"

# Windows PowerShell
$env:DEEPSEEK_API_KEY="sk-your-key"
```

**或：编辑配置文件**

修改 `config/agent1_config.yaml` 和 `config/agent2_config.yaml`：

```yaml
llm:
  provider: "deepseek"
  api_key: "${DEEPSEEK_API_KEY}"  # 或直接使用 "sk-your-key"
```

### 3. 运行对战

```bash
python game.py              # 默认对战
python game.py --turns 200  # 指定最大回合数
```

---

## 支持的 LLM 提供商

| Provider | Adapter | Protocol | Default Model |
|----------|---------|----------|---------------|
| `deepseek` | `DeepSeekAdapter` | OpenAI | `deepseek-chat` |
| `mimo` | `MiMoAdapter` | OpenAI | `mimo-v2-pro` |
| `minimax` | `MiniMaxAdapter` | Anthropic | `MiniMax-M2.7` |

接入新 LLM 只需继承 `OpenAICompatibleAdapter` 或 `AnthropicCompatibleAdapter`，详见 [API 文档](docs/api-standard.md)。

---

## 项目结构

```
llm-xiangqi/
├── config/              # 配置文件（Agent、游戏设置）
├── prompts/             # System prompts
├── src/
│   ├── agents/          # Agent 实现
│   ├── core/            # 核心引擎（裁判、控制器）
│   ├── gui/             # 3D 可视化（pyglet）
│   ├── llm_adapters/    # LLM 适配器
│   └── web_3d/          # Web 3D 服务器
├── web_3d_client/       # Web 3D 前端（Three.js）
├── docs/
│   ├── api-standard.md  # API 详细文档
│   ├── CODE_REVIEW_REPORT.md    # 代码审查报告
│   ├── OPTIMIZATION_PLAN.md     # 优化计划
│   └── FIXES_APPLIED.md         # 修复记录
├── tests/               # 单元测试
├── game.py              # 对战入口
└── main.py              # 演示入口
```

---

## Web 3D 可视化

```bash
cd web_3d_client
npm install
npm run dev    # http://localhost:5173
```

---

## 文档

| 文档 | 说明 |
|------|------|
| [api-standard.md](docs/api-standard.md) | API 规范、数据结构、接入指南 |
| [CODE_REVIEW_REPORT.md](docs/CODE_REVIEW_REPORT.md) | 代码审查报告 |
| [OPTIMIZATION_PLAN.md](docs/OPTIMIZATION_PLAN.md) | 优化路线图 |
| [FIXES_APPLIED.md](docs/FIXES_APPLIED.md) | 已应用的修复 |

---

## 测试

```bash
python -m pytest tests/ -v
```
