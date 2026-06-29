# Profile Avatar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为玩家档案增加持久化头像 URL 字段，并在大厅个人资料弹窗中支持查看和修改头像。

**Architecture:** 后端在 `player_profile`、领域实体、仓储和 REST API 中加入 `avatar_url`，复用现有游戏 token 鉴权。前端在 `playerStore` 中同步头像状态，并由 `LobbyView.vue` 渲染底部头像和个人资料弹窗。

**Tech Stack:** FastAPI、SQLAlchemy、pytest、Vue 3、Pinia、Vue Router、Vitest、Vue Test Utils。

## Global Constraints

- 文档和新增用户可见说明使用中文。
- `avatar_url` 是 `player_profile` 的可空字符串字段，最长 500。
- 空字符串或 `null` 表示清空头像并恢复默认头像占位。
- 非空头像地址仅允许 `http://`、`https://`、`/static/...`、`/api/uploads/...`。
- 修改头像必须复用现有游戏 token，并通过 `ensure_player_access` 限制只能修改自己的档案。
- 不实现图片上传、裁剪、审核或文件处理。
- 不修改匹配、房间状态、结算或排位规则。
- 遵守 TDD：每个行为先写失败测试，确认失败原因正确后再写实现。
- 不还原、覆盖或清理与本任务无关的用户改动；当前未跟踪的 `AGENTS.md` 不纳入提交。

---

## 文件结构

- Modify: `backend/app/infrastructure/database/models.py`
  - 给 `PlayerProfileORM` 增加 `avatar_url` 数据库字段。
- Modify: `backend/app/infrastructure/database/session.py`
  - 给开发数据库启动自愈逻辑增加 `avatar_url` 补列。
- Modify: `backend/app/domain/game/entities.py`
  - 给 `PlayerProfile` 增加可选 `avatar_url` 属性。
- Modify: `backend/app/infrastructure/database/game_repository.py`
  - 映射 `avatar_url`，新增 `update_avatar_url(player_id: str, avatar_url: str | None) -> None`。
- Modify: `backend/app/interfaces/api/game_routes.py`
  - 扩展 profile 返回，新增头像更新请求体、URL 校验和更新路由。
- Modify: `backend/tests/test_game_repository.py`
  - 覆盖仓储层头像映射和保存。
- Modify: `backend/tests/test_game_api.py`
  - 覆盖 profile 返回头像、头像更新、清空、鉴权和非法 URL。
- Modify: `frontend/src/stores/playerStore.ts`
  - 增加 `avatarUrl` 状态、持久化和 `modifyAvatar()`。
- Create: `frontend/src/stores/__tests__/playerStore.spec.ts`
  - 覆盖头像拉取、保存和清空。
- Modify: `frontend/src/views/LobbyView.vue`
  - 顶部退出文案、底部头像图片渲染、个人资料弹窗。
- Create: `frontend/src/views/__tests__/LobbyView.spec.ts`
  - 覆盖退出文案、弹窗打开、头像输入和预览。

---

### Task 1: 后端档案模型与仓储头像字段

**Files:**
- Modify: `backend/tests/test_game_repository.py`
- Modify: `backend/app/domain/game/entities.py`
- Modify: `backend/app/infrastructure/database/models.py`
- Modify: `backend/app/infrastructure/database/session.py`
- Modify: `backend/app/infrastructure/database/game_repository.py`

**Interfaces:**
- Consumes: `PlayerProfileORM`, `PlayerProfile`, `SQLGameRepository.get_or_create_profile`
- Produces: `PlayerProfile.avatar_url: Optional[str]`
- Produces: `SQLGameRepository.update_avatar_url(player_id: str, avatar_url: Optional[str]) -> None`

- [ ] **Step 1: 写仓储层失败测试**

在 `backend/tests/test_game_repository.py` 文件末尾追加：

```python
def test_sql_game_repository_avatar_url_mapping_and_update():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    repo = SQLGameRepository(session)

    profile = repo.get_or_create_profile("player_avatar", "AvatarTester")
    assert profile.avatar_url is None

    repo.update_avatar_url("player_avatar", "https://example.com/avatar.png")
    profile = repo.get_or_create_profile("player_avatar", "AvatarTester")
    assert profile.avatar_url == "https://example.com/avatar.png"

    orm = session.query(PlayerProfileORM).filter_by(player_id="player_avatar").first()
    assert orm.avatar_url == "https://example.com/avatar.png"

    repo.update_avatar_url("player_avatar", None)
    profile = repo.get_or_create_profile("player_avatar", "AvatarTester")
    assert profile.avatar_url is None

    session.close()
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
python -m pytest backend/tests/test_game_repository.py::test_sql_game_repository_avatar_url_mapping_and_update -v
```

