# 🃏 happy_doudizhu — 欢乐斗地主网络对战系统

本项目是一个采用前后端彻底分离架构的“欢乐斗地主”网络对战系统。系统以 **FastAPI + Vue 3** 为核心，搭配 **Redis** 存储匹配队列与对局状态，以及 **MySQL** 落地存储战绩与玩家档案。系统内置了强健的掉线重连机制与自研扑克牌规则引擎，并提供独立的 AI 降级接管机器人，实现了极佳的可玩性与开发调试体验。

---

## 🎨 游戏界面巡礼 (Screenshot Tour)

### 1. 账号登录与注册页
玩家通过唯一的账号或昵称快捷注册与登录，进入持久化游戏大厅，所有的欢乐豆和段位战绩将绑定账号，终局持久化。
![登录与注册](docs/images/login.png)

### 2. 多人游戏大厅
支持底分不同的六大段位场次选择；集成全局欢乐豆富豪排行榜；界面采用流畅的玻璃态毛玻璃视觉设计。
![多人游戏大厅](docs/images/lobby.png)

### 3. 实时对局房间
支持逼真的实时叫地主、抢地主、加倍与出牌交互。游戏界面包含精细的头像标识、手牌排列、上家出牌反馈、剩牌提示以及气泡短语聊天。
![实时对局房间](docs/images/game.png)

### 4. 调试控制台与 Mock 模式
为开发与运维人员量言打造的控制台。支持 WebSocket 文本消息调试、广播站内信发送与接收、大文件并发分片上传进度条展示以及系统审计日志的高级筛选与气泡预览。
```text
体验开发 Mock 模式：
如果在前端开发环境下，在 URL 后面附带 `?mock=true` 参数，例如：
http://localhost:5173/lobby?mock=true 
即可在无需启动后端的情况下直接体验和预览完整的前端交互界面！
```
![调试控制台](docs/images/console.png)

---

## ✨ 核心功能特性 (Key Features)

* **🧩 DDD 领域驱动设计实践**：后端严格隔离业务核心与基础设施实现。领域层定义扑克牌编码、洗牌发牌、牌型校验与压制算法以及五大状态的游戏房间状态机。
* **⚡ WebSocket 实时对战网关**：基于双向长连接，实时进行叫地主、出牌、过牌等交互。采用玩家专属个人视角的防作弊手牌广播机制，确保数据公平。
* **🤖 托管 AI 决策与双层兜底**：匹配超时自动机器人常驻补位，对局中玩家离线自动托管。结合 DouZero 强化学习 AI 模型与 Rule-based 规则兜底 AI，确保出牌合理且不中断。
* **🏆 36级特色排位头衔系统**：涵盖从`包身工`到`至尊`的趣味称号，按对局胜负、炸弹数量、春天等触发原子星数变动。支持低段位新手保护与高段位硬核无保护博弈。
* **🎵 自研 Web Audio 音频引擎**：支持背景音乐的无缝切换，以及出牌、加倍、叫分等动作音效的异步解码与低延迟播放。
* **🛡️ 安全大文件切片上传**：调试控制台支持大文件的 WebSocket 并发分片上传，内置文件名净化、路径穿越防护与分片切片边界校验。
* **📝 完整的审计日志追踪**：对系统核心数据如欢乐豆增减、段位变更和敏感上传进行严密的审计记录，支持防抖异步写入。

---

## 📂 项目目录结构树

