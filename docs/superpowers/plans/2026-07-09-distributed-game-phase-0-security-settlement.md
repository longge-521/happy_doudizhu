# 分布式改造阶段 0：生产安全与结算止损实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在引入多实例消息链路前，先封堵生产环境资产直改和默认签名密钥风险，并让同一房间结算具备数据库幂等性，确保结算失败时 Redis 房间不会被提前清理。

**Architecture:** 保持现有 WebSocket 和 `GameRoom` 状态机不变。新增独立结算应用服务，将数据库结算从 `game_handler.py` 移出；MySQL 通过唯一结算主记录和战绩联合唯一约束保证重复调用只生效一次；Handler 只在结算成功后清理 Redis。

**Tech Stack:** Python 3.10.20、FastAPI、SQLAlchemy 2.0.25、Alembic、MySQL、Redis、pytest；Vue 3、TypeScript、Vitest、Vite。

## Global Constraints

- 后端命令必须使用 `D:\ProgramData\miniconda3\envs\hmp_ai\python.exe`。
- 禁止批量删除文件或目录。
- 不还原、覆盖或清理用户已有改动。
- 修复缺陷必须先写失败测试，再做最小修改。
- 文档使用中文。
- 本阶段不引入 RabbitMQ 游戏命令总线、分片 Worker、Redis 租约或持久 Scheduler。
- 本阶段不重构 `GameRoom` 规则和前端页面布局。
- 用户人工确认完整无误前不得执行 `git commit`；本计划没有 commit 步骤。

---

## 文件结构

### 新增

- `backend/app/application/game/settlement_service.py`
  - 计算稳定结算摘要。
  - 编排结算主记录、玩家档案、段位和战绩的事务。
  - 重复调用已完成结算时返回 `already_completed`。
- `backend/tests/test_game_settlement_service.py`
  - 覆盖首次结算、重复结算、结果冲突和事务失败回滚。
- `backend/tests/test_game_settlement_handler.py`
  - 覆盖结算成功后清理、结算失败时保留房间。
- `backend/alembic/versions/a7c4d2e91f08_add_game_settlement_idempotency.py`
  - 新增结算主表。
  - 为战绩增加 `(room_id, player_id)` 唯一约束。
- `frontend/src/utils/runtimeFeatures.ts`
  - 集中定义仅开发环境开放的资料调试功能。
- `frontend/src/utils/__tests__/runtimeFeatures.spec.ts`
  - 验证生产环境关闭资产和段位直改功能。

### 修改

- `backend/app/infrastructure/config.py`
  - 移除可用于生产的默认游戏签名密钥。
  - 新增生产配置校验。
- `backend/app/infrastructure/auth.py`
  - 生产环境只接受显式 `GAME_AUTH_SECRET`。
- `backend/main.py`
  - lifespan 启动最前面执行生产配置校验。
  - 使用 `settings.PORT` 启动 Uvicorn。
- `backend/tests/test_auth.py`
  - 补生产密钥失败和开发环境兼容测试。
- `backend/app/interfaces/api/game_routes.py`
  - 生产环境拒绝欢乐豆和段位直改。
- `backend/tests/test_game_api.py`
  - 验证生产拒绝、开发允许。
- `frontend/src/views/LobbyView.vue`
  - 生产构建不绑定资产编辑动作，也不渲染编辑弹窗。
- `frontend/src/views/__tests__/LobbyView.spec.ts`
  - 保留开发环境编辑入口行为测试。
- `backend/app/infrastructure/database/models.py`
  - 新增 `GameSettlementORM`。
  - 新增战绩联合唯一约束。
- `backend/app/infrastructure/database/game_repository.py`
  - 新增结算主记录和加锁读取方法。
- `backend/app/interfaces/websocket/game_handler.py`
  - 使用结算应用服务。
  - 结算失败时保留并刷新 Redis 房间。
- `README.md`
  - 补充生产密钥和生产环境禁用调试修改说明。

---

### Task 1：强制生产环境使用显式游戏签名密钥

**Files:**

- Modify: `backend/tests/test_auth.py`
- Modify: `backend/app/infrastructure/config.py`
- Modify: `backend/app/infrastructure/auth.py`
- Modify: `backend/main.py`

