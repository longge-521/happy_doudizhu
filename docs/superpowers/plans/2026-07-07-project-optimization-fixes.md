# 项目优化修复实施计划

> **给后续智能体使用：** 实施本计划时按任务逐步执行。每个任务先复现问题或写失败测试，再做最小修改，最后运行对应验证命令。本文使用复选框跟踪进度。
> **提交约束：** 根据本仓库 `AGENTS.md`，用户人工确认完整无误前不得执行 `git commit`。本计划只要求查看 diff 和运行验证，不包含自动提交步骤。

**目标：** 先恢复前端测试与构建基线，再逐步处理匹配并发、头像上传安全和游戏链路可维护性问题。

**架构思路：** 第一批优化只处理证据明确、可独立验证、低风险的问题；每个任务都保持小范围改动。后端改动遵循现有 DDD 分层，不把 WebSocket、数据库、Redis 与领域规则混到一起新增抽象。

**技术栈：** 后端 FastAPI、SQLAlchemy、Redis、pytest；前端 Vue 3、TypeScript、Vite、Pinia、Vitest。

## 全局约束

- 禁止批量删除文件或目录，不使用 `del /s`、`rd /s`、`rmdir /s`、`Remove-Item -Recurse`、`rm -rf`。
- 后端命令必须使用 `D:\ProgramData\miniconda3\envs\hmp_ai\python.exe`，不得使用系统默认 Python。
- 文档和提交信息使用中文；本计划执行期间不自动提交。
- 当前仓库可能存在用户未提交改动，实施时不得还原、覆盖或清理非本次产生的变更。
- 每个任务按 `plan -> step -> check` 执行；修 bug 先复现或写失败测试，再修复。

## 当前证据

- 后端基线：`D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest tests/ -q --tb=short` 已观察到 `152 passed`。
- 前端单测：`npm.cmd run test:unit -- --run` 已观察到 1 个失败，失败点是 `frontend/src/stores/__tests__/playerStore.spec.ts` 仍期待旧头像接口 `/api/game/profile/{player_id}/avatar`，而当前实现 `modifyAvatar()` 已复用 `/api/game/profile/{player_id}/update`。
- 前端构建：`npm.cmd run build` 已观察到 `vue-tsc` 报错，位置是 `frontend/src/utils/cardUtils.ts` 第 765 行，`h[0]` 在 `noUncheckedIndexedAccess` 下可能为 `undefined`。
- 结构风险：`backend/app/infrastructure/redis_game_repository.py` 的 `pop_match_players()` 注释写“原子”，实现是循环 `lpop`，高并发下存在交错消费风险。
- 安全风险：`backend/app/interfaces/api/game_routes.py` 的头像上传只校验 `content_type.startswith("image/")`，并一次性读取文件内容，缺少大小上限、扩展名白名单和基础文件头校验。

## 本轮执行范围

1. 修复前端单测与类型检查，让 `test:unit` 和 `build` 重新通过。
2. 将 Redis 匹配队列的批量弹出改成单次 Redis 原子操作。
3. 收紧头像上传接口的文件大小和格式校验。

## 暂不执行范围

- 不在本轮拆分 `LobbyView.vue`、`GameRoomView.vue`、`DebugConsoleView.vue` 等大文件。
- 不在本轮重构 `game_handler.py` 和 `useGameWebSocket.ts` 的事件架构，只保留为后续专项。
- 不新增前端 UI 功能，不改游戏规则。

---

### Task 1：修复前端测试与构建基线

**文件：**

- 修改：`frontend/src/stores/__tests__/playerStore.spec.ts`
- 修改：`frontend/src/utils/cardUtils.ts`

**接口：**

- 消费：`usePlayerStore().modifyAvatar(newAvatarUrl)` 仍调用现有 `modifyProfile(nickname.value, newAvatarUrl)`。
- 产出：前端单测和构建命令恢复通过。

- [x] **Step 1：复现当前失败**

运行：

```powershell
cd frontend
npm.cmd run test:unit -- --run
npm.cmd run build
```

期望当前状态：

- `playerStore.spec.ts` 中 `updates avatarUrl through profile avatar api` 失败，实际请求为 `/api/game/profile/player123/update`。
- `vue-tsc` 报 `frontend/src/utils/cardUtils.ts` 第 765 行 `number | undefined` 不能传给 `number`。

