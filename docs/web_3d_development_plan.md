# Web 3D 中国象棋对战平台 - 详细开发方案

> 版本: 1.1.0
> 最后更新: 2026-03-29

---

## 1. 项目概述

### 1.1 目标

构建基于 Web 技术的 3D 中国象棋对战可视化平台，通过浏览器提供现代化的观战体验。

**关键约束**: Web 3D 模块**完全由 `game_config.yaml` 配置控制**，不单独操作启动，随主程序生命周期管理。

### 1.2 技术栈

```
┌─────────────────────────────────────────────────────────┐
│                     前端技术栈                           │
├─────────────────────────────────────────────────────────┤
│  3D渲染引擎:   Three.js r171+ (WebGPU / WebGL 2.0)     │
│  模型格式:     glTF 2.0 (.glb/.gltf)                    │
│  着色器语言:   TSL (Three Shader Language)              │
│  构建工具:     Vite 5+                                  │
│  状态管理:    原生 JavaScript (无需额外库)               │
│  通信协议:     WebSocket (原生 API)                     │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│                     后端技术栈                           │
├─────────────────────────────────────────────────────────┤
│  Web框架:      FastAPI (内嵌到主程序)                    │
│  ASGI服务器:   uvicorn (后台线程运行)                   │
│  WebSocket:    FastAPI 内置 WebSocket 支持              │
│  数据验证:     Pydantic v2                              │
│  异步任务:     asyncio                                  │
└─────────────────────────────────────────────────────────┘
```

### 1.3 核心特性

- WebGPU 渲染（自动降级 WebGL 2.0）
- glTF 模型加载（棋盘、棋子）
- TSL 材质特效（选中高亮、移动轨迹）
- 实时 WebSocket 状态同步
- 服务端权威架构
- 阴影与基础光照
- 配置驱动启动（无需单独操作）
- WebSocket 断线自动重连与状态重同步

---

## 2. 系统架构设计

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         客户端 (Browser)                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │   UI Layer   │  │  Game State  │  │   3D Render Engine   │  │
│  │  (Vanilla)   │◄─┤   Manager    │◄─┤  (Three.js WebGPU)   │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
│          │                │                     │                │
│          └────────────────┼─────────────────────┘                │
│                           │                                      │
│                    ┌──────▼──────┐                              │
│                    │  WebSocket  │◄── 断线重连 + 状态重同步      │
│                    │   Client    │                              │
│                    └──────┬──────┘                              │
└───────────────────────────┼─────────────────────────────────────┘
                            │
                            ▼ WebSocket
┌───────────────────────────┼─────────────────────────────────────┐
│                      服务端 (Python)                             │
│  ┌────────────────────────┼──────────────────────────────────┐ │
│  │                    game.py (主程序)                          │ │
│  │  ┌──────────────┐  ┌───▼──────────┐  ┌────────────────┐   │ │
│  │  │GameController│  │ Web 3D Server│  │   LLM Agent    │   │ │
│  │  └──────┬───────┘  │  (FastAPI)   │  │    Battle      │   │ │
│  │         │          └─────┬────────┘  └────────────────┘   │ │
│  │         │                │                                  │ │
│  │         │          ┌─────┴──────┐                          │ │
│  │         │          │ WebSocket  │◄── 观战客户端 (Browser)   │ │
│  │         │          │  Manager   │                          │ │
│  │         │          └────────────┘                          │ │
│  │         │                                                   │ │
│  │    ┌────┴────┐                                              │ │
│  │    │ Referee │                                              │ │
│  │    │ Engine  │                                              │ │
│  │    └─────────┘                                              │ │
│  └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 生命周期管理

Web 3D Server 随主程序启动和关闭，**必须在 `asyncio.run()` 的事件循环内启动**：

```python
# game.py 启动流程
async def main():
    config = load_game_config()

    # web_server 必须在事件循环启动后、run_battle 内部初始化
    result = await run_battle(..., gui_config=config.gui)


async def run_battle(agent1, agent2, max_turns, gui_config):
    web_server = None

    if gui_config and gui_config.web_3d:
        web_server = Web3DServer(gui_config.web_3d_config)
        web_server.start()  # 内部用 uvicorn 在独立线程启动

        # 注册 Observer (sync wrapper 包裹 async 广播)
        controller.register_observer(
            make_sync_observer(web_server)
        )

    try:
        result = await controller.run_game(verbose=True)
    finally:
        if web_server:
            web_server.stop()

    return result
```

### 2.3 数据流向

