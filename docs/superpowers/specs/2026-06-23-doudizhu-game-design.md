# 欢乐斗地主 — 设计规格文档

> **项目**: HMP WS Service  
> **日期**: 2026-06-23  
> **状态**: 已审核通过，待实施

---

## 1. 概述

基于 HMP WS Service 现有的 FastAPI + WebSocket + Redis + RabbitMQ + SQLAlchemy 技术栈，新增"欢乐斗地主"网络对战游戏功能。采用前后端彻底分离架构（方案 B），后端作为纯 Game Server 提供 WebSocket 事件驱动的实时通信，前端使用 Vue 3 + Vite 独立开发游戏客户端。

### 核心决策摘要

| 决策项 | 选定方案 |
|---|---|
| 前后端架构 | 彻底分离：后端 FastAPI (backend/)，前端 Vue 3 (frontend/) |
| 通信模式 | 纯 WebSocket 双向事件驱动（方案 1） |
| 匹配机制 | 支持 AI 机器人填充 + 断线托管 |
| 游戏规则 | 经典玩法 MVP（后续可扩展） |
| 状态存储 | Redis 分布式状态存储 |

---

## 2. 整体架构

### 2.1 架构框图

```
┌─────────────────────────────┐       ┌────────────────────────────────────┐
│   Frontend (Vue 3 + Vite)   │       │    Backend (FastAPI + DDD)         │
│                             │       │                                    │
│  游戏界面 / UI              │       │  WebSocket 游戏网关                │
│  WebSocket 客户端           │◄─────►│  HTTP API / 鉴权                   │
│                             │  WS   │  游戏状态机 / Room管理器           │
│                             │       │  AI 机器人模拟器                   │
└─────────────────────────────┘       └──────┬───────┬───────┬─────────────┘
                                             │       │       │
                                      ┌──────▼──┐ ┌──▼──┐ ┌──▼──┐
                                      │  Redis  │ │ MQ  │ │MySQL│
                                      │房间状态 │ │广播 │ │持久 │
                                      │匹配队列 │ │     │ │数据 │
                                      └─────────┘ └─────┘ └─────┘
```

### 2.2 重构后的项目目录结构

```text
hmp_ws_service/                   # 根目录
  ├── backend/                    # 所有 Python 后端源码 (含原有功能 + 斗地主)
  │    ├── alembic/
  │    ├── app/
  │    │    ├── domain/
  │    │    │    ├── message/      # (原有) 站内信领域
  │    │    │    ├── upload/       # (原有) 文件上传领域
  │    │    │    ├── audit_log/    # (原有) 审计日志领域
  │    │    │    └── game/         # 🆕 斗地主游戏领域 (核心规则/状态机/AI)
  │    │    ├── application/
  │    │    │    ├── message/      # (原有)
  │    │    │    ├── upload/       # (原有)
  │    │    │    ├── audit_log/    # (原有)
  │    │    │    └── game/         # 🆕 游戏编排服务 (匹配/房间管理/结算)
  │    │    ├── infrastructure/
  │    │    │    ├── database/     # (原有) + 新增 Player/GameRecord 模型
  │    │    │    ├── mq/           # (原有) RabbitMQ
  │    │    │    ├── redis_client.py  # (原有) + 新增 Redis 房间状态存取
  │    │    │    └── ...
  │    │    └── interfaces/
  │    │         ├── api/          # (原有) HTTP 路由 + 新增游戏 API
  │    │         ├── web/          # (原有) 控制台首页路由
  │    │         └── websocket/
  │    │              ├── ws_routes.py     # (原有) 通信 WebSocket
  │    │              ├── handler.py       # (原有) 通信 Handler
  │    │              ├── game_routes.py   # 🆕 游戏 WebSocket 端点
  │    │              └── game_handler.py  # 🆕 游戏 Handler (独立隔离)
  │    ├── static/                # (原有) 控制台静态资源
  │    ├── templates/             # (原有) 控制台 HTML 模板
  │    ├── tests/                 # (原有) + 新增游戏相关测试
  │    ├── main.py
  │    ├── requirements.txt
  │    ├── alembic.ini
  │    └── .env
  │
  ├── frontend/                   # 🆕 Vue 3 斗地主游戏客户端 (Vite)
  │    ├── src/
  │    │    ├── assets/           # 扑克牌样式、音效
  │    │    ├── components/       # 游戏 UI 组件
  │    │    ├── views/            # 页面视图 (登录/大厅/房间)
  │    │    ├── composables/      # Vue 组合式函数 (WebSocket 管理等)
  │    │    ├── stores/           # Pinia 状态管理
  │    │    ├── router/           # Vue Router 路由
  │    │    └── utils/            # 工具函数
  │    ├── package.json
  │    └── vite.config.js         # 含 WebSocket 代理配置
  │
  └── README.md
```

