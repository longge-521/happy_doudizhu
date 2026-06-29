# HMP WS Service (DDD)

HMP WS Service 高性能异步长连接与大文件传输中心，是一套基于 **FastAPI + SQLAlchemy + RabbitMQ** 的高性能实时通信与文件服务。项目采用领域驱动设计（DDD）的分层架构，实现了安全的 WebSocket 长连接生命周期管理、RabbitMQ 扇出模式的多实例实时消息广播、MySQL 站内信系统以及基于二进制帧零拷贝与并发滑动窗口的流式大文件分片上传。

---

## 🚀 核心功能

1. **WebSocket 长连接网关**
   - **多标签页共存**：完美支持同一客户端 ID 下的多浏览器标签页/多连接管理，下线精确移除。
   - **自动重连机制**：前端具备指数退避自动重连，服务端具备鲁棒垃圾回收。
   - **安全令牌校验**：支持基于 Bearer Header 或 Query 参数的安全 Token 校验边界。
2. **分布式站内信广播系统**
   - **多实例分发**：支持 **RabbitMQ Fanout Exchange** 扇出广播。在集群/多实例水平扩展部署时，保证每个节点都能消费到消息并推送给其本地的在线用户。
   - **非阻塞落库**：采用多线程隔离机制（`asyncio.to_thread`），高并发下数据库操作不阻塞 asyncio 主事件循环。
3. **滑动窗口并发大文件分片上传**
   - **二进制流式传输**：采用纯二进制 Websocket 帧配合零拷贝技术，保障内存与 CPU 的极致低负荷。
   - **并发滑动窗口**：基于客户端并发发送控制（滑动窗口机制），兼顾测速、ETA 预估与上传取消防护。
   - **路径穿越防御**：严格校验 `upload_id` 规范，对临时目录删除进行绝对物理路径防越权穿越保护。
4. **全局无侵入式审计日志**
   - **全局拦截**：基于 FastAPI APIRoute 拦截器自动对关键接口请求（方法、耗时、过滤敏感 Token 的参数等）进行统计与异步落库。
5. **Redis 高频滑动防抖去重**
   - **高频防抖**：提供基于 Redis 分布式锁与滑动过期时间的防抖机制，3 秒内同一操作指纹仅保留一次日志落库。支持自愈降级，确保 Redis 故障时不影响主线业务。
6. **大屏全屏自适应与悬浮气泡预览**
   - **全屏平铺**：优化大屏利用率，整体布局升级为 100vw * 100vh 满屏，各面板支持独立滚动。
   - **参数气泡**：表格中过长的请求参数自动截断，鼠标悬浮时可通过 Tooltip 浮现展示多行高亮 JSON 参数预览，提升排查效率。

---

## 🛠️ 技术栈

