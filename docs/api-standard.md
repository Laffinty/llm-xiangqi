# LLM-Xiangqi 统一通信 API 标准

> 版本: 0.2.0
> 最后更新: 2026-03-27

本文档定义主程序（Game Controller / Agent）与 LLM 适配器（Adapter）之间的统一通信契约，确保任意 LLM 后端均可无缝接入。

---

## 1. 架构概览

### 1.1 组件总览

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
│          │                               │                  │
│  ┌───────┴──────────┐        ┌───────────┴──────────┐      │
│  │OpenAICompatible  │        │AnthropicCompatible   │      │
│  │Adapter (base)    │        │Adapter (base)        │      │
│  └───────┬──────────┘        └───────────┬──────────┘      │
│      ┌───┴───┐                      ┌────┴────┐            │
│      │       │                      │         │            │
│ ┌────┴──┐┌───┴───┐            ┌────┴───┐     │            │
│ │DeepSeek││ MiMo  │            │MiniMax │     │            │
│ │Adapter ││Adapter│            │Adapter │     │            │
│ └───┬────┘└───┬───┘            └───┬────┘     │            │
└─────┼─────────┼────────────────────┼──────────┼────────────┘
      │         │                    │          │
  OpenAI API  OpenAI API        Anthropic API (SDK)
```

### 1.2 适配器继承层级

```
BaseLLMAdapter (ABC)                    ← src/llm_adapters/base_adapter.py
  ├── OpenAICompatibleAdapter           ← src/llm_adapters/openai_base_adapter.py
  │     ├── DeepSeekAdapter             ← src/llm_adapters/deepseek_adapter.py
  │     └── MiMoAdapter                 ← src/llm_adapters/mimo_adapter.py
  └── AnthropicCompatibleAdapter        ← src/llm_adapters/anthropic_base_adapter.py
        └── MiniMaxAdapter              ← src/llm_adapters/minimax_adapter.py
```

**设计原则**: 协议级公共逻辑（消息格式转换、重试策略、响应解析）由协议基类实现；具体适配器只需覆盖默认的 `model` 和 `base_url`。

### 1.3 数据流

```
GameState → LLMAgent.think() → [PromptBuilder → Adapter.chat()] → AgentResult
                   │                       │
                   │                 LLMResponse
                   │                       │
                   └── ToolExecutor ← tool_calls ┘
```

---

## 2. 核心数据结构

### 2.1 GameState（游戏状态）

主程序传递给 Agent 的完整棋局信息。

```python
@dataclass
class GameState:
    turn: str                        # 当前方: "Red" | "Black"
    fen: str                         # FEN局面字符串
    ascii_board: str                 # ASCII棋盘渲染
    legal_moves: List[str]           # ICCS合法走步列表, 如 ["h2e2", "b0c2", ...]
    legal_moves_count: int           # 合法走步数量
    game_history: List[str]          # 完整走棋历史
    last_move: Optional[str]         # 上一步走步 (ICCS)
    last_move_by: Optional[str]      # 上一步执行者 (Agent名称)
    phase: GamePhase                 # 游戏阶段枚举
    result: GameResult               # 游戏结果枚举
    result_reason: Optional[str]     # 结束原因
```

**序列化格式 (to_dict)**:
```json
{
  "turn": "Red",
  "fen": "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1",
  "ascii_board": "  a b c d e f g h i\n9 r n b a k a b n r\n...",
  "legal_moves": ["h0g2", "h0i2", "b0c2", "b0a2", ...],
  "legal_moves_count": 44,
  "game_history": ["h2e2", "h7e7"],
  "last_move": "h7e7",
  "last_move_by": "Agent2",
  "phase": "red_to_move",
  "result": "in_progress",
  "result_reason": null
}
```

### 2.2 枚举定义

```python
class GamePhase(Enum):
    NOT_STARTED   = "not_started"
    RED_TO_MOVE   = "red_to_move"
    BLACK_TO_MOVE = "black_to_move"
    GAME_OVER     = "game_over"

class GameResult(Enum):
    RED_WIN     = "red_win"
    BLACK_WIN   = "black_win"
    DRAW        = "draw"
    IN_PROGRESS = "in_progress"

class AgentStatus(Enum):
    IDLE         = "idle"
    THINKING     = "thinking"
    WAITING_TOOL = "waiting_tool"
    DONE         = "done"
    ERROR        = "error"