---

## 3. 游戏状态机

### 3.1 状态流转

```
[开始] → MATCHING → DEALING → CALLING → PLAYING → SETTLING → [结束]
                                 ↑         │
                                 └─────────┘
                              (无人叫地主, 重新发牌)
```

### 3.2 状态定义

| 状态 | 含义 | 进入条件 | 退出条件 |
|---|---|---|---|
| `MATCHING` | 玩家在匹配队列中等待 | 玩家发送 `join_match` | 3 人就位或超时 AI 填充 |
| `DEALING` | 洗牌发牌 | 匹配成功 | 发牌完成 |
| `CALLING` | 叫地主/抢地主 | 发牌完毕 | 地主产生 / 无人叫地主触发重发 |
| `PLAYING` | 出牌轮转 | 地主确定，底牌分配 | 某方手牌出完 |
| `SETTLING` | 结算 | 游戏结束 | 结算写入 DB，房间销毁 |

### 3.3 叫地主规则

- 从随机一位玩家开始，按顺序轮流叫分（1分/2分/3分）或不叫。
- 叫分必须高于前一位叫分的玩家。
- 有人叫 3 分则直接成为地主。
- 一轮结束后，叫分最高者成为地主。
- 若三人均不叫，重新洗牌发牌（最多重发 3 次，之后随机指定地主）。

### 3.4 出牌规则

- 地主先出。
- 顺时针轮转：地主 → 下家(农民) → 下家(农民) → 地主。
- 新一轮首位出牌者可出任意合法牌型。
- 后续玩家必须出与上家相同牌型且更大的牌，或者出炸弹/王炸。
- 可以选择"不出"（过），但新一轮首位出牌者必须出牌。

### 3.5 合法牌型

| 牌型 | 说明 | 示例 |
|---|---|---|
| 单张 | 1 张牌 | 3 |
| 对子 | 2 张相同点数 | 33 |
| 三条 | 3 张相同点数 | 333 |
| 三带一 | 3 + 1 | 333+4 |
| 三带二 | 3 + 1对 | 333+44 |
| 顺子 | ≥5 张连续点数 (不含2和王) | 34567 |
| 连对 | ≥3 对连续点数 (不含2和王) | 334455 |
| 飞机不带 | ≥2 组连续三条 | 333444 |
| 飞机带单 | 飞机 + 等量单张 | 333444+5+6 |
| 飞机带对 | 飞机 + 等量对子 | 333444+55+66 |
| 炸弹 | 4 张相同点数 | 3333 (倍数×2) |
| 王炸 | 大小王 | 🃏🃏 (倍数×2) |
| 四带二单 | 4 + 2单张 | 3333+4+5 |
| 四带二对 | 4 + 2对 | 3333+44+55 |

---

## 4. Redis 数据结构设计

### 4.1 匹配队列

```
Key:    game:match_queue
Type:   List (FIFO)
Value:  ["player_A", "player_B", ...]

操作:
  - 加入匹配:  RPUSH game:match_queue "player_A"
  - 取出3人:   Lua 脚本原子性 LPOP ×3
  - 取消匹配:  LREM game:match_queue 1 "player_A"
```

### 4.2 玩家-房间映射

```
Key:    game:player_room:{player_id}
Type:   String
Value:  "room_abc123"
TTL:    3600s

用途:
  - 断线重连定位房间
  - 防止重复加入匹配
```

### 4.3 房间完整状态

```
Key:    game:room:{room_id}
Type:   String (JSON)
TTL:    7200s (2小时兜底过期)
```

JSON 结构：

```json
{
  "room_id": "room_abc123",
  "status": "PLAYING",
  "players": [
    {"id": "player_A", "nickname": "玩家A", "is_ai": false, "is_online": true},
    {"id": "player_B", "nickname": "玩家B", "is_ai": false, "is_online": true},
    {"id": "ai_bot_1", "nickname": "机器人小明", "is_ai": true, "is_online": true}
  ],
  "hands": {
    "player_A": [0, 3, 5, 8, 12, 15, 20, 25, 30, 35, 38, 40, 42, 45, 48, 50, 52],
    "player_B": [1, 4, 6, 9, 13, 16, 21, 26, 31, 36, 39, 41, 43, 46, 49, 51, 53],
    "ai_bot_1": [2, 7, 10, 11, 14, 17, 18, 19, 22, 23, 24, 27, 28, 29, 32, 33, 34]
  },
  "bottom_cards": [37, 44, 47],
  "landlord": null,
  "current_turn": "player_A",
  "turn_deadline": 1719158400,
  "last_play": {"player": null, "cards": [], "card_type": null},
  "call_info": {
    "current_caller": "player_A",
    "call_history": [],
    "highest_score": 0
  },
  "multiplier": 1,
  "pass_count": 0,
  "redeal_count": 0,
  "created_at": "2026-06-23T18:55:00"
}
```