Expected: FAIL，失败原因是 `PlayerProfile` 没有 `avatar_url` 属性或 `SQLGameRepository` 没有 `update_avatar_url` 方法。

- [ ] **Step 3: 实现领域实体头像属性**

修改 `backend/app/domain/game/entities.py` 中 `PlayerProfile.__init__` 参数和属性赋值：

```python
from typing import Optional


class PlayerProfile:
    """玩家档案领域实体"""
    DEFAULT_BEANS = 10000

    def __init__(
        self,
        player_id: str,
        nickname: str,
        beans: int = DEFAULT_BEANS,
        total_games: int = 0,
        wins: int = 0,
        id: Optional[int] = None,
        rank_id: int = 1,
        sub_rank: int = 4,
        stars: int = 0,
        avatar_url: Optional[str] = None,
    ):
        self.id = id
        self.player_id = player_id
        self.nickname = nickname
        self.beans = beans
        self.total_games = total_games
        self.wins = wins
        self.rank_id = rank_id
        self.sub_rank = sub_rank
        self.stars = stars
        self.avatar_url = avatar_url
```

保留文件中已有 `rank_title` 和其他类定义不变。

- [ ] **Step 4: 实现数据库模型字段**

修改 `backend/app/infrastructure/database/models.py` 的 `PlayerProfileORM`：

```python
class PlayerProfileORM(Base):
    __tablename__ = "player_profile"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    player_id = Column(String(100), nullable=False, unique=True, index=True, comment="玩家ID")
    nickname = Column(String(100), nullable=False, comment="昵称")
    avatar_url = Column(String(500), nullable=True, comment="头像图片URL")
    beans = Column(Integer, default=10000, nullable=False, comment="欢乐豆")
    total_games = Column(Integer, default=0, nullable=False, comment="总对局数")
    wins = Column(Integer, default=0, nullable=False, comment="胜场数")
    rank_id = Column(Integer, default=1, nullable=False, comment="大级别(1-36)")
    sub_rank = Column(Integer, default=4, nullable=False, comment="子级别(1-4，对应I-IV)")
    stars = Column(Integer, default=0, nullable=False, comment="当前小段位星星数")
    created_at = Column(DateTime, default=datetime.datetime.now, comment="创建时间")
```

- [ ] **Step 5: 实现数据库自愈补列**

修改 `backend/app/infrastructure/database/session.py` 中 `player_profile` 自愈逻辑：

```python
            if "avatar_url" not in columns_profile:
                conn.execute(text("ALTER TABLE player_profile ADD COLUMN avatar_url VARCHAR(500) NULL COMMENT '头像图片URL'"))
            if "rank_id" not in columns_profile:
                conn.execute(text("ALTER TABLE player_profile ADD COLUMN rank_id INT NOT NULL DEFAULT 1 COMMENT '大级别(1-36)'"))
```

将 `avatar_url` 检查放在现有 `rank_id` 检查之前或之后都可以，但只添加一次。

- [ ] **Step 6: 实现仓储映射和更新方法**

修改 `backend/app/infrastructure/database/game_repository.py`：

```python
from typing import List, Optional
```

在 `get_or_create_profile()` 返回 `PlayerProfile` 时加入 `avatar_url`：

```python
        return PlayerProfile(
            id=orm.id, player_id=orm.player_id, nickname=orm.nickname,
            avatar_url=orm.avatar_url,
            beans=orm.beans, total_games=orm.total_games, wins=orm.wins,
            rank_id=getattr(orm, "rank_id", 1),
            sub_rank=getattr(orm, "sub_rank", 4),
            stars=getattr(orm, "stars", 0),
        )
```

在 `get_leaderboard()` 的 `PlayerProfile` 构造中加入：

```python
            avatar_url=r.avatar_url,
```

在仓储类中新增方法：

```python
    def update_avatar_url(self, player_id: str, avatar_url: Optional[str]) -> None:
        orm = self._db.query(PlayerProfileORM).filter_by(player_id=player_id).first()
        if orm:
            orm.avatar_url = avatar_url
            self._db.commit()
```

