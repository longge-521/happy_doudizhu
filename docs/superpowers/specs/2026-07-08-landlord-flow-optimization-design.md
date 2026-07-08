# 地主流程优化设计规格（对齐腾讯欢乐斗地主经典版）

> 日期：2026-07-08
> 状态：待审阅

## 背景

当前项目在确定地主后的流程为：`CALLING → LANDLORD_CONFIRM → DOUBLING → PLAYING`。地主在加倍之前需要先决定是否明牌，此时农民被阻塞等待，体验不佳。

腾讯欢乐斗地主经典版的流程为四步：
1. **叫地主** — 竞叫决定地主
2. **加倍** — 全场同时选择加倍/超级加倍/不加倍
3. **明牌或出牌**（条件性） — 地主决定是否明牌，如果发牌时已明牌则跳过
4. **出牌** — 正常出牌对战

本次优化的目标是将项目流程调整为与腾讯经典版一致。

## 核心变更：状态机流转顺序

```
当前：CALLING → LANDLORD_CONFIRM → DOUBLING → PLAYING
目标：CALLING → DOUBLING → LANDLORD_CONFIRM(条件) → PLAYING
```

`LANDLORD_CONFIRM` 阶段从"加倍之前"移至"加倍之后、出牌之前"。

## 详细设计

### 1. 后端领域层 (`room.py`)

#### 1.1 `_set_landlord()` 方法

**变更**：无论地主是否在发牌时已明牌，`_set_landlord()` 一律将阶段设置为 `DOUBLING`。删除当前的条件分支（当前逻辑是：已明牌 → `DOUBLING`，未明牌 → `LANDLORD_CONFIRM`）。

```python
def _set_landlord(self, player_id: str) -> dict:
    """确定地主，分配底牌，进入加倍阶段"""
    self.landlord = player_id
    self.hands[player_id] = sort_cards(self.hands[player_id] + self.bottom_cards)
    # 一律进入加倍阶段
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

#### 1.2 `_finish_doubling()` 方法

**变更**：加倍结束后，检查地主是否在发牌时已明牌：
- **已明牌** → 直接进入 `PLAYING`，地主首回合出牌。
- **未明牌** → 进入 `LANDLORD_CONFIRM`，等待地主选择"明牌"或"出牌"。

```python
def _finish_doubling(self) -> dict:
    """所有玩家完成加倍确认后，决定下一阶段"""
    if self.landlord in self.show_cards_players:
        # 地主发牌时已明牌，直接进入出牌阶段
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

#### 1.3 `landlord_show_cards()` 方法

地主选择明牌后直接进入 `PLAYING` 阶段（而非当前的进入 `DOUBLING`）。

```python
def landlord_show_cards(self, player_id: str) -> dict:
    """地主选择明牌（倍数 ×2），然后进入出牌阶段"""
    if self.phase != GamePhase.LANDLORD_CONFIRM:
        return {"success": False, "error": "当前不在明牌选择阶段"}
    if player_id != self.landlord:
        return {"success": False, "error": "只有地主可以在此阶段明牌"}
    if player_id in self.show_cards_players:
        return {"success": False, "error": "你已经明牌了"}

    self.show_cards_players[player_id] = 2
    self.multiplier *= 2

    # 明牌后直接进入出牌阶段
    self.phase = GamePhase.PLAYING
    self.current_turn = self.landlord
    self.turn_deadline = time.time() + 30

    return {
        "success": True,
        "player_id": player_id,
        "cards": self.hands[player_id],
        "show_multiplier": 2,
        "total_multiplier": self.multiplier,
    }
```

#### 1.4 `finish_landlord_confirm()` 方法

地主选择"出牌"（不明牌）后直接进入 `PLAYING` 阶段。

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

### 2. 后端应用层 (`game_app_service.py`)

#### 2.1 `handle_landlord_show()` 方法

适配新流程。当 `show=True` 时调用 `landlord_show_cards()`，当 `show=False` 时调用 `finish_landlord_confirm()`。两种情况下阶段都会推进到 `PLAYING`。

#### 2.2 AI 处理顺序调整