```text
happy_doudizhu/
├── backend/                        # 后端项目根目录 (FastAPI + SQLAlchemy)
│   ├── alembic/                    # 数据库迁移脚本及历史版本
│   │   └── versions/               # 具体迁移版本脚本文件
│   ├── app/
│   │   ├── domain/                 # 领域层：纯业务逻辑与核心规则 (无技术细节依赖)
│   │   │   ├── game/               # 游戏核心逻辑
│   │   │   │   ├── card.py         # 扑克牌编码、排序与洗牌发牌规则
│   │   │   │   ├── card_type.py    # 14种牌型智能判定与压制(can_beat)算法
│   │   │   │   └── room.py         # 游戏房间状态机 (五大生命周期阶段流转控制)
│   │   │   └── audit_log/          # 审计日志领域对象及仓储契约
│   │   ├── application/            # 应用层：业务流程编排与用例驱动 (协调指挥官)
│   │   │   ├── game/
│   │   │   │   └── game_app_service.py # 玩家匹配、开局、出牌流程及托管 AI 决策编排
│   │   │   └── audit_log/          # 审计日志记录应用服务
│   │   ├── infrastructure/         # 基础设施层：具体技术选型与工具落地
│   │   │   ├── database/           # 关系型数据库 MySQL 读写实现
│   │   │   │   ├── models.py       # SQLAlchemy 数据库映射模型 (已统一 ddz_ 表前缀及注释)
│   │   │   │   ├── session.py      # 数据库连接池与初始化管理 (含库表自愈机制)
│   │   │   │   └── game_repository.py # SQL 战绩、积分、个人档案物理存取
│   │   │   ├── mq/                 # 站内信 RabbitMQ 适配器与消费者
│   │   │   └── redis/              # Redis 高性能匹配队列与对局房间状态缓存
│   │   └── interfaces/             # 接口层：对外的 API 网关与协议解析
│   │       ├── api/                # REST 接口 (玩家账号、战绩查询、审计检索、分片上传)
│   │       └── websocket/          # 对局长连接网关 (处理 WebSocket 握手与心跳)
│   ├── tests/                      # pytest 单元测试目录 (覆盖率达 90% 以上)
│   └── main.py                     # 后端服务入口 (负责 Lifespan 初始化、CORS 与路由挂载)
├── frontend/                       # 前端项目根目录 (Vue 3 + Vite + Pinia)
│   ├── src/
│   │   ├── assets/                 # 音频 (出牌、加倍、叫分音效) 与图片静态资源
│   │   ├── components/             # 可复用游戏 UI 元素组件
│   │   │   ├── PokerCard.vue       # 单张扑克牌渲染与高亮选取动画
│   │   │   ├── HandCards.vue       # 玩家当前手牌水平排列、排列间距及滑选控制
│   │   │   └── PlayerSeat.vue      # 玩家座席头像、倒计时、叫加倍提示及聊天气泡
│   │   ├── composables/            # 组合式函数封装
│   │   │   └── useGameWebSocket.ts # 斗地主对局 WebSocket 通信与掉线指数退避重连机制
│   │   ├── stores/                 # Pinia 状态管理中心
│   │   │   ├── playerStore.ts      # 管理玩家个人档案、欢乐豆及排位段位变动
│   │   │   └── gameStore.ts        # 全局对局状态、出牌响应及动画状态映射
│   │   ├── views/                  # 页面级视图组件
│   │   │   ├── LoginView.vue       # 登录与快速注册页面
│   │   │   ├── LobbyView.vue       # 多人游戏大厅 (选择低分场次、全局富豪排行榜)
│   │   │   ├── GameRoomView.vue    # 实战对局房间 (抢地主、加倍、对局出牌及结算弹窗)
│   │   │   └── DebugConsoleView.vue # 调试控制台 (实时WS消息调试、大文件分片上传测试)
│   │   └── utils/                  # 辅助工具函数
│   │       └── cardUtils.ts        # 前端手牌大小排序与基础出牌校验
│   ├── package.json                # 前端工程依赖与运行指令配置
│   └── vite.config.ts              # Vite 编译与开发服务器反向代理设置
├── docs/                           # 系统历史设计规格书与实施计划文档
└── AGENTS.md                       # 协同开发智能体的操作约束说明
```

### 1. 各层职责划分

