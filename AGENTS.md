# AGENTS.md

本文件给后续进入本仓库的 agent 使用，记录当前项目结构、技术栈、运行方式和开发约束。请优先阅读并遵守本文，再修改代码。

## 强制约束

- 禁止批量删除文件或目录。
- 不要使用 `del /s`、`rd /s`、`rmdir /s`、`Remove-Item -Recurse`、`rm -rf`。
- 如需删除文件，只能一次删除一个明确路径的文件，例如：`Remove-Item "C:\path\to\file.txt"`。
- 如果确实需要批量删除文件，应停止操作并询问用户，让用户手动删除。
- 当前仓库可能存在用户未提交的改动。不要还原、覆盖或清理自己没有制造的变更。

## 项目概览

该仓库是 `HMP WS Service` 与“欢乐斗地主”网络对战系统的组合项目，采用前后端分离架构：

- 后端位于 `backend/`，基于 FastAPI、SQLAlchemy、Redis、RabbitMQ，按 DDD 分层组织。
- 前端位于 `frontend/`，基于 Vue 3、TypeScript、Vite、Pinia、Vue Router。
- 文档位于 `docs/superpowers/`，包含历史设计规格和实施计划，尤其是斗地主、审计日志、DouZero AI、欢乐豆和排位系统相关文档。
- 测试主要位于 `backend/tests/`，覆盖领域规则、API、WebSocket、Redis 仓储、上传安全、鉴权、审计日志等。

项目核心业务包括：

- 斗地主实时对战，入口 WebSocket 为 `/ws/game/{player_id}`。
- 用户注册/登录、玩家档案、欢乐豆、排行榜、排位段位。
- Redis 匹配队列、玩家房间映射和房间状态缓存。
- MySQL 持久化用户、玩家档案、战绩、站内信、上传文件和审计日志。
- RabbitMQ 站内信广播。
- WebSocket 大文件分片上传与调试控制台。
- DouZero 强化学习 AI 权重与规则 AI 降级策略。

## 顶层目录

```text
hmp_ws_service/
├── backend/                 # FastAPI 后端服务
│   ├── app/
│   │   ├── domain/          # 领域层：实体、规则、仓储契约
│   │   ├── application/     # 应用层：业务编排服务
│   │   ├── infrastructure/  # 基础设施：数据库、Redis、RabbitMQ、鉴权、日志
│   │   └── interfaces/      # 接口层：REST、WebSocket、Web 页面路由
│   ├── alembic/             # 数据库迁移
│   ├── static/              # 后端静态资源
│   ├── tests/               # pytest 测试
│   ├── main.py              # 后端入口
│   └── requirements.txt     # Python 依赖
├── frontend/                # Vue 3 + Vite 前端
│   ├── src/
│   │   ├── views/           # Login、Lobby、GameRoom、DebugConsole 等页面
│   │   ├── components/      # PokerCard、HandCards、PlayerSeat、SettlementModal 等组件
│   │   ├── stores/          # Pinia 状态：playerStore、gameStore
│   │   ├── composables/     # useGameWebSocket
│   │   └── utils/           # cardUtils 等前端规则工具
│   ├── package.json
│   └── vite.config.ts
├── docs/superpowers/        # 设计规格与实施计划
├── pytest.ini               # pytest 配置，pythonpath 指向 backend
└── README.md                # 项目说明
```

## 后端架构要点

后端入口是 `backend/main.py`：

- 创建 `FastAPI(title="HMP WS Service (DDD)")`。
- 注册 CORS，允许 `http://localhost:5173` 和 `http://127.0.0.1:5173`。
- 挂载 `/static` 到 `backend/static`。
- 注册站内信、上传、审计日志、普通 WebSocket、斗地主 WebSocket、斗地主 REST API 等路由。
- 在 lifespan 中初始化数据库、上传服务、RabbitMQ、斗地主 WebSocket 管理器、Redis 游戏仓储和 `GameAppService`。
- 后台任务包括 RabbitMQ 自动重连消费者和过期上传目录清理。
- 默认监听端口是 `18088`。

DDD 分层约定：

- `backend/app/domain/`：纯领域逻辑。斗地主牌、牌型、房间状态机、AI 策略、实体和仓储抽象都在这里。
- `backend/app/application/`：应用服务。负责调用领域对象和基础设施完成业务流程。
- `backend/app/infrastructure/`：数据库、Redis、RabbitMQ、鉴权、日志、存储适配器等外部依赖。
- `backend/app/interfaces/`：HTTP REST、WebSocket 和 Web 控制台路由。