```
1. LLM Agent 计算走法
        │
        ▼
2. Game Controller 验证合法性
        │
        ▼
3. Observer 通知 (sync callback)
        │
        ▼
4. Web3DServer 广播状态 (async, 通过 ensure_future 调度)
        │
        ▼
5. 客户端接收并更新 3D 场景
```

---

## 3. 配置设计

### 3.1 game_config.yaml 更新

```yaml
# config/game_config.yaml

# 游戏全局配置
game:
  initial_fen: "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"
  time_control:
    enabled: false
    seconds_per_turn: 60
  max_turns: 200

# GUI 配置 (控制显示方式)
gui:
  3d: false           # 原生 3D GUI (pyglet)
  web_3d: true        # Web 3D 界面 (浏览器)

  # Web 3D 服务器配置
  web_3d_config:
    host: "0.0.0.0"               # 绑定地址
    port: 8080                    # 服务端口
    auto_open_browser: true       # 自动打开浏览器
    static_dir: "src/web_3d/static"  # 静态文件目录

    # 渲染配置
    rendering:
      shadow_map_size: 2048
      default_camera_position: [8, 12, 12]
      animation_duration: 0.5    # 秒

mcp_tools:
  enabled: true
  tools_dir: "data/opening_books"
  pikafish:
    enabled: false
    path: "engines/pikafish.exe"
    depth: 15
    threads: 4

logging:
  level: "INFO"
  file: "logs/game.log"
  console: true
```

### 3.2 配置加载更新

```python
# src/utils/config_loader.py 新增

@dataclass
class Web3DConfig:
    """Web 3D 配置"""
    host: str = "0.0.0.0"
    port: int = 8080
    auto_open_browser: bool = True
    static_dir: str = "src/web_3d/static"
    shadow_map_size: int = 2048
    animation_duration: float = 0.5

@dataclass
class GUIConfig:
    """GUI配置"""
    enable_3d: bool = False
    web_3d: bool = True
    web_3d_config: Web3DConfig = field(default_factory=Web3DConfig)
```

---

## 4. 通信协议设计

### 4.1 WebSocket 消息协议

#### 消息格式
```typescript
interface WebSocketMessage {
  type: string;      // 消息类型
  timestamp: number; // 服务端时间戳 (ms)
  payload: any;      // 消息体
}
```

#### 协议版本

客户端连接后发送 `client.ready` 时应携带 `protocol_version` 字段，服务端据此进行兼容性检查。

当前版本: `"1.0.0"`

#### 消息类型定义

**服务端 → 客户端**

| Message Type | Description | Payload |
|-------------|-------------|---------|
| `game.init` | 客户端就绪后的完整初始状态 | `WebSocketGameState` |
| `game.move` | 棋子移动（增量更新） | `MoveEvent` |
| `game.game_over` | 游戏结束 | `GameOverEvent` |
| `server.error` | 错误通知 | `{ code: string, message: string }` |

**客户端 → 服务端**

| Message Type | Description | Payload |
|-------------|-------------|---------|
| `client.ready` | 客户端就绪，请求初始状态 | `{ client_id?: string, protocol_version: string }` |
| `client.ping` | 心跳检测 | `{ id: number }` |

> **设计说明**: 去掉了 `game.state_update` 全量推送类型。观战场景下，每次走步发送增量 `game.move` 即可；客户端需要全量状态时发送 `client.ready` 重新获取，避免冗余传输。

#### 错误码定义

| Error Code | Description |
|------------|-------------|
| `PROTOCOL_VERSION_MISMATCH` | 客户端协议版本不兼容 |
| `PARSE_ERROR` | 消息格式解析失败 |
| `INTERNAL_ERROR` | 服务端内部错误 |

### 4.2 数据结构定义

> **注意**: 以下数据结构为 WebSocket 协议专用，与 `src/core/state_serializer.py` 中的核心 `GameState` 是**独立定义**。核心 `GameState` 用于 Agent 交互，WebSocket `GameState` 用于浏览器渲染，两者字段不同。

#### WebSocketGameState (游戏状态 — WebSocket 专用)

```python
@dataclass
class WebSocketGameState:
    """WebSocket 广播用的游戏状态，基于核心 GameState 扩展"""
    turn: Literal["Red", "Black"]           # 与核心 GameState 保持一致，首字母大写
    turn_number: int
    fen: str
    players: dict[Literal["Red", "Black"], PlayerInfo]
    move_history: list[str]                 # ICCS 走步列表
    last_move: Optional[LastMove] = None
    status: Literal["playing", "finished"]
    result: Optional[dict] = None
    result_reason: Optional[str] = None
    legal_moves: list[str] = field(default_factory=list)

@dataclass
class PlayerInfo:
    name: str
    model: str

@dataclass
class LastMove:
    from_pos: str     # ICCS, e.g., "h2"
    to_pos: str       # ICCS, e.g., "e2"
    piece: str        # 棋子字符, e.g., "R"
    captured: Optional[str] = None
```