* **领域层 (`backend/app/domain/`)**：
  - **无外部依赖的纯业务逻辑**：定义扑克牌编码、排序、洗牌 (`card.py`) 与 14 种斗地主常见牌型的智能校验与 `can_beat` 压制判定算法 (`card_type.py`)。
  - **房间状态机 (`room.py`)**：严密的五大阶段状态转换 (`MATCHING` -> `DEALING` -> `CALLING` -> `PLAYING` -> `SETTLING`)，规避前后端状态不一致。
* **应用层 (`backend/app/application/`)**：
  - **业务流程编排**：由 `GameAppService` 统一提供匹配排队、自动开局、AI 机器人补齐席位、叫地主/出牌的流程驱动。
* **基础设施层 (`backend/app/infrastructure/`)**：
  - **持久化与外部依赖**：提供 MySQL 的 SQLAlchemy 数据模型与持久化仓储 (`game_repository.py`)、Redis 匹配队列与房间缓存仓储 (`redis_game_repository.py`)、RabbitMQ 站内信广播适配器。
* **接口层 (`backend/app/interfaces/`)**：
  - **外部通信网关**：包含面向普通 REST 的游戏 API (`api/game_routes.py`)，提供大文件 WebSocket 分片上传路由与 WebSocket 调试接口，以及斗地主的核心 WebSocket 对战网关 (`websocket/game_routes.py`)。

---

## ⚡ WebSocket 核心交互协议

对局过程完全基于 WebSocket 事件驱动交互。核心交互事件协议如下：

### 1. 客户端发起动作 (Client Actions)
客户端往对战网关发送消息时使用统一格式：`{"action": "动作名", ...}`

* **开始匹配 / 取消匹配**：
  ```json
  {"action": "join_match", "nickname": "玩家昵称", "base_score": 80}
  {"action": "cancel_match"}
  ```
* **叫地主 / 不叫 / 抢地主 / 不抢**：
  ```json
  {"action": "call_landlord", "score": 3}
  {"action": "skip_call"}
  ```
* **加倍 / 超级加倍 / 不加倍**：
  ```json
  {"action": "choose_doubling", "choice": "double"} // choice 可选: double | super | none
  ```
* **出牌 / 过牌**：
  ```json
  {"action": "play_cards", "cards": [48, 49, 50]} // 传入出牌 ID 数组
  {"action": "pass_turn"}
  ```

### 2. 服务端广播事件 (Server Events)
服务端会根据不同事件向房间内玩家推送更新。为保证游戏公平性，向不同座席广播时会调用 `GameRoom.get_player_view(player_id)`，隐藏他人手牌并只暴露其余手牌张数。

* **对局开始 (`game_start`)**：
  ```json
  {
    "event": "game_start",
    "room_id": "room_xxx",
    "hand": [53, 52, 50, 49, 48], // 当前玩家被分配的手牌 ID 列表
    "current_turn": "player_123",  // 第一个叫分的座席 ID
    "turn_deadline": 1782390120,   // 当前回合超时的绝对时间戳
    "players": [
      {"id": "p1", "nickname": "玩家A", "is_ai": false, "remaining": 17},
      {"id": "p2", "nickname": "机器人", "is_ai": true, "remaining": 17}
    ]
  }
  ```
* **地主确定 (`landlord_decided`)**：
  ```json
  {
    "event": "landlord_decided",
    "landlord": "p1",
    "bottom_cards": [51, 47, 43], // 广播三张明面底牌
    "multiplier": 2                // 当前房间倍数翻倍
  }
  ```
* **出牌成功 (`cards_played`)**：
  ```json
  {
    "event": "cards_played",
    "player": "p1",
    "cards": [48, 49, 50],
    "card_type": "triple",         // 智能识别的牌型
    "next_turn": "p2"              // 下一个出牌回合的玩家 ID
  }
  ```

---

## ⚙️ 运行环境与先决条件 (Prerequisites)

在本地运行或开发本项目之前，请确保您的系统已安装以下软件环境：