使用单个 JSON String 而非 Redis Hash，配合 `WATCH/MULTI` 乐观锁保证原子性。

### 4.4 扑克牌编码

54 张牌使用整数 0~53 编码：

| 编号 | 计算方式 | 点数 | 花色 |
|---|---|---|---|
| 0~51 | `rank = n // 4`, `suit = n % 4` | 0→3, 1→4, ..., 10→K, 11→A, 12→2 | 0→♠, 1→♥, 2→♣, 3→♦ |
| 52 | 固定 | 小王 | — |
| 53 | 固定 | 大王 | — |

斗地主牌力排序：3 < 4 < 5 < ... < K < A < 2 < 小王 < 大王

---

## 5. WebSocket 事件协议

### 5.1 连接端点

```
ws://{host}:{port}/ws/game/{player_id}?token={api_token}
```

独立于现有的 `/ws/{client_id}` 通信端点。

### 5.2 客户端 → 服务端（玩家动作）

统一格式：`{"action": "xxx", ...payload}`

| action | 说明 | Payload |
|---|---|---|
| `join_match` | 加入匹配队列 | `{"action": "join_match"}` |
| `cancel_match` | 取消匹配 | `{"action": "cancel_match"}` |
| `call_landlord` | 叫地主 | `{"action": "call_landlord", "score": 3}` |
| `skip_call` | 不叫 | `{"action": "skip_call"}` |
| `play_cards` | 出牌 | `{"action": "play_cards", "cards": [40, 41, 42]}` |
| `pass_turn` | 不出 (过) | `{"action": "pass_turn"}` |
| `chat` | 快捷聊天 | `{"action": "chat", "msg_id": 3}` |

### 5.3 服务端 → 客户端（游戏事件）

统一格式：`{"event": "xxx", ...payload}`

#### 匹配阶段

| event | 说明 |
|---|---|
| `match_waiting` | 正在匹配，含已匹配人数 |
| `match_success` | 匹配成功，含房间ID和玩家列表 |
| `match_cancelled` | 取消匹配确认 |

#### 叫地主阶段

| event | 说明 |
|---|---|
| `game_start` | 发牌完成，下发自己的手牌 + 座位索引 + 首位叫牌者 |
| `call_turn` | 轮到某人叫地主，含倒计时 |
| `call_made` | 某人叫了N分 |
| `call_skipped` | 某人不叫 |
| `landlord_decided` | 地主产生 + 底牌公示 + 倍数 |
| `redeal` | 无人叫地主，重新发牌 |

#### 出牌阶段

| event | 说明 |
|---|---|
| `your_turn` | 轮到你出牌，含倒计时和是否必须出牌 |
| `cards_played` | 某人出牌，含牌型名称和剩余牌数 |
| `turn_passed` | 某人不出(过) |
| `timeout_auto` | 超时自动操作 |

#### 结算 & 连接管理

| event | 说明 |
|---|---|
| `game_over` | 对局结束，含胜负方、倍数、各玩家得分、所有手牌公示 |
| `player_offline` | 某玩家断线，含托管倒计时 |
| `player_reconnected` | 某玩家重连 |
| `ai_takeover` | AI 接管断线玩家 |
| `error` | 错误信息，含错误码和描述 |
| `chat_msg` | 聊天消息转发 |

### 5.4 信息安全：玩家数据隔离

- 服务端永远不向玩家下发其他人的手牌详情，只下发对手的**剩余牌数**。
- 结算时 (`game_over`) 才公示所有人的手牌。
- 出牌校验完全由后端 `GameStateMachine` 负责，前端仅提交选择。

---