#### MoveEvent (移动事件)

```python
@dataclass
class MoveEvent:
    move: str              # ICCS 格式, e.g., "h2e2"
    move_cn: Optional[str] = None  # 中文记谱, e.g., "炮二平五" (TODO: 需实现 ICCS→中文转换)
    piece: str             # 移动的棋子
    from_pos: str          # 起始位置 (ICCS)
    to_pos: str            # 目标位置 (ICCS)
    captured: Optional[str] = None
    fen_after: str         # 移动后的 FEN
    turn_number: int
    animation_duration: float = 0.5
```

> **TODO**: `move_cn` 字段需要实现 ICCS 到中文记谱的转换工具（如 "h2e2" → "炮二平五"），当前版本先置为 `null`。

#### GameOverEvent (游戏结束事件)

```python
@dataclass
class GameOverEvent:
    result: str            # "red_win" | "black_win" | "draw"
    result_reason: str     # 结束原因描述
    turn_count: int        # 总回合数
    move_history: list[str]  # 完整走步历史
    winner: Optional[str] = None  # "Red" | "Black" | None (平局)
```

### 4.3 连接与初始化流程

```
客户端                          服务端
  │                               │
  │──── WebSocket Connect ───────►│
  │                               │
  │──── client.ready ────────────►│
  │     { protocol_version,       │
  │       client_id }             │
  │                               │
  │◄─── game.init ───────────────│  发送当前完整状态
  │     (WebSocketGameState)      │
  │                               │
  │                               │── [游戏进行中] ──│
  │                               │                 │
  │◄─── game.move ───────────────│  每步走棋后推送
  │     (MoveEvent)               │
  │                               │
  │                               │── [游戏结束] ────│
  │                               │                 │
  │◄─── game.game_over ──────────│
  │     (GameOverEvent)           │
  │                               │
```

---

## 5. 3D 场景设计

### 5.1 场景层级结构

```
Scene
├── Camera (PerspectiveCamera)
│   └── OrbitControls
├── Lights
│   ├── AmbientLight (环境光, 强度0.4)
│   ├── DirectionalLight (主光源, 产生阴影)
│   └── PointLight (补光)
├── ChessBoard (棋盘)
│   ├── BoardBase (底座)
│   ├── BoardSurface (棋盘面)
│   └── GridLines (楚河汉界、九宫格线)
├── Pieces (棋子容器)
│   ├── RedPieces
│   │   ├── R1, R2 (车)
│   │   ├── H1, H2 (马)
│   │   └── ...
│   └── BlackPieces
│       ├── r1, r2 (车)
│       └── ...
└── Effects (特效容器)
    ├── LastMoveHighlight (最后走法高亮)
    └── SelectedHighlight (选中高亮)
```

### 5.2 glTF 模型规范

**棋盘模型 (`board.glb`)**
```
尺寸: 10 x 11 单位 (对应 9x10 棋路)
原点: 棋盘中心
包含:
  - BoardBase: 底座
  - BoardSurface: 棋盘面，带UV坐标
  - GridLines: 刻线

材质命名:
  - BoardWood: 木质纹理
  - BoardLine: 线条
```

**棋子模型 (`pieces.glb`)**
```
单个棋子尺寸: ~0.8 单位直径，高度 ~0.4 单位
包含7种类型，每种分红黑两色:
  - King (将/帅)
  - Advisor (士/仕)
  - Elephant (象/相)
  - Horse (马/傌)
  - Rook (车/俥)
  - Cannon (炮/砲)
  - Pawn (兵/卒)

材质命名规范:
  - RedPiece_Mat / BlackPiece_Mat: 棋子主体
  - RedText_Mat / BlackText_Mat: 文字
```

#### 程序化棋子 Fallback 方案

在 glTF 模型就绪之前，使用 Three.js 程序化生成棋子作为临时方案：