`handle_ai_turn()` 中的阶段处理顺序调整为：
1. `CALLING` → AI 叫地主/抢地主
2. `DOUBLING` → AI 选择加倍/不加倍
3. `LANDLORD_CONFIRM` → AI 地主决定是否明牌（沿用 `_should_ai_show_cards` 评估）
4. `PLAYING` → AI 出牌

### 3. 后端接口层 (`game_handler.py`)

#### 3.1 事件分发

- `landlord_show` 动作处理不变，但返回的房间状态阶段为 `PLAYING`（而非 `DOUBLING`）。
- AI 处理器 `_do_process_ai_turns` 中的阶段判断顺序调整：先处理 `CALLING`，再处理 `DOUBLING`，再处理 `LANDLORD_CONFIRM`，最后处理 `PLAYING`。

#### 3.2 加倍完成后的广播

当 `_finish_doubling()` 返回 `landlord_confirm_required=True` 时，服务端广播 `doubling_finished` 事件，携带 `landlord_confirm_required` 标志，通知前端进入"明牌或出牌"阶段。

### 4. 前端状态管理 (`gameStore.ts`)

`LANDLORD_CONFIRM` 阶段语义不变。前端在收到包含 `landlord_confirm_required: true` 的 `doubling_finished` 事件时，将 `gamePhase` 设为 `LANDLORD_CONFIRM`，触发新的 UI 渲染。

### 5. 前端 UI (`GameRoomView.vue`)

#### 5.1 加倍阶段按钮（第 2 步）

加倍面板中增加**"超级加倍"**按钮，按钮排列为：

```
[ 加倍 ]  [ 超级加倍 ]  [ 不加倍 ]
```

后端 `choose_double()` 方法已支持 `"super"` 选项（倍数 ×4），前端仅需新增按钮并发送 `choice: "super"`。

#### 5.2 明牌或出牌阶段（第 3 步）

当 `gamePhase === 'LANDLORD_CONFIRM'` 时：

**地主视角**：
- 显示两个按钮：`[ 明牌 ]`（蓝色）和 `[ 出牌 ]`（橙色），中间显示倒计时时钟。
- 点击 `[ 明牌 ]` → 发送 `landlord_show` 动作（`show: true`）。
- 点击 `[ 出牌 ]` → 发送 `landlord_show` 动作（`show: false`）。
- 超时 → 自动发送 `show: false`（不明牌，直接出牌）。

**非地主视角**：
- 显示"等待地主选择..."的等待提示。

#### 5.3 出牌阶段（第 4 步）

正常出牌操作栏，与现有实现一致：`[ 不出 ]` / `[ 提示 ]` / `[ 出牌 ]`。无需变更。

### 6. 前端 WebSocket (`useGameWebSocket.ts`)

- 适配 `doubling_finished` 事件中新增的 `landlord_confirm_required` 标志。
- 适配 `landlord_show_decided` 事件返回的新阶段（`PLAYING` 而非 `DOUBLING`）。

### 7. 音效

明牌音效和语音沿用已实现的合成和弦与 TTS 降级方案，不需要变更。

## 测试计划

### 自动化测试

```powershell
cd backend
D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest tests/ -x -q --tb=short
```

需要验证的核心场景：
1. 叫地主后直接进入 `DOUBLING`（无论是否已明牌）。
2. 加倍结束后，若地主未明牌，进入 `LANDLORD_CONFIRM`。
3. 加倍结束后，若地主已明牌，直接进入 `PLAYING`。
4. `LANDLORD_CONFIRM` 阶段地主选择明牌后，倍数 ×2 并进入 `PLAYING`。
5. `LANDLORD_CONFIRM` 阶段地主选择出牌后，直接进入 `PLAYING`。
6. 超时后默认不明牌并进入 `PLAYING`。
7. AI 地主在 `LANDLORD_CONFIRM` 阶段的明牌决策正常执行。

### 前端编译验证

```powershell
cd frontend
npm run build
```

### 手动验证

1. 发牌时不明牌 → 叫地主 → 加倍 → 看到 `[ 明牌 ]` / `[ 出牌 ]` 按钮 → 出牌。
2. 发牌时明牌 → 叫地主 → 加倍 → 直接进入出牌（无明牌选择界面）。
3. 加倍面板中"超级加倍"按钮正常工作。
4. AI 对局中流程顺畅无卡顿。