## 6. HTTP REST API

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/game/profile/{player_id}` | 获取玩家档案（欢乐豆、胜率、等级） |
| `GET` | `/api/game/history/{player_id}` | 获取历史对局记录 |
| `GET` | `/api/game/leaderboard` | 获取排行榜 |
| `GET` | `/api/game/room/{room_id}/state` | 断线重连拉取房间快照 |

---

## 7. 前端设计

### 7.1 技术选型

| 技术 | 选择 | 理由 |
|---|---|---|
| 框架 | Vue 3 (Composition API) | 用户指定 |
| 构建 | Vite | 极速 HMR，Vue 官方推荐 |
| 状态管理 | Pinia | Vue 3 官方状态管理 |
| 路由 | Vue Router 4 | SPA 页面导航 |
| UI 库 | 不使用第三方 | 游戏界面高度定制 |
| CSS | 原生 CSS + CSS Variables | 全局主题控制 |

### 7.2 路由规划

| 路由 | 视图组件 | 功能 |
|---|---|---|
| `/login` | `LoginView` | 输入玩家昵称进入大厅 |
| `/lobby` | `LobbyView` | 玩家信息、匹配按钮、排行榜、历史记录 |
| `/game/:roomId` | `GameRoomView` | 斗地主核心游戏界面 |

### 7.3 核心组件层级

```text
GameRoomView (游戏房间页面)
├── GameBoard (牌桌主区域 - 绿色牌桌背景)
│    ├── PlayerSeat × 3 (三个座位: 底部自己 / 左侧上家 / 右侧下家)
│    │    ├── PlayerAvatar (头像 + 昵称 + 身份标签)
│    │    ├── CardCount (剩余手牌数)
│    │    ├── PlayedCards (最近出的牌)
│    │    ├── ChatBubble (聊天气泡)
│    │    └── TurnTimer (倒计时圆环)
│    └── BottomCards (底牌展示区)
│
├── HandCards (手牌区 - 底部排列)
│    └── PokerCard × N (单张扑克牌, 支持选中弹起)
│
├── ActionBar (操作按钮)
│    ├── 叫地主阶段: [1分] [2分] [3分] [不叫]
│    └── 出牌阶段: [出牌] [不出] [提示]
│
└── SettlementModal (结算弹窗)
```

### 7.4 PokerCard 组件

- Props: `cardId (0~53)`, `selected`, `faceDown`, `size`
- 选中时向上弹起 20px（CSS transition）
- 牌面使用 CSS 纯绘制（点数 + 花色图标），不依赖外部图片

### 7.5 Pinia Store

#### `usePlayerStore`

```javascript
{
  playerId: "player_A",
  nickname: "小明",
  beans: 10000,
  totalGames: 50,
  winRate: 0.56
}
```

#### `useGameStore`

```javascript
{
  wsConnected: true,
  roomId: "room_abc123",
  gamePhase: "PLAYING",   // MATCHING | DEALING | CALLING | PLAYING | SETTLING
  players: [
    { id: "...", nickname: "...", isAi: false, isOnline: true, remaining: 14, isLandlord: true },
    // ... ×3
  ],
  myHand: [0, 3, 5, ...],
  selectedCards: [],
  bottomCards: [37, 44, 47],
  lastPlay: { player: "...", cards: [...], cardType: "顺子" },
  currentTurn: "player_A",
  turnTimeout: 20,
  callHistory: [],
  highestCall: 0,
  multiplier: 2,
  settlement: null
}
```

### 7.6 WebSocket Composable — `useGameWebSocket`

- 自动重连（指数退避: 1s → 2s → 4s → 8s → 最大 30s）
- 心跳保活（每 15s 发送 ping）
- 消息分发：根据 `event` 类型自动更新 Pinia GameStore
- 断线重连后自动恢复房间状态

### 7.7 UI 视觉风格

| 维度 | 风格 |
|---|---|
| 配色 | 深绿色牌桌 (#1a5c2e) + 深木纹边框 + 暖黄灯光 |
| 牌面 | CSS 纯绘制，白底红/黑花色 |
| 动画 | 发牌飞入、出牌飞出、选牌弹起、倒计时环形进度条 |
| 布局 | 全屏 100vw × 100vh，牌桌居中 |
| 响应式 | 优先桌面端，手牌区自适应 |

---

## 8. AI 机器人策略（MVP）

MVP 版本的 AI 采用简单规则策略：

1. **叫地主**: 根据手牌强度评分（大牌数量、炸弹数量）决定是否叫分。
2. **出牌**: 优先出最小的合法牌型；遇到队友（另一个农民）的牌时考虑不出。
3. **牌型选择**: 优先出单张/对子消耗小牌，保留炸弹到关键时刻。

---

## 9. 超时与托管机制

| 场景 | 超时时间 | 自动操作 |
|---|---|---|
| 叫地主超时 | 15 秒 | 自动不叫 |
| 出牌超时 | 20 秒 | 自动不出（过）；若必须出牌则出最小单张 |
| 玩家断线 | 30 秒等待 | 超时后 AI 接管托管 |
| 匹配等待 | 10 秒 | AI 机器人填充 |