- [ ] **Step 7: 运行测试确认通过**

Run:

```bash
python -m pytest backend/tests/test_game_repository.py::test_sql_game_repository_avatar_url_mapping_and_update -v
```

Expected: PASS。

- [ ] **Step 8: 运行仓储测试回归**

Run:

```bash
python -m pytest backend/tests/test_game_repository.py -v
```

Expected: PASS。

- [ ] **Step 9: 提交后端模型与仓储改动**

```bash
git add backend/tests/test_game_repository.py backend/app/domain/game/entities.py backend/app/infrastructure/database/models.py backend/app/infrastructure/database/session.py backend/app/infrastructure/database/game_repository.py
git commit -m "feat: add avatar field to player profiles"
```

---

### Task 2: 后端头像 REST API

**Files:**
- Modify: `backend/tests/test_game_api.py`
- Modify: `backend/app/interfaces/api/game_routes.py`

**Interfaces:**
- Consumes: `SQLGameRepository.update_avatar_url(player_id: str, avatar_url: Optional[str]) -> None`
- Produces: `POST /api/game/profile/{player_id}/avatar`
- Produces: response shape `{"ok": true, "player_id": str, "avatar_url": Optional[str]}`

- [ ] **Step 1: 写 profile 返回头像的失败测试**

修改 `backend/tests/test_game_api.py` 的 `test_get_player_profile()` 中 `mock_profile` 构造：

```python
    mock_profile = PlayerProfile(
        player_id="player123",
        nickname="TestNick",
        beans=12000,
        total_games=10,
        wins=6,
        avatar_url="https://example.com/avatar.png",
    )
```

并在断言中加入：

```python
        assert data["avatar_url"] == "https://example.com/avatar.png"
```

- [ ] **Step 2: 写头像更新 API 失败测试**

在 `backend/tests/test_game_api.py` 末尾追加：

```python
def test_update_player_avatar(mock_db):
    client = TestClient(app)
    with patch("app.interfaces.api.game_routes.SQLGameRepository") as mock_repo_class:
        mock_repo = MagicMock()
        mock_profile = MagicMock()
        mock_profile.avatar_url = "https://example.com/new-avatar.png"
        mock_repo.get_or_create_profile.return_value = mock_profile
        mock_repo_class.return_value = mock_repo

        from app.infrastructure.auth import create_game_auth_token
        token = create_game_auth_token("player123")
        response = client.post(
            "/api/game/profile/player123/avatar",
            json={"avatar_url": "  https://example.com/new-avatar.png  "},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["player_id"] == "player123"
        assert data["avatar_url"] == "https://example.com/new-avatar.png"
        mock_repo.update_avatar_url.assert_called_once_with(
            "player123",
            "https://example.com/new-avatar.png",
        )


def test_clear_player_avatar(mock_db):
    client = TestClient(app)
    with patch("app.interfaces.api.game_routes.SQLGameRepository") as mock_repo_class:
        mock_repo = MagicMock()
        mock_profile = MagicMock()
        mock_profile.avatar_url = None
        mock_repo.get_or_create_profile.return_value = mock_profile
        mock_repo_class.return_value = mock_repo

        from app.infrastructure.auth import create_game_auth_token
        token = create_game_auth_token("player123")
        response = client.post(
            "/api/game/profile/player123/avatar",
            json={"avatar_url": ""},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        assert response.json()["avatar_url"] is None
        mock_repo.update_avatar_url.assert_called_once_with("player123", None)


def test_update_player_avatar_rejects_invalid_url(mock_db):
    client = TestClient(app)
    from app.infrastructure.auth import create_game_auth_token
    token = create_game_auth_token("player123")

    response = client.post(
        "/api/game/profile/player123/avatar",
        json={"avatar_url": "javascript:alert(1)"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400


def test_update_player_avatar_rejects_mismatched_token(mock_db):
    client = TestClient(app)
    from app.infrastructure.auth import create_game_auth_token
    token = create_game_auth_token("other-player")

    response = client.post(
        "/api/game/profile/player123/avatar",
        json={"avatar_url": "https://example.com/avatar.png"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
```

- [ ] **Step 3: 运行 API 测试确认失败**

Run:

```bash
python -m pytest backend/tests/test_game_api.py::test_get_player_profile backend/tests/test_game_api.py::test_update_player_avatar backend/tests/test_game_api.py::test_clear_player_avatar backend/tests/test_game_api.py::test_update_player_avatar_rejects_invalid_url backend/tests/test_game_api.py::test_update_player_avatar_rejects_mismatched_token -v
```

Expected: FAIL，失败原因是 profile 未返回 `avatar_url` 或头像路由不存在。

- [ ] **Step 4: 实现请求体和 URL 规范化函数**

修改 `backend/app/interfaces/api/game_routes.py`，在现有请求体类附近加入：

```python
from typing import Optional
```

```python
class UpdateAvatarRequest(BaseModel):
    avatar_url: Optional[str] = Field(None, max_length=500)
```

在 `ensure_player_access()` 下方加入：

```python
def normalize_avatar_url(avatar_url: Optional[str]) -> Optional[str]:
    if avatar_url is None:
        return None
    normalized = avatar_url.strip()
    if not normalized:
        return None
    allowed_prefixes = ("http://", "https://", "/static/", "/api/uploads/")
    if not normalized.startswith(allowed_prefixes):
        raise HTTPException(status_code=400, detail="头像地址必须是 http(s) 或站内静态资源地址")
    return normalized
```

- [ ] **Step 5: 扩展 profile 和 leaderboard 返回**

在 `get_player_profile()` 返回 dict 中加入：

```python
        "avatar_url": profile.avatar_url,
```

在 `get_leaderboard()` 每个玩家 dict 中加入：

```python
        "avatar_url": p.avatar_url,
```

- [ ] **Step 6: 实现头像更新路由**

在 `backend/app/interfaces/api/game_routes.py` 中新增：

```python
@router.post("/profile/{player_id}/avatar")
def update_player_avatar(
    player_id: str,
    req: UpdateAvatarRequest,
    db: Session = Depends(get_db),
    current_player_id: str = Depends(require_game_player_id),
):
    ensure_player_access(player_id, current_player_id)
    repo = SQLGameRepository(db)
    normalized_avatar_url = normalize_avatar_url(req.avatar_url)
    repo.get_or_create_profile(player_id, player_id)
    repo.update_avatar_url(player_id, normalized_avatar_url)
    updated_profile = repo.get_or_create_profile(player_id, player_id)
    return {
        "ok": True,
        "player_id": player_id,
        "avatar_url": updated_profile.avatar_url,
    }
```

- [ ] **Step 7: 运行 API 测试确认通过**

Run:

```bash
python -m pytest backend/tests/test_game_api.py::test_get_player_profile backend/tests/test_game_api.py::test_update_player_avatar backend/tests/test_game_api.py::test_clear_player_avatar backend/tests/test_game_api.py::test_update_player_avatar_rejects_invalid_url backend/tests/test_game_api.py::test_update_player_avatar_rejects_mismatched_token -v
```

Expected: PASS。

- [ ] **Step 8: 运行 API 测试回归**

Run:

```bash
python -m pytest backend/tests/test_game_api.py -v
```

Expected: PASS。

- [ ] **Step 9: 提交后端 API 改动**

```bash
git add backend/tests/test_game_api.py backend/app/interfaces/api/game_routes.py
git commit -m "feat: add profile avatar api"
```

---

### Task 3: 前端玩家 Store 头像状态

**Files:**
- Create: `frontend/src/stores/__tests__/playerStore.spec.ts`
- Modify: `frontend/src/stores/playerStore.ts`

**Interfaces:**
- Consumes: `GET /api/game/profile/{player_id}` response `avatar_url`
- Consumes: `POST /api/game/profile/{player_id}/avatar`
- Produces: `playerStore.avatarUrl`
- Produces: `playerStore.modifyAvatar(avatarUrl: string | null): Promise<{ ok: boolean; error?: string }>`

- [ ] **Step 1: 写 playerStore 头像失败测试**

创建 `frontend/src/stores/__tests__/playerStore.spec.ts`：

