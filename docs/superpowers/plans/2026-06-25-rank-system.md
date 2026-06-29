# 欢乐斗地主 36级古风排位系统实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 36级古风排位段位系统的数据库持久化、后端胜负结算升降星状态机、段位设定与查询 API，以及前端大厅称号和星条的动态展示与修改。

**Architecture:** 
1. 数据库在 `player_profile` 中增加 `rank_id`、`sub_rank`、`stars` 字段。
2. 领域层 `PlayerProfile` 中添加 36级段位常量列表，并提供只读属性 `rank_title` 动态输出 “头衔 + 罗马级别”（如 “富农III”，至尊段位直接显示为 “至尊”）。
3. 仓储层实现胜负星级状态机：赢牌普通 +1 星，炸弹/春天等爆发性胜利 +2 星并能溢出进阶；输牌 -1 星，中低段位提供新手大段位保级和降段保护，高段位则无保护。
4. HTTP 接口及 WebSocket 结算层相应适配，提供修改段位接口。
5. 前端大厅自适应渲染当前大段位的星星数（3、4 或 5 颗星），并提供修改弹窗供开发调试。

**Tech Stack:** FastAPI, Python, SQLAlchemy, Vue 3, Pinia, TypeScript

## Global Constraints

- 所有排位修改或结算过程均限制 `rank_id` 介于 1 到 36 之间，`sub_rank` 介于 1 到 4 之间，星星数非负。
- 大厅段位显示符合格式：`头衔名称 + 罗马小级别`（I-IV），至尊级别无罗马数字后缀。
- 总是采用 TDD 流程编写每一项后端改动。

---

### Task 1: 数据库与领域模型扩展

**Files:**
- Modify: `backend/app/infrastructure/database/models.py`
- Modify: `backend/app/domain/game/entities.py`
- Modify: `backend/app/infrastructure/database/game_repository.py`
- Modify: `backend/tests/test_game_models.py`

**Interfaces:**
- Produces: `PlayerProfile.rank_title -> str`
- Produces: `PlayerProfileORM` columns: `rank_id`, `sub_rank`, `stars`

- [ ] **Step 1: Write the failing test**

修改 `backend/tests/test_game_models.py` 在 `TestPlayerProfile` 类末尾追加测试，验证新增属性值及其向罗马称号的自动映射：

```python
    def test_player_profile_rank_title(self):
        p = PlayerProfile(player_id="p1", nickname="玩家1", rank_id=1, sub_rank=4, stars=0)
        assert p.rank_title == "包身工IV"
        
        # 验证 1 映射为 I 级
        p2 = PlayerProfile(player_id="p1", nickname="玩家1", rank_id=6, sub_rank=1, stars=2)
        assert p2.rank_title == "掌柜I"
        
        # 验证 36 级(至尊)不带罗马数字后缀
        p3 = PlayerProfile(player_id="p1", nickname="玩家1", rank_id=36, sub_rank=1, stars=10)
        assert p3.rank_title == "至尊"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest tests/test_game_models.py -v`
Expected: FAIL due to missing arguments `rank_id` etc, or unexpected attribute `rank_title`.

- [ ] **Step 3: Write minimal implementation**

1. 修改 `backend/app/infrastructure/database/models.py` 在 `PlayerProfileORM` 实体中增加字段（行 57 附近）：
```python
    rank_id = Column(Integer, default=1, nullable=False, comment="大级别(1-36)")
    sub_rank = Column(Integer, default=4, nullable=False, comment="子级别(1-4，对应I-IV)")
    stars = Column(Integer, default=0, nullable=False, comment="累积星星数")
```