```

### 2.3 AgentResult（Agent 决策结果）

Agent 返回给主程序的决策产出。

```python
@dataclass
class AgentResult:
    success: bool                    # 是否成功产出走步
    move: Optional[str] = None       # ICCS走步, 如 "h2e2"
    thought: Optional[str] = None    # LLM思考过程
    error: Optional[str] = None      # 错误信息 (success=False时)
    tool_results: List[Dict] = []    # MCP工具调用结果列表
```

**示例**:
```json
{
  "success": true,
  "move": "h2e2",
  "thought": "分析当前局面，中炮开局对敌方形成压制...",
  "error": null,
  "tool_results": [
    {
      "tool": "validate_and_explain",
      "arguments": {"fen": "...", "move": "h2e2"},
      "result": {"success": true, "valid": true, "explanation": "..."}
    }
  ]
}
```

### 2.4 MoveResult（走步执行结果）

主程序执行走步后的返回值。

```python
@dataclass
class MoveResult:
    success: bool                    # 是否执行成功
    move: Optional[str] = None       # 执行的ICCS走步
    thought: Optional[str] = None    # Agent思考过程 (透传)
    error: Optional[str] = None      # 错误信息
    new_fen: Optional[str] = None    # 走步后的新FEN
```

### 2.5 ValidationResult（验证结果）

```python
@dataclass
class ValidationResult:
    is_valid: bool                   # 是否合法
    error_message: Optional[str]     # 错误信息
    explanation: Optional[str]       # 详细解释
```

---

## 3. LLM 适配器层 API

### 3.1 BaseLLMAdapter（适配器基类接口）

所有 LLM 适配器必须实现的统一接口。

```python
class BaseLLMAdapter(ABC):
    """LLM适配器基类"""

    def __init__(
        self,
        api_key: str,            # API密钥
        model: str,              # 模型标识
        base_url: str,           # API端点
        timeout: int = 30,       # 请求超时(秒)
        max_retries: int = 3,    # 最大重试次数
        temperature: float = 0.7,# 生成温度
        max_tokens: int = 2048   # 最大输出token数
    ): ...

    @abstractmethod
    async def chat(
        self,
        messages: List[Dict[str, str]],  # 消息列表
        tools: Optional[List[Dict]] = None,  # MCP工具定义
        **kwargs                           # 扩展参数
    ) -> LLMResponse: ...

    @abstractmethod
    async def close(self): ...

    def build_messages(
        self,
        system_prompt: str,
        user_content: str,
        history: Optional[List[Dict[str, str]]] = None
    ) -> List[Dict[str, str]]:
        """构建消息列表（便捷方法）"""
        ...
```

#### `chat()` 方法

**输入 messages 格式**:
```python
[
    {"role": "system", "content": "你是一位象棋大师..."},
    {"role": "user",   "content": "# 当前局面\n回合: Red\n..."},
    {"role": "assistant", "content": "{\"thought\":\"...\", \"move\":\"h2e2\"}"},
    {"role": "user",   "content": "【系统纠错】你的上一次输出..."}
]
```

**输入 tools 格式** (OpenAI Function Calling Schema):
```python
[
    {
        "type": "function",
        "function": {
            "name": "validate_and_explain",
            "description": "验证走步并给出解释",
            "parameters": {
                "type": "object",
                "properties": {
                    "fen":  {"type": "string", "description": "当前局面FEN"},
                    "move": {"type": "string", "description": "要验证的ICCS走步"}
                },
                "required": ["fen", "move"]
            }
        }
    }
]
```

**输出**: `LLMResponse`

#### `close()` 方法

关闭底层 HTTP 客户端连接，释放资源。适配器析构时应自动调用。

### 3.2 LLMResponse（LLM 响应）

适配器必须将不同 LLM 的原始响应统一为此格式。

```python
@dataclass
class LLMResponse:
    content: str                             # 文本内容 (必填)
    thought: Optional[str] = None            # 思维链/推理过程
    tool_calls: Optional[List[Dict]] = None  # 工具调用列表
    raw_response: Any = None                 # 原始响应对象 (调试用)

    def has_tool_calls(self) -> bool:
        return self.tool_calls is not None and len(self.tool_calls) > 0