**Interfaces:**

- Produces: `Settings.validate_production_settings() -> None`
- Produces: `Settings.is_production -> bool`
- Consumes: `settings.GAME_AUTH_SECRET`

- [ ] **Step 1：写生产配置失败测试**

在 `backend/tests/test_auth.py` 增加：

```python
def test_validate_production_settings_rejects_missing_game_secret(monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "GAME_AUTH_SECRET", None)

    with pytest.raises(RuntimeError, match="GAME_AUTH_SECRET"):
        settings.validate_production_settings()


def test_validate_production_settings_accepts_explicit_game_secret(monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "GAME_AUTH_SECRET", "a" * 32)

    settings.validate_production_settings()


def test_development_uses_local_game_secret_fallback(monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "development")
    monkeypatch.setattr(settings, "GAME_AUTH_SECRET", None)
    monkeypatch.setattr(settings, "API_TOKEN", None)

    token = auth.create_game_auth_token("player123")

    assert auth.verify_game_auth_token(token) == "player123"
```

同时将现有 `test_game_auth_secret_required_in_production` 的期望文案改为只匹配 `GAME_AUTH_SECRET`，不再允许生产环境回退到 `API_TOKEN`。

- [ ] **Step 2：运行测试确认失败**

运行：

```powershell
cd backend
D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest tests/test_auth.py -q --tb=short
```

预期：失败，原因是 `validate_production_settings()` 和 `is_production` 尚不存在，且当前配置仍提供默认密钥。

- [ ] **Step 3：实现配置校验**

在 `backend/app/infrastructure/config.py` 中将：

```python
GAME_AUTH_SECRET: str = Field(
    default="secure-game-auth-secret", description="JWT/Token签名密钥"
)
```

改为：

```python
GAME_AUTH_SECRET: Optional[str] = Field(
    default=None, description="游戏访问令牌签名密钥；生产环境必须显式配置"
)
```

并在 `Settings` 中加入：

```python
@property
def is_production(self) -> bool:
    return self.APP_ENV.strip().lower() in {"prod", "production"}

def validate_production_settings(self) -> None:
    if not self.is_production:
        return
    if not self.GAME_AUTH_SECRET or len(self.GAME_AUTH_SECRET) < 32:
        raise RuntimeError(
            "GAME_AUTH_SECRET must be explicitly configured with at least 32 characters in production"
        )
```

将 `should_auto_init_db` 改为复用 `is_production`：

```python
@property
def should_auto_init_db(self) -> bool:
    if self.AUTO_INIT_DB is not None:
        return self.AUTO_INIT_DB
    return not self.is_production
```

- [ ] **Step 4：收紧签名密钥选择**

将 `backend/app/infrastructure/auth.py` 的 `_game_auth_secret()` 改为：

```python
def _game_auth_secret() -> bytes:
    if settings.is_production:
        settings.validate_production_settings()
        return settings.GAME_AUTH_SECRET.encode("utf-8")

    secret = settings.GAME_AUTH_SECRET or settings.API_TOKEN or "hmp-dev-game-auth-secret"
    return secret.encode("utf-8")
```

保留 `_is_production_env()` 供普通 API token 逻辑使用，避免扩大本任务修改范围。

- [ ] **Step 5：启动时失败并使用配置端口**

在 `backend/main.py` 的 `lifespan()` 第一行加入：

```python
settings.validate_production_settings()
```

补充导入：

```python
from app.infrastructure.config import settings
```

将 Uvicorn 的硬编码端口：

```python
port=18088,
```

改为：

```python
port=settings.PORT,
```

- [ ] **Step 6：运行安全配置测试**

运行：

```powershell
cd backend
D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest tests/test_auth.py tests/test_database_startup.py -q --tb=short
```

预期：全部通过。

---

### Task 2：生产环境禁用欢乐豆和段位直改

**Files:**

- Modify: `backend/tests/test_game_api.py`
- Modify: `backend/app/interfaces/api/game_routes.py`
- Create: `frontend/src/utils/runtimeFeatures.ts`
- Create: `frontend/src/utils/__tests__/runtimeFeatures.spec.ts`
- Modify: `frontend/src/views/LobbyView.vue`
- Modify: `frontend/src/views/__tests__/LobbyView.spec.ts`