2. 修改 `backend/app/domain/game/entities.py` 扩充 `PlayerProfile` 头衔映射及属性：
```python
# 头衔对照常量
RANK_TITLES = [
    "", "包身工", "短工", "长工", "中农", "富农", "掌柜", "商人", "小财主", "大财主",
    "县尉", "县丞", "县令", "通判", "主事", "知府", "员外郎", "郎中", "侍郎", "巡抚",
    "总督", "尚书", "大学士", "太保", "太傅", "太师", "三等伯", "二等伯", "一等伯",
    "三等侯", "二等侯", "一等侯", "辅国公", "镇国公", "郡王", "亲王", "至尊"
]

class PlayerProfile:
    def __init__(
        self,
        player_id: str,
        nickname: str,
        beans: int = DEFAULT_BEANS,
        total_games: int = 0,
        wins: int = 0,
        created_at: Optional[datetime.datetime] = None,
        rank_id: int = 1,
        sub_rank: int = 4,
        stars: int = 0
    ):
        self.player_id = player_id
        self.nickname = nickname
        self.beans = beans
        self.total_games = total_games
        self.wins = wins
        self.created_at = created_at
        self.rank_id = rank_id
        self.sub_rank = sub_rank
        self.stars = stars

    @property
    def rank_title(self) -> str:
        if self.rank_id >= 36:
            return "至尊"
        roman_map = {1: "I", 2: "II", 3: "III", 4: "IV"}
        roman = roman_map.get(self.sub_rank, "IV")
        title = RANK_TITLES[self.rank_id] if self.rank_id < len(RANK_TITLES) else "包身工"
        return f"{title}{roman}"
```

3. 修改 `backend/app/infrastructure/database/game_repository.py` 以将新数据库字段映射传参给 `PlayerProfile`：
   * 修改 `get_or_create_profile` 方法返回处：
     ```python
             beans=orm.beans, total_games=orm.total_games, wins=orm.wins,
             created_at=orm.created_at,
             rank_id=orm.rank_id, sub_rank=orm.sub_rank, stars=orm.stars
     ```
   * 修改 `get_leaderboard` 列表生成映射处：
     ```python
             beans=r.beans, total_games=r.total_games, wins=r.wins,
             created_at=r.created_at,
             rank_id=r.rank_id, sub_rank=r.sub_rank, stars=r.stars
     ```

- [ ] **Step 4: Run test to verify it passes**

Run: `D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest tests/test_game_models.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/infrastructure/database/models.py backend/app/domain/game/entities.py backend/app/infrastructure/database/game_repository.py backend/tests/test_game_models.py
git commit -m "feat: extend db models and entities with rank properties"
```

---

### Task 2: 后端结算状态机与排位仓储逻辑实现

**Files:**
- Modify: `backend/tests/test_game_repository.py`
- Modify: `backend/app/infrastructure/database/game_repository.py`
- Modify: `backend/app/interfaces/websocket/game_handler.py`

**Interfaces:**
- Produces: `SQLGameRepository.update_rank_stats(player_id: str, is_win: bool, multiplier: int) -> None`
- Produces: `SQLGameRepository.update_rank_profile(player_id: str, rank_id: int, sub_rank: int, stars: int) -> None`

- [ ] **Step 1: Write the failing test**

在 `backend/tests/test_game_repository.py` 末尾追加测试用例，校验赢加星（含春天双星及晋级），输扣星（含新手保护及段位保级、掉大段等状态）：