```

**tool_calls 格式** (统一后):
```python
[
    {
        "name": "validate_and_explain",          # 工具名称
        "arguments": {"fen": "...", "move": "h2e2"}  # 工具参数 (已解析为dict)
    }
]
```

### 3.3 适配器职责矩阵

| 职责 | DeepSeek | MiMo | MiniMax |
|------|----------|------|---------|
| 协议基类 | OpenAICompatible | OpenAICompatible | AnthropicCompatible |
| 协议 | OpenAI | OpenAI | Anthropic |
| 提取 `content` | `message.content` | `message.content` | `text` block |
| 提取 `thought` | `reasoning_content` | `reasoning_content` | `thinking` block |
| 提取 `tool_calls` | `message.tool_calls` | `message.tool_calls` | `tool_use` block |
| system消息处理 | messages列表中 | messages列表中 | 提取为 `system` 参数 |
| 重试策略 | 指数退避 | 指数退避 | 指数退避 + 超时递增 |
| SDK | openai (async) | openai (async) | anthropic (sync→async) |

---

## 4. 协议原理详解

### 4.1 OpenAI 兼容协议 (`OpenAICompatibleAdapter`)

适用于使用 OpenAI Chat Completions API 格式的服务（DeepSeek、MiMo 等）。

#### 客户端初始化

```python
from openai import AsyncOpenAI

self.client = AsyncOpenAI(
    api_key=api_key,
    base_url=base_url,
    timeout=timeout
)
```

#### 请求流程

1. **参数构建**: `messages` 直接透传，`tools` 直接透传（OpenAI Function Calling Schema）
2. **API 调用**: `response = await self.client.chat.completions.create(**params)`
3. **重试策略**: 指数退避（`2^attempt` 秒），遇到 `TimeoutError` 或其他异常时重试
4. **响应解析**:
   - `content` ← `choice.message.content`
   - `thought` ← `choice.message.reasoning_content`（推理模型特有字段）
   - `tool_calls` ← `choice.message.tool_calls`（`arguments` JSON 字符串解析为 dict）

#### 消息格式

```python
# 直接使用标准 OpenAI 格式
messages = [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."},
]
# system 消息作为 messages 列表中的条目
```

#### 子类实现示例

```python
class DeepSeekAdapter(OpenAICompatibleAdapter):
    def __init__(self, api_key, model="deepseek-chat",
                 base_url="https://api.deepseek.com", **kwargs):
        super().__init__(api_key=api_key, model=model, base_url=base_url, **kwargs)
```

子类只需指定默认的 `model` 和 `base_url`，所有协议逻辑由基类处理。

### 4.2 Anthropic 兼容协议 (`AnthropicCompatibleAdapter`)

适用于使用 Anthropic Messages API 格式的服务（MiniMax 等）。

#### 客户端初始化

```python
import os
import anthropic

os.environ["ANTHROPIC_BASE_URL"] = base_url
os.environ["ANTHROPIC_API_KEY"] = api_key
self.client = anthropic.Anthropic(timeout=timeout)
```

Anthropic SDK 通过环境变量读取 base_url 和 api_key，因此需要在创建客户端前设置。

#### 请求流程

1. **system 消息提取**: 从 `messages` 中找到 `role="system"` 的条目，提取为独立参数
2. **消息格式转换**: 将 `str` content 转换为 Anthropic content-blocks 数组：
   ```python
   # 原始: {"role": "user", "content": "你好"}
   # 转换: {"role": "user", "content": [{"type": "text", "text": "你好"}]}
   ```
3. **参数构建**:
   ```python
   params = {
       "model": self.model,
       "max_tokens": max_tokens,
       "temperature": temperature,
       "system": system_msg,        # 独立的 system 参数
       "messages": anthropic_messages,
       "tools": tools               # 可选
   }
   ```
4. **同步 SDK 异步包装**: Anthropic SDK 是同步的，通过 `run_in_executor` + `asyncio.wait_for` 包装为异步调用
5. **递增超时重试**: 每次超时后超时值乘以 1.5（上限 60 秒），同时指数退避
6. **响应解析**:
   - 遍历 `response.content` 块列表：
     - `block.type == "thinking"` → `thought`
     - `block.type == "text"` → `content`
     - `block.type == "tool_use"` → `tool_calls`（`{name, arguments}`）

#### 消息格式

```python
# 原始 messages（与 OpenAI 格式相同）
messages = [
    {"role": "system", "content": "你是一位象棋大师..."},
    {"role": "user", "content": "当前局面..."},
]