```javascript
function createPieceMesh(pieceChar, color) {
    const group = new THREE.Group();

    // 底座圆柱
    const baseGeo = new THREE.CylinderGeometry(0.38, 0.4, 0.08, 32);
    const baseMat = new THREE.MeshStandardMaterial({
        color: color === "Red" ? 0xddaa77 : 0x8B7355,
        roughness: 0.3
    });
    const base = new THREE.Mesh(baseGeo, baseMat);
    group.add(base);

    // 主体圆柱
    const bodyGeo = new THREE.CylinderGeometry(0.34, 0.38, 0.28, 32);
    const bodyMat = new THREE.MeshStandardMaterial({
        color: color === "Red" ? 0xf5deb3 : 0xdeb887,
        roughness: 0.4
    });
    const body = new THREE.Mesh(bodyGeo, bodyMat);
    body.position.y = 0.18;
    group.add(body);

    // 文字 (Canvas 纹理)
    const canvas = document.createElement("canvas");
    canvas.width = 128;
    canvas.height = 128;
    const ctx = canvas.getContext("2d");
    ctx.fillStyle = color === "Red" ? "#cc0000" : "#1a1a1a";
    ctx.font = "bold 80px serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(pieceChar, 64, 64);

    const texture = new THREE.CanvasTexture(canvas);
    const textGeo = new THREE.PlaneGeometry(0.5, 0.5);
    const textMat = new THREE.MeshBasicMaterial({
        map: texture, transparent: true
    });
    const textMesh = new THREE.Mesh(textGeo, textMat);
    textMesh.rotation.x = -Math.PI / 2;
    textMesh.position.y = 0.33;
    group.add(textMesh);

    return group;
}
```

### 5.3 坐标系统

**ICCS 转 3D 世界坐标**
```javascript
// ICCS: 列(a-i) + 行(0-9)
// 3D: X向右, Y向上, Z向前

const CELL_SIZE = 1.0;

function iccsToWorld(iccs) {
    const col = iccs[0].toLowerCase();
    const row = parseInt(iccs.slice(1));

    const colIndex = col.charCodeAt(0) - 'a'.charCodeAt(0);  // 0-8
    const rowIndex = row;  // 0-9

    return {
        x: (colIndex - 4) * CELL_SIZE,
        y: 0.2,  // 棋子高度的一半
        z: (4.5 - rowIndex) * CELL_SIZE
    };
}
```

### 5.4 TSL 特效设计

> **稳定性提示**: TSL (Three Shader Language) 仍处于实验阶段，API 可能随 Three.js 版本变化。开发时应锁定 Three.js 版本（建议 `package.json` 中使用精确版本号），升级前需验证 TSL API 兼容性。

#### 选中高亮效果
```javascript
import { color, position, length, sin, time, smoothstep, Fn, vec4 } from 'three/tsl';

const selectedHighlight = Fn(() => {
    const baseColor = color(0xffd700);  // 金黄色
    const dist = length(position.xz);
    const pulse = sin(time.mul(4)).mul(0.3).add(0.7);
    const ring = smoothstep(0.5, 0.3, dist).mul(smoothstep(0.1, 0.3, dist));
    const finalColor = baseColor.mul(pulse).mul(ring.add(0.3));
    const alpha = ring.mul(pulse).add(0.2);
    return vec4(finalColor, alpha);
});
```

#### 最后走法标记
```javascript
const moveIndicator = (isFrom) => Fn(() => {
    const fromColor = color(0x00ff00);  // 起点: 绿色
    const toColor = color(0x0088ff);    // 终点: 蓝色
    const baseColor = isFrom ? fromColor : toColor;

    const dist = length(position.xz);
    const breathe = sin(time.mul(3)).mul(0.2).add(0.8);
    const circle = smoothstep(0.4, 0.2, dist);
    const hole = smoothstep(0.1, 0.15, dist);

    return vec4(baseColor, circle.mul(hole).mul(breathe).mul(0.6));
});
```

---

## 6. 项目结构

```
llm-xiangqi/
├── src/
│   ├── core/                    # 核心业务逻辑
│   │   ├── referee_engine.py
│   │   ├── game_controller.py
│   │   └── state_serializer.py
│   ├── web_3d/                  # Web 3D 模块
│   │   ├── __init__.py
│   │   ├── server.py            # FastAPI 服务器
│   │   ├── websocket_manager.py # WebSocket 管理
│   │   ├── observer_bridge.py   # Observer sync/async 桥接
│   │   └── static/              # 静态文件 (构建产物)
│   │       ├── index.html
│   │       ├── js/
│   │       │   ├── main.js
│   │       │   ├── GameApp.js
│   │       │   ├── SceneManager.js
│   │       │   ├── PieceManager.js
│   │       │   └── WebSocketClient.js
│   │       └── models/          # glTF 模型
│   │           ├── board.glb
│   │           └── pieces.glb
│   └── agents/                  # LLM Agent
│
├── web_3d_client/               # 前端源码 (Vite 项目)
│   ├── package.json
│   ├── vite.config.js
│   └── src/
│       ├── index.html
│       └── js/
│           ├── main.js
│           ├── GameApp.js
│           ├── SceneManager.js
│           ├── PieceManager.js
│           └── WebSocketClient.js
│
├── config/
│   └── game_config.yaml         # 包含 web_3d 配置
│
├── docs/
│   ├── api-standard.md
│   └── web_3d_development_plan.md  # 本文档
│
└── game.py                      # 主程序入口
```

