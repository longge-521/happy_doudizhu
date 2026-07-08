# 地主流程优化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将斗地主对局流程从 `CALLING → LANDLORD_CONFIRM → DOUBLING → PLAYING` 调整为 `CALLING → DOUBLING → LANDLORD_CONFIRM(条件) → PLAYING`，对齐腾讯欢乐斗地主经典版。

**Architecture:** 后端状态机中 `_set_landlord()` 一律进入 `DOUBLING`，`_finish_doubling()` 根据地主是否已明牌决定进入 `LANDLORD_CONFIRM` 或 `PLAYING`。前端 `LANDLORD_CONFIRM` 阶段 UI 从"📢 明牌 ×2 / 不明牌"调整为"明牌 / 出牌"（蓝色/橙色按钮对，参考腾讯经典版截图 3）。

**Tech Stack:** Python/FastAPI (后端), Vue 3/TypeScript/Pinia (前端)

## Global Constraints

- Python 环境必须使用 `D:\ProgramData\miniconda3\envs\hmp_ai\python.exe`
- 所有 git commit 信息必须使用中文，且必须由用户确认后方可提交
- 不得批量删除文件
- 遵守 DDD 分层约定

---

### Task 1: 后端 `_set_landlord()` — 一律进入 DOUBLING

**Files:**
- Modify: `backend/app/domain/game/room.py:271-304`
- Test: `backend/tests/test_room.py`

**Interfaces:**
- Produces: `_set_landlord(player_id)` 返回 dict，阶段一律为 `DOUBLING`，不再有 `skip_confirm` 字段

- [ ] **Step 1: 修改 `_set_landlord()` 方法**

将 L271-304 的整个方法替换为统一逻辑（删除 `if player_id in self.show_cards_players` 条件分支）：

```python
def _set_landlord(self, player_id: str) -> dict:
    """确定地主，分配底牌，进入加倍阶段"""
    self.landlord = player_id
    self.hands[player_id] = sort_cards(self.hands[player_id] + self.bottom_cards)
    # 一律进入加倍阶段（无论地主是否已在发牌时明牌）
    self.phase = GamePhase.DOUBLING
    self.current_turn = None
    self.turn_deadline = time.time() + 15
    self.last_play = LastPlay()
    self.pass_count = 0
    self.doubling_choices = {}
    return {
        "success": True,
        "landlord": player_id,
        "bottom_cards": self.bottom_cards,
        "multiplier": self.multiplier,
    }
```

- [ ] **Step 2: 运行测试确认影响范围**

Run: `D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest tests/test_room.py -x -q --tb=short`

Expected: 可能有断言失败（旧测试假定 `LANDLORD_CONFIRM` 在 `DOUBLING` 之前），记录需要修复的测试。

---

### Task 2: 后端 `_finish_doubling()` — 条件进入 LANDLORD_CONFIRM 或 PLAYING

**Files:**
- Modify: `backend/app/domain/game/room.py:333-342`

**Interfaces:**
- Consumes: `self.show_cards_players`（发牌阶段明牌记录）
- Produces: `_finish_doubling()` 返回 dict，新增 `landlord_confirm_required` 布尔字段

- [ ] **Step 1: 修改 `_finish_doubling()` 方法**

将 L333-342 的方法替换为：

```python
def _finish_doubling(self) -> dict:
    """所有玩家完成加倍确认后，决定下一阶段"""
    if self.landlord in self.show_cards_players:
        # 地主在发牌时已明牌，直接进入出牌阶段
        self.phase = GamePhase.PLAYING
        self.current_turn = self.landlord
        self.turn_deadline = time.time() + 30
        return {
            "doubling_finished": True,
            "next_turn": self.current_turn,
            "multiplier": self.multiplier,
        }
    else:
        # 地主未明牌，进入"明牌或出牌"决策阶段
        self.phase = GamePhase.LANDLORD_CONFIRM
        self.current_turn = self.landlord
        self.turn_deadline = time.time() + 30
        return {
            "doubling_finished": True,
            "landlord_confirm_required": True,
            "next_turn": self.current_turn,
            "multiplier": self.multiplier,
        }
```

- [ ] **Step 2: 运行测试**

Run: `D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest tests/test_room.py -x -q --tb=short`

---

### Task 3: 后端 `landlord_show_cards()` 和 `finish_landlord_confirm()` — 出口改为 PLAYING

**Files:**
- Modify: `backend/app/domain/game/room.py` — `landlord_show_cards()` 和 `finish_landlord_confirm()` 方法

**Interfaces:**
- Produces: 两个方法结束后阶段均为 `PLAYING`，`current_turn = self.landlord`