```typescript
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { usePlayerStore } from '../playerStore'

function mockFetch(response: unknown, ok = true) {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok,
    json: () => Promise.resolve(response),
  }))
}

describe('playerStore avatar profile state', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
    setActivePinia(createPinia())
  })

  it('hydrates avatarUrl from fetched profile data', async () => {
    localStorage.setItem('hmp_player_id', 'player123')
    localStorage.setItem('hmp_nickname', 'TestNick')
    localStorage.setItem('hmp_game_auth_token', 'token123')
    setActivePinia(createPinia())
    const store = usePlayerStore()
    mockFetch({
      nickname: 'TestNick',
      beans: 12000,
      total_games: 10,
      win_rate: 0.6,
      rank_id: 2,
      sub_rank: 3,
      stars: 1,
      rank_title: '短工III',
      avatar_url: 'https://example.com/avatar.png',
    })

    await store.fetchProfile()

    expect(store.avatarUrl).toBe('https://example.com/avatar.png')
    expect(localStorage.getItem('hmp_avatar_url')).toBe('https://example.com/avatar.png')
  })

  it('updates avatarUrl through profile avatar api', async () => {
    localStorage.setItem('hmp_player_id', 'player123')
    localStorage.setItem('hmp_nickname', 'TestNick')
    localStorage.setItem('hmp_game_auth_token', 'token123')
    setActivePinia(createPinia())
    const store = usePlayerStore()
    mockFetch({
      ok: true,
      player_id: 'player123',
      avatar_url: 'https://example.com/new-avatar.png',
    })

    const result = await store.modifyAvatar('https://example.com/new-avatar.png')

    expect(result.ok).toBe(true)
    expect(store.avatarUrl).toBe('https://example.com/new-avatar.png')
    expect(fetch).toHaveBeenCalledWith('/api/game/profile/player123/avatar', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: 'Bearer token123',
      },
      body: JSON.stringify({ avatar_url: 'https://example.com/new-avatar.png' }),
    })
  })

  it('clears avatarUrl when api returns null', async () => {
    localStorage.setItem('hmp_player_id', 'player123')
    localStorage.setItem('hmp_nickname', 'TestNick')
    localStorage.setItem('hmp_avatar_url', 'https://example.com/old.png')
    localStorage.setItem('hmp_game_auth_token', 'token123')
    setActivePinia(createPinia())
    const store = usePlayerStore()
    mockFetch({ ok: true, player_id: 'player123', avatar_url: null })

    const result = await store.modifyAvatar('')

    expect(result.ok).toBe(true)
    expect(store.avatarUrl).toBe('')
    expect(localStorage.getItem('hmp_avatar_url')).toBeNull()
  })
})
```

- [ ] **Step 2: 运行 store 测试确认失败**

Run:

```bash
cd frontend
npm run test:unit -- src/stores/__tests__/playerStore.spec.ts
```

Expected: FAIL，失败原因是 `avatarUrl` 或 `modifyAvatar` 不存在。

- [ ] **Step 3: 实现 playerStore 头像状态**

修改 `frontend/src/stores/playerStore.ts`：

```typescript
  const avatarUrl = ref(localStorage.getItem('hmp_avatar_url') || '')
```

在 `setSession()` 中继续保持头像由 `fetchProfile()` 同步，不需要额外参数。

在 `fetchProfile()` 成功分支加入：

```typescript
        avatarUrl.value = data.avatar_url || ''
        if (avatarUrl.value) {
          localStorage.setItem('hmp_avatar_url', avatarUrl.value)
        } else {
          localStorage.removeItem('hmp_avatar_url')
        }
```

在 `logout()` 中加入：

```typescript
    avatarUrl.value = ''
    localStorage.removeItem('hmp_avatar_url')
```

在 `modifyRank()` 后、`return` 前新增 action：

```typescript
  async function modifyAvatar(newAvatarUrl: string | null): Promise<{ ok: boolean; error?: string }> {
    try {
      const res = await fetch(`/api/game/profile/${playerId.value}/avatar`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({ avatar_url: newAvatarUrl })
      })
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}))
        return { ok: false, error: errData.detail || '修改头像失败' }
      }
      const data = await res.json()
      avatarUrl.value = data.avatar_url || ''
      if (avatarUrl.value) {
        localStorage.setItem('hmp_avatar_url', avatarUrl.value)
      } else {
        localStorage.removeItem('hmp_avatar_url')
      }
      return { ok: true }
    } catch (e: any) {
      return { ok: false, error: e.message || '网络连接失败' }
    }
  }
```

扩展 return：

```typescript
    playerId, nickname, username, authToken, avatarUrl, beans, totalGames, winRate,
    rankId, subRank, stars, rankTitle,
    register, login, logout, fetchProfile, modifyBeans, modifyRank, modifyAvatar
```

- [ ] **Step 4: 运行 store 测试确认通过**

Run:

```bash
cd frontend
npm run test:unit -- src/stores/__tests__/playerStore.spec.ts
```

Expected: PASS。

- [ ] **Step 5: 提交前端 store 改动**

```bash
git add frontend/src/stores/playerStore.ts frontend/src/stores/__tests__/playerStore.spec.ts
git commit -m "feat: persist player avatar in frontend store"
```

---

### Task 4: 大厅个人资料弹窗与头像渲染

**Files:**
- Create: `frontend/src/views/__tests__/LobbyView.spec.ts`
- Modify: `frontend/src/views/LobbyView.vue`

**Interfaces:**
- Consumes: `playerStore.avatarUrl`
- Consumes: `playerStore.modifyAvatar(avatarUrl: string | null)`
- Produces: lobby top-left logout label
- Produces: profile modal opened by `.bottom-user-card`
- Produces: avatar image rendering through `.avatar-image`

- [ ] **Step 1: 写大厅 UI 失败测试**

创建 `frontend/src/views/__tests__/LobbyView.spec.ts`：

```typescript
import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { usePlayerStore } from '@/stores/playerStore'
import { useGameStore } from '@/stores/gameStore'
import LobbyView from '../LobbyView.vue'

vi.mock('@/composables/useGameWebSocket', () => ({
  useGameWebSocket: () => ({
    connect: vi.fn(),
    disconnect: vi.fn(),
    sendAction: vi.fn(),
  }),
}))

const push = vi.fn()

vi.mock('vue-router', () => ({
  useRouter: () => ({ push }),
}))

function mountLobby(playerOverrides = {}) {
  localStorage.setItem('hmp_player_id', 'player123')
  localStorage.setItem('hmp_nickname', '请叫我longge')
  localStorage.setItem('hmp_username', 'longge')
  localStorage.setItem('hmp_game_auth_token', 'token123')
  localStorage.setItem('hmp_avatar_url', 'https://example.com/avatar.png')
  const pinia = createPinia()
  setActivePinia(pinia)
  const player = usePlayerStore()
  Object.assign(player, {
    beans: 6820,
    totalGames: 12,
    winRate: 0.5,
    rankId: 2,
    subRank: 2,
    stars: 1,
    rankTitle: '短工II',
    modifyAvatar: vi.fn().mockResolvedValue({ ok: true }),
    fetchProfile: vi.fn().mockResolvedValue(undefined),
    ...playerOverrides,
  })
  const game = useGameStore()
  Object.assign(game, { gamePhase: 'IDLE', wsConnected: false })
  return mount(LobbyView, { global: { plugins: [pinia] } })
}

describe('LobbyView profile avatar UI', () => {
  it('labels the top-left action as logout', () => {
    const wrapper = mountLobby()

    expect(wrapper.find('.btn-back .back-text').text()).toBe('退出')
    expect(wrapper.find('.btn-back').attributes('aria-label')).toBe('退出登录')
  })

  it('renders avatar image in the bottom user card', () => {
    const wrapper = mountLobby()

    const image = wrapper.find('.bottom-user-card .avatar-image')
    expect(image.exists()).toBe(true)
    expect(image.attributes('src')).toBe('https://example.com/avatar.png')
  })

  it('opens profile modal from bottom user card', async () => {
    const wrapper = mountLobby()

    await wrapper.find('.bottom-user-card').trigger('click')

    expect(wrapper.find('.profile-modal').exists()).toBe(true)
    expect(wrapper.find('.profile-modal').text()).toContain('个人资料')
    expect(wrapper.find('input.profile-avatar-input').exists()).toBe(true)
  })
})
```

- [ ] **Step 2: 运行大厅 UI 测试确认失败**

Run:

```bash
cd frontend
npm run test:unit -- src/views/__tests__/LobbyView.spec.ts
```

Expected: FAIL，失败原因是 `.back-text` 仍不是退出文案、`.avatar-image` 不存在或 `.profile-modal` 不存在。

- [ ] **Step 3: 实现脚本状态与处理函数**

修改 `frontend/src/views/LobbyView.vue` 的 `<script setup>`：

```typescript
const showProfileModal = ref(false)
const avatarInputValue = ref('')
const avatarSaveError = ref('')
const avatarImageFailed = ref(false)

function openProfileModal() {
  avatarInputValue.value = playerStore.avatarUrl
  avatarSaveError.value = ''
  avatarImageFailed.value = false
  showProfileModal.value = true
}
```