**Interfaces:**

- Produces: `ensure_profile_debug_mutation_allowed() -> None`
- Produces: `isProfileDebugEnabled(isDev: boolean) -> boolean`
- Produces: `PROFILE_DEBUG_ENABLED: boolean`

- [ ] **Step 1：写后端生产拒绝测试**

在 `backend/tests/test_game_api.py` 增加：

```python
@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/api/game/profile/player123/beans", {"beans": 25000}),
        (
            "/api/game/profile/player123/rank",
            {"rank_id": 35, "sub_rank": 4, "stars": 3},
        ),
    ],
)
def test_profile_debug_mutations_are_disabled_in_production(
    monkeypatch, mock_db, path, payload
):
    from app.infrastructure.auth import create_game_auth_token
    from app.infrastructure.config import settings

    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "GAME_AUTH_SECRET", "a" * 32)
    token = create_game_auth_token("player123")

    response = TestClient(app).post(
        path,
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "生产环境不允许手动修改欢乐豆或段位"
```

在现有 `test_update_player_beans` 和 `test_update_player_rank` 开头显式加入：

```python
monkeypatch.setattr(settings, "APP_ENV", "development")
```

并给两个测试函数加入 `monkeypatch` 参数，避免测试依赖执行顺序。

- [ ] **Step 2：运行后端测试确认失败**

```powershell
cd backend
D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest tests/test_game_api.py -q --tb=short
```

预期：新增生产环境用例得到 200，而不是 403。

- [ ] **Step 3：实现后端环境守卫**

在 `backend/app/interfaces/api/game_routes.py` 增加：

```python
def ensure_profile_debug_mutation_allowed() -> None:
    if settings.is_production:
        raise HTTPException(
            status_code=403,
            detail="生产环境不允许手动修改欢乐豆或段位",
        )
```

在 `update_beans()` 和 `update_player_rank()` 函数体第一行调用：

```python
ensure_profile_debug_mutation_allowed()
```

不要影响头像、昵称、密码和正常结算逻辑。

- [ ] **Step 4：写前端运行特性失败测试**

新建 `frontend/src/utils/__tests__/runtimeFeatures.spec.ts`：

```ts
import { describe, expect, it } from 'vitest'
import { isProfileDebugEnabled } from '../runtimeFeatures'

describe('runtimeFeatures', () => {
  it('enables profile debug mutations only in development builds', () => {
    expect(isProfileDebugEnabled(true)).toBe(true)
    expect(isProfileDebugEnabled(false)).toBe(false)
  })
})
```

- [ ] **Step 5：运行前端测试确认失败**

```powershell
cd frontend
npm.cmd run test:unit -- --run src/utils/__tests__/runtimeFeatures.spec.ts
```

预期：失败，原因是 `runtimeFeatures.ts` 不存在。

- [ ] **Step 6：实现前端特性开关并限制 UI**

新建 `frontend/src/utils/runtimeFeatures.ts`：

```ts
export function isProfileDebugEnabled(isDev: boolean): boolean {
  return isDev
}

export const PROFILE_DEBUG_ENABLED = isProfileDebugEnabled(import.meta.env.DEV)
```

在 `LobbyView.vue` 导入：

```ts
import { PROFILE_DEBUG_ENABLED } from '@/utils/runtimeFeatures'
```

将两处欢乐豆资产块从无条件点击改为：

```vue
<div
  class="asset-pill gold-beans"
  :class="{ editable: PROFILE_DEBUG_ENABLED }"
  @click="PROFILE_DEBUG_ENABLED && openEditBeansModal()"
>
```

保留两处原有布局相关内联样式，但移除无条件 `cursor: pointer`。将编辑弹窗条件改为：

```vue
<div
  v-if="PROFILE_DEBUG_ENABLED && showEditBeansModal"
  class="modal-overlay"
  @click.self="showEditBeansModal = false"
>
```

增加局部样式：

```css
.asset-pill.gold-beans.editable {
  cursor: pointer;
}
```