```python
def test_sql_game_repository_rank_state_machine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    repo = SQLGameRepository(session)
    
    # 建立初始段位：包身工IV (rank_id=1, sub_rank=4, stars=0)
    repo.get_or_create_profile("player_rank", "Tester")
    
    # 1. 验证新手保护：输牌不扣星 (包身工IV 0星输球 -> 仍为包身工IV 0星)
    repo.update_rank_stats("player_rank", is_win=False, multiplier=1)
    orm = session.query(PlayerProfileORM).filter_by(player_id="player_rank").first()
    assert orm.rank_id == 1 and orm.sub_rank == 4 and orm.stars == 0
    
    # 2. 验证赢球加星及溢出升小段 (包身工IV 0星 -> 普通赢 -> 包身工IV 1星)
    repo.update_rank_stats("player_rank", is_win=True, multiplier=1)
    # 再普通赢两场 -> 包身工IV 3星 (满星升段门槛3) -> 晋级短工IV (即 rank_id=2, sub_rank=4, stars=0)
    repo.update_rank_stats("player_rank", is_win=True, multiplier=1)
    repo.update_rank_stats("player_rank", is_win=True, multiplier=1)
    orm = session.query(PlayerProfileORM).filter_by(player_id="player_rank").first()
    assert orm.rank_id == 1 and orm.sub_rank == 3 and orm.stars == 0
    
    # 3. 验证爆发赢加双星及大段晋级
    # 设定为大财主I 2星 (rank_id=9, sub_rank=1, stars=2)
    repo.update_rank_profile("player_rank", rank_id=9, sub_rank=1, stars=2)
    # 特殊赢(+2星) -> 星星变成 4(大财主满星限制3) -> 溢出 1星并大段晋级为县尉IV (rank_id=10, sub_rank=4, stars=1)
    repo.update_rank_stats("player_rank", is_win=True, multiplier=4)
    orm = session.query(PlayerProfileORM).filter_by(player_id="player_rank").first()
    assert orm.rank_id == 10 and orm.sub_rank == 4 and orm.stars == 1
    
    # 4. 验证中等段位大段位保护 (县尉IV 0星输球 -> 触发保级 -> 仍为县尉IV 0星)
    repo.update_rank_profile("player_rank", rank_id=10, sub_rank=4, stars=0)
    repo.update_rank_stats("player_rank", is_win=False, multiplier=1)
    orm = session.query(PlayerProfileORM).filter_by(player_id="player_rank").first()
    assert orm.rank_id == 10 and orm.sub_rank == 4 and orm.stars == 0
    
    # 5. 验证高级段位无降段保护 (大学士IV 0星输球 -> 无保级降大级 -> 尚书I 4星 (尚书满星4，扣1后剩3))
    repo.update_rank_profile("player_rank", rank_id=22, sub_rank=4, stars=0)
    repo.update_rank_stats("player_rank", is_win=False, multiplier=1)
    orm = session.query(PlayerProfileORM).filter_by(player_id="player_rank").first()
    assert orm.rank_id == 21 and orm.sub_rank == 1 and orm.stars == 3
    
    session.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest tests/test_game_repository.py -v`
Expected: FAIL due to missing attribute `update_rank_stats` / `update_rank_profile`.

- [ ] **Step 3: Write minimal implementation**

1. 修改 `backend/app/infrastructure/database/game_repository.py` 实现状态机和接口：
```python
    def update_rank_profile(self, player_id: str, rank_id: int, sub_rank: int, stars: int) -> None:
        orm = self._db.query(PlayerProfileORM).filter_by(player_id=player_id).first()
        if orm:
            orm.rank_id = max(1, min(36, rank_id))
            orm.sub_rank = max(1, min(4, sub_rank))
            orm.stars = max(0, stars)

    def update_rank_stats(self, player_id: str, is_win: bool, multiplier: int) -> None:
        orm = self._db.query(PlayerProfileORM).filter_by(player_id=player_id).first()
        if not orm:
            return
        
        # 1. 判定当前段位所需的满星数
        # 1-9级：3星；10-21级：4星；22-35级：5星；36级(至尊)：无限制
        if orm.rank_id < 10:
            max_stars = 3
        elif orm.rank_id < 22:
            max_stars = 4
        else:
            max_stars = 5

        if is_win:
            # 2. 赢牌加星：multiplier >= 4 为爆发胜利 +2星，否则 +1星
            delta = 2 if multiplier >= 4 else 1
            if orm.rank_id >= 36:
                # 至尊不限制子级别，无限累加星星
                orm.stars += delta
                return
                
            orm.stars += delta
            # 星星溢出，小段位晋级
            while orm.stars >= max_stars:
                orm.stars -= max_stars
                orm.sub_rank -= 1
                
                # 子级别溢出(小于1)，大级别晋升
                if orm.sub_rank < 1:
                    orm.sub_rank = 4
                    orm.rank_id += 1
                    
                    if orm.rank_id >= 36:
                        # 满阶升入至尊
                        orm.rank_id = 36
                        orm.sub_rank = 1
                        # 溢出星扣除
                        break
                    
                    # 重新刷新当前段位满星数
                    if orm.rank_id < 10:
                        max_stars = 3
                    elif orm.rank_id < 22:
                        max_stars = 4
                    else:
                        max_stars = 5
        else:
            # 3. 输牌扣星：1-9 级新手保护，不扣星
            if orm.rank_id < 10:
                return
            if orm.rank_id >= 36:
                # 至尊段位输球扣星，但不降段
                orm.stars = max(0, orm.stars - 1)
                return
                
            orm.stars -= 1
            # 掉星降级
            if orm.stars < 0:
                if orm.sub_rank < 4:
                    orm.sub_rank += 1
                    orm.stars = max_stars - 1
                else:
                    # 子级别已到最低 (sub_rank == 4)
                    if orm.rank_id < 22:
                        # 10-21 级大段位保护，不降级
                        orm.stars = 0
                    else:
                        # 22-35 级无保护降大级
                        orm.rank_id -= 1
                        orm.sub_rank = 1
                        
                        # 降大级后的满星扣减
                        new_max = 3 if orm.rank_id < 10 else (4 if orm.rank_id < 22 else 5)
                        orm.stars = new_max - 1
```

