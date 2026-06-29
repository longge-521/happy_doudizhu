# 欢乐斗地主欢乐豆管理与门槛限制实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现欢乐豆的非负限制、破产保护、手动修改功能以及各个场次的进入欢乐豆门槛校验与拦截。

**Architecture:** 
1. 数据库仓储层对欢乐豆变更限制下限为 0（破产保护）；
2. 暴露 `POST /api/game/profile/{player_id}/beans` HTTP API 用于手动修改；
3. WebSocket 连接在处理 `join_match` 时读取玩家金豆，根据映射做拦截；
4. 前端 Store 支持 `modifyBeans` 触发 API，大厅提供点击修改资产的模态框以及场次前置校验拦截。

**Tech Stack:** FastAPI, Python, SQLAlchemy, Vue 3, Pinia, TypeScript

## Global Constraints

- 所有欢乐豆修改逻辑（对局结算、直接设置）均限制欢乐豆 >= 0。
- 场次进入门槛与底分映射关系全局一致。
- 总是采用 TDD 流程编写每一项后端改动。

---

### Task 1: 数据库与结算层修改（防负数与破产保护）

**Files:**
- Create: `backend/tests/test_game_repository.py`
- Modify: `backend/app/infrastructure/database/game_repository.py`

**Interfaces:**
- Produces: `SQLGameRepository.update_beans(player_id: str, beans: int) -> None`
- Produces: `SQLGameRepository.update_profile_stats(player_id: str, beans_delta: int, is_win: bool) -> None`

- [ ] **Step 1: Write the failing test**

在新文件 `backend/tests/test_game_repository.py` 中编写以下测试，验证 `update_beans` 对负数的截断，以及 `update_profile_stats` 扣减超出时归零的破产保护：

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.infrastructure.database.models import Base, PlayerProfileORM
from app.infrastructure.database.game_repository import SQLGameRepository

def test_sql_game_repository_beans():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    repo = SQLGameRepository(session)
    
    # 初始创建
    profile = repo.get_or_create_profile("player_test", "Tester")
    assert profile.beans == 10000
    
    # 测试 update_beans 限制非负数
    repo.update_beans("player_test", -500)
    orm = session.query(PlayerProfileORM).filter_by(player_id="player_test").first()
    assert orm.beans == 0
    
    # 测试 update_profile_stats 破产保护扣减
    repo.update_beans("player_test", 100)
    repo.update_profile_stats("player_test", -200, is_win=False)
    orm = session.query(PlayerProfileORM).filter_by(player_id="player_test").first()
    assert orm.beans == 0
    
    session.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_game_repository.py -v`
Expected: FAIL due to `SQLGameRepository` missing `update_beans` method.

- [ ] **Step 3: Write minimal implementation**

修改 `backend/app/infrastructure/database/game_repository.py`：
```python
    def update_beans(self, player_id: str, beans: int) -> None:
        orm = self._db.query(PlayerProfileORM).filter_by(player_id=player_id).first()
        if orm:
            orm.beans = max(0, beans)

    def update_profile_stats(self, player_id: str, beans_delta: int, is_win: bool) -> None:
        orm = self._db.query(PlayerProfileORM).filter_by(player_id=player_id).first()
        if orm:
            orm.beans = max(0, orm.beans + beans_delta)
            orm.total_games += 1
            if is_win:
                orm.wins += 1
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_game_repository.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/infrastructure/database/game_repository.py backend/tests/test_game_repository.py
git commit -m "feat: implement database level bean update and negative protection with tests"
```

---

### Task 2: 后端 HTTP REST API 支持修改金豆

**Files:**
- Modify: `backend/tests/test_game_api.py`
- Modify: `backend/app/interfaces/api/game_routes.py`

**Interfaces:**
- Consumes: `SQLGameRepository.update_beans`
- Produces: `POST /api/game/profile/{player_id}/beans`

- [ ] **Step 1: Write the failing test**

在 `backend/tests/test_game_api.py` 的末尾追加测试用例：

```python
def test_update_player_beans(mock_db):
    client = TestClient(app)
    with patch("app.interfaces.api.game_routes.SQLGameRepository") as mock_repo_class:
        mock_repo = MagicMock()
        mock_profile = MagicMock()
        mock_profile.beans = 25000
        mock_repo.get_or_create_profile.return_value = mock_profile
        mock_repo_class.return_value = mock_repo
        
        # 测试成功设置欢乐豆
        response = client.post("/api/game/profile/player123/beans", json={"beans": 25000})
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["beans"] == 25000
        mock_repo.update_beans.assert_called_once_with("player123", 25000)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_game_api.py::test_update_player_beans -v`
Expected: FAIL with status code 404/405 (endpoint not found)

- [ ] **Step 3: Write minimal implementation**

在 `backend/app/interfaces/api/game_routes.py` 中引入 `Field`（若无），并加入以下类和路由方法：

```python
# 在 schema 部分加入
class UpdateBeansRequest(BaseModel):
    beans: int = Field(..., ge=0, comment="修改欢乐豆，必须非负数")