- [ ] **Step 7：补大厅开发环境行为测试**

在 `frontend/src/views/__tests__/LobbyView.spec.ts` 增加：

```ts
it('opens the beans and rank editor in development builds', async () => {
  const wrapper = mountLobby()

  await wrapper.find('.asset-pill.gold-beans').trigger('click')

  expect(wrapper.text()).toContain('修改资产与排位')
})
```

- [ ] **Step 8：验证生产构建会裁剪入口**

运行：

```powershell
cd frontend
npm.cmd run test:unit -- --run src/utils/__tests__/runtimeFeatures.spec.ts src/views/__tests__/LobbyView.spec.ts
npm.cmd run build
```

预期：测试和构建通过；`import.meta.env.DEV` 在生产构建中为 `false`。

---

### Task 3：新增结算主表和战绩唯一约束

**Files:**

- Modify: `backend/tests/test_game_models.py`
- Modify: `backend/app/infrastructure/database/models.py`
- Create: `backend/alembic/versions/a7c4d2e91f08_add_game_settlement_idempotency.py`

**Interfaces:**

- Produces: `GameSettlementORM`
- Produces: unique constraint `uq_ddz_game_record_room_player`

- [ ] **Step 1：写模型失败测试**

在 `backend/tests/test_game_models.py` 增加：

```python
from sqlalchemy import UniqueConstraint
from app.infrastructure.database.models import GameRecordORM, GameSettlementORM


def test_game_record_has_room_player_unique_constraint():
    names = {
        constraint.name
        for constraint in GameRecordORM.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert "uq_ddz_game_record_room_player" in names


def test_game_settlement_model_uses_unique_room_id():
    assert GameSettlementORM.__tablename__ == "ddz_game_settlement"
    names = {
        constraint.name
        for constraint in GameSettlementORM.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert "uq_ddz_game_settlement_room_id" in names
    assert GameSettlementORM.__table__.c.status.default.arg == "pending"
```

- [ ] **Step 2：运行模型测试确认失败**

```powershell
cd backend
D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest tests/test_game_models.py -q --tb=short
```

预期：导入 `GameSettlementORM` 失败。

- [ ] **Step 3：实现 ORM 模型**

在 `backend/app/infrastructure/database/models.py` 补充导入：

```python
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    SmallInteger,
    Index,
    Float,
    UniqueConstraint,
)
```

将 `GameRecordORM.__table_args__` 改为：

```python
__table_args__ = (
    UniqueConstraint(
        "room_id",
        "player_id",
        name="uq_ddz_game_record_room_player",
    ),
    {"comment": "对局战绩记录表"},
)
```

新增：

```python
class GameSettlementORM(Base):
    __tablename__ = "ddz_game_settlement"
    __table_args__ = (
        UniqueConstraint(
            "room_id",
            name="uq_ddz_game_settlement_room_id",
        ),
        {"comment": "对局幂等结算主记录"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    room_id = Column(String(100), nullable=False, index=True)
    result_hash = Column(String(64), nullable=False)
    status = Column(String(20), nullable=False, default="pending", index=True)
    attempts = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.now, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.datetime.now,
        onupdate=datetime.datetime.now,
        nullable=False,
    )
    completed_at = Column(DateTime, nullable=True)
```

- [ ] **Step 4：编写 Alembic 迁移**

新建 `backend/alembic/versions/a7c4d2e91f08_add_game_settlement_idempotency.py`，其 `down_revision` 为 `56455943753d`。

`upgrade()` 必须：

1. 执行以下只读预检；发现重复时抛出 `RuntimeError`，不得自动删除：

```sql
SELECT room_id, player_id, COUNT(*) AS duplicate_count
FROM ddz_game_record
GROUP BY room_id, player_id
HAVING COUNT(*) > 1
LIMIT 1
```

2. 使用 `op.create_table()` 创建与 ORM 一致的 `ddz_game_settlement`，并显式声明 `uq_ddz_game_settlement_room_id`。
3. 创建 `ix_ddz_game_settlement_room_id` 和 `ix_ddz_game_settlement_status`。
4. 使用：