2. 修改 `backend/app/interfaces/websocket/game_handler.py` 结算接口：
   在 `_on_game_over` 方法中（约行 278 附近）：
```python
                    repo.update_profile_stats(p.id, score_change, is_win)
                    repo.update_rank_stats(p.id, is_win, room.multiplier)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest tests/test_game_repository.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/infrastructure/database/game_repository.py backend/app/interfaces/websocket/game_handler.py backend/tests/test_game_repository.py
git commit -m "feat: implement settlement rank state machine and ws integration with tests"
```

---

### Task 3: 后端段位修改与获取 API 接口扩展

**Files:**
- Modify: `backend/tests/test_game_api.py`
- Modify: `backend/app/interfaces/api/game_routes.py`

**Interfaces:**
- Produces: `POST /api/game/profile/{player_id}/rank`

- [ ] **Step 1: Write the failing test**

在 `backend/tests/test_game_api.py` 末尾追加测试用例，校验排位设定 API 正常响应：

```python
def test_update_player_rank(mock_db):
    client = TestClient(app)
    with patch("app.interfaces.api.game_routes.SQLGameRepository") as mock_repo_class:
        mock_repo = MagicMock()
        mock_profile = MagicMock()
        mock_profile.rank_id = 35
        mock_profile.sub_rank = 4
        mock_profile.stars = 3
        mock_profile.rank_title = "亲王IV"
        mock_repo.get_or_create_profile.return_value = mock_profile
        mock_repo_class.return_value = mock_repo
        
        # 测试修改排位接口
        response = client.post("/api/game/profile/player123/rank", json={
            "rank_id": 35,
            "sub_rank": 4,
            "stars": 3
        })
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["rank_id"] == 35
        assert data["sub_rank"] == 4
        assert data["stars"] == 3
        mock_repo.update_rank_profile.assert_called_once_with("player123", 35, 4, 3)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest tests/test_game_api.py::test_update_player_rank -v`
Expected: FAIL (404 Not Found)

- [ ] **Step 3: Write minimal implementation**