> **路径说明**: `web_3d_client/` 是 Vite 前端源码目录，构建产物输出到 `src/web_3d/static/`。`static_dir` 配置项指向后者。

---

## 7. 开发步骤

### Phase 1: 基础架构 (Week 1)

#### 7.1 配置与启动集成

- [ ] 更新 `game_config.yaml` 添加 `web_3d_config` 配置节
- [ ] 在 `ConfigLoader` 中新增 `Web3DConfig` 并更新 `GUIConfig`
- [ ] 修改 `game.py` 在 `run_battle()` 内部启动 Web 3D Server
- [ ] 实现 Observer sync/async 桥接（`observer_bridge.py`）
- [ ] 实现 Web 3D Server 生命周期管理（随主程序启动/关闭）

#### 7.2 服务端基础

- [ ] 创建 `src/web_3d/server.py` FastAPI 基础框架（独立线程运行 uvicorn）
- [ ] 实现 WebSocket Manager 连接管理
- [ ] 实现 `game.init` / `game.move` / `game.game_over` 消息广播
- [ ] 实现 `client.ready` → 发送完整初始状态的流程

#### 7.3 客户端基础

- [ ] 初始化 `web_3d_client/` Vite 项目（`npm create vite`）
- [ ] 搭建基础 HTML/CSS 结构
- [ ] 实现 WebSocketClient（含断线重连机制）
- [ ] 实现 GameStateManager（本地状态管理）
- [ ] 配置 Vite `build.outDir` 输出到 `src/web_3d/static/`

### Phase 2: 3D 渲染 (Week 2)

#### 7.4 棋盘与棋子渲染

- [ ] 实现 WebGPU/WebGL 2.0 自动降级渲染器初始化
- [ ] 创建 SceneManager 管理场景
- [ ] 加载棋盘 glTF 模型（或程序化生成）
- [ ] 加载棋子 glTF 模型（优先使用 §5.2 程序化 fallback）
- [ ] 实现 FEN 解析和棋子摆放

#### 7.5 坐标与交互

- [ ] 实现 ICCS ↔ 世界坐标转换
- [ ] 添加 OrbitControls 相机控制
- [ ] 配置光照系统（DirectionalLight + 阴影）

### Phase 3: 动画与特效 (Week 3)

#### 7.6 移动动画

- [ ] 实现 MoveAnimator（贝塞尔曲线/缓动动画）
- [ ] 处理 WebSocket `game.move` 事件触发动画
- [ ] 添加棋子被吃的淡出效果

#### 7.7 TSL 特效

- [ ] 实现选中高亮材质（脉冲效果）
- [ ] 实现最后走法标记（起点绿/终点蓝）
- [ ] 添加基础 UI 覆盖层（玩家信息、回合数）

### Phase 4: 集成与优化 (Week 4)

#### 7.8 文档更新

- [ ] 更新 `docs/api-standard.md` WebSocket API 规范
- [ ] 编写用户使用说明

#### 7.9 性能优化

- [ ] glTF 模型 Draco 压缩
- [ ] 纹理压缩 (KTX2/Basis)
- [ ] 渲染性能调优

#### 7.10 测试

- [ ] 浏览器兼容性测试（Chrome, Edge, Safari, Firefox）
- [ ] WebGPU/WebGL 2.0 降级测试
- [ ] WebSocket 断线重连测试
- [ ] 长时间运行稳定性测试

---

## 8. 关键实现代码

### 8.1 Observer sync/async 桥接

`GameController._notify_observers()` 是同步调用，而 Web3D 广播是异步操作。需要一个桥接层：