# 在文件末尾加入
@router.post("/profile/{player_id}/beans")
def update_beans(player_id: str, req: UpdateBeansRequest, db: Session = Depends(get_db)):
    repo = SQLGameRepository(db)
    repo.get_or_create_profile(player_id, player_id)
    repo.update_beans(player_id, req.beans)
    updated_profile = repo.get_or_create_profile(player_id, player_id)
    return {
        "ok": True,
        "player_id": player_id,
        "beans": updated_profile.beans
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_game_api.py::test_update_player_beans -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/interfaces/api/game_routes.py backend/tests/test_game_api.py
git commit -m "feat: add update beans REST API with tests"
```

---

### Task 3: WebSocket 匹配前门槛拦截

**Files:**
- Modify: `backend/tests/test_game_websocket.py`
- Modify: `backend/app/interfaces/websocket/game_handler.py`

**Interfaces:**
- Consumes: `SQLGameRepository.get_or_create_profile`

- [ ] **Step 1: Write the failing test**

在 `backend/tests/test_game_websocket.py` 末尾追加测试用例，校验欢乐豆不足以参加 80 分的初级场时匹配失败：

```python
def test_game_websocket_join_match_insufficient_beans(monkeypatch, mock_game_service):
    monkeypatch.setattr(auth, "API_TOKEN", "")
    
    # 模拟 Profile 欢乐豆仅 500
    mock_profile = MagicMock()
    mock_profile.beans = 500
    
    client = TestClient(app)
    with patch("app.interfaces.websocket.game_handler.SQLGameRepository") as mock_repo_class:
        mock_repo = MagicMock()
        mock_repo.get_or_create_profile.return_value = mock_profile
        mock_repo_class.return_value = mock_repo
        
        with client.websocket_connect("/ws/game/player1") as websocket:
            # 申请加入底分为 80 的初级场（需要最低 3000）
            websocket.send_json({"action": "join_match", "nickname": "Player One", "base_score": 80})
            resp = websocket.receive_json()
            assert resp["event"] == "error"
            assert "欢乐豆不足" in resp["msg"]
            mock_game_service.join_match.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_game_websocket.py::test_game_websocket_join_match_insufficient_beans -v`
Expected: FAIL because no validation is implemented yet and `mock_game_service.join_match` is called.

- [ ] **Step 3: Write minimal implementation**

在 `backend/app/interfaces/websocket/game_handler.py` 中：
1. 定义全局门槛 `BASE_SCORE_MIN_BEANS`：
```python
BASE_SCORE_MIN_BEANS = {
    20: 1000,
    80: 3000,
    300: 8000,
    900: 25000,
    2700: 80000,
    6000: 300000,
}
```
2. 更改 `join_match` 的 action 响应流程：
```python
        if action == "join_match":
            nickname = data.get("nickname", self.player_id)
            base_score = data.get("base_score", 10)
            
            # 加入金币准入条件核查
            from app.infrastructure.database.session import transactional_session
            from app.infrastructure.database.game_repository import SQLGameRepository
            
            with transactional_session() as db:
                repo = SQLGameRepository(db)
                profile = repo.get_or_create_profile(self.player_id, nickname)
                min_beans = BASE_SCORE_MIN_BEANS.get(base_score, 0)
                if profile.beans < min_beans:
                    await self._send({
                        "event": "error",
                        "msg": f"您的欢乐豆不足，该赛事最低需要 {min_beans} 欢乐豆"
                    })
                    return
            
            result = await self.service.join_match(self.player_id, nickname, auto_ai=False, base_score=base_score)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_game_websocket.py::test_game_websocket_join_match_insufficient_beans -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/interfaces/websocket/game_handler.py backend/tests/test_game_websocket.py
git commit -m "feat: enforce websocket matching entry verification with tests"
```

---

### Task 4: 前端 Pinia Store 状态动作管理修改

**Files:**
- Modify: `frontend/src/stores/playerStore.ts`

**Interfaces:**
- Produces: `modifyBeans(newBeans: number) => Promise<{ ok: boolean; error?: string }>`

- [ ] **Step 1: Implement modifyBeans in playerStore**

修改 `frontend/src/stores/playerStore.ts`，加入 `modifyBeans` action 方法并返回：
```typescript
  async function modifyBeans(newBeans: number): Promise<{ ok: boolean; error?: string }> {
    if (newBeans < 0) {
      return { ok: false, error: '欢乐豆不能为负数' }
    }
    try {
      const res = await fetch(`/api/game/profile/${playerId.value}/beans`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ beans: newBeans })
      })
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}))
        return { ok: false, error: errData.detail || '修改欢乐豆失败' }
      }
      const data = await res.json()
      beans.value = data.beans
      return { ok: true }
    } catch (e: any) {
      return { ok: false, error: e.message || '网络连接失败' }
    }
  }