```python
op.create_unique_constraint(
    "uq_ddz_game_record_room_player",
    "ddz_game_record",
    ["room_id", "player_id"],
)
```

`downgrade()` 依次删除 `uq_ddz_game_record_room_player`、两个结算表索引和结算表。不要删除任何战绩行。

- [ ] **Step 5：验证模型和迁移语法**

```powershell
cd backend
D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest tests/test_game_models.py -q --tb=short
D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m compileall alembic/versions/a7c4d2e91f08_add_game_settlement_idempotency.py
```

预期：模型测试通过，迁移脚本可编译。

---

### Task 4：实现幂等结算应用服务

**Files:**

- Create: `backend/tests/test_game_settlement_service.py`
- Modify: `backend/app/infrastructure/database/game_repository.py`
- Create: `backend/app/application/game/settlement_service.py`

**Interfaces:**

- Produces: `GameSettlementService.settle(room: GameRoom, result: dict) -> Literal["completed", "already_completed"]`
- Produces: `SQLGameRepository.ensure_settlement(room_id: str, result_hash: str) -> GameSettlementORM`
- Produces: `SQLGameRepository.get_settlement_for_update(room_id: str) -> GameSettlementORM`
- Produces: `SQLGameRepository.mark_settlement_failure(room_id: str, error: str) -> None`

- [ ] **Step 1：写首次和重复结算失败测试**

新建 `backend/tests/test_game_settlement_service.py`。使用 SQLite 内存数据库、`Base.metadata.create_all()` 和返回新 Session 的 contextmanager。构造两名真人和一名 AI 的 `GameRoom`，先创建两名真人档案。

核心断言：

```python
first = settlement_service.settle(room, result)
second = settlement_service.settle(room, result)

assert first == "completed"
assert second == "already_completed"
assert session.query(GameSettlementORM).filter_by(room_id=room.room_id).one().status == "completed"
assert session.query(GameRecordORM).filter_by(room_id=room.room_id).count() == 2
assert player_one.total_games == 1
assert player_two.total_games == 1
```

分数使用：

```python
result = {
    "scores": {"p1": 40, "p2": -40, "ai_bot_1": 0},
    "multiplier": 2,
}
```

- [ ] **Step 2：写冲突结果和回滚测试**

在同一测试文件增加：

```python
with pytest.raises(SettlementConflictError):
    settlement_service.settle(
        room,
        {"scores": {"p1": 80, "p2": -80, "ai_bot_1": 0}, "multiplier": 4},
    )
```

冲突后继续断言原结算主记录仍为 `completed`，不能被冲突请求改成失败。

再使用一个新的房间，通过 `monkeypatch` 让 `SQLGameRepository.update_rank_stats()` 抛出 `RuntimeError("db failure")`，断言：

- 玩家欢乐豆、总局数和胜场没有变化。
- 没有新增战绩。
- 结算主记录为 `failed`。
- `attempts == 1`。
- `last_error` 包含 `db failure`，但长度不超过 500。

- [ ] **Step 3：运行服务测试确认失败**

```powershell
cd backend
D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest tests/test_game_settlement_service.py -q --tb=short
```

预期：失败，原因是结算服务和仓储接口尚不存在。

- [ ] **Step 4：实现仓储结算方法**

在 `game_repository.py` 导入 `GameSettlementORM`，新增：

```python
def ensure_settlement(self, room_id: str, result_hash: str) -> GameSettlementORM:
    settlement = (
        self._db.query(GameSettlementORM)
        .filter_by(room_id=room_id)
        .first()
    )
    if settlement is None:
        settlement = GameSettlementORM(
            room_id=room_id,
            result_hash=result_hash,
            status="pending",
        )
        self._db.add(settlement)
        self._db.flush()
    return settlement

def get_settlement_for_update(self, room_id: str) -> GameSettlementORM:
    settlement = (
        self._db.query(GameSettlementORM)
        .filter_by(room_id=room_id)
        .with_for_update()
        .one()
    )
    return settlement

def mark_settlement_failure(self, room_id: str, error: str) -> None:
    settlement = (
        self._db.query(GameSettlementORM)
        .filter_by(room_id=room_id)
        .one()
    )
    settlement.status = "failed"
    settlement.attempts += 1
    settlement.last_error = error[:500]
```