* **Python**: 3.10.20 (**强制使用项目专用 conda 环境 `hmp_ai`**)
* **Node.js**: 18.0+ (推荐 v20.x 或以上)
* **MySQL**: 5.7+ 或 8.0+
* **Redis**: 6.0+ (用于存放匹配队列和房间状态)
* **RabbitMQ**: 3.8+ (可选，用于站内信通知的广播分发)

---

## 🚀 快速启动指南

### 1. 数据库准备与配置

1. 复制或创建后端目录下的环境变量配置文件 `.env`：
   ```ini
   PORT=18088
   DB_HOST=127.0.0.1
   DB_PORT=3306
   DB_USER=root
   DB_PASSWORD=your_password
   DB_NAME=happy_doudizhu
   REDIS_HOST=127.0.0.1
   REDIS_PORT=6379
   REDIS_PASSWORD=your_redis_password
   RABBITMQ_HOST=127.0.0.1
   RABBITMQ_PORT=5672
   RABBITMQ_USER=guest
   RABBITMQ_PASSWORD=guest
   ```
2. 运行一键初始化脚本，自动检测并创建 MySQL 数据库 `happy_doudizhu` 及其所有表结构：
   ```powershell
   # 请确保当前终端处于 backend 目录下，且使用的是 hmp_ai 专属环境的 Python
   cd backend
   D:\ProgramData\miniconda3\envs\hmp_ai\python.exe scripts/create_db.py
   ```

### 2. 后端启动

1. 安装项目依赖：
   ```powershell
   cd backend
   D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pip install -r requirements.txt
   ```
2. 启动 FastAPI 后端服务：
   ```powershell
   D:\ProgramData\miniconda3\envs\hmp_ai\python.exe main.py
   ```

### 3. 前端配置与启动

### 2. 前端配置与启动
1. 进入前端目录：
   ```bash
   cd frontend
   ```
2. 安装项目依赖：
   ```bash
   npm install
   npm run dev
   ```
4. 启动成功后，在浏览器访问 `http://localhost:5173` 即可开始对局。

### 4. 数据库版本管理与迁移 (Alembic)

项目配置了 Alembic 作为数据库物理表结构的迁移和演进工具。为了保障安全性，Alembic 在 `backend/alembic/env.py` 中被配置为**动态从后端 `.env` 中加载 `DATABASE_URL`**，无需在 `alembic.ini` 中配置任何明文密码。

如果未来您修改了 `backend/app/infrastructure/database/models.py` 中的表模型结构，可以通过以下命令进行迁移操作：

1. **自动比对并生成迁移版本脚本** (开发环境)：
   ```powershell
   cd backend
   # 使用 hmp_ai 专属环境的 Python 运行 alembic
   D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m alembic revision --autogenerate -m "描述你的表结构变更"
   ```
   > 运行后会在 `backend/alembic/versions/` 下生成一个新的 `.py` 变更历史脚本。请仔细核对脚本中的 `upgrade()` 和 `downgrade()` 逻辑。

2. **应用迁移更新数据库表结构** (生产/开发环境升级)：
   ```powershell
   cd backend
   D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m alembic upgrade head
   ```

3. **回滚最近一次数据库迁移**：
   ```powershell
   cd backend
   D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m alembic downgrade -1
   ```

4. **查看历史迁移记录列表**：
   ```powershell
   cd backend
   D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m alembic history
   ```

---

## 🏆 独特排位头衔系统 (Rank System)

运行以下命令执行全自动单元测试，验证核心领域规则：

* **后端测试** (覆盖领域模型、AI 叫牌判定、大文件安全分片等)：
   ```powershell
   # 使用 hmp_ai 专属环境的 Python 运行测试
   D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest backend/tests/ -v
   ```
* **前端测试**：
   ```bash
   cd frontend
   npm run test:unit
   ```

---

## 🔄 核心对局与匹配数据流向

整个游戏系统的用户匹配、实时叫分、打牌到终局结算，依赖于 Redis 缓存的低延迟性能和 MySQL 的持久化保障。以下是核心数据流向时序图：