- [x] **Step 2：修正头像测试的当前协议断言**

将 `frontend/src/stores/__tests__/playerStore.spec.ts` 中 `modifyAvatar()` 的断言改为当前实现实际协议：

```ts
expect(fetch).toHaveBeenCalledWith('/api/game/profile/player123/update', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    Authorization: 'Bearer token123',
  },
  body: JSON.stringify({
    nickname: 'TestNick',
    avatar_url: 'https://example.com/new-avatar.png',
  }),
})
```

- [x] **Step 3：修正 `cardUtils.ts` 的严格索引类型错误**

在炸弹去重判断中先取首牌并判空，保持运行时行为不变：

```ts
if (!hints.some((hint) => {
  const firstCard = hint[0]
  return hint.length === 4 && firstCard !== undefined && getCardRank(firstCard) === rank
})) {
  hints.push(bombCards)
}
```

- [x] **Step 4：验证前端基线**

运行：

```powershell
cd frontend
npm.cmd run test:unit -- --run
npm.cmd run build
```

期望：

- Vitest 全部通过。
- `npm.cmd run build` 退出码为 0，没有 TypeScript 错误。

---

### Task 2：让 Redis 匹配队列批量弹出成为真正原子操作

**文件：**

- 修改：`backend/tests/test_redis_game_repository.py`
- 修改：`backend/app/infrastructure/redis_game_repository.py`

**接口：**

- 消费：`RedisGameRepository.pop_match_players(count: int = 3, base_score: int = 10) -> List[str]`
- 产出：该方法仍返回玩家 ID 列表，但底层用单次 Redis 脚本完成 `LRANGE + LTRIM`。

- [x] **Step 1：写失败测试**

在 `backend/tests/test_redis_game_repository.py` 中增加测试，要求 `pop_match_players()` 使用 `eval` 一次性弹出指定底分队列：

```python
@pytest.mark.asyncio
async def test_pop_match_players_uses_single_atomic_eval(repo, mock_redis):
    mock_redis.eval = AsyncMock(return_value=[b"p1", b"p2", b"p3"])

    players = await repo.pop_match_players(3, base_score=80)

    assert players == ["p1", "p2", "p3"]
    mock_redis.eval.assert_called_once()
    args = mock_redis.eval.call_args.args
    assert args[1] == 1
    assert args[2] == "game:match_queue:80"
    assert args[3] == 3
```

- [x] **Step 2：确认测试失败**

运行：

```powershell
cd backend
D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest tests/test_redis_game_repository.py -q --tb=short
```

期望：新增测试失败，原因是当前实现未调用 `eval`。

- [x] **Step 3：实现最小修改**

在 `backend/app/infrastructure/redis_game_repository.py` 中增加 Lua 脚本常量：

```python
POP_MATCH_PLAYERS_SCRIPT = """
local count = tonumber(ARGV[1])
local players = redis.call('LRANGE', KEYS[1], 0, count - 1)
if #players > 0 then
    redis.call('LTRIM', KEYS[1], #players, -1)
end
return players
"""
```

并将 `pop_match_players()` 改为：

```python
async def pop_match_players(self, count: int = 3, base_score: int = 10) -> List[str]:
    key = self._get_queue_key(base_score)
    raw_players = await self._redis.eval(POP_MATCH_PLAYERS_SCRIPT, 1, key, count)
    players = []
    for pid in raw_players:
        if isinstance(pid, bytes):
            pid = pid.decode("utf-8")
        players.append(pid)
    return players
```

- [x] **Step 4：验证 Redis 仓储测试**

运行：

```powershell
cd backend
D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest tests/test_redis_game_repository.py -q --tb=short
```

期望：该测试文件全部通过。

- [x] **Step 5：验证后端全量测试**

运行：

```powershell
cd backend
D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest tests/ -q --tb=short
```

期望：后端测试全部通过。

---

### Task 3：收紧头像上传接口安全边界

**文件：**

- 修改：`backend/tests/test_profile_update.py`
- 修改：`backend/app/interfaces/api/game_routes.py`

**接口：**

