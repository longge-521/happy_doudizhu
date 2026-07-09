# 分布式模式对局卡住修复实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**目标：** 修复 `DISTRIBUTED_MODE=True` 时玩家动作后 AI 不推进、真人超时命令失效且前端不刷新房间状态的问题。

**架构：** 同一条分片命令只提交一次房间状态；后续 AI 回合通过带预期房间版本的独立持久调度任务继续驱动。Worker 按 `room_id` 读取权威快照，在保存前生成逐玩家视角事件，使房间快照、命令幂等记录和 Redis Outbox 在同一次 CAS 中提交。

**技术栈：** FastAPI、Python 3.10、Redis Lua/CAS、RabbitMQ、pytest、Vue 3 WebSocket 事件协议。

## 全局约束

- 只修改分布式命令、调度、事件投递及其测试，不重构斗地主领域状态机。
- 保留当前工作区中其他助手已经产生的未提交改动。
- 后端测试只使用 `D:\ProgramData\miniconda3\envs\hmp_ai\python.exe`。
- 不执行批量删除，不执行 Git 提交。

---

### Task 1：建立分布式 Worker 回归测试

**文件：**
- 新建：`backend/tests/test_distributed_game_command.py`
- 修改：`backend/main.py`

**接口：**
- 输入：`GameCommandSchema`
- 输出：一次房间 CAS 保存、逐玩家 Outbox 事件和零或一个后续调度任务

- [ ] **Step 1：编写失败测试**

覆盖以下行为：

```python
async def test_timeout_command_loads_room_by_room_id_and_targets_expected_player():
    ...

async def test_ai_command_commits_once_and_schedules_next_ai_turn():
    ...

async def test_worker_builds_player_view_events_before_room_save():
    ...
```

- [ ] **Step 2：验证测试因现有缺陷失败**

运行：

```powershell
D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest backend/tests/test_distributed_game_command.py -v
```

预期：分别因 `system` 无玩家房间映射、Worker 内循环多次保存、保存前没有 Outbox 事件而失败。

- [ ] **Step 3：实现最小命令处理器**

在 `backend/main.py` 中让 Worker：

1. 直接调用 `repo.get_room(command.room_id)`。
2. 校验命令目标玩家属于房间且轮到该玩家。
3. 每条命令只执行一个真人、托管或 AI 领域动作。
4. 在 `repo.save_room(room)` 前填充逐真人玩家视角的 `GameEventSchema`。
5. 保存成功后仅调度一个后续 AI 或真人超时任务。

- [ ] **Step 4：验证定向测试通过**

运行：

```powershell
D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest backend/tests/test_distributed_game_command.py -v
```

预期：PASS。

### Task 2：修正持久调度命令目标与过期校验

**文件：**
- 修改：`backend/main.py`
- 修改：`backend/app/application/game/game_app_service.py`
- 修改：`backend/app/interfaces/websocket/game_handler.py`
- 修改：`backend/app/infrastructure/game/redis_scheduler.py`
- 测试：`backend/tests/test_redis_scheduler.py`

- [ ] **Step 1：补充失败测试**

```python
async def test_scheduler_command_keeps_target_player_and_expected_room_version():
    ...
```

- [ ] **Step 2：验证测试失败**

运行：

```powershell
D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest backend/tests/test_redis_scheduler.py -v
```

- [ ] **Step 3：实现最小修复**

调度任务 payload 必须包含 `player_id`；发布命令时恢复真实目标玩家并携带 `expected_room_version`。Worker 发现房间版本、阶段或当前玩家不匹配时将旧任务安全忽略。

- [ ] **Step 4：验证调度测试通过**

运行同一测试文件，预期 PASS。

### Task 3：补齐分布式动作入口和回归验证

**文件：**
- 修改：`backend/app/interfaces/websocket/game_handler.py`
- 测试：`backend/tests/test_game_websocket.py`

- [ ] **Step 1：补充失败测试**

验证 `choose_double`、`landlord_show` 等房间写动作在分布式模式下也进入分片命令，避免绕过 fencing token 直接写 Redis。

- [ ] **Step 2：实现动作转发**

复用 `_forward_distributed_command()`，不改变单机模式行为。

- [ ] **Step 3：运行相关测试**

```powershell
D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest backend/tests/test_distributed_game_command.py backend/tests/test_redis_scheduler.py backend/tests/test_game_websocket.py -v
```

- [ ] **Step 4：运行后端回归**

```powershell
D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest backend/tests/ -x -q --tb=short
```

预期：全部通过。