1. 修改 `backend/app/interfaces/api/game_routes.py` 接口文件，增加 `UpdateRankRequest` 并在末尾加入段位修改接口路由，同时更新原有 `get_player_profile` / `get_leaderboard` 接口返回：
```python
# 定义请求结构
class UpdateRankRequest(BaseModel):
    rank_id: int = Field(..., ge=1, le=36, comment="头衔级别(1-36)")
    sub_rank: int = Field(..., ge=1, le=4, comment="小级别(1-4)")
    stars: int = Field(..., ge=0, comment="星星数")

# 更新 get_player_profile 接口返回，加入 rank 信息
@router.get("/profile/{player_id}")
def get_player_profile(player_id: str, db: Session = Depends(get_db)):
    repo = SQLGameRepository(db)
    profile = repo.get_or_create_profile(player_id, player_id)
    return {
        "player_id": profile.player_id,
        "nickname": profile.nickname,
        "beans": profile.beans,
        "total_games": profile.total_games,
        "wins": profile.wins,
        "win_rate": profile.win_rate,
        "rank_id": profile.rank_id,
        "sub_rank": profile.sub_rank,
        "stars": profile.stars,
        "rank_title": profile.rank_title
    }

# 更新 get_leaderboard 排行榜接口返回
@router.get("/leaderboard")
def get_leaderboard(limit: int = 20, db: Session = Depends(get_db)):
    repo = SQLGameRepository(db)
    profiles = repo.get_leaderboard(limit)
    return [{
        "rank": i + 1,
        "player_id": p.player_id,
        "nickname": p.nickname,
        "beans": p.beans,
        "total_games": p.total_games,
        "win_rate": p.win_rate,
        "rank_title": p.rank_title
    } for i, p in enumerate(profiles)]

# 在文件末尾增加新的 POST/rank 接口
@router.post("/profile/{player_id}/rank")
def update_player_rank(player_id: str, req: UpdateRankRequest, db: Session = Depends(get_db)):
    repo = SQLGameRepository(db)
    repo.get_or_create_profile(player_id, player_id)
    repo.update_rank_profile(player_id, req.rank_id, req.sub_rank, req.stars)
    updated_profile = repo.get_or_create_profile(player_id, player_id)
    return {
        "ok": True,
        "player_id": player_id,
        "rank_id": updated_profile.rank_id,
        "sub_rank": updated_profile.sub_rank,
        "stars": updated_profile.stars
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest tests/test_game_api.py::test_update_player_rank -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/interfaces/api/game_routes.py backend/tests/test_game_api.py
git commit -m "feat: add update rank API and expand rank profiles in responses"
```

---

### Task 4: 前端 Pinia Store 状态动作管理修改

**Files:**
- Modify: `frontend/src/stores/playerStore.ts`

**Interfaces:**
- Produces: `rankId`, `subRank`, `stars`, `rankTitle` state
- Produces: `modifyRank(rankId: number, subRank: number, stars: number) => Promise<{ ok: boolean; error?: string }>`

- [ ] **Step 1: Extend playerStore properties and actions**

修改 `frontend/src/stores/playerStore.ts`：
1. 扩充状态：
```typescript
  const rankId = ref(1)
  const subRank = ref(4)
  const stars = ref(0)
  const rankTitle = ref('包身工IV')
```
2. 扩充 `fetchProfile` 刷新同步：
```typescript
        beans.value = data.beans
        totalGames.value = data.total_games
        winRate.value = data.win_rate || 0
        rankId.value = data.rank_id || 1
        subRank.value = data.sub_rank || 4
        stars.value = data.stars || 0
        rankTitle.value = data.rank_title || '包身工IV'
```
3. 新增 `modifyRank` action：
```typescript
  async function modifyRank(rid: number, srank: number, starCount: number): Promise<{ ok: boolean; error?: string }> {
    try {
      const res = await fetch(`/api/game/profile/${playerId.value}/rank`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rank_id: rid, sub_rank: srank, stars: starCount })
      })
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}))
        return { ok: false, error: errData.detail || '修改排位失败' }
      }
      const data = await res.json()
      rankId.value = data.rank_id
      subRank.value = data.sub_rank
      stars.value = data.stars
      // 触发 profile 获取刷新称号
      await fetchProfile()
      return { ok: true }
    } catch (e: any) {
      return { ok: false, error: e.message || '网络连接失败' }
    }
  }
```
4. 在 return 导出全部新增属性及 `modifyRank`。

- [ ] **Step 2: Run type check to verify compilation**

Run: `npm run type-check` (在 `frontend` 文件夹下)
Expected: Compile successfully.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/stores/playerStore.ts
git commit -m "feat: extend playerStore to manage rank states and REST action"
```

---

### Task 5: 前端大厅 UI 段位罗马称号与自适应星条渲染

**Files:**
- Modify: `frontend/src/views/LobbyView.vue`

- [ ] **Step 1: Render dynamic titles and stars inside LobbyView**

修改 `frontend/src/views/LobbyView.vue`：
1. 在 `<script setup>` 中扩充头衔常量和计算属性：
```typescript
const RANK_NAMES = [
  "", "包身工", "短工", "长工", "中农", "富农", "掌柜", "商人", "小财主", "大财主",
  "县尉", "县丞", "县令", "通判", "主事", "知府", "员外郎", "郎中", "侍郎", "巡抚",
  "总督", "尚书", "大学士", "太保", "太傅", "太师", "三等伯", "二等伯", "一等伯",
  "三等侯", "二等侯", "一等侯", "辅国公", "镇国公", "郡王", "亲王", "至尊"
]