- 消费：`POST /api/game/profile/{player_id}/upload-avatar`
- 产出：继续返回 `{ "ok": true, "avatar_url": "..." }`；非法文件返回 400。

- [x] **Step 1：补充失败测试**

在 `backend/tests/test_profile_update.py` 增加两个测试：

```python
def test_upload_player_avatar_rejects_oversized_file(mock_db):
    client = TestClient(app)
    token = create_game_auth_token("player123")
    oversized = io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"x" * (2 * 1024 * 1024 + 1))

    response = client.post(
        "/api/game/profile/player123/upload-avatar",
        files={"file": ("big.png", oversized, "image/png")},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    assert "头像文件不能超过" in response.json()["detail"]


def test_upload_player_avatar_rejects_fake_image_payload(mock_db):
    client = TestClient(app)
    token = create_game_auth_token("player123")
    fake_image = io.BytesIO(b"not-an-image")

    response = client.post(
        "/api/game/profile/player123/upload-avatar",
        files={"file": ("fake.png", fake_image, "image/png")},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "头像文件内容不是支持的图片格式"
```

- [x] **Step 2：确认测试失败**

运行：

```powershell
cd backend
D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest tests/test_profile_update.py -q --tb=short
```

期望：新增测试失败，原因是当前上传接口未限制文件大小，也未校验图片文件头。

- [x] **Step 3：实现最小安全校验**

在 `backend/app/interfaces/api/game_routes.py` 增加常量：

```python
AVATAR_MAX_BYTES = 2 * 1024 * 1024
AVATAR_ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
AVATAR_SIGNATURES = (
    b"\x89PNG\r\n\x1a\n",
    b"\xff\xd8\xff",
    b"GIF87a",
    b"GIF89a",
    b"RIFF",
)
```

在 `upload_player_avatar()` 中：

```python
file_ext = os.path.splitext(file.filename or "")[1].lower()
if file_ext not in AVATAR_ALLOWED_EXTENSIONS:
    raise HTTPException(status_code=400, detail="只允许上传 png、jpg、jpeg、gif 或 webp 头像")

content = await file.read(AVATAR_MAX_BYTES + 1)
if len(content) > AVATAR_MAX_BYTES:
    raise HTTPException(status_code=400, detail="头像文件不能超过 2MB")

if not content.startswith(AVATAR_SIGNATURES):
    raise HTTPException(status_code=400, detail="头像文件内容不是支持的图片格式")
```

保存时使用已读取的 `content`，避免再次读取空内容。

- [x] **Step 4：验证头像测试**

运行：

```powershell
cd backend
D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest tests/test_profile_update.py -q --tb=short
```

期望：该测试文件全部通过。

- [x] **Step 5：验证后端全量测试**

运行：

```powershell
cd backend
D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest tests/ -q --tb=short
```

期望：后端测试全部通过。

---

### Task 4：后续专项设计，不在本轮直接改代码

**文件：**

- 只读评估：`backend/app/interfaces/websocket/game_handler.py`
- 只读评估：`frontend/src/composables/useGameWebSocket.ts`
- 只读评估：`frontend/src/views/LobbyView.vue`
- 只读评估：`frontend/src/views/GameRoomView.vue`

**目标：**

- 后续单独写设计文档，把 WebSocket 事件分发、AI 自动回合、结算入库、前端音效特效副作用拆成更清晰的边界。
- 后续大页面拆分必须结合具体功能改动进行，不做纯粹“为了拆而拆”的重构。

**当前处理：**

- 本轮只记录风险，不改这些文件。

## 最终验证矩阵

完成 Task 1 后运行：

```powershell
cd frontend
npm.cmd run test:unit -- --run
npm.cmd run build
```

完成 Task 2 或 Task 3 后运行：

```powershell
cd backend
D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest tests/ -q --tb=short
```

全部任务完成后运行：

```powershell
cd frontend
npm.cmd run test:unit -- --run
npm.cmd run build
cd ..\backend
D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest tests/ -q --tb=short
```

## 自查结果

- 本计划没有占位项或未决项。
- 每个进入本轮执行范围的问题都有已观察证据、修改文件和验证命令。
- WebSocket 架构拆分与大页面拆分已明确延后，避免把本轮修复扩大成高风险重构。