```

- [ ] **Step 2: Run type check to verify compilation**

在前端目录运行 TypeScript 类型检查：
Run: `npm run type-check` (在 `frontend` 文件夹下)
Expected: Compile successfully, no type errors in `playerStore.ts`.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/stores/playerStore.ts
git commit -m "feat: extend playerStore to support beans modification via REST API"
```

---

### Task 5: 前端大厅 UI 修改与门槛拦截

**Files:**
- Modify: `frontend/src/views/LobbyView.vue`

- [ ] **Step 1: Add modal UI and validation logic in LobbyView**

修改 `frontend/src/views/LobbyView.vue`，在 `<script setup>` 中：
1. 定义门槛常数：
```typescript
const TIER_MIN_BEANS: Record<number, number> = {
  20: 1000,
  80: 3000,
  300: 8000,
  900: 25000,
  2700: 80000,
  6000: 300000
}
```
2. 新增修改金豆相关的 state 和逻辑：
```typescript
const showEditBeansModal = ref(false)
const inputBeansValue = ref(10000)
const editBeansError = ref('')

function openEditBeansModal() {
  inputBeansValue.value = playerStore.beans
  editBeansError.value = ''
  showEditBeansModal.value = true
}

async function handleSaveBeans() {
  if (inputBeansValue.value < 0) {
    editBeansError.value = '欢乐豆数量不能为负数！'
    return
  }
  const result = await playerStore.modifyBeans(inputBeansValue.value)
  if (result.ok) {
    showEditBeansModal.value = false
    await loadLobbyData() // 刷新大厅排行及自身数据
  } else {
    editBeansError.value = result.error || '保存失败'
  }
}
```
3. 改造 `selectTier` 门槛前置校验：
```typescript
function selectTier(tier: any) {
  const minRequired = TIER_MIN_BEANS[tier.baseScore] || 0
  if (playerStore.beans < minRequired) {
    alert(`您的欢乐豆不足以进入【${tier.name}】！入场门槛为 ${formatBeans(minRequired)} 欢乐豆。`)
    return
  }
  selectedTier.value = tier
  selectedBaseScore.value = tier.baseScore
  showReadyPage.value = true
}
```
4. 在“快速开始”按钮中同样检验金豆门槛：
```typescript
function handleLobbyStartClick() {
  const minRequired = TIER_MIN_BEANS[selectedTier.value.baseScore] || 0
  if (playerStore.beans < minRequired) {
    alert(`您的欢乐豆不足以进入【${selectedTier.value.name}】！入场门槛为 ${formatBeans(minRequired)} 欢乐豆。`)
    return
  }
  showReadyPage.value = true
}
```

在 HTML 模板部分：
1. 顶部欢乐豆资产加上点击入口：
```html
          <div class="asset-pill gold-beans" @click="openEditBeansModal" style="cursor: pointer;">
```
2. 新增模态弹窗模板：
```html
    <!-- 欢乐豆修改弹窗 -->
    <div v-if="showEditBeansModal" class="modal-overlay" @click.self="showEditBeansModal = false">
      <div class="glass-panel leaderboard-modal" style="max-width: 400px; padding: 24px;">
        <div class="modal-header" style="margin-bottom: 20px;">
          <h3>🪙 修改欢乐豆数量</h3>
          <button class="btn-close" @click="showEditBeansModal = false">×</button>
        </div>
        <div class="modal-body" style="display: flex; flex-direction: column; gap: 16px;">
          <div style="display: flex; flex-direction: column; gap: 8px;">
            <label style="color: #ccc; font-size: 0.9rem;">请输入新的欢乐豆数量 (不少于 0)：</label>
            <input
              v-model.number="inputBeansValue"
              type="number"
              min="0"
              style="background: rgba(0,0,0,0.5); border: 1.5px solid rgba(255,255,255,0.2); border-radius: 8px; padding: 10px; color: #fff; font-size: 1.2rem; font-weight: bold;"
            />
          </div>
          <p v-if="editBeansError" style="color: #f44336; margin: 0; font-size: 0.85rem;">{{ editBeansError }}</p>
        </div>
        <div class="modal-footer" style="display: flex; justify-content: flex-end; gap: 12px; margin-top: 24px;">
          <button class="btn-hud-tool" @click="showEditBeansModal = false" style="background: rgba(255,255,255,0.1); color: #fff;">取消</button>
          <button class="btn-leaderboard-toggle" @click="handleSaveBeans">确认保存</button>
        </div>
      </div>
    </div>
```

- [ ] **Step 2: Run type check and verify frontend compilation**

Run: `npm run type-check` (在 `frontend` 文件夹下)
Expected: Compile successfully, no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/LobbyView.vue
git commit -m "feat: implement beans edit dialog and entry validation UI in LobbyView"
```