const showEditRankBlock = ref(false)
const inputRankId = ref(1)
const inputSubRank = ref(4)
const inputStars = ref(0)
const editRankError = ref('')

// 获取某段位的满星数
function getRankMaxStars(rid: number): number {
  if (rid < 10) return 3
  if (rid < 22) return 4
  return 5
}

function subRankRoman(srank: number, rid: number): string {
  if (rid >= 36) return ""
  const romans = ["", "I", "II", "III", "IV"]
  return romans[srank] || "IV"
}

// 拓展 openEditBeansModal 绑定段位初始输入值
function openEditBeansModal() {
  inputBeansValue.value = playerStore.beans
  editBeansError.value = ''
  
  // 段位初始化参数
  inputRankId.value = playerStore.rankId
  inputSubRank.value = playerStore.subRank
  inputStars.value = playerStore.stars
  editRankError.value = ''
  
  showEditBeansModal.value = true
}

// 拓展 handleSaveBeans 并入段位修改逻辑
async function handleSaveBeans() {
  if (inputBeansValue.value < 0) {
    editBeansError.value = '欢乐豆数量不能为负数！'
    return
  }
  
  // 1. 保存欢乐豆
  const resBeans = await playerStore.modifyBeans(inputBeansValue.value)
  if (!resBeans.ok) {
    editBeansError.value = resBeans.error || '保存欢乐豆失败'
    return
  }

  // 2. 保存段位等级
  const maxStars = getRankMaxStars(inputRankId.value)
  if (inputStars.value > maxStars && inputRankId.value < 36) {
    editRankError.value = `当前段位最高只能设定为 ${maxStars} 颗星！`
    return
  }
  
  const resRank = await playerStore.modifyRank(inputRankId.value, inputSubRank.value, inputStars.value)
  if (resRank.ok) {
    showEditBeansModal.value = false
    await loadLobbyData()
  } else {
    editRankError.value = resRank.error || '保存排位失败'
  }
}
```

2. 修改 HTML 模板大厅右下角个人资料头衔气泡（约行 280 附近）：
```html
            <div class="user-name-row">
              <span class="username truncate">{{ playerStore.nickname }}</span>
              <span class="title-badge" style="background: linear-gradient(135deg, #a6c0fe 0%, #f1a7f1 100%); color: #3e27brown;">
                {{ playerStore.rankTitle }}
              </span>
            </div>
            <!-- 星星等级动态自适应渲染 -->
            <div class="stars-row">
              <template v-if="playerStore.rankId < 36">
                <!-- 循环渲染满星长度 -->
                <span 
                  v-for="index in getRankMaxStars(playerStore.rankId)" 
                  :key="index" 
                  class="star" 
                  :class="{ active: index <= playerStore.stars }"
                >
                  ★
                </span>
                <span class="star-text">{{ playerStore.stars }}/{{ getRankMaxStars(playerStore.rankId) }}</span>
              </template>
              <template v-else>
                <!-- 至尊展示为总星星数 -->
                <span class="star active">★</span>
                <span class="star-text">至尊星星: {{ playerStore.stars }}</span>
              </template>
            </div>