这些方法不调用 `commit()`，事务边界由应用服务控制。

- [ ] **Step 5：实现结算服务**

新建 `settlement_service.py`，包含：

```python
import datetime
import hashlib
import json
from typing import Callable, ContextManager, Literal

from sqlalchemy.exc import IntegrityError

from app.domain.game.entities import GameRecord
from app.domain.game.room import GameRoom
from app.infrastructure.database.game_repository import SQLGameRepository
from app.infrastructure.database.session import transactional_session


class SettlementConflictError(RuntimeError):
    pass


class GameSettlementService:
    def __init__(
        self,
        session_scope: Callable[[], ContextManager] = transactional_session,
    ):
        self._session_scope = session_scope

    @staticmethod
    def _result_hash(room: GameRoom, result: dict) -> str:
        payload = {
            "room_id": room.room_id,
            "landlord": room.landlord,
            "multiplier": int(result.get("multiplier", room.multiplier)),
            "scores": {
                player_id: int(score)
                for player_id, score in sorted(result.get("scores", {}).items())
            },
        }
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()
```

`settle()` 按以下明确顺序实现：

1. 计算 `result_hash`。
2. 用短事务调用 `ensure_settlement()`；捕获并忽略并发插入导致的 `IntegrityError`。
3. 开启业务事务并 `get_settlement_for_update()`。
4. `completed` 且 hash 相同则返回 `already_completed`。
5. hash 不同则抛 `SettlementConflictError`。
6. 对真人玩家依次调用现有 `get_or_create_profile()`、`update_profile_stats()`、`update_rank_stats()`、`save_game_record()`。
7. 成功时设置 `status="completed"`、`attempts += 1`、清空 `last_error`、写入 `completed_at`。
8. 返回 `completed`。
9. `SettlementConflictError` 直接重新抛出，不修改已完成记录。
10. 其他业务事务异常时，用独立短事务调用 `mark_settlement_failure()`，然后重新抛出原异常；记录失败本身若再次失败，只写日志，不能掩盖最初的业务异常。

创建 `GameRecord` 时继续使用现有字段：

```python
GameRecord(
    room_id=room.room_id,
    player_id=player.id,
    role="landlord" if player.id == room.landlord else "farmer",
    result="win" if score_change > 0 else "lose",
    score_change=score_change,
    multiplier=multiplier,
)
```

- [ ] **Step 6：运行服务测试**

```powershell
cd backend
D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest tests/test_game_settlement_service.py tests/test_game_repository.py -q --tb=short
```

预期：全部通过。

---

### Task 5：Handler 只在结算成功后清理房间

**Files:**

- Create: `backend/tests/test_game_settlement_handler.py`
- Modify: `backend/app/interfaces/websocket/game_handler.py`

**Interfaces:**

- Consumes: `GameSettlementService.settle(room, result)`
- Produces: `GameWebSocketHandler._on_game_over(room, result) -> bool`

- [ ] **Step 1：写 Handler 失败测试**

新建 `backend/tests/test_game_settlement_handler.py`，构造 `AsyncMock` 游戏服务、`GameWSConnectionManager`、Mock WebSocket 和可注入的结算服务。

结算成功用例：

```python
settlement_service.settle.return_value = "completed"

completed = await handler._on_game_over(room, result)

assert completed is True
settlement_service.settle.assert_called_once_with(room, result)
game_service.cleanup_room.assert_awaited_once()
```

结算失败用例：

```python
settlement_service.settle.side_effect = RuntimeError("mysql unavailable")

completed = await handler._on_game_over(room, result)

assert completed is False
game_service.cleanup_room.assert_not_awaited()
game_service._repo.save_room.assert_awaited_once_with(room)
```

- [ ] **Step 2：运行测试确认失败**

```powershell
cd backend
D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest tests/test_game_settlement_handler.py -q --tb=short
```

预期：失败，因为 Handler 不能注入结算服务，且当前异常后仍会清理房间。

- [ ] **Step 3：注入并使用结算服务**

修改 Handler 构造函数：