```python
# src/web_3d/observer_bridge.py
import asyncio
from typing import Optional
from src.utils.logger import get_logger

logger = get_logger("web_3d", level="INFO")


def make_sync_observer(web_server) -> callable:
    """创建同步 Observer 回调，内部将 async 广播调度到事件循环

    解决问题:
    - GameController._notify_observers() 是同步调用 observer(move, fen, is_game_over)
    - Web3DServer.broadcast_state() 是 async 方法
    - 同步调用 async 函数只会返回 coroutine 对象，不会执行

    方案: 用 asyncio.ensure_future() 将 async 任务投递到当前事件循环
    """
    def on_state_update(move: str, fen: str, is_game_over: bool):
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(
                web_server.broadcast_move(move, fen, is_game_over)
            )
        except RuntimeError:
            logger.warning("No running event loop, skipping WebSocket broadcast")

    return on_state_update
```

> **配套修改**: `game_controller.py` 的 `_notify_observers` 方法需要保持同步语义不变，桥接逻辑完全在 `make_sync_observer` 中处理，无需修改 Controller 本身。

### 8.2 Web 3D Server

```python
# src/web_3d/__init__.py
from .server import Web3DServer

__all__ = ['Web3DServer']
```

```python
# src/web_3d/server.py
import asyncio
import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
import uvicorn
from typing import Optional

from .websocket_manager import WebSocketManager
from .observer_bridge import make_sync_observer


class Web3DServer:
    """Web 3D 服务器，在独立线程中运行 uvicorn"""

    def __init__(self, config):
        self.config = config
        self.app = self._create_app()
        self.server: Optional[uvicorn.Server] = None
        self.ws_manager = WebSocketManager()
        self._current_state: Optional[dict] = None

    def _create_app(self):
        @asynccontextmanager
        async def lifespan(app):
            yield
            await self.ws_manager.close_all()

        app = FastAPI(lifespan=lifespan)

        @app.websocket("/ws")
        async def websocket_endpoint(ws: WebSocket):
            await self.ws_manager.connect(ws)
            try:
                while True:
                    data = await ws.receive_json()
                    await self._handle_message(ws, data)
            except WebSocketDisconnect:
                await self.ws_manager.disconnect(ws)

        app.mount("/", StaticFiles(
            directory=self.config.static_dir, html=True
        ))

        return app

    async def _handle_message(self, ws, data: dict):
        msg_type = data.get("type", "")

        if msg_type == "client.ready":
            if self._current_state:
                await self.ws_manager.send_to(
                    ws,
                    {
                        "type": "game.init",
                        "timestamp": _now_ms(),
                        "payload": self._current_state,
                    }
                )

        elif msg_type == "client.ping":
            await self.ws_manager.send_to(
                ws,
                {
                    "type": "server.pong",
                    "timestamp": _now_ms(),
                    "payload": {"id": data.get("id")},
                }
            )

    def start(self):
        """在独立线程中启动 uvicorn

        使用 threading 而非 asyncio.create_task()，因为:
        1. asyncio.run() 的事件循环尚未启动时不能调用 create_task
        2. uvicorn 内部有自己的事件循环，放在独立线程更安全
        """
        config = uvicorn.Config(
            self.app,
            host=self.config.host,
            port=self.config.port,
            log_level="info",
        )
        self.server = uvicorn.Server(config)
        thread = threading.Thread(target=self.server.run, daemon=True)
        thread.start()

        if self.config.auto_open_browser:
            import webbrowser
            webbrowser.open(f"http://localhost:{self.config.port}")

    def stop(self):
        """停止服务器"""
        if self.server:
            self.server.should_exit = True

    async def broadcast_move(self, move: str, fen: str, is_game_over: bool):
        """广播走步事件 (由 Observer 桥接调用)"""
        if is_game_over:
            await self.ws_manager.broadcast({
                "type": "game.game_over",
                "timestamp": _now_ms(),
                "payload": {
                    "result": self._current_state.get("result", "unknown")
                        if self._current_state else "unknown",
                    "result_reason": self._current_state.get("result_reason", "")
                        if self._current_state else "",
                    "fen": fen,
                },
            })
        else:
            from_pos, to_pos = move[:2], move[2:]
            fen_parts = fen.split()
            await self.ws_manager.broadcast({
                "type": "game.move",
                "timestamp": _now_ms(),
                "payload": {
                    "move": move,
                    "piece": "",
                    "from_pos": from_pos,
                    "to_pos": to_pos,
                    "fen_after": fen,
                },
            })


def _now_ms() -> int:
    import time
    return int(time.time() * 1000)
```

### 8.3 主程序集成