# 基类自动转换为 Anthropic 格式:
# 1. system 提取 → params["system"] = "你是一位象棋大师..."
# 2. 剩余消息 → content-blocks 数组
```

#### 子类实现示例

```python
class MiniMaxAdapter(AnthropicCompatibleAdapter):
    def __init__(self, api_key, model="MiniMax-M2.7",
                 base_url="https://api.minimaxi.com/anthropic", **kwargs):
        super().__init__(api_key=api_key, model=model, base_url=base_url, **kwargs)
```

### 4.3 协议对比总结

| 特性 | OpenAI 兼容 | Anthropic 兼容 |
|------|------------|---------------|
| SDK | `openai.AsyncOpenAI` (原生异步) | `anthropic.Anthropic` (同步→异步包装) |
| API 端点 | `chat.completions.create()` | `messages.create()` |
| system 消息 | messages 列表中的条目 | 独立 `system` 参数 |
| 消息 content 格式 | 直接 `str` | `[{"type": "text", "text": str}]` 数组 |
| thought 提取 | `reasoning_content` 属性 | `thinking` content block |
| tool_calls 提取 | `message.tool_calls` 列表 | `tool_use` content block |
| 超时处理 | 固定超时 + 指数退避 | 递增超时 (1.5x, cap 60s) + 指数退避 |

---

## 5. Agent 层 API

### 5.1 通用 LLMAgent

项目使用单一的通用 `LLMAgent` 类，通过注入不同的适配器适配任意 LLM 后端，消除了原来 agent_deepseek / agent_glm / agent_minimax 的重复代码。

```python
class LLMAgent(BaseAgent):
    """通用 LLM Agent，通过注入的 adapter 适配任意 LLM 后端"""

    async def think(self, game_state: Dict[str, Any]) -> AgentResult:
        # 1. PromptBuilder.build_game_prompt() 构建消息
        # 2. adapter.chat() 调用 LLM
        # 3. 如果有 tool_calls → execute_tool_loop()
        # 4. _extract_move() 提取走步
        # 5. 返回 AgentResult
```

### 5.2 BaseAgent（Agent 基类接口）

```python
class BaseAgent(ABC):
    def __init__(self, config: AgentConfig): ...

    @abstractmethod
    async def think(self, game_state: Dict[str, Any]) -> AgentResult:
        """核心决策方法

        Args:
            game_state: GameState.to_dict() 产出的字典

        Returns:
            AgentResult: 包含走步和思考过程
        """
        ...

    async def execute_tool_loop(
        self,
        initial_response: LLMResponse,
        tool_executor: ToolExecutor,
        game_state: Dict[str, Any]
    ) -> AgentResult:
        """MCP工具调用循环 (最多3轮)"""
        ...

    def add_correction_feedback(
        self,
        error_msg: str,
        legal_moves: List[str] = None
    ) -> None:
        """注入纠错反馈到prompt历史"""
        ...

    def reset(self) -> None:
        """重置Agent状态和对话历史"""
        ...

    def get_status(self) -> AgentStatus:
        """获取当前状态"""
        ...
```

### 5.3 AgentConfig（Agent 配置）

```python
@dataclass
class AgentConfig:
    name: str                           # Agent名称 (如 "Agent1")
    color: str                          # 执棋颜色 ("Red" | "Black")
    description: str                    # 描述
    llm_adapter: BaseLLMAdapter         # LLM适配器实例
    system_prompt: str                  # 系统提示词
    max_retries: int = 3                # 最大重试次数
    retry_delay: int = 2                # 重试间隔(秒)
    use_tools: bool = True              # 是否启用MCP工具
    use_reflection: bool = False        # 是否启用ReflAct反思