- [ ] **Step 1: 修改 `landlord_show_cards()` 方法**

在 `self.multiplier *= 2` 之后，将阶段设置为 `PLAYING`（而不是当前可能的其他状态），并设置 `current_turn` 和 `turn_deadline`：

```python
# 明牌后直接进入出牌阶段
self.phase = GamePhase.PLAYING
self.current_turn = self.landlord
self.turn_deadline = time.time() + 30
```

- [ ] **Step 2: 修改 `finish_landlord_confirm()` 方法**

将方法修改为进入 `PLAYING` 阶段：

```python
def finish_landlord_confirm(self) -> dict:
    """地主选择出牌（不明牌），进入出牌阶段"""
    if self.phase != GamePhase.LANDLORD_CONFIRM:
        return {"success": False, "error": "当前不在明牌选择阶段"}
    self.phase = GamePhase.PLAYING
    self.current_turn = self.landlord
    self.turn_deadline = time.time() + 30
    return {
        "success": True,
        "multiplier": self.multiplier,
    }
```

- [ ] **Step 3: 运行测试**

Run: `D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest tests/test_room.py -x -q --tb=short`

---

### Task 4: 修复后端单元测试适配新流程

**Files:**
- Modify: `backend/tests/test_room.py`

**Interfaces:**
- Consumes: Task 1-3 产出的新状态机流转

- [ ] **Step 1: 修复所有叫地主流转测试中的断言**

旧测试中，叫地主后期望进入 `LANDLORD_CONFIRM`（在 `DOUBLING` 之前）的断言需要改为期望直接进入 `DOUBLING`。

具体修复：将所有 `assert room.phase == GamePhase.LANDLORD_CONFIRM`（在叫地主完成后的断言）改为 `assert room.phase == GamePhase.DOUBLING`。

- [ ] **Step 2: 修复加倍结束后的断言**

对于"地主未明牌"的场景，加倍结束后应进入 `LANDLORD_CONFIRM`（而非 `PLAYING`）。对于"地主已明牌"的场景，加倍结束后应直接进入 `PLAYING`。

- [ ] **Step 3: 更新 `test_landlord_already_shown_cards_skips_confirm` 测试**

该测试需要验证新流程：发牌时明牌 → 叫地主 → `DOUBLING` → 加倍完成 → 直接进入 `PLAYING`（跳过 `LANDLORD_CONFIRM`）。

- [ ] **Step 4: 运行全量测试确认全部通过**

Run: `D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest tests/ -x -q --tb=short`

Expected: 全部 PASS

---

### Task 5: 后端 `game_handler.py` — AI 处理顺序调整

**Files:**
- Modify: `backend/app/interfaces/websocket/game_handler.py:412-461` (LANDLORD_CONFIRM 块) 和 L463-509 (DOUBLING 块)，以及 L500-508 (doubling_finished 广播)

**Interfaces:**
- Consumes: Task 2 产出的 `_finish_doubling()` 新返回值（`landlord_confirm_required`）

- [ ] **Step 1: 调整 `_do_process_ai_turns` 中的阶段处理顺序**

将当前的代码顺序：
```
0. LANDLORD_CONFIRM
1. DOUBLING
2. CALLING / PLAYING
```

调整为：
```
0. DOUBLING
1. LANDLORD_CONFIRM
2. CALLING / PLAYING
```

即将 L416-461 的 LANDLORD_CONFIRM 块移到 L463-509 的 DOUBLING 块之后。

- [ ] **Step 2: 修改 DOUBLING 完成后的广播和流转**

在 DOUBLING 阶段处理完毕后（L500-508），当 `result.get("doubling_finished")` 为 True 时：
- 广播 `doubling_finished` 事件时，附带 `landlord_confirm_required` 字段。
- 如果 `result.get("landlord_confirm_required")` 为 True，则阶段已切换为 `LANDLORD_CONFIRM`，需要继续调用 `_do_process_ai_turns(room)` 处理 AI 地主的明牌决策。
- 如果为 False（地主已明牌），阶段已切换为 `PLAYING`，继续调用 `_do_process_ai_turns(room)` 处理 AI 出牌。

```python
if result.get("doubling_finished"):
    logger.info(f"游戏WS [room={room.room_id}]: 加倍确认完毕")
    event_data = {
        "event": "doubling_finished",
        "current_turn": result.get("next_turn"),
        "multiplier": result.get("multiplier", room.multiplier),
    }
    if result.get("landlord_confirm_required"):
        event_data["landlord_confirm_required"] = True
    await self._broadcast_room_event(room, event_data)
    # 继续处理后续阶段（LANDLORD_CONFIRM 或 PLAYING）
    await self._do_process_ai_turns(room)
```