```python
def __init__(
    self,
    websocket: WebSocket,
    player_id: str,
    manager: GameWSConnectionManager,
    game_service: "GameAppService",
    settlement_service=None,
):
    from app.application.game.settlement_service import GameSettlementService

    self.ws = websocket
    self.player_id = player_id
    self.manager = manager
    self.service = game_service
    self.settlement_service = settlement_service or GameSettlementService()
```

将 `_on_game_over()` 改为：

```python
async def _on_game_over(self, room, result: dict) -> bool:
    try:
        self.settlement_service.settle(room, result)
    except Exception:
        logger.exception("游戏结算入库失败，保留房间等待后续恢复: room_id=%s", room.room_id)
        await self.service._repo.save_room(room)
        return False

    player_ids = [player.id for player in room.players]
    await self.service.cleanup_room(room.room_id, player_ids)
    return True
```

删除原方法内直接导入数据库、遍历玩家和无条件清理的代码。其他调用方暂不依赖返回值。

- [ ] **Step 4：运行 Handler 与 WebSocket 测试**

```powershell
cd backend
D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest tests/test_game_settlement_handler.py tests/test_game_websocket.py -q --tb=short
```

预期：全部通过。

---

### Task 6：文档、全量验证与人工测试交接

**Files:**

- Modify: `README.md`
- Verify: all files changed by Tasks 1–5

**Interfaces:**

- Produces: 可供用户人工验证的阶段 0 完整结果。

- [ ] **Step 1：更新 README 生产配置**

在 README 的 `.env` 示例中补充：

```ini
APP_ENV=development
GAME_AUTH_SECRET=replace-with-at-least-32-random-characters
GAME_AUTH_TOKEN_TTL_SECONDS=604800
```

在安全说明中明确：

- 生产环境缺少至少 32 字符的 `GAME_AUTH_SECRET` 时启动失败。
- 欢乐豆和段位手动修改只用于开发调试，生产环境 API 返回 403，前端不显示编辑入口。
- 结算失败时房间保留在 Redis，当前阶段通过日志告警；持久重试由后续分布式结算 Worker 阶段实现。

- [ ] **Step 2：运行后端全量测试**

```powershell
cd backend
D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest tests/ -q --tb=short
```

预期：全部通过。

- [ ] **Step 3：运行前端全量测试与构建**

```powershell
cd frontend
npm.cmd run test:unit -- --run
npm.cmd run build
```

预期：全部测试和生产构建通过。

- [ ] **Step 4：检查改动范围**

```powershell
git diff --check
git diff --stat
git status --short
```

预期：

- 没有空白错误。
- 没有 `frontend/dist/`、日志、上传文件或临时文件进入版本控制。
- 没有 RabbitMQ 游戏总线、Redis 分片租约等后续阶段代码混入。
- 不包含 `git commit`。

- [ ] **Step 5：向用户列出人工测试点**

请求用户人工确认前，必须列出：

1. 开发环境点击大厅欢乐豆区域，编辑欢乐豆和段位仍可正常保存。
2. 生产构建中欢乐豆仅展示，点击不会弹出编辑窗口。
3. 生产环境直接调用 beans/rank 修改 API 返回 403。
4. 使用显式 `GAME_AUTH_SECRET` 时注册、登录、REST 鉴权和游戏 WebSocket 连接正常。
5. 生产环境缺少或使用短于 32 字符的 `GAME_AUTH_SECRET` 时，服务拒绝启动。
6. 正常完成一局后，欢乐豆、胜场、段位和战绩只更新一次，房间正常清理。
7. 模拟 MySQL 结算失败后，客户端仍收到对局结果，但 Redis 房间未删除，日志包含可定位的 `room_id`。

用户人工确认完整无误后，才可另行请求执行中文提交信息的 `git commit`。

## 计划自查

- 本计划覆盖设计规约阶段 0 的全部范围。
- 每个行为修改均先有失败测试。
- 类型、方法名和文件路径在各任务间保持一致。
- 没有占位符、批量删除或提前提交步骤。
- 后续 RabbitMQ 游戏总线、Redis 分片租约、Presence、Scheduler 和持久结算 Worker 明确留给独立计划。