```

### 5.4 think() 方法完整流程

```
输入: GameState.to_dict()
  │
  ├── 1. PromptBuilder.build_game_prompt(game_state, player_color)
  │      └── 输出: [{"role":"system",...}, {"role":"user",...}]
  │
  ├── 2. adapter.chat(messages, tools=...)
  │      └── 输出: LLMResponse(content, thought, tool_calls)
  │
  ├── 3. [如果有 tool_calls]
  │      └── execute_tool_loop(response, tool_executor, game_state)
  │            ├── ToolExecutor.execute(name, args) → Dict
  │            ├── PromptBuilder.add_tool_results(results)
  │            ├── [可选] ReflAct 反思
  │            └── adapter.chat() → 直到无tool_calls
  │
  ├── 4. _extract_move(response.content, legal_moves)
  │      └── 正则: \b([a-iA-I][0-9][a-iA-I][0-9])\b
  │      └── 优先匹配 legal_moves 中的走步
  │
  └── 5. 返回 AgentResult(success, move, thought, tool_results)
```

**thought 提取逻辑**: `response.thought or (response.content[:500] if response.content else "")`
- 如果 LLM 返回了独立的 thought（如推理模型的 `reasoning_content`），直接使用
- 否则截取 `content` 前 500 字符作为 thought 备选

---

## 6. 用户调用方法

### 6.1 快速开始

```bash
# 使用默认配置运行对战
python game.py

# 指定最大回合数
python game.py --turns 200
```

### 6.2 配置适配器

项目通过 YAML 配置文件指定每个 Agent 使用的 LLM 后端。

**Agent 配置** (`config/agent1_config.yaml`):
```yaml
agent:
  name: "Agent1"
  color: "Red"
  description: "红方Agent"
  system_prompt_file: "prompts/agent_default.txt"
  max_retries: 3
  use_tools: false
  use_reflection: false

llm:
  provider: "deepseek"          # 适配器标识
  model: "deepseek-chat"
  api_key: "sk-xxx"
  base_url: "https://api.deepseek.com"
  temperature: 0.7
  max_tokens: 2048
  timeout: 30
```

### 6.3 支持的 LLM Provider

| provider | 适配器类 | 协议 | 默认模型 | 默认 base_url |
|----------|---------|------|---------|--------------|
| `deepseek` | `DeepSeekAdapter` | OpenAI | `deepseek-chat` | `https://api.deepseek.com` |
| `mimo` | `MiMoAdapter` | OpenAI | `mimo-v2-pro` | `https://api.xiaomimimo.com/v1` |
| `minimax` | `MiniMaxAdapter` | Anthropic | `MiniMax-M2.7` | `https://api.minimaxi.com/anthropic` |

### 6.4 ADAPTER_MAP 机制

`game.py` 使用 `ADAPTER_MAP` 字典将 provider 名称映射到适配器类：

```python
ADAPTER_MAP = {
    "deepseek": DeepSeekAdapter,
    "mimo":     MiMoAdapter,
    "minimax":  MiniMaxAdapter,
}
```

`_create_adapter()` 根据配置中的 `provider` 字段查找适配器类并实例化：

```python
def _create_adapter(llm_config: dict) -> BaseLLMAdapter:
    provider = llm_config["provider"]
    adapter_cls = ADAPTER_MAP.get(provider)
    if not adapter_cls:
        raise ValueError(f"Unknown LLM provider: '{provider}'. Supported: {list(ADAPTER_MAP.keys())}")
    return adapter_cls(
        api_key=llm_config["api_key"],
        model=llm_config["model"],
        base_url=llm_config["base_url"],
        timeout=llm_config.get("timeout", 30),
        max_retries=llm_config.get("max_retries", 3),
        temperature=llm_config.get("temperature", 0.7),
        max_tokens=llm_config.get("max_tokens", 2048),
    )
```

### 6.5 代码中直接使用适配器

```python
from src.llm_adapters.deepseek_adapter import DeepSeekAdapter
from src.llm_adapters.mimo_adapter import MiMoAdapter
from src.llm_adapters.minimax_adapter import MiniMaxAdapter

# 创建适配器实例
adapter = DeepSeekAdapter(
    api_key="sk-xxx",
    model="deepseek-chat",
    base_url="https://api.deepseek.com",
    temperature=0.7,
    max_tokens=2048,
)

# 发送聊天请求
response = await adapter.chat(
    messages=[
        {"role": "system", "content": "你是一位象棋大师。"},
        {"role": "user", "content": "当前局面: ..."},
    ],
    tools=None,  # 可选 MCP 工具定义
)

print(response.content)     # 文本回复
print(response.thought)     # 推理过程（如有）
print(response.tool_calls)  # 工具调用（如有）
```