- [ ] **Step 3: 修改 LANDLORD_CONFIRM 块中的注释和后续流转**

将 L459 的注释"继续处理后续阶段（DOUBLING）"改为"继续处理后续阶段（PLAYING）"。因为现在 `LANDLORD_CONFIRM` 之后是 `PLAYING`。

- [ ] **Step 4: 运行全量后端测试**

Run: `D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest tests/ -x -q --tb=short`

Expected: 全部 PASS

---

### Task 6: 前端 `GameRoomView.vue` — LANDLORD_CONFIRM 阶段 UI 调整

**Files:**
- Modify: `frontend/src/views/GameRoomView.vue:744-764` (LANDLORD_CONFIRM 面板)

**Interfaces:**
- Consumes: `gameStore.gamePhase === 'LANDLORD_CONFIRM'`, `gameStore.landlord`, `playerStore.playerId`

- [ ] **Step 1: 修改地主视角的按钮文案和样式**

将 L749-763 的按钮从当前的"📢 明牌 ×2 / 不明牌"改为腾讯经典版风格的"明牌 / 出牌"：

```html
<div v-if="gameStore.landlord === playerStore.playerId" class="actions-group">
  <button
    class="btn-action-call"
    style="background: linear-gradient(135deg, #42a5f5 0%, #1565c0 100%); border-color: #90caf9;"
    @click="handleLandlordShow(true)"
  >
    明 牌
  </button>

  <!-- 倒计时闹钟 -->
  <div class="turn-alarm-clock">
    <div class="clock-icon">⏰</div>
    <span class="time-left-digits">{{ timeLeft }}</span>
  </div>

  <button
    class="btn-action-call"
    style="background: linear-gradient(135deg, #ff7043 0%, #d84315 100%); border-color: #ffab91;"
    @click="handleLandlordShow(false)"
  >
    出 牌
  </button>
</div>
<div v-else class="waiting-hint-text">
  等待地主 ({{ getLandlordNickname() }}) 选择...
</div>
```

关键变化：
- "📢 明牌 ×2" → "明 牌"（蓝色按钮，渐变从 #42a5f5 到 #1565c0）
- "不明牌" → "出 牌"（橙色按钮，渐变从 #ff7043 到 #d84315）
- 倒计时闹钟移至两个按钮中间
- 等待提示文案简化

- [ ] **Step 2: 修改超时处理文案**

L334 附近的超时处理中，提示文案从"未明牌"相关改为"出牌"相关（如果有自动超时逻辑的话）。

- [ ] **Step 3: 运行前端构建验证**

Run: `cd frontend && npm run build`

Expected: 编译成功

---

### Task 7: 前端 `useGameWebSocket.ts` — 适配 doubling_finished 事件的新字段

**Files:**
- Modify: `frontend/src/composables/useGameWebSocket.ts`

**Interfaces:**
- Consumes: 服务端推送的 `doubling_finished` 事件（新增 `landlord_confirm_required` 字段）

- [ ] **Step 1: 搜索 `doubling_finished` 事件处理逻辑**

在 `useGameWebSocket.ts` 中搜索 `doubling_finished` 事件的处理代码，确认当前的处理方式。

- [ ] **Step 2: 添加对 `landlord_confirm_required` 的处理**

当收到 `doubling_finished` 事件时，如果 `data.landlord_confirm_required` 为 true，则将 `gameStore.gamePhase` 设为 `'LANDLORD_CONFIRM'`，并设置 `gameStore.awaitingLandlordShow = true`。

- [ ] **Step 3: 运行前端构建验证**

Run: `cd frontend && npm run build`

Expected: 编译成功

---

### Task 8: 全量验证

**Files:**
- 无新增文件

- [ ] **Step 1: 运行后端全量测试**

Run: `D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest tests/ -v`

Expected: 全部 PASS

- [ ] **Step 2: 运行前端构建**

Run: `cd frontend && npm run build`

Expected: 编译成功，无类型错误

- [ ] **Step 3: 列出需要手动测试的功能点**

手动验证清单：
1. 发牌时不明牌 → 叫地主 → 加倍（测试"加倍/超级加倍/不加倍"三个按钮） → 看到 `[ 明牌 ]` / `[ 出牌 ]` 按钮 → 正常出牌
2. 发牌时明牌 → 叫地主 → 加倍 → 直接进入出牌（无明牌选择界面）
3. AI 对局中整条流程顺畅无卡顿
4. 超时后自动不明牌并进入出牌阶段