## 斗地主核心模块

关键文件：

- `backend/app/domain/game/card.py`：扑克牌编码、排序、洗牌发牌。
- `backend/app/domain/game/card_type.py`：牌型检测和 `can_beat` 压制判断。
- `backend/app/domain/game/room.py`：斗地主房间状态机。
- `backend/app/application/game/game_app_service.py`：匹配、创建房间、叫地主、出牌、AI 回合编排。
- `backend/app/infrastructure/redis_game_repository.py`：Redis 房间状态、玩家房间映射、按底分区分的匹配队列。
- `backend/app/interfaces/websocket/game_routes.py`：游戏 WebSocket 连接入口和连接管理器。
- `backend/app/interfaces/websocket/game_handler.py`：WebSocket 事件分发、广播、AI 自动回合、结算入库。
- `backend/app/interfaces/api/game_routes.py`：用户、玩家档案、战绩、排行榜、欢乐豆、段位 API。

游戏状态机阶段：

- `MATCHING`
- `DEALING`
- `CALLING`
- `PLAYING`
- `SETTLING`

常见 WebSocket 客户端动作：

- `join_match`
- `cancel_match`
- `call_landlord`
- `skip_call`
- `play_cards`
- `pass_turn`
- `chat`
- `sync_room_state`

常见服务端事件：

- `match_waiting`
- `match_success`
- `game_start`
- `call_made`
- `call_skipped`
- `landlord_decided`
- `redeal`
- `cards_played`
- `turn_passed`
- `game_over`
- `chat_msg`
- `reconnected`
- `error`

游戏状态会按玩家视角返回，`GameRoom.get_player_view(player_id)` 会隐藏其他玩家手牌，只暴露剩余牌数。

## 数据与外部依赖

主要环境变量：

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
REDIS_DB=0
RABBITMQ_HOST=127.0.0.1
RABBITMQ_PORT=5672
RABBITMQ_USER=guest
RABBITMQ_PASSWORD=guest
API_TOKEN=secure-secret-token
GAME_AUTH_SECRET=secure-game-auth-secret
APP_ENV=development
AUTO_INIT_DB=true
```

数据库模型在 `backend/app/infrastructure/database/models.py`，实际表名均带 `ddz_` 前缀：

| 模型类 | 实际表名 | 说明 |
| --- | --- | --- |
| `SiteMessageORM` | `ddz_site_message` | 站内信 |
| `UploadedFileORM` | `ddz_uploaded_file` | 上传文件 |
| `AuditLogORM` | `ddz_audit_log` | 审计日志 |
| `PlayerProfileORM` | `ddz_player_profile` | 玩家档案 |
| `UserORM` | `ddz_user_account` | 用户账号 |
| `GameRecordORM` | `ddz_game_record` | 对局战绩 |

数据库初始化逻辑在 `backend/app/infrastructure/database/session.py`：

- 非生产环境默认自动建表。
- 生产环境默认不自动建表，除非显式设置 `AUTO_INIT_DB`。
- 对 `audit_log` 和 `player_profile` 的部分字段有自愈补齐逻辑。

Redis 游戏键名前缀：

- 房间：`game:room:{room_id}`
- 玩家房间映射：`game:player_room:{player_id}`
- 匹配队列：`game:match_queue:{base_score}`

Redis TTL：

- 房间状态 2 小时。
- 玩家房间映射 1 小时。

## 鉴权与安全

- 普通 HTTP API 可使用 `API_TOKEN`，支持 Bearer Header 或 `?token=` Query。
- 开发环境未配置 `API_TOKEN` 时，普通 API 默认放行。
- 生产环境必须配置 `API_TOKEN`，否则拒绝访问。
- 斗地主用户登录后返回 `auth_token`，前端保存到 `localStorage` 的 `hmp_game_auth_token`。
- 斗地主 REST API 使用 `Authorization: Bearer <auth_token>`。
- 斗地主 WebSocket 使用 `?auth_token=<token>`，并校验 token 内的 `player_id` 必须与路径中的 `{player_id}` 一致。
- 密码使用 PBKDF2-SHA256 存储，新逻辑仍兼容旧的明文比对。
- 上传模块有文件名净化、`upload_id` 校验、路径穿越防护和切片大小/索引校验。

## 前端架构要点

前端入口和路由：

- `frontend/src/main.ts`：Vue 应用入口。
- `frontend/src/router/index.ts`：路由配置。
- `/` 重定向到 `/login`。
- `/login`：登录/注册。
- `/lobby`：大厅、排行榜、欢乐豆和段位管理、场次选择。
- `/game/:roomId?`：斗地主对局页面。
- `/console`：仅开发环境注册，用于 HMP 调试控制台。

状态管理：

- `frontend/src/stores/playerStore.ts`
  - 管理玩家 ID、昵称、账号、游戏 token、欢乐豆、战绩、段位。
  - 提供 `register`、`login`、`logout`、`fetchProfile`、`modifyBeans`、`modifyRank`。
- `frontend/src/stores/gameStore.ts`
  - 管理 WebSocket 连接状态、房间、游戏阶段、手牌、玩家、当前回合、叫分、地主、结算、动画效果等。
  - 后端 snake_case 状态在这里映射为前端需要的字段。

WebSocket 前端封装：

- `frontend/src/composables/useGameWebSocket.ts`
  - 根据当前页面协议构造 `ws://` 或 `wss://`。
  - 连接 `/ws/game/{playerId}?auth_token=...`。
  - 断线后指数退避重连，最大 30 秒。
  - 分发服务端事件并更新 Pinia 状态。