---

## 7. MCP 工具层 API

### 7.1 BaseTool（工具基类）

```python
class BaseTool(ABC):
    def __init__(self, name: str, description: str): ...

    @abstractmethod
    async def execute(self, **kwargs) -> Dict[str, Any]: ...

    def get_schema(self) -> Dict[str, Any]: ...
```

### 7.2 ToolExecutor（工具执行器）

```python
class ToolExecutor:  # 单例
    def register(self, name: str, func: Callable): ...

    async def execute(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Dict[str, Any]: ...

    def get_available_tools(self) -> List[str]: ...
```

### 7.3 标准工具定义

#### evaluate_position

| 字段 | 值 |
|------|-----|
| name | `evaluate_position` |
| 调用方 | LLM (通过 tool_calls) |
| 参数 | `fen: str` (必填), `depth: int` (可选, 默认15) |
| 返回 | `{success: bool, score: float, best_move: str, ...}` |
| 状态 | **未实现** (需接入 Pikafish 引擎) |

#### query_opening_book

| 字段 | 值 |
|------|-----|
| name | `query_opening_book` |
| 调用方 | LLM (通过 tool_calls) |
| 参数 | `fen: str` (必填) |
| 返回 | `{success: bool, fen: str, moves: list, evaluation: str}` |
| 状态 | **Stub** (返回空列表) |

#### validate_and_explain

| 字段 | 值 |
|------|-----|
| name | `validate_and_explain` |
| 调用方 | LLM (通过 tool_calls) |
| 参数 | `fen: str` (必填), `move: str` (必填) |
| 返回 | `{success: bool, fen: str, move: str, valid: bool, explanation: str}` |
| 状态 | **已实现** |

---

## 8. ICCS 坐标规范

所有走步使用 ICCS (International Computer Chinese Chess Society) 坐标格式：

```
格式: [源列][源行][目标列][目标行]
示例: "h2e2" = 从 h2 走到 e2

列: a-i (从左到右, 对应列0-8)
行: 0-9 (从下到上, 对应行0-9)
       ┌─────────────────────┐
    9  │ r n b a k a b n r   │  ← 黑方底线
    8  │ . . . . . . . . .   │
    7  │ . c . . . . . c .   │
    6  │ p . p . p . p . p   │
    5  │ . . . . . . . . .   │
    ───│─ ─ 楚 河 ─ 汉 界 ─ ─│───
    4  │ . . . . . . . . .   │
    3  │ P . P . P . P . P   │
    2  │ . C . . . . . C .   │
    1  │ . . . . . . . . .   │
    0  │ R N B A K A B N R   │  ← 红方底线
       └─────────────────────┘
         a b c d e f g h i
```

---

## 9. 接入新 LLM 适配器指南

### 9.1 判断协议类型

首先确认目标 LLM 服务使用的 API 协议：

- **OpenAI 兼容**: 使用 `chat.completions.create()` 端点，消息格式为 OpenAI 标准 → 继承 `OpenAICompatibleAdapter`
- **Anthropic 兼容**: 使用 `messages.create()` 端点，消息格式为 Anthropic content-blocks → 继承 `AnthropicCompatibleAdapter`
- **其他协议**: 直接继承 `BaseLLMAdapter`，自行实现 `chat()` 和 `close()`

### 9.2 OpenAI 兼容适配器（推荐）

```python
from src.llm_adapters.openai_base_adapter import OpenAICompatibleAdapter

class NewLLMAdapter(OpenAICompatibleAdapter):
    def __init__(
        self,
        api_key: str,
        model: str = "default-model-name",
        base_url: str = "https://api.newllm.com/v1",
        **kwargs
    ):
        super().__init__(
            api_key=api_key,
            model=model,
            base_url=base_url,
            **kwargs
        )
```

只需指定默认的 `model` 和 `base_url`，所有协议逻辑（客户端创建、消息透传、重试、响应解析）由 `OpenAICompatibleAdapter` 基类处理。

### 9.3 Anthropic 兼容适配器