替换 `handleProfileClick()`：

```typescript
function handleProfileClick() {
  openProfileModal()
}
```

新增：

```typescript
async function handleSaveAvatar() {
  avatarSaveError.value = ''
  const result = await playerStore.modifyAvatar(avatarInputValue.value)
  if (!result.ok) {
    avatarSaveError.value = result.error || '头像保存失败'
    return
  }
  avatarInputValue.value = playerStore.avatarUrl
  avatarImageFailed.value = false
}

async function handleClearAvatar() {
  avatarSaveError.value = ''
  const result = await playerStore.modifyAvatar('')
  if (!result.ok) {
    avatarSaveError.value = result.error || '头像清空失败'
    return
  }
  avatarInputValue.value = ''
  avatarImageFailed.value = false
}

function handleAvatarImageError() {
  avatarImageFailed.value = true
}
```

- [ ] **Step 4: 修改顶部退出按钮文案**

在主大厅顶部按钮中改为：

```vue
<button class="btn-back" type="button" aria-label="退出登录" @click="handleLogout">
  <div class="btn-back-circle">
    <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
      <path d="M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z"/>
    </svg>
  </div>
  <span class="back-text">退出</span>
</button>
```

- [ ] **Step 5: 修改底部头像渲染**

将两处底部用户卡片中的头像块替换为同样结构：

```vue
<div class="user-avatar-wrap">
  <img
    v-if="playerStore.avatarUrl"
    class="avatar-image"
    :src="playerStore.avatarUrl"
    alt="玩家头像"
    @error="handleAvatarImageError"
  />
  <span v-else class="avatar-emoji">👤</span>
</div>
```

如需让远程图片失败后隐藏图片，在实际实现中使用一个 helper：

```vue
<img
  v-if="playerStore.avatarUrl && !avatarImageFailed"
  class="avatar-image"
  :src="playerStore.avatarUrl"
  alt="玩家头像"
  @error="handleAvatarImageError"
/>
<span v-else class="avatar-emoji">👤</span>
```

- [ ] **Step 6: 增加个人资料弹窗模板**

在现有排行榜弹窗和欢乐豆弹窗附近加入：

```vue
<div v-if="showProfileModal" class="modal-overlay" @click.self="showProfileModal = false">
  <div class="glass-panel profile-modal">
    <div class="modal-header">
      <h3>个人资料</h3>
      <button class="btn-close" type="button" @click="showProfileModal = false">×</button>
    </div>

    <div class="profile-summary">
      <div class="profile-avatar-preview">
        <img
          v-if="playerStore.avatarUrl && !avatarImageFailed"
          class="profile-avatar-image"
          :src="playerStore.avatarUrl"
          alt="玩家头像"
          @error="handleAvatarImageError"
        />
        <span v-else class="profile-avatar-placeholder">👤</span>
      </div>
      <div class="profile-main-info">
        <div class="profile-nickname">{{ playerStore.nickname }}</div>
        <div class="profile-account">账号：{{ playerStore.username || '未绑定' }}</div>
        <div class="profile-player-id">ID：{{ playerStore.playerId }}</div>
      </div>
    </div>

    <div class="profile-stats-grid">
      <div class="profile-stat"><span>欢乐豆</span><strong>{{ formatBeans(playerStore.beans) }}</strong></div>
      <div class="profile-stat"><span>总局数</span><strong>{{ playerStore.totalGames }}</strong></div>
      <div class="profile-stat"><span>胜率</span><strong>{{ (playerStore.winRate * 100).toFixed(0) }}%</strong></div>
      <div class="profile-stat"><span>段位</span><strong>{{ playerStore.rankTitle }}</strong></div>
    </div>

    <label class="profile-avatar-field">
      <span>头像图片 URL</span>
      <input
        v-model="avatarInputValue"
        class="profile-avatar-input"
        type="url"
        placeholder="https://example.com/avatar.png"
      />
    </label>
    <p v-if="avatarSaveError" class="profile-error">{{ avatarSaveError }}</p>

    <div class="profile-actions">
      <button class="btn-leaderboard-toggle profile-secondary-action" type="button" @click="handleClearAvatar">
        清空头像
      </button>
      <button class="btn-leaderboard-toggle" type="button" @click="handleSaveAvatar">
        保存头像
      </button>
    </div>
  </div>
</div>
```

- [ ] **Step 7: 增加个人资料和图片样式**