```
   同样适配准备页面底部的个人信息字段星级展示。

3. 修改排行榜单中富豪榜的返回字段展示，把原本固定比例映射改为显示玩家对应的官衔头衔名 `item.rank_title`。

4. 拓展弹窗模态框 `edit-beans-modal` 增加段位手动设定表单：
```html
        <!-- 模态框主体并入排位表单 -->
        <div class="modal-body" style="display: flex; flex-direction: column; gap: 16px;">
          <!-- 欢乐豆输入 -->
          <div style="display: flex; flex-direction: column; gap: 8px;">
            <label style="color: #ccc; font-size: 0.9rem; text-align: left;">请输入新的欢乐豆数量：</label>
            <input
              v-model.number="inputBeansValue"
              type="number"
              min="0"
              style="background: rgba(0,0,0,0.5); border: 1.5px solid rgba(255,255,255,0.2); border-radius: 8px; padding: 10px; color: #fff; font-size: 1.2rem; font-weight: bold; width: 100%; box-sizing: border-box;"
            />
            <p v-if="editBeansError" style="color: #f44336; margin: 0; font-size: 0.85rem; text-align: left;">{{ editBeansError }}</p>
          </div>
          
          <hr style="border: 0; border-top: 1px solid rgba(255,255,255,0.15); margin: 8px 0;" />

          <!-- 段位设定 -->
          <div style="display: flex; flex-direction: column; gap: 12px;">
            <h4 style="color: #ffd700; margin: 0; text-align: left;">🏆 定制段位信息</h4>
            
            <div style="display: flex; flex-direction: column; gap: 6px;">
              <label style="color: #ccc; font-size: 0.85rem; text-align: left;">头衔名称：</label>
              <select 
                v-model="inputRankId" 
                style="background: rgba(0,0,0,0.8); border: 1.5px solid rgba(255,255,255,0.25); border-radius: 8px; padding: 10px; color: #fff; font-size: 1rem; width: 100%; box-sizing: border-box;"
              >
                <!-- 循环渲染 36 头衔 -->
                <option v-for="(name, idx) in RANK_NAMES" :key="idx" :value="idx" v-show="idx > 0">
                  {{ idx }}. {{ name }} (门槛: {{ getRankMaxStars(idx) }}星)
                </option>
              </select>
            </div>

            <div style="display: flex; gap: 12px;" v-show="inputRankId < 36">
              <div style="flex: 1; display: flex; flex-direction: column; gap: 6px;">
                <label style="color: #ccc; font-size: 0.85rem; text-align: left;">级别后缀：</label>
                <select 
                  v-model="inputSubRank" 
                  style="background: rgba(0,0,0,0.8); border: 1.5px solid rgba(255,255,255,0.25); border-radius: 8px; padding: 10px; color: #fff; font-size: 1rem; width: 100%;"
                >
                  <option :value="4">IV 级</option>
                  <option :value="3">III 级</option>
                  <option :value="2">II 级</option>
                  <option :value="1">I 级</option>
                </select>
              </div>
              <div style="flex: 1; display: flex; flex-direction: column; gap: 6px;">
                <label style="color: #ccc; font-size: 0.85rem; text-align: left;">当前星星：</label>
                <input 
                  v-model.number="inputStars" 
                  type="number" 
                  min="0" 
                  :max="getRankMaxStars(inputRankId)"
                  style="background: rgba(0,0,0,0.8); border: 1.5px solid rgba(255,255,255,0.25); border-radius: 8px; padding: 10px; color: #fff; font-size: 1rem; width: 100%; box-sizing: border-box;"
                />
              </div>
            </div>
            
            <!-- 至尊模式下只输入总星星 -->
            <div style="display: flex; flex-direction: column; gap: 6px;" v-show="inputRankId == 36">
              <label style="color: #ccc; font-size: 0.85rem; text-align: left;">至尊星星数：</label>
              <input 
                v-model.number="inputStars" 
                type="number" 
                min="0"
                style="background: rgba(0,0,0,0.8); border: 1.5px solid rgba(255,255,255,0.25); border-radius: 8px; padding: 10px; color: #fff; font-size: 1rem; width: 100%; box-sizing: border-box;"
              />
            </div>
            
            <p v-if="editRankError" style="color: #f44336; margin: 0; font-size: 0.85rem; text-align: left;">{{ editRankError }}</p>
          </div>
        </div>
```

- [ ] **Step 2: Run type check and verify compilation**

Run: `npm run type-check` (在 `frontend` 文件夹下)
Expected: Compile successfully, no type errors in LobbyView.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/LobbyView.vue
git commit -m "feat: complete interactive rank display and modifying UI in LobbyView"
```
