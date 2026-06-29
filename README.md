# HMP WS Service — 欢乐斗地主 (Happy Dou Di Zhu)

本项目是在 HMP WS Service 基础上构建的、采用前后端彻底分离架构的“欢乐斗地主”网络对战系统。系统采用 **FastAPI + Vue 3** 作为底座，搭配 **Redis** 存储匹配队列与对局状态，以及 **MySQL** 落地存储战绩与玩家档案。

---

## 🎨 游戏特色

1. **实时 WebSocket 对战网关**
   - 独立的对局连接通道 `/ws/game/{player_id}`，全事件驱动交互。
   - 自主研发的 `GameWSConnectionManager` 提供精细的多人会话广播与管道隔离。
   - 强健的掉线重连机制（指数退避自动重连），玩家刷新页面或短暂断网能无缝返回原房间继续对局。

2. **多套自研核心规则算法引擎**
   - **扑克牌领域模型**：严格的编码与处理机制。
   - **智能牌型检测引擎**：支持单张、对子、三张、三带一、三带二、单顺、双顺、飞机、四带二、炸弹、火箭等 14 种斗地主常规牌型的智能校验与牌型压制（`can_beat`）判定。
   - **AI 智能策略机器人**：在对局匹配等待超时（10秒）时自动补齐空余席位；当真人玩家断线时提供极致逼真的 AI 自动接管托管。

3. **双层持久化与排行榜系统**
   - 匹配排队原子性地依托 Redis 列表管理。
   - 游戏战绩记录与玩家属性（欢乐豆、局数、胜率）在终局清算时通过 SQLAlchemy ORM 原子写入 MySQL 中。
   - 提供全局欢乐豆富豪排行榜展示。

4. **快捷广播气泡聊天**
   - 内置常用聊天短句广播（“快点吧”、“合作愉快”等），为座席气泡提供 3 秒自清理动画。

---

## 📂 项目结构

```text
hmp_ws_service/
├── backend/            # 后端服务 (FastAPI + DDD 架构)
│   ├── app/            # 领域/应用/基础设施/适配器分层
│   ├── tests/          # pytest 单元测试与 mock 通道
│   └── main.py         # 后端主程序入口
└── frontend/           # 前端客户端 (Vue 3 + Vite SPA)
    ├── src/            
    │   ├── components/ # 扑克牌 (PokerCard)、手牌 (HandCards)、座位 (PlayerSeat) 等
    │   ├── stores/     # Pinia 状态管理 (playerStore, gameStore)
    │   └── views/      # 页面视图 (Login, Lobby, GameRoom)
    └── vite.config.ts  # Vite 配置 (包含 WebSocket 与 API 路由代理)
```

---

## 🛠️ 技术栈

### 后端
- **框架**: FastAPI (Python 3.10+)
- **缓存 & 匹配**: Redis (aioredis 异步驱动)
- **关系数据库**: MySQL 5.7+ / PostgreSQL (SQLAlchemy 2.0 ORM)
- **测试框架**: pytest

### 前端
- **核心**: Vue 3 (Composition API) + TypeScript
- **构建工具**: Vite 8.0+
- **状态管理**: Pinia
- **路由导航**: Vue Router 4
- **测试框架**: Vitest + JSDOM

---

## 🚀 快速开始

### 1. 后端启动

1. 进入后端目录：
   ```bash
   cd backend
   ```
2. 激活 Python 虚拟环境（如 conda 环境 `hmp_ai`）：
   ```bash
   conda activate hmp_ai
   ```
3. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```
4. 配置 `.env` 环境变量，例如：
   ```ini
   PORT=18088
   DB_HOST=127.0.0.1
   DB_PORT=3306
   DB_USER=root
   DB_PASSWORD=your_password
   DB_NAME=hmp_websocket
   REDIS_HOST=127.0.0.1
   REDIS_PORT=6379
   ```
5. 启动后端：
   ```bash
   python main.py
   ```
   服务将运行在 `http://127.0.0.1:18088`。

### 2. 前端启动

1. 进入前端目录：
   ```bash
   cd frontend
   ```
2. 安装依赖：
   ```bash
   npm install
   ```
3. 启动开发服务器：
   ```bash
   npm run dev
   ```
   前端服务将运行在 `http://localhost:5173`。打开浏览器访问即可开始游玩。

---

## 🧪 单元测试

### 后端测试
进入后端目录，运行以下命令验证后端逻辑（包含领域状态机、AI、Redis、API 与 WebSocket 测试共 75 项）：
```bash
cd backend
python -m pytest tests/ -v
```

### 前端测试
进入前端目录，运行以下命令验证前端单元测试：
```bash
cd frontend
npm run test:unit
```