前端代理配置在 `frontend/vite.config.ts`：

- `/ws/game` 和 `/ws` 代理到 `ws://127.0.0.1:18088`。
- `/api/game`、`/api/messages`、`/api/uploads`、`/api/audit-logs` 代理到 `http://127.0.0.1:18088`。

## 调试控制台与原 HMP 能力

除了斗地主，项目仍保留 HMP WS Service 的调试能力：

- 普通 WebSocket：`/ws/{client_id}`。
- 旧仓储镜像 WebSocket：`/hmp_ws_service/repository/mirror/v2.0`。
- 站内信 API：`/api/messages`。
- 上传文件 API：`/api/uploads`。
- 审计日志 API：`/api/audit-logs`。
- 开发环境前端控制台页面：`/console`。

`DebugConsoleView.vue` 内置 WebSocket 调试、站内信、二进制切片上传、审计日志查询等功能。

## Python 运行环境

> **强制要求**：后端必须使用以下专用 conda 环境运行，禁止使用系统默认 Python。

| 项目 | 値 |
| --- | --- |
| Conda 环境名 | `hmp_ai` |
| Python 解释器路径 | `D:\ProgramData\miniconda3\envs\hmp_ai\python.exe` |
| Python 版本 | 3.10.20 |
| 激活命令（可选） | `conda activate hmp_ai` |

**原因**：系统全局 Python 为 3.13，SQLAlchemy 2.0.25 与 Python 3.13 存在类继承兼容性问题（`__static_attributes__`、`__firstlineno__`），会导致所有测试和服务启动失败。`hmp_ai` 环境已完整安装 `requirements.txt` 中的所有依赖，是本项目唯一经过验证的运行环境。

**新环境初始化数据库**（首次部署时运行）：

```powershell
cd backend
D:\ProgramData\miniconda3\envs\hmp_ai\python.exe scripts/create_db.py
```

---

## 运行命令

> 以下命令中的 `python` 均指 `D:\ProgramData\miniconda3\envs\hmp_ai\python.exe`，请勿使用系统 python。

后端依赖安装：

```powershell
cd backend
D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pip install -r requirements.txt
```

后端启动：

```powershell
cd backend
D:\ProgramData\miniconda3\envs\hmp_ai\python.exe main.py
```

后端测试（全量）：

```powershell
cd backend
D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest tests/ -v
```

后端测试（快速，失败即停）：

```powershell
cd backend
D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest tests/ -x -q --tb=short
```

前端依赖安装：

```bash
cd frontend
npm install
```

前端开发服务器：

```bash
cd frontend
npm run dev
```

前端测试：

```bash
cd frontend
npm run test:unit
```

前端构建：

```bash
cd frontend
npm run build
```

## 测试现状

后端当前有约 20 个测试文件、145 个测试函数（截至 2026-07-07 全部通过），重点覆盖：