```python
from src.llm_adapters.anthropic_base_adapter import AnthropicCompatibleAdapter

class NewLLMAdapter(AnthropicCompatibleAdapter):
    def __init__(
        self,
        api_key: str,
        model: str = "default-model-name",
        base_url: str = "https://api.newllm.com/anthropic",
        **kwargs
    ):
        super().__init__(
            api_key=api_key,
            model=model,
            base_url=base_url,
            **kwargs
        )
```

### 9.4 自定义协议适配器

如果不兼容以上两种协议，直接继承 `BaseLLMAdapter`：

```python
from src.llm_adapters.base_adapter import BaseLLMAdapter, LLMResponse

class NewLLMAdapter(BaseLLMAdapter):

    async def chat(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict]] = None,
        **kwargs
    ) -> LLMResponse:
        # 1. 将 messages 转换为目标API格式
        # 2. 调用目标API
        # 3. 将原始响应映射为 LLMResponse:
        #    - content: 文本回复
        #    - thought: 推理过程 (如有)
        #    - tool_calls: [{"name": str, "arguments": dict}, ...]
        ...

    async def close(self):
        # 释放HTTP客户端资源
        ...
```

### 9.5 注册适配器

在 `game.py` 的 `ADAPTER_MAP` 中添加新 provider 的映射：

```python
from src.llm_adapters.new_llm_adapter import NewLLMAdapter

ADAPTER_MAP = {
    "deepseek": DeepSeekAdapter,
    "mimo":     MiMoAdapter,
    "minimax":  MiniMaxAdapter,
    "new_llm":  NewLLMAdapter,  # 新增
}
```

配置文件 `config/agentX_config.yaml`:
```yaml
llm:
  provider: "new_llm"
  model: "model-name"
  api_key: "sk-xxx"
  base_url: "https://api.example.com"
  temperature: 0.7
  max_tokens: 2048
  timeout: 30
```

---

## 10. Observer API（GUI 通知接口）

```python
class LLMAgentGameController:
    def register_observer(self, callback):
        """注册观察者回调
        callback 签名: callback(move: str, fen: str, is_game_over: bool)
        """

    def unregister_observer(self, callback):
        """注销观察者"""
```

---

## 11. 错误处理约定

| 层级 | 错误场景 | 处理方式 |
|------|---------|---------|
| Adapter | API 超时 | 指数退避重试 (OpenAI) / 递增超时+退避 (Anthropic), 最终 raise |
| Adapter | API 返回格式异常 | 返回 `LLMResponse(content="", thought=None, tool_calls=None)` |
| Agent | LLM 输出非法走步 | `add_correction_feedback()` + 重试 (最多3次) |
| Agent | LLM 未输出可解析的走步 | 返回 `AgentResult(success=False, error="...")` |
| Controller | 走步不在 legal_moves 中 | 返回 `MoveResult(success=False, error="Illegal move: ...")` |
| Tool | 工具执行异常 | 返回 `{success: False, error: str(e)}` |

---

## 12. 配置文件 schema

### Agent 配置 (`config/agentX_config.yaml`)

```yaml
agent:
  name: string               # Agent名称
  color: "Red" | "Black"     # 执棋方
  description: string        # 描述
  system_prompt_file: string # 系统提示词文件路径
  max_retries: int           # 默认 3
  retry_delay: int           # 默认 2
  use_tools: bool            # 默认 false
  use_reflection: bool       # 默认 false

llm:
  provider: string           # 适配器标识 (deepseek/mimo/minimax)
  model: string              # 模型名称
  api_key: string            # API密钥 (支持 ${ENV_VAR} 引用)
  base_url: string           # API端点
  temperature: float         # 默认 0.7
  max_tokens: int            # 默认 2048
  timeout: int               # 默认 30 (秒)
```

### 游戏配置 (`config/game_config.yaml`)

```yaml
game:
  initial_fen: string        # 初始FEN
  max_turns: int             # 最大回合数, 默认 200
  time_control:
    enabled: bool            # 是否启用时限
    seconds_per_turn: int    # 每步秒数

mcp_tools:
  enabled: bool              # 是否启用MCP工具
  tools_dir: string          # 开局库目录
  pikafish:
    enabled: bool            # 是否启用Pikafish
    path: string             # 引擎路径
    depth: int               # 搜索深度
    threads: int             # 线程数

logging:
  level: string              # 日志级别
  file: string               # 日志文件路径
  console: bool              # 是否输出到控制台
```