```mermaid
sequenceDiagram
    actor PlayerA as 玩家 A
    actor PlayerB as 玩家 B (或 AI机器人)
    participant WS as WebSocket 网关 (game_routes.py)
    participant AppService as 游戏应用服务 (GameAppService)
    participant Redis as Redis 缓存 (RedisGameRepository)
    participant DB as MySQL 数据库 (SQLGameRepository)

    PlayerA->>WS: join_match (请求加入匹配, 携带底分)
    WS->>AppService: 触发匹配请求
    AppService->>Redis: 压入匹配队列 (base_score 键名)
    Note over AppService, Redis: 队列满 3 人即匹配成功, 自动建房并分牌
    AppService->>WS: 广播 game_start 事件
    WS-->>PlayerA: 推送 PlayerA 专属视角手牌 (隐藏他人手牌)
    WS-->>PlayerB: 推送 PlayerB 专属视角手牌 (隐藏他人手牌)
    
    PlayerA->>WS: call_landlord / play_cards (叫地主/出牌)
    WS->>AppService: 提交出牌动作，校验合法性
    AppService->>Redis: 更新房间状态机与对局状态 (2小时TTL)
    AppService->>WS: 广播 cards_played / turn_passed 事件

    Note over AppService: 某一玩家手牌出完, 触发游戏结束
    AppService->>DB: 写入 game_record，原子更新玩家积分/欢乐豆/排位星数
    AppService->>WS: 广播 game_over (推送终局结算详情)
```

---

## ⚡ WebSocket 核心交互协议

对局过程完全基于 WebSocket 事件驱动交互。核心交互事件协议如下：

### 1. 客户端发起动作 (Client Actions)
客户端往对战网关发送消息时使用统一格式：`{"action": "动作名", ...}`

* **开始匹配 / 取消匹配**：
  ```json
  {"action": "join_match", "nickname": "玩家昵称", "base_score": 80}
  {"action": "cancel_match"}
  ```
* **叫地主 / 不叫 / 抢地主 / 不抢**：
  ```json
  {"action": "call_landlord", "score": 3}
  {"action": "skip_call"}
  ```
* **加倍 / 超级加倍 / 不加倍**：
  ```json
  {"action": "choose_doubling", "choice": "double"} // choice 可选: double | super | none
  ```
* **出牌 / 过牌**：
  ```json
  {"action": "play_cards", "cards": [48, 49, 50]} // 传入出牌 ID 数组
  {"action": "pass_turn"}
  ```

### 2. 服务端广播事件 (Server Events)
服务端会根据不同事件向房间内玩家推送更新。为保证游戏公平性，向不同座席广播时会过滤数据，隐藏他人手牌并只暴露其余手牌张数。

* **对局开始 (`game_start`)**：
  ```json
  {
    "event": "game_start",
    "room_id": "room_xxx",
    "hand": [53, 52, 50, 49, 48], // 当前玩家被分配的手牌 ID 列表
    "current_turn": "player_123",  // 第一个叫分的座席 ID
    "turn_deadline": 1782390120,   // 当前回合超时的绝对时间戳
    "players": [
      {"id": "p1", "nickname": "玩家A", "is_ai": false, "remaining": 17},
      {"id": "p2", "nickname": "机器人", "is_ai": true, "remaining": 17}
    ]
  }
  ```
* **地主确定 (`landlord_decided`)**：
  ```json
  {
    "event": "landlord_decided",
    "landlord": "p1",
    "bottom_cards": [51, 47, 43], // 广播三张明面底牌
    "multiplier": 2                // 当前房间倍数翻倍
  }
  ```
* **出牌成功 (`cards_played`)**：
  ```json
  {
    "event": "cards_played",
    "player": "p1",
    "cards": [48, 49, 50],
    "card_type": "triple",         // 智能识别的牌型
    "next_turn": "p2"              // 下一个出牌回合的玩家 ID
  }
  ```

---

## 🏆 独特排位头衔系统 (Rank System)

游戏包含一套富有趣味的 **36 级特色排位头衔系统**，玩家通过赢取星星提升段位，展现身价头衔。

