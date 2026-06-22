# 审计日志接口查询 Redis 防抖设计规格说明书

本项目需要拦截并审计关键查询接口（如查询站内信 `QUERY_MESSAGES`，查询上传文件 `QUERY_UPLOADED_FILES`）。但为了避免高频重复点击导致审计日志表冗余泛滥以及内存压力，我们需要引入防抖去重过滤。

## 设计目标
1. 拦截高频重复查询，防抖周期为 3 秒。若 3 秒内同一操作者使用相同参数发出同类查询，则只返回业务数据，不记录重复审计日志。
2. 规避死循环审计：彻底移除 `"QUERY_AUDIT_LOGS"`（查询审计日志本身）的审计逻辑。
3. 稳定性保证：采用 Redis 作为防抖缓存源；当 Redis 服务宕机或异常时，优雅降级（不进行防抖过滤，但绝不影响主业务的查询和默认审计功能）。

## 技术实现

### 1. 依赖与配置
- 引入 `redis` 包（异步客户端模式）。
- 在 `.env` 中加入 Redis 基础配置：
  - `REDIS_HOST=127.0.0.1`
  - `REDIS_PORT=6379`
  - `REDIS_PASSWORD=123456`
  - `REDIS_DB=0`

### 2. Redis 连接器 (app/infrastructure/redis_client.py)
初始化全局 `redis_client`，采用 `redis.asyncio` 连接池以支持异步。
- 定义 `is_query_debounced(key: str, expire_seconds: int = 3) -> bool`。
  - 通过 Redis `SET key 1 EX expire_seconds NX` 来原子性判断并写入 Key。
  - 如果写入失败（返回 `None` / `False`），说明防抖 Key 已存在，本次操作应该被防抖拦截。
  - 发生任何 Redis 交互异常时捕获并打印 warn 日志，返回 `False`，实现安全优雅降级。

### 3. 自定义拦截路由 (app/infrastructure/audit_route.py)
- 更新 `auditable_actions`，移除 `"QUERY_AUDIT_LOGS"`。
- 在拦截器开始计时前后，若是查询类型的 action（例如以 `"QUERY_"` 开头的 action）：
  1. 计算当前请求的指纹/Key：格式为 `hmp:audit:debounce:{operator}:{action}:{hash(request_params)}`。
  2. 调用 `redis_client` 进行防抖判定。
  3. 如果被判定为重复请求，在上下文中打上 `skip_audit = True` 标记。
  4. 如果 `skip_audit` 为 True，在请求完成时跳过 `record_log` 操作。

### 4. 单元测试校验
- 在 [test_audit_route.py](file:///d:/Project_2023/hmp_ws_service/tests/test_audit_route.py) 中，测试查询接口时的 Redis 成功/失败降级判定。
- Mock 模拟 Redis 并在高频重复请求下验证仅有一条审计记录写入。