```python
# game.py 修改
from src.web_3d import Web3DServer
from src.web_3d.observer_bridge import make_sync_observer

async def run_battle(agent1, agent2, max_turns: int = 100,
                     gui_config: GUIConfig = None):

    referee_engine = RefereeEngine()
    controller = LLMAgentGameController(
        red_agent=agent1,
        black_agent=agent2,
        referee_engine=referee_engine,
        max_turns=max_turns,
    )

    web_server = None
    if gui_config and gui_config.web_3d:
        logger.info(
            f"Web 3D enabled, starting server on port "
            f"{gui_config.web_3d_config.port}"
        )
        web_server = Web3DServer(gui_config.web_3d_config)
        web_server.start()

        controller.register_observer(make_sync_observer(web_server))

    try:
        result = await controller.run_game(verbose=True)
    finally:
        if web_server:
            web_server.stop()

    return result
```

### 8.4 WebSocket Manager

```python
# src/web_3d/websocket_manager.py
import json
from fastapi import WebSocket
from typing import List


class WebSocketManager:
    """管理 WebSocket 连接和消息广播"""

    def __init__(self):
        self.connections: List[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.connections.append(ws)

    async def disconnect(self, ws: WebSocket):
        if ws in self.connections:
            self.connections.remove(ws)

    async def send_to(self, ws: WebSocket, message: dict):
        try:
            await ws.send_json(message)
        except Exception:
            await self.disconnect(ws)

    async def broadcast(self, message: dict):
        """向所有连接广播消息，自动清理断开的连接"""
        disconnected = []
        for ws in self.connections:
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            await self.disconnect(ws)

    async def close_all(self):
        for ws in self.connections:
            try:
                await ws.close()
            except Exception:
                pass
        self.connections.clear()
```

### 8.5 WebGPU/WebGL 2.0 降级渲染器

```javascript
// src/web_3d/static/js/SceneManager.js

async function createRenderer(canvas) {
    // 尝试 WebGPU
    if (navigator.gpu) {
        try {
            const { WebGPURenderer } = await import('three/addons/renderers/webgpu/WebGPURenderer.js');
            const renderer = new WebGPURenderer({ canvas, antialias: true });
            await renderer.init();
            console.info('[Web3D] Using WebGPU renderer');
            return renderer;
        } catch (e) {
            console.warn('[Web3D] WebGPU init failed, falling back to WebGL 2.0:', e);
        }
    }

    // 降级 WebGL 2.0
    const { WebGLRenderer } = await import('three/src/renderers/WebGLRenderer.js');
    const renderer = new WebGLRenderer({
        canvas,
        antialias: true,
        powerPreference: 'high-performance',
    });
    console.info('[Web3D] Using WebGL 2.0 fallback renderer');
    return renderer;
}
```

> **降级说明**: WebGPU 和 WebGL 2.0 的材质 API 不同（TSL 仅在 WebGPU 下可用）。降级到 WebGL 2.0 时，TSL 特效需要替换为 GLSL shader 或简单的 MeshStandardMaterial 动画。建议将特效部分封装为抽象接口，按渲染后端分别实现。

### 8.6 WebSocket 断线重连

```javascript
// src/web_3d/static/js/WebSocketClient.js

export class WebSocketClient {
    constructor(url) {
        this.url = url;
        this.ws = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 10;
        this.reconnectDelay = 1000;      // 初始延迟 1s
        this.maxReconnectDelay = 30000;  // 最大延迟 30s
        this.onMessage = null;
        this.onOpen = null;
        this.onClose = null;
    }

    connect() {
        this.ws = new WebSocket(this.url);

        this.ws.onopen = () => {
            console.info('[WS] Connected');
            this.reconnectAttempts = 0;
            this.reconnectDelay = 1000;

            // 发送 client.ready 请求初始状态
            this.ws.send(JSON.stringify({
                type: "client.ready",
                protocol_version: "1.0.0"
            }));

            if (this.onOpen) this.onOpen();
        };

        this.ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (this.onMessage) this.onMessage(data);
        };

        this.ws.onclose = () => {
            console.warn('[WS] Disconnected');
            if (this.onClose) this.onClose();
            this._scheduleReconnect();
        };

        this.ws.onerror = (error) => {
            console.error('[WS] Error:', error);
        };
    }

    _scheduleReconnect() {
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.error('[WS] Max reconnect attempts reached');
            return;
        }

        const delay = Math.min(
            this.reconnectDelay * Math.pow(1.5, this.reconnectAttempts),
            this.maxReconnectDelay
        );
        this.reconnectAttempts++;

        console.info(`[WS] Reconnecting in ${Math.round(delay)}ms (attempt ${this.reconnectAttempts})`);
        setTimeout(() => this.connect(), delay);
    }

    send(data) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(data));
        }
    }

    close() {
        this.reconnectAttempts = this.maxReconnectAttempts; // 阻止自动重连
        if (this.ws) {
            this.ws.close();
        }
    }
}
```