- 扑克牌编码、排序和发牌。
- 斗地主牌型识别与压制规则。
- 房间状态机、叫地主、出牌、结算。
- AI 策略、DouZero 模型适配和降级。
- Redis 游戏仓储与 Redis 防抖。
- 游戏 REST API 与 WebSocket。
- 用户鉴权、游戏 token、生产环境安全要求。
- 上传安全、路径穿越防护、切片边界。
- 审计日志 APIRoute。
- 数据库启动初始化策略。

运行测试必须使用 `hmp_ai` 环境（见“Python 运行环境”章节），否则因 Python 3.13 兼容性问题无法收集测试。

前端目前只有默认组件测试较少，修改核心前端交互时应优先做手动联调，必要时补 Vitest。

## 开发注意事项

- 后端新增业务逻辑时，优先放在合适分层：领域规则进 `domain`，流程编排进 `application`，外部依赖进 `infrastructure`，路由进 `interfaces`。
- 斗地主核心规则不要绕过 `GameRoom` 状态机，避免前后端状态不一致。
- WebSocket 广播给房间玩家时，应使用玩家个人视角，不要泄露其他玩家手牌。
- 修改游戏事件协议时，需要同步更新 `game_handler.py`、`useGameWebSocket.ts` 和相关 Pinia store。
- 修改数据库模型后，检查 Alembic 迁移和 `session.py` 中是否仍有必要的自愈逻辑。
- 修改鉴权逻辑时，同时考虑开发环境兼容和生产环境强制安全。
- 修改上传清理逻辑时，尤其注意路径穿越防护；并遵守本文开头的删除限制。
- 前端 UI 已经是游戏化界面，修改时应保持实际可玩，不要把首页改成营销落地页。
- 前端文本和按钮较多，改样式后要检查移动端和桌面端是否有文字溢出或遮挡。
- 运行或生成文件时，避免提交 `backend/log/`、`backend/uploads/`、`backend/temp_uploads/`、`frontend/dist/`、`frontend/node_modules/` 等忽略目录。

## 重要历史文档

`docs/superpowers/` 中的文档可作为需求和设计来源：

- 斗地主完整设计：`docs/superpowers/specs/2026-06-23-doudizhu-game-design.md`
- 斗地主实现计划：`docs/superpowers/plans/2026-06-23-doudizhu-game.md`
- AI 策略设计：`docs/superpowers/specs/2026-06-24-ai-strategy-design.md`
- DouZero 集成设计：`docs/superpowers/specs/2026-06-24-douzero-integration-design.md`
- 欢乐豆管理设计：`docs/superpowers/specs/2026-06-25-beans-management-design.md`
- 排位系统设计：`docs/superpowers/specs/2026-06-25-rank-system-design.md`
- 审计日志设计：`docs/superpowers/specs/2026-06-23-audit-log-design.md`
- Redis 防抖设计：`docs/superpowers/specs/2026-06-23-audit-log-redis-debounce-design.md`
- 日志解耦设计：`docs/superpowers/specs/2026-06-23-logging-decoupling-architecture-design.md`

## 快速定位表

| 需求 | 优先查看 |
| --- | --- |
| 斗地主规则、状态机 | `backend/app/domain/game/room.py`、`card_type.py` |
| AI 出牌/叫地主 | `backend/app/domain/game/ai_strategy.py`、`douzero_*` |
| 匹配与房间创建 | `backend/app/application/game/game_app_service.py` |
| 游戏 WebSocket 协议 | `backend/app/interfaces/websocket/game_handler.py`、`useGameWebSocket.ts` |
| 游戏 REST API | `backend/app/interfaces/api/game_routes.py` |
| 玩家档案/欢乐豆/排位 | `backend/app/infrastructure/database/game_repository.py`、`playerStore.ts` |
| 数据库表结构 | `backend/app/infrastructure/database/models.py` |
| Redis 房间状态 | `backend/app/infrastructure/redis_game_repository.py` |
| 普通长连接/上传 | `backend/app/interfaces/websocket/ws_routes.py`、`DebugConsoleView.vue` |
| 站内信 | `message_routes.py`、`message_app_service.py`、`rabbitmq_adapter.py` |
| 审计日志 | `audit_route.py`、`audit_log_routes.py` |
| 前端大厅 | `frontend/src/views/LobbyView.vue` |
| 前端对局 | `frontend/src/views/GameRoomView.vue` |
| 前端牌组件 | `PokerCard.vue`、`HandCards.vue`、`PlayerSeat.vue` |

