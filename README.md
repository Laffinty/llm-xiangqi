# LLM 中国象棋对战程序 (LLM Xiangqi Arena)

基于大语言模型的中国象棋对战程序，支持多种 LLM Provider。

## 功能特性

- 中国象棋完整棋规实现 (包括将军、应将、困毙判断)
- 支持多种 LLM Provider: DeepSeek, MiniMax, GLM, MiMo
- 支持 Referee Agent 校验走步合法性
- MCP Tools 集成 (棋谱分析、局面评估)
- 完整的游戏状态序列化和日志记录

## 项目结构

```
llm-xiangqi/
├── config/                 # 配置文件
│   ├── agent1_config.yaml  # Agent1 (红方) 配置
│   ├── agent2_config.yaml  # Agent2 (黑方) 配置
│   ├── referee_config.yaml # 裁判配置
│   └── game_config.yaml    # 游戏全局配置
├── prompts/                # System prompts
│   ├── agent_system.txt
│   └── referee_system.txt
├── src/
│   ├── agents/             # Agent 实现
│   ├── core/               # 核心引擎
│   ├── llm_adapters/       # LLM 适配器
│   ├── mcp_tools/          # MCP Tools
│   └── utils/              # 工具函数
├── tests/                  # 测试
├── main.py                 # 入口文件
└── game.py                 # 游戏对战入口
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 API Keys

编辑配置文件，填入你的 API Key:

- `config/agent1_config.yaml` - 红方 Agent
- `config/agent2_config.yaml` - 黑方 Agent
- `config/referee_config.yaml` - 裁判 Agent

### 3. 运行演示

```bash
python main.py
```

## 配置说明

### LLM Provider

| Provider | Model | Config Key |
|----------|-------|------------|
| DeepSeek | deepseek-chat | `provider: deepseek` |
| MiniMax | MiniMax-M2.7 | `provider: minimax` |
| GLM | glm-4 | `provider: glm` |
| MiMo | mimo-v2-pro | `provider: mimo` |

### Agent 配置

```yaml
agent:
  name: "Agent1"
  color: "Red"          # Red 或 Black
  use_tools: false
  use_reflection: false

llm:
  provider: "deepseek"
  api_key: "YOUR_API_KEY"
  temperature: 0.7
  max_tokens: 2048
```

## 开发

### 运行测试

```bash
pytest
```

### 代码格式化

```bash
ruff check .
ruff format .
```

## License

MIT