### 8.7 WebGPU 渲染器初始化 (SceneManager)

```javascript
// src/web_3d/static/js/SceneManager.js
import * as THREE from 'three/webgpu';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

export class SceneManager {
    constructor(canvas) {
        this.canvas = canvas;
        this.renderer = null;
        this.scene = null;
        this.camera = null;
        this.controls = null;
    }

    async init() {
        this.renderer = await createRenderer(this.canvas);
        this.renderer.shadowMap.enabled = true;
        this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;

        this.scene = new THREE.Scene();
        this.scene.background = new THREE.Color(0x1a1a2e);

        this.camera = new THREE.PerspectiveCamera(
            45,
            this.canvas.width / this.canvas.height,
            0.1,
            100
        );
        this.camera.position.set(8, 12, 12);
        this.camera.lookAt(0, 0, 0);

        this.controls = new OrbitControls(this.camera, this.canvas);
        this.controls.enableDamping = true;
        this.controls.maxPolarAngle = Math.PI / 2.2;

        this.setupLighting();
    }

    setupLighting() {
        const ambient = new THREE.AmbientLight(0xffffff, 0.4);
        this.scene.add(ambient);

        const mainLight = new THREE.DirectionalLight(0xffffff, 1.2);
        mainLight.position.set(5, 10, 5);
        mainLight.castShadow = true;
        mainLight.shadow.mapSize.set(2048, 2048);
        this.scene.add(mainLight);

        const fillLight = new THREE.DirectionalLight(0xffffff, 0.3);
        fillLight.position.set(-5, 5, -5);
        this.scene.add(fillLight);
    }

    render() {
        this.controls.update();
        this.renderer.render(this.scene, this.camera);
    }
}
```

---

## 9. 安全说明

当前 Web 3D Server 设计为本地开发/演示工具，**默认无认证机制**。注意事项：

- 服务端仅绑定 `0.0.0.0`（所有网卡），如需限制访问，将 `host` 改为 `127.0.0.1`
- 如果需要在公网暴露，建议在反向代理（如 Nginx）层面添加认证
- WebSocket 端点 `/ws` 不做 origin 检查，适合本地工具场景

---

## 10. 运行方式

```bash
# 1. 构建前端 (首次或前端代码变更后)
cd web_3d_client
npm install
npm run build
# 构建产物自动输出到 src/web_3d/static/

# 2. 运行主程序 (无需单独操作 Web 3D Server)
cd ..
python game.py

# 如果 game_config.yaml 中 web_3d: true
# - 自动在独立线程启动 Web 3D Server
# - 自动打开浏览器 (如果 auto_open_browser: true)
# - 游戏结束后自动关闭服务器
```

---

## 11. 注意事项

1. **配置驱动**: Web 3D 完全由 `game_config.yaml` 控制，不单独操作
2. **WebGPU 兼容性**: Chrome 113+, Edge 113+, Safari 26+, Firefox 141+ (Win)；不支持时自动降级 WebGL 2.0
3. **静态文件**: 构建后的客户端代码输出到 `src/web_3d/static/`，由 `static_dir` 配置指向
4. **端口占用**: 默认 8080，如果被占用可配置其他端口
5. **生命周期**: Web 3D Server 随主程序启动/关闭，运行在独立 daemon 线程中
6. **TSL 稳定性**: TSL 仍处于实验阶段，升级 Three.js 版本前需验证 TSL API 兼容性
7. **安全**: 默认无认证，适合本地使用；公网部署需额外配置

---

## 12. 浏览器兼容性

| 浏览器 | 最低版本 | WebGPU | WebGL Fallback |
|--------|---------|--------|----------------|
| Chrome | 113+ | Yes | Yes |
| Edge | 113+ | Yes | Yes |
| Safari | 26+ | Yes | Yes |
| Firefox | 141+ (Win) | Yes | Yes |

> WebGL 2.0 fallback 时 TSL 特效不可用，自动替换为简化视觉效果。

---

## 13. 参考资源

- [Three.js WebGPU 文档](https://threejs.org/docs/?q=webgpu)
- [TSL 指南](https://github.com/mrdoob/three.js/wiki/Three.js-Shading-Language)
- [glTF 2.0 规范](https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html)
- [FastAPI WebSocket](https://fastapi.tiangolo.com/advanced/websockets/)
- [uvicorn 线程模式](https://www.uvicorn.org/settings/#running-with-uvicorn)
