# 审计日志 Redis 防抖实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 引入 Redis 实现接口查询防抖，消除审计日志无限自审计死循环，并保障单机及多实例环境下的内存安全与优雅降级。

**Architecture:** 拦截查询类操作前，通过 Redis 原子写入 `SET key 1 EX 3 NX` 锁定指纹。如 key 已存在，则忽略当前审计记录。Redis 不可用时静默记录日志并跳过防抖。

**Tech Stack:** FastAPI, Redis, Python-dotenv, Pytest

## Global Constraints
- 保证 Redis 故障时不会抛出未捕获异常而阻断主接口业务（优雅降级）。
- 绝不重复审计 `QUERY_AUDIT_LOGS` 自身（防死循环）。

---

### Task 1: 依赖安装与 Redis 配置

**Files:**
- Modify: `requirements.txt`
- Modify: `.env`

- [ ] **Step 1: 往 requirements.txt 追加依赖**

```text
redis>=4.2.0
```

- [ ] **Step 2: 往 .env 追加 Redis 配置**

```ini
# Redis 缓存配置（用于接口查询防抖）
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
REDIS_PASSWORD=123456
REDIS_DB=0
```

- [ ] **Step 3: 终端安装依赖**

在终端执行：
`D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pip install -r requirements.txt`
期望：安装成功。

- [ ] **Step 4: 提交依赖与配置修改**

```bash
git add requirements.txt
git commit -m "chore: add redis dependency"
```

---

### Task 2: 编写 Redis 客户端与优雅降级函数

**Files:**
- Create: `app/infrastructure/redis_client.py`
- Test: `tests/test_redis_client.py`

**Interfaces:**
- Produces: `is_query_debounced(key: str, expire_seconds: int = 3) -> bool`

- [ ] **Step 1: 编写测试用例**

创建 `tests/test_redis_client.py`：
```python
import pytest
from app.infrastructure.redis_client import is_query_debounced, redis_client

@pytest.mark.asyncio
async def test_redis_debounce_flow():
    # 清理测试 Key
    test_key = "hmp:test:debounce:user:action"
    await redis_client.delete(test_key)
    
    # 第一次应该不被防抖（返回 False）
    res1 = await is_query_debounced(test_key, expire_seconds=3)
    assert res1 is False
    
    # 3 秒内第二次应该被防抖（返回 True）
    res2 = await is_query_debounced(test_key, expire_seconds=3)
    assert res2 is True
    
    # 手动删除 key 后第三次应该成功
    await redis_client.delete(test_key)
    res3 = await is_query_debounced(test_key, expire_seconds=3)
    assert res3 is False
```

- [ ] **Step 2: 运行测试验证失败**

运行：`D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest tests/test_redis_client.py`
期望：失败，模块未定义。

- [ ] **Step 3: 编写代码实现**

创建 `app/infrastructure/redis_client.py`：
```python
import os
import logging
from redis.asyncio import Redis, ConnectionPool
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("hmp_ws_service")

REDIS_HOST = os.getenv("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)
REDIS_DB = int(os.getenv("REDIS_DB", "0"))

# 创建异步连接池
pool = ConnectionPool(
    host=REDIS_HOST,
    port=REDIS_PORT,
    password=REDIS_PASSWORD,
    db=REDIS_DB,
    decode_responses=True,
    socket_connect_timeout=2.0
)

redis_client = Redis(connection_pool=pool)

async def is_query_debounced(key: str, expire_seconds: int = 3) -> bool:
    """
    判断查询是否需要防抖。
    使用 Redis 的 SET key 1 EX expire_seconds NX 原子操作。
    若设置成功（返回 True），说明之前没有这个缓存，无需防抖；
    若设置失败（返回 None/False），说明已存在缓存，需要防抖。
    若 Redis 连接异常，则返回 False（不防抖，优雅降级）。
    """
    try:
        # SETEX with NX
        result = await redis_client.set(key, "1", ex=expire_seconds, nx=True)
        return not result
    except Exception as e:
        logger.warning(f"Redis debounce failed (degraded to write log): {e}")
        return False
```

- [ ] **Step 4: 运行测试验证通过**

运行：`D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest tests/test_redis_client.py`
期望：测试 PASS。

- [ ] **Step 5: 提交 Redis 客户端**

```bash
git add app/infrastructure/redis_client.py tests/test_redis_client.py
git commit -m "feat: add redis client and debounce helper"
```

---

### Task 3: 路由审计器与测试逻辑更新

**Files:**
- Modify: `app/infrastructure/audit_route.py`
- Modify: `tests/test_audit_route.py`

- [ ] **Step 1: 在拦截器中更新白名单及引入防抖**

修改 `app/infrastructure/audit_route.py` 中的 `custom_route_handler` 如下：
- 移除白名单中的 `"QUERY_AUDIT_LOGS"`。
- 新增对以 `"QUERY_"` 开头的 action 进行 Redis 锁定的防抖逻辑。
- 引入哈希计算以确保 Key 足够精简：
```python
import hashlib
from app.infrastructure.redis_client import is_query_debounced

# 组装参数 hash
param_str = json.dumps(request_params, sort_keys=True, ensure_ascii=False)
param_hash = hashlib.md5(param_str.encode("utf-8")).hexdigest()
debounce_key = f"hmp:audit:debounce:{operator or 'system'}:{action}:{param_hash}"

skip_audit = False
if action.startswith("QUERY_"):
    # 异步检测是否重复请求
    skip_audit = await is_query_debounced(debounce_key, expire_seconds=3)

# 仅在非 skip_audit 时执行 audit_service.record_log
if not skip_audit:
    await audit_service.record_log(...)
```

- [ ] **Step 2: 更新测试用例并重跑**

修改 `tests/test_audit_route.py` 补充防抖拦截的 Mock 测试和正常接口测试。
运行所有测试：`D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest`
期望：所有 8+ 单元测试均绿灯通过。

- [ ] **Step 3: 提交并完成修改**

```bash
git add app/infrastructure/audit_route.py tests/test_audit_route.py
git commit -m "feat: integrate redis debounce in audit route"
```