- **核心框架**：[FastAPI](https://fastapi.tiangolo.com/) (Python 3.10+)
- **ORM / 数据库**：[SQLAlchemy 2.0](https://www.sqlalchemy.org/) + [PyMySQL](https://github.com/PyMySQL/PyMySQL) (MySQL 5.7+)
- **版本迁移管理**：[Alembic](https://alembic.sqlalchemy.org/)
- **消息队列**：[aio-pika](https://github.com/mosbrupture/aio-pika) (RabbitMQ 异步驱动，兼容最新 RabbitMQ 4.3.0+ 版本)
- **校验边界**：[Pydantic v2](https://docs.pydantic.dev/)
- **测试保障**：[pytest](https://docs.pytest.org/) + [httpx](https://www.python-httpx.org/)
- **缓存/防抖**：[Redis](https://redis.io/) (支持无感知优雅降级与密码配置)

---

## 📂 项目目录结构

项目严格遵循 DDD (领域驱动设计) 分层规范进行划分，代码高内聚、低耦合：

```text
hmp_ws_service/
  ├── alembic/                  # Alembic 数据库版本演进迁移目录
  ├── app/                      # DDD 业务代码目录
  │    ├── domain/              # 领域层：包含 site_message 实体、对局卡牌、牌型检测、房间状态机、AI 决策及仓储契约
  │    ├── application/         # 应用层：负责业务流转与编排（Message/Upload 服务层及 GameAppService 匹配发牌）
  │    ├── infrastructure/      # 基础设施层：MySQL 战绩仓储、Redis 状态仓储、RabbitMQ 及 Auth 鉴权
  │    └── interfaces/          # 接口层：HTTP REST 接口、游戏 API 路由、Websockets 端点与对局消息处理器 (Handler)
  ├── static/                   # 独立出来的静态文件托管（CSS/JS/图标库）
  ├── templates/                # HMP 控制台调试 HTML 模板
  ├── tests/                    # 单元测试模块 (包含上传安全、Token鉴权、游戏逻辑、WebSocket 与 REST 测试)
  ├── requirements.txt          # 运行、开发与测试统一依赖清单
  ├── main.py                   # 服务主运行入口
  ├── alembic.ini               # Alembic 配置文件
  └── run.bat                   # Windows 下一键启动批处理脚本
```

---

## ⚙️ 环境配置

在根目录下创建 `.env` 配置文件（或在操作系统环境变量中声明）：

```ini
# 监听端口
PORT=18088

# 数据库配置
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_password
DB_NAME=hmp_websocket

# RabbitMQ 配置
RABBITMQ_HOST=127.0.0.1
RABBITMQ_PORT=5672
RABBITMQ_USER=guest
RABBITMQ_PASSWORD=guest

# 安全令牌配置（若留空则不拦截，便于本地调试）
API_TOKEN=secure-secret-token

# Redis 缓存与防抖配置
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
REDIS_PASSWORD=your_redis_password
REDIS_DB=0
```

---

## 🏃 启动与运行

### 1. 安装项目依赖
建议在 Python 虚拟环境中，运行以下命令一键安装所有运行与开发依赖：
```bash
pip install -r requirements.txt
```

### 2. 数据库迁移与初始化
如果您的数据库之前已包含 `site_message` 表，Alembic 系统已为您配置了最新基线。只需在项目根目录下执行以下指令完成迁移更新：
```bash
alembic upgrade head
```

### 3. 运行服务
您可以通过以下命令直接拉起服务：
```bash
python main.py
```
*在 Windows 环境下，您也可以直接双击根目录下的 `run.bat` 进行一键快速启动。*

启动成功后，您可以通过以下地址访问服务：
- **HMP WS Service 全功能控制台**：[http://127.0.0.1:18088/](http://127.0.0.1:18088/) （用于 WebSocket 通信自测、模拟站内信分发及大文件并发上传验证）
- **Swagger 接口文档**：[http://127.0.0.1:18088/docs](http://127.0.0.1:18088/docs)

---

## 🧪 运行单元测试

项目中已包含完备的单元测试，已经通过 Mock 对 MySQL 及 RabbitMQ 连接进行解耦隔离，您可以直接在本地无污染运行：

```bash
pytest
```

测试覆盖了：
- **路径与上传安全**：校验上传会话 ID 的合法性正则与文件名穿越防护行为。
- **Token 鉴权机制**：验证在提供/不提供 `API_TOKEN` 时的 API 拦截行为与 Query Token 校验。
- **站内信 API 约束**：检验站内信发送接口的字段校验、空字段检测与长度溢出拦截。

---

## 🔄 数据库开发迁移规范 (Alembic)

项目已经初始化了 Alembic 架构支持，在日常迭代中：

1. **更新数据库模型**：当您在 [models.py](file:///d:/Project_2023/hmp_ws_service/app/infrastructure/database/models.py) 中更新了表结构（如修改了字段、增加了索引等）。
2. **自动生成迁移脚本**：在根目录下执行：
   ```bash
   alembic revision --autogenerate -m "变更说明文案"
   ```
   它会在 `alembic/versions/` 目录中生成带有时间戳的 `.py` 版本脚本。请确认脚本内自动生成的 DDL 逻辑（`upgrade` 和 `downgrade`）完全无误。
3. **应用迁移**：
   ```bash
   alembic upgrade head
   ```

---

## 📝 最近更新说明 (Recent Updates)

系统于 2026 年 6 月进行了整体的“控制台全屏化重构”与“审计日志架构升级”，核心变动如下：

1. **审计日志与 APIRoute 拦截器**：
   - 引入了 `AuditLogRoute` 全局拦截器，无侵入式拦截关键路由，自动解析请求方法、路径、传参及耗时，异步执行入库。
   - 数据库表安全扩容，新增 `request_params`（脱敏后传参）、`execution_time`（毫秒耗时）、`method`（请求方式）字段。
2. **Redis 高频滑动防抖拦截器**：
   - 采用 Redis 分布式锁进行防抖锁定，通过 3 秒滑动过期时间合并高频重复请求，显著减轻数据库日志读写压力。
   - 具备自愈降级机制，若 Redis 服务异常会自动打印警告并降级为常规数据库落库，保障业务不中断。
3. **控制台全屏自适应与体验优化**：
   - 对前端进行了全平铺改造，禁止全局溢出，改为各面板独立溢出滚动，提高大屏空间利用率。
   - 新增请求参数长文本截断与 CSS 悬浮气泡预览功能，悬停即可直观查看格式化的多行 JSON 传参。
4. **RabbitMQ 4.3+ 兼容性修复**：
   - 针对新版 RabbitMQ (>=4.0/4.3.0) 废弃并禁止 `transient_nonexcl_queues` 特性以及 `amq.` 系统保留字声明限制，将订阅广播的临时队列重构为 `durable=True, exclusive=False, auto_delete=True` 并使用客户端 UUID 生成队列名称，彻底规避了高版本下的连接中断与 `RESOURCE_LOCKED` 锁冲突报错。