### 1. 36级头衔一览
头衔由低到高划分为 36 个大级别：
* **新手期 (1-9级)**：`包身工`、`短工`、`长工`、`中农`、`富农`、`掌柜`、`商人`、`小财主`、`大财主`。
* **中产期 (10-21级)**：`县尉`、`县丞`、`县令`、`通判`、`主事`、`知府`、`员外郎`、`郎中`、`侍郎`、`巡抚`、`总督`、`尚书`。
* **达贵期 (22-35级)**：`大学士`、`太保`、`太傅`、`太师`、`三等伯`、`二等伯`、`一等伯`、`三等侯`、`二等侯`、`一等侯`、`辅国公`、`镇国公`、`郡王`、`亲王`。
* **终极大满贯 (36级)**：`至尊`。

> 除【至尊】外，每个头衔划分为 `IV, III, II, I` 四个子级别。

### 2. 升降星状态机规则
后端通过 `SQLGameRepository` 在每局终局结算时对段位执行原子变动：
* **爆发胜利加星**：普通胜利积 **1 星**；使用炸弹/王炸或者以春天获胜（爆发性胜利），星星 **+2**。
* **新手保护机制 (1-9级)**：小段位满 **3 星** 即可晋级；输牌不扣星，不降段。
* **中大段位保护 (10-21级)**：小段位满 **4 星** 晋级；输牌扣 **1 星**；大段位触发保护机制（例如不会从“县尉IV”降回“大财主I”）。
* **无保护硬核博弈 (22-35级)**：小段位满 **5 星** 晋级；输牌扣 **1 星**；段位无任何保护（降星可直接跌落大级别）。

---

## 🤖 托管 AI 决策与降级策略

对局系统集成了高可用的 AI 机制，保障流畅的网络对战体验：

1. **自动补位与托管**：匹配等待超时 10 秒后，AI 机器人将自动补齐空位开局；对局中玩家掉线时，AI 会无缝接管出牌。
2. **双层决策引擎**：
   - **DouZero 强化学习 AI**：优先调用基于 DeepMind 强化学习训练的 DouZero AI 进行精细的算牌与出牌决策。
   - **规则兜底 (Rule-based AI)**：若 DouZero 推理模型未加载或出现计算异常，系统会瞬间降级到规则 AI，依据手牌顺位、大牌压制等预设规则执行合理出牌，保障人机对战完全不中断。

---

## 🙏 开源依赖与鸣谢 (Credits & Dependencies)

本项目在开发过程中，深受开源社区众多优秀项目启发与支撑，特此向以下 GitHub 优质开源项目及团队致以最诚挚的敬意：

### 1. 算法与决策 AI 模型
* **[kwai/douzero](https://github.com/kwai/douzero)** — 经典的基于强化学习（Deep Monte-Carlo, DMC）的斗地主 AI 训练框架。

### 2. 后端异步生态依赖
* **[tiangolo/fastapi](https://github.com/tiangolo/fastapi)** — 高性能、易学、快速编写代码的异步 Web 框架。
* **[sqlalchemy/sqlalchemy](https://github.com/sqlalchemy/sqlalchemy)** — 极具工业强度且设计优雅的 Python SQL 工具包与 ORM 映射器。
* **[redis/redis-py](https://github.com/redis/redis-py)** — 强大的 Redis 异步 Python 客户端驱动，提供了极其稳定的连接池管理。
* **[mosbrupture/aio-pika](https://github.com/mosbrupture/aio-pika)** — 专为 asyncio 打造的 RabbitMQ 异步驱动。

### 3. 前端响应式生态依赖
* **[vuejs/core](https://github.com/vuejs/core)** — 渐进式 JavaScript 框架。
* **[vitejs/vite](https://github.com/vitejs/vite)** — 极速的下一代前端开发与构建工具。
* **[vuejs/pinia](https://github.com/vuejs/pinia)** — 专为 Vue 打造的轻量状态管理库。