在 `LobbyView.vue` 样式区追加：

```css
.avatar-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: 50%;
}

.profile-modal {
  width: min(92vw, 460px);
  max-height: 86vh;
  overflow-y: auto;
  padding: 24px;
  box-sizing: border-box;
}

.profile-summary {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 18px;
}

.profile-avatar-preview {
  width: 82px;
  height: 82px;
  border-radius: 50%;
  border: 2px solid #ffd700;
  background: rgba(255, 255, 255, 0.14);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  flex: 0 0 auto;
}

.profile-avatar-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.profile-avatar-placeholder {
  font-size: 2.4rem;
}

.profile-main-info {
  min-width: 0;
  text-align: left;
}

.profile-nickname {
  font-size: 1.18rem;
  font-weight: 900;
  color: #fff;
  overflow-wrap: anywhere;
}

.profile-account,
.profile-player-id {
  margin-top: 6px;
  color: rgba(255, 255, 255, 0.72);
  font-size: 0.9rem;
}

.profile-stats-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 18px;
}

.profile-stat {
  border: 1px solid rgba(255,255,255,0.12);
  border-radius: 8px;
  padding: 10px;
  background: rgba(0,0,0,0.22);
  display: flex;
  flex-direction: column;
  gap: 4px;
  text-align: left;
}

.profile-stat span {
  color: rgba(255,255,255,0.68);
  font-size: 0.78rem;
}

.profile-stat strong {
  color: #ffd700;
  font-size: 1rem;
  overflow-wrap: anywhere;
}

.profile-avatar-field {
  display: flex;
  flex-direction: column;
  gap: 8px;
  text-align: left;
  color: rgba(255,255,255,0.82);
  font-weight: 800;
}

.profile-avatar-input {
  width: 100%;
  box-sizing: border-box;
  border: 1.5px solid rgba(255,255,255,0.22);
  border-radius: 8px;
  padding: 10px 12px;
  color: #fff;
  background: rgba(0,0,0,0.45);
  font-size: 0.95rem;
}

.profile-error {
  color: #ff8a80;
  margin: 10px 0 0;
  text-align: left;
  font-weight: 700;
}

.profile-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 20px;
}

.profile-secondary-action {
  background: rgba(255,255,255,0.1);
  border: 1px solid rgba(255,255,255,0.2);
  color: #fff;
}
```

- [ ] **Step 8: 运行大厅 UI 测试确认通过**

Run:

```bash
cd frontend
npm run test:unit -- src/views/__tests__/LobbyView.spec.ts
```

Expected: PASS。

- [ ] **Step 9: 运行前端测试回归**

Run:

```bash
cd frontend
npm run test:unit
```

Expected: PASS。

- [ ] **Step 10: 提交大厅 UI 改动**

```bash
git add frontend/src/views/LobbyView.vue frontend/src/views/__tests__/LobbyView.spec.ts
git commit -m "feat: add lobby profile avatar editor"
```

---

### Task 5: 集成验证

**Files:**
- Verify only: no planned code changes

**Interfaces:**
- Consumes: all previous tasks
- Produces: verified avatar profile workflow

- [ ] **Step 1: 运行后端相关测试**

Run:

```bash
python -m pytest backend/tests/test_game_repository.py backend/tests/test_game_api.py -v
```

Expected: PASS。

- [ ] **Step 2: 运行前端相关测试**

Run:

```bash
cd frontend
npm run test:unit -- src/stores/__tests__/playerStore.spec.ts src/views/__tests__/LobbyView.spec.ts
```

Expected: PASS。

- [ ] **Step 3: 运行前端构建检查**

Run:

```bash
cd frontend
npm run build
```

Expected: PASS，无 TypeScript 或 Vite 构建错误。

- [ ] **Step 4: 如本地服务已运行，手动检查大厅页面**

打开 `http://localhost:5173/lobby`，确认：

- 左上角按钮显示退出含义。
- 点击底部用户卡片打开个人资料弹窗。
- 输入 `https://example.com/avatar.png` 保存后，底部头像区域尝试渲染图片。
- 清空头像后恢复默认头像占位。

- [ ] **Step 5: 确认无需额外提交**

如果 Step 1 到 Step 4 都通过，并且没有为了修复验证问题产生新的代码改动，则不创建额外提交。若验证发现问题，回到对应任务补充失败测试并按该任务的提交步骤提交修复。
