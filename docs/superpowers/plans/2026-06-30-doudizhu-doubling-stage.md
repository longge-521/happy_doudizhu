# 斗地主正式加倍阶段 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将“确定地主后每人确认加倍”从前端模拟改成服务端正式流程，支持加倍、超级加倍、不加倍、出牌区展示、语音、重连和结算倍数一致。

**Architecture:** 后端 `GameRoom` 新增 `DOUBLING` 阶段作为唯一事实来源，WebSocket 负责广播选择与阶段结束事件，前端 `gameStore` 同步服务端 `doubling_choices` 并驱动按钮、出牌区展示和语音。保留现有大文件结构，不做无关拆分。

**Tech Stack:** Python 3 + pytest + FastAPI WebSocket；Vue 3 + TypeScript + Pinia + Vitest；Redis 房间序列化沿用现有 `GameRoom.to_dict()` / `from_dict()`。

## Global Constraints

- 禁止批量删除文件或目录。
- 文档使用中文。
- 只改必须改的地方，不做无关重构。
- 修 bug 和行为变更先写可失败测试，再做实现。
- 不调整叫地主/抢地主规则。
- 不新增欢乐豆准入或扣费规则。
- 不改变炸弹、王炸导致的后续翻倍规则。

---

## File Structure

- Modify: `backend/app/domain/game/room.py`
  - 新增 `GamePhase.DOUBLING`、`doubling_choices`、`choose_double()`、`_finish_doubling()`。
  - 负责加倍阶段规则、倍数计算、序列化、玩家视图。
- Modify: `backend/app/application/game/game_app_service.py`
  - 新增 `handle_double_choice()`。
  - 在 AI 流程中处理 `DOUBLING` 阶段。
- Modify: `backend/app/interfaces/websocket/game_handler.py`
  - 新增 `choose_double` action。
  - 广播 `double_chosen` 与 `doubling_finished`。
  - 让 `_process_ai_turns()` 支持 `DOUBLING`。
- Modify: `backend/tests/test_room.py`
  - 覆盖领域规则、序列化、出牌阻断。
- Modify: `frontend/src/stores/gameStore.ts`
  - 新增 `doublingChoices` 状态。
- Modify: `frontend/src/composables/useGameWebSocket.ts`
  - 处理 `landlord_decided`、`double_chosen`、`doubling_finished`。
- Modify: `frontend/src/composables/__tests__/useGameWebSocket.spec.ts`
  - 覆盖前端事件同步与语音触发。
- Modify: `frontend/src/views/GameRoomView.vue`
  - 移除本地模拟加倍状态。
  - 发送真实 `choose_double`。
  - `DOUBLING` 阶段超时自动不加倍。

---

### Task 1: 后端领域层正式加倍阶段

**Files:**
- Modify: `backend/app/domain/game/room.py`
- Test: `backend/tests/test_room.py`

**Interfaces:**
- Produces: `GamePhase.DOUBLING`
- Produces: `GameRoom.doubling_choices: Dict[str, str]`
- Produces: `GameRoom.choose_double(player_id: str, choice: str) -> dict`
- Produces: `GameRoom.get_player_view(player_id)["doubling_choices"]`

- [ ] **Step 1: 写失败测试：地主确定后进入 DOUBLING**

在 `backend/tests/test_room.py` 的 `TestGameRoom` 中新增：

```python
    def test_landlord_decided_enters_doubling_phase(self):
        room = GameRoom.create("room_1", make_players())
        room.deal()
        caller = room.current_turn

        result = room.call_landlord(caller, 3)

        assert result["success"] is True
        assert room.phase == GamePhase.DOUBLING
        assert room.landlord == caller
        assert room.current_turn is None
        assert room.doubling_choices == {}
        assert len(room.hands[caller]) == 20
```

- [ ] **Step 2: 运行失败测试**

Run: `python -m pytest backend/tests/test_room.py::TestGameRoom::test_landlord_decided_enters_doubling_phase -v`

Expected: FAIL，原因是 `GamePhase.DOUBLING` 不存在或地主确定后仍是 `PLAYING`。

- [ ] **Step 3: 写最小实现让地主确定进入 DOUBLING**

在 `backend/app/domain/game/room.py` 中：

```python
class GamePhase(Enum):
    MATCHING = "MATCHING"
    DEALING = "DEALING"
    CALLING = "CALLING"
    DOUBLING = "DOUBLING"
    PLAYING = "PLAYING"
    SETTLING = "SETTLING"
```

在 `__init__()` 中增加：

```python
        self.doubling_choices: Dict[str, str] = {}
```

在 `deal()` 中重置：

```python
        self.doubling_choices = {}
```

修改 `_set_landlord()`：

```python
    def _set_landlord(self, player_id: str) -> dict:
        """确定地主，分配底牌，进入加倍确认阶段"""
        self.landlord = player_id
        self.hands[player_id] = sort_cards(self.hands[player_id] + self.bottom_cards)
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

- [ ] **Step 4: 运行测试转绿**

Run: `python -m pytest backend/tests/test_room.py::TestGameRoom::test_landlord_decided_enters_doubling_phase -v`

Expected: PASS。

- [ ] **Step 5: 写失败测试：加倍选择规则、完成后地主先出**

新增：

```python
    def test_double_choices_update_multiplier_and_finish_to_playing(self):
        room = GameRoom.create("room_1", make_players())
        room.deal()
        ids = [p.id for p in room.players]
        room._first_caller_index = 0
        room._call_index = 0
        room.current_turn = ids[0]
        room.call_landlord(ids[0], 3)

        first = room.choose_double(ids[0], "double")
        second = room.choose_double(ids[1], "super")
        third = room.choose_double(ids[2], "none")

        assert first["success"] is True
        assert second["success"] is True
        assert third["success"] is True
        assert third["doubling_finished"] is True
        assert room.doubling_choices == {
            ids[0]: "double",
            ids[1]: "super",
            ids[2]: "none",
        }
        assert room.multiplier == 24
        assert room.phase == GamePhase.PLAYING
        assert room.current_turn == ids[0]

    def test_cannot_play_before_all_players_choose_double(self):
        room = GameRoom.create("room_1", make_players())
        room.deal()
        caller = room.current_turn
        room.call_landlord(caller, 3)

        result = room.play_cards(caller, [room.hands[caller][0]])

        assert result["success"] is False
        assert "出牌" in result["error"] or "阶段" in result["error"]

    def test_cannot_choose_double_twice_or_with_invalid_choice(self):
        room = GameRoom.create("room_1", make_players())
        room.deal()
        caller = room.current_turn
        room.call_landlord(caller, 3)

        first = room.choose_double(caller, "double")
        repeat = room.choose_double(caller, "none")
        invalid = room.choose_double(room.current_turn or caller, "bad")

        assert first["success"] is True
        assert repeat["success"] is False
        assert invalid["success"] is False
```

- [ ] **Step 6: 运行失败测试**

Run: `python -m pytest backend/tests/test_room.py::TestGameRoom::test_double_choices_update_multiplier_and_finish_to_playing backend/tests/test_room.py::TestGameRoom::test_cannot_play_before_all_players_choose_double backend/tests/test_room.py::TestGameRoom::test_cannot_choose_double_twice_or_with_invalid_choice -v`

Expected: FAIL，原因是 `choose_double()` 不存在。

- [ ] **Step 7: 实现 `choose_double()` 和 `_finish_doubling()`**

在 `GameRoom` 中加入：

```python
    def choose_double(self, player_id: str, choice: str) -> dict:
        """玩家确认加倍选择"""
        if self.phase != GamePhase.DOUBLING:
            return {"success": False, "error": "当前不在加倍确认阶段"}
        if player_id not in self._player_ids():
            return {"success": False, "error": "玩家不在当前房间"}
        if player_id in self.doubling_choices:
            return {"success": False, "error": "你已经选择过加倍"}
        if choice not in ("double", "super", "none"):
            return {"success": False, "error": "无效的加倍选择"}

        self.doubling_choices[player_id] = choice
        if choice == "double":
            self.multiplier *= 2
        elif choice == "super":
            self.multiplier *= 4

        result = {
            "success": True,
            "player": player_id,
            "choice": choice,
            "multiplier": self.multiplier,
        }
        if len(self.doubling_choices) >= len(self.players):
            result.update(self._finish_doubling())
        return result

    def _finish_doubling(self) -> dict:
        """所有玩家完成加倍确认后，进入出牌阶段"""
        self.phase = GamePhase.PLAYING
        self.current_turn = self.landlord
        self.turn_deadline = time.time() + 15
        return {
            "doubling_finished": True,
            "next_turn": self.current_turn,
            "multiplier": self.multiplier,
        }
```

- [ ] **Step 8: 运行领域测试**

Run: `python -m pytest backend/tests/test_room.py -v`

Expected: 本文件通过。若旧测试仍断言地主确定后立刻 `PLAYING`，更新旧断言为先 `DOUBLING`，再通过三人 `none` 进入 `PLAYING`。

- [ ] **Step 9: 写失败测试：序列化和玩家视图保留选择**

新增：

```python
    def test_doubling_choices_are_serialized_and_visible(self):
        room = GameRoom.create("room_1", make_players())
        room.deal()
        ids = [p.id for p in room.players]
        room._first_caller_index = 0
        room._call_index = 0
        room.current_turn = ids[0]
        room.call_landlord(ids[0], 3)
        room.choose_double(ids[0], "double")

        restored = GameRoom.from_dict(room.to_dict())
        view = restored.get_player_view(ids[1])

        assert restored.doubling_choices == {ids[0]: "double"}
        assert view["doubling_choices"] == {ids[0]: "double"}
```

- [ ] **Step 10: 运行失败测试**

Run: `python -m pytest backend/tests/test_room.py::TestGameRoom::test_doubling_choices_are_serialized_and_visible -v`

Expected: FAIL，原因是序列化或视图没有 `doubling_choices`。

- [ ] **Step 11: 实现序列化和视图字段**

在 `to_dict()` 返回值中增加：

```python
            "doubling_choices": self.doubling_choices,
```

在 `from_dict()` 中增加：

```python
        room.doubling_choices = data.get("doubling_choices", {})
```

在 `get_player_view()` 的 `view` 中增加：

```python
            "doubling_choices": dict(self.doubling_choices),
```

- [ ] **Step 12: 运行后端领域测试**

Run: `python -m pytest backend/tests/test_room.py -v`

Expected: PASS。

- [ ] **Step 13: 提交 Task 1**

```bash
git add backend/app/domain/game/room.py backend/tests/test_room.py
git commit -m "feat: add doudizhu doubling phase"
```

---

### Task 2: 后端应用服务、WebSocket 与 AI 加倍流程

**Files:**
- Modify: `backend/app/application/game/game_app_service.py`
- Modify: `backend/app/interfaces/websocket/game_handler.py`
- Test: `backend/tests/test_room.py` 继续作为领域保护；如现有 WebSocket 测试适合扩展，再修改 `backend/tests/test_game_websocket.py`

**Interfaces:**
- Consumes: `GameRoom.choose_double(player_id: str, choice: str) -> dict`
- Produces: `GameAppService.handle_double_choice(player_id: str, choice: str) -> dict`
- Produces WebSocket action: `choose_double`
- Produces WebSocket events: `double_chosen`, `doubling_finished`

- [ ] **Step 1: 写失败测试：应用服务能调用加倍选择**

若 `GameAppService` 单元测试已有 Redis mock，则扩展现有测试；否则在 `backend/tests/test_room.py` 已覆盖领域后，本任务通过最小 WebSocket handler 代码审查加后端全量测试保护。优先新增服务层测试文件 `backend/tests/test_game_app_service_doubling.py`：

```python
import pytest
from app.application.game.game_app_service import GameAppService
from app.domain.game.room import GameRoom, Player, GamePhase


class MemoryRepo:
    def __init__(self, room):
        self.room = room
        self.saved_room = None

    async def get_player_room(self, player_id):
        return self.room.room_id

    async def get_room(self, room_id):
        return self.room

    async def save_room(self, room):
        self.saved_room = room


def make_room():
    players = [
        Player(id="p1", nickname="玩家1"),
        Player(id="p2", nickname="玩家2"),
        Player(id="p3", nickname="玩家3"),
    ]
    room = GameRoom.create("room_1", players)
    room.deal()
    room._first_caller_index = 0
    room._call_index = 0
    room.current_turn = "p1"
    room.call_landlord("p1", 3)
    return room


@pytest.mark.asyncio
async def test_handle_double_choice_saves_room():
    room = make_room()
    repo = MemoryRepo(room)
    service = GameAppService(repo)

    result = await service.handle_double_choice("p1", "double")

    assert result["success"] is True
    assert result["choice"] == "double"
    assert repo.saved_room is room
    assert room.doubling_choices == {"p1": "double"}
```

- [ ] **Step 2: 运行失败测试**

Run: `python -m pytest backend/tests/test_game_app_service_doubling.py -v`

Expected: FAIL，原因是 `handle_double_choice` 不存在。

- [ ] **Step 3: 实现服务层方法**

在 `GameAppService` 中新增：

```python
    async def handle_double_choice(self, player_id: str, choice: str) -> dict:
        """处理玩家加倍确认"""
        room = await self._get_player_room(player_id)
        if not room:
            return {"error": "你不在任何房间中"}
        result = room.choose_double(player_id, choice)
        await self._repo.save_room(room)
        result["room"] = room
        return result
```

- [ ] **Step 4: 运行服务层测试**

Run: `python -m pytest backend/tests/test_game_app_service_doubling.py -v`

Expected: PASS。

- [ ] **Step 5: 实现 AI 加倍策略**

在 `GameAppService` 中新增私有方法：

```python
    def _decide_ai_double_choice(self, room: GameRoom, ai_id: str) -> str:
        """保守 AI 加倍策略：牌力明显较好时加倍，否则不加倍"""
        hand = room.hands.get(ai_id, [])
        high_cards = sum(1 for card in hand if card >= 48)
        is_landlord = ai_id == room.landlord
        if is_landlord or high_cards >= 3:
            return "double"
        return "none"
```

在 `handle_ai_turn()` 中 `CALLING` 与 `PLAYING` 之间增加：

```python
        elif room.phase == GamePhase.DOUBLING:
            await asyncio.sleep(1.0)
            choice = self._decide_ai_double_choice(room, ai_id)
            result = room.choose_double(ai_id, choice)
            await self._repo.save_room(room)
            result["room"] = room
            result["ai_player"] = ai_id
            result["double_choice"] = choice
            return result
```

- [ ] **Step 6: 修改 WebSocket action**

在 `GameWebSocketHandler._handle_message()` 中新增分支，放在 `pass_turn` 前后均可：

```python
        elif action == "choose_double":
            choice = data.get("choice", "none")
            result = await self.service.handle_double_choice(self.player_id, choice)
            if result.get("error") or result.get("success") is False:
                await self._send({"event": "error", "msg": result.get("error", "加倍失败")})
            else:
                room = result.get("room")
                if room:
                    event = {
                        "event": "double_chosen",
                        "player": self.player_id,
                        "choice": choice,
                        "label": self._double_choice_label(choice),
                        "multiplier": result.get("multiplier", room.multiplier),
                    }
                    await self._broadcast_room_event(room, event)
                    if result.get("doubling_finished"):
                        await self._broadcast_room_event(room, {
                            "event": "doubling_finished",
                            "current_turn": result.get("next_turn"),
                            "multiplier": result.get("multiplier", room.multiplier),
                        })
                    await self._process_ai_turns(room)
```

在类中新增：

```python
    def _double_choice_label(self, choice: str) -> str:
        return {
            "double": "加倍",
            "super": "超级加倍",
            "none": "不加倍",
        }.get(choice, "不加倍")
```

- [ ] **Step 7: 修改 AI 事件广播循环**

将 `_process_ai_turns()` 的循环条件改为：

```python
        while room.phase in (GamePhase.CALLING, GamePhase.DOUBLING, GamePhase.PLAYING):
```

在 `"score" in result` 分支后、`cards_played` 分支前增加：

```python
            elif result.get("double_choice"):
                choice = result["double_choice"]
                event = {
                    "event": "double_chosen",
                    "player": ai_id,
                    "choice": choice,
                    "label": self._double_choice_label(choice),
                    "multiplier": result.get("multiplier", room.multiplier),
                }
                await self._broadcast_room_event(room, event)
                if result.get("doubling_finished"):
                    await self._broadcast_room_event(room, {
                        "event": "doubling_finished",
                        "current_turn": result.get("next_turn"),
                        "multiplier": result.get("multiplier", room.multiplier),
                    })
```

- [ ] **Step 8: 确认地主确定后不立即处理出牌 AI**

现有 `landlord_decided` 后调用 `_process_ai_turns(room)`。因为房间阶段变为 `DOUBLING`，新逻辑会先处理 AI 加倍，而不会直接出牌。保留调用位置。

- [ ] **Step 9: 运行后端测试**

Run: `python -m pytest backend/tests/test_room.py backend/tests/test_game_app_service_doubling.py -v`

Expected: PASS。

- [ ] **Step 10: 提交 Task 2**

```bash
git add backend/app/application/game/game_app_service.py backend/app/interfaces/websocket/game_handler.py backend/tests/test_game_app_service_doubling.py
git commit -m "feat: broadcast doudizhu double choices"
```

---

### Task 3: 前端 Store 与 WebSocket 事件

**Files:**
- Modify: `frontend/src/stores/gameStore.ts`
- Modify: `frontend/src/composables/useGameWebSocket.ts`
- Modify: `frontend/src/composables/__tests__/useGameWebSocket.spec.ts`

**Interfaces:**
- Consumes event: `landlord_decided` with `room_state.phase === "DOUBLING"`
- Consumes event: `double_chosen`
- Consumes event: `doubling_finished`
- Produces state: `gameStore.doublingChoices`

- [ ] **Step 1: 写失败测试：WebSocket 处理加倍事件**

在 `frontend/src/composables/__tests__/useGameWebSocket.spec.ts` 中扩展 mock：

```ts
const playSoundMock = vi.fn()

vi.mock('../useSoundEngine', () => ({
  useSoundEngine: () => ({
    playSound: playSoundMock,
    startBgm: vi.fn(),
    stopBgm: vi.fn(),
  }),
}))
```

新增测试：

```ts
  it('syncs double choice events and plays matching voice', async () => {
    const playerStore = usePlayerStore()
    playerStore.playerId = 'p1'
    playerStore.authToken = 'token'

    const { connect } = useGameWebSocket()
    connect()
    const socket = MockWebSocket.instances[0]!
    socket.readyState = MockWebSocket.OPEN
    socket.onopen?.()

    socket.onmessage?.(new MessageEvent('message', {
      data: JSON.stringify({
        event: 'double_chosen',
        player: 'p2',
        choice: 'super',
        room_state: {
          room_id: 'room_1',
          phase: 'DOUBLING',
          players: [],
          doubling_choices: { p2: 'super' },
          multiplier: 4,
        },
      }),
    }))

    const { useGameStore } = await import('@/stores/gameStore')
    const gameStore = useGameStore()
    expect(gameStore.gamePhase).toBe('DOUBLING')
    expect(gameStore.doublingChoices).toEqual({ p2: 'super' })
    expect(gameStore.playerActions.p2).toBe('超级加倍')
    expect(playSoundMock).toHaveBeenCalledWith('doubling')
    expect(playSoundMock).toHaveBeenCalledWith('superDouble', 'p2')
  })
```

- [ ] **Step 2: 运行失败测试**

Run: `npm.cmd run test:unit -- src/composables/__tests__/useGameWebSocket.spec.ts --run`

Expected: FAIL，原因是 `doublingChoices` 不存在或事件未处理。

- [ ] **Step 3: 实现 Store 状态**

在 `frontend/src/stores/gameStore.ts` 增加类型：

```ts
export type DoublingChoice = 'double' | 'super' | 'none'
```

在 store 中新增：

```ts
  const doublingChoices = ref<Record<string, DoublingChoice>>({})
```

在 `updateFromRoomState()` 中增加：

```ts
    if (state.doubling_choices !== undefined) doublingChoices.value = state.doubling_choices || {}
```

在 `reset()` 中增加：

```ts
    doublingChoices.value = {}
```

在 return 中暴露：

```ts
    doublingChoices,
```

- [ ] **Step 4: 修改 WebSocket 事件处理**

在 `useGameWebSocket.ts` 中新增辅助函数：

```ts
function getDoubleChoiceLabel(choice: string) {
  if (choice === 'double') return '加倍'
  if (choice === 'super') return '超级加倍'
  return '不加倍'
}

function playDoubleChoiceSound(choice: string, playerId: string) {
  const { playSound } = useSoundEngine()
  if (choice === 'double') {
    playSound('doubling')
    setTimeout(() => playSound('jiabei', playerId), 120)
  } else if (choice === 'super') {
    playSound('doubling')
    setTimeout(() => playSound('superDouble', playerId), 120)
  } else {
    playSound('bujiabei', playerId)
  }
}
```

修改 `landlord_decided` 分支：

```ts
        if (data.room_state) gameStore.updateFromRoomState(data.room_state)
        gameStore.landlord = data.landlord
        gameStore.bottomCards = data.bottom_cards || []
        gameStore.multiplier = data.multiplier || 1
        gameStore.playerActions = {}
```

不要再写死：

```ts
gameStore.gamePhase = 'PLAYING'
```

新增事件分支：

```ts
      case 'double_chosen': {
        if (data.room_state) gameStore.updateFromRoomState(data.room_state)
        const label = data.label || getDoubleChoiceLabel(data.choice)
        gameStore.playerActions = { ...gameStore.playerActions, [data.player]: label }
        if (data.multiplier !== undefined) gameStore.multiplier = data.multiplier
        playDoubleChoiceSound(data.choice, data.player)
        break
      }
      case 'doubling_finished': {
        if (data.room_state) gameStore.updateFromRoomState(data.room_state)
        gameStore.gamePhase = 'PLAYING'
        if (data.current_turn !== undefined) gameStore.currentTurn = data.current_turn || ''
        if (data.multiplier !== undefined) gameStore.multiplier = data.multiplier
        break
      }
```

- [ ] **Step 5: 运行前端 WebSocket 测试**

Run: `npm.cmd run test:unit -- src/composables/__tests__/useGameWebSocket.spec.ts --run`

Expected: PASS。

- [ ] **Step 6: 提交 Task 3**

```bash
git add frontend/src/stores/gameStore.ts frontend/src/composables/useGameWebSocket.ts frontend/src/composables/__tests__/useGameWebSocket.spec.ts
git commit -m "feat: sync doudizhu double choice events"
```

---

### Task 4: 前端对局页真实加倍面板与出牌位置展示

**Files:**
- Modify: `frontend/src/views/GameRoomView.vue`

**Interfaces:**
- Consumes: `gameStore.gamePhase === "DOUBLING"`
- Consumes: `gameStore.doublingChoices`
- Produces client action: `{ action: "choose_double", choice }`

- [ ] **Step 1: 移除本地模拟状态**

在 `GameRoomView.vue` 删除：

```ts
const localDoublingState = ref<Record<string, string>>({})
const myDoublingChoice = ref('')
```

新增辅助映射：

```ts
function getDoubleChoiceLabel(choice?: string) {
  if (choice === 'double') return '加倍'
  if (choice === 'super') return '超级加倍'
  if (choice === 'none') return '不加倍'
  return ''
}
```

- [ ] **Step 2: 修改加倍面板显示条件**

将 `showDoublingPanel` 改为：

```ts
const showDoublingPanel = computed(() => {
  return gameStore.gamePhase === 'DOUBLING' &&
         !gameStore.doublingChoices[playerStore.playerId]
})
```

- [ ] **Step 3: 修改座位加倍标识来源**

在 `orderedSeats` 中把 `doubling` 注入改为：

```ts
  const decoratedLeft = { ...leftPlayer, doubling: getDoubleChoiceLabel(gameStore.doublingChoices[leftPlayer.id]) }
  const decoratedRight = { ...rightPlayer, doubling: getDoubleChoiceLabel(gameStore.doublingChoices[rightPlayer.id]) }
  const decoratedSelf = { ...selfPlayer, doubling: getDoubleChoiceLabel(gameStore.doublingChoices[selfPlayer.id]) }
```

- [ ] **Step 4: 替换 `chooseDoubling()`**

将原函数替换为：

```ts
function chooseDoubling(type: 'double' | 'super' | 'none') {
  playSound('btnClick')
  idleRoundCount.value = 0
  sendAction({ action: 'choose_double', choice: type })
}
```

不要在前端直接修改 `gameStore.multiplier`，不要前端随机模拟 AI。

- [ ] **Step 5: 修改超时逻辑**

在倒计时为 0 的分支中保留：

```ts
        if (showDoublingPanel.value) {
          if (!hasHandledTimeout.value) {
            hasHandledTimeout.value = true
            chooseDoubling('none')
          }
        } else if (gameStore.isMyTurn) {
```

此逻辑现在会发送真实 `choose_double`。

- [ ] **Step 6: 修改阶段相关 UI 判断**

需要包含 `DOUBLING` 的位置：

```vue
v-if="gameStore.gamePhase === 'PLAYING' || gameStore.gamePhase === 'CALLING' || gameStore.gamePhase === 'DOUBLING'"
```

至少更新：

- 记牌器显示条件。
- 托管按钮显示条件。
- 顶部倍数展示不需要改。

不要让出牌按钮在 `DOUBLING` 阶段显示，因为它依赖 `gameStore.isMyTurn`，而服务端会让 `current_turn` 为空。

- [ ] **Step 7: 删除退出/结算时本地加倍清理**

删除：

```ts
myDoublingChoice.value = ''
localDoublingState.value = {}
```

保留 `gameStore.reset()`。

- [ ] **Step 8: 运行前端测试**

Run: `npm.cmd run test:unit -- src/composables/__tests__/useGameWebSocket.spec.ts --run`

Expected: PASS。

- [ ] **Step 9: 运行前端构建类型检查**

Run: `npm.cmd run build`

Expected: PASS。若项目已有 unrelated 类型错误，记录具体错误，不顺手修无关文件。

- [ ] **Step 10: 提交 Task 4**

```bash
git add frontend/src/views/GameRoomView.vue
git commit -m "feat: use real doudizhu doubling panel"
```

---

### Task 5: 端到端回归与协议收尾

**Files:**
- Modify only if tests reveal necessary scoped fixes:
  - `backend/app/domain/game/room.py`
  - `backend/app/application/game/game_app_service.py`
  - `backend/app/interfaces/websocket/game_handler.py`
  - `frontend/src/stores/gameStore.ts`
  - `frontend/src/composables/useGameWebSocket.ts`
  - `frontend/src/views/GameRoomView.vue`

- [ ] **Step 1: 运行后端核心测试**

Run: `python -m pytest backend/tests/test_room.py backend/tests/test_game_app_service_doubling.py -v`

Expected: PASS。

- [ ] **Step 2: 运行前端相关测试**

Run: `npm.cmd run test:unit -- src/composables/__tests__/useGameWebSocket.spec.ts src/composables/__tests__/useSoundEngine.spec.ts --run`

Expected: PASS。

- [ ] **Step 3: 运行更宽回归**

Run: `python -m pytest backend/tests -v`

Expected: PASS。若因本地 MySQL/Redis/RabbitMQ 环境缺失失败，记录失败测试名和错误，不改无关基础设施。

- [ ] **Step 4: 运行前端构建**

Run: `npm.cmd run build`

Expected: PASS。

- [ ] **Step 5: 人工检查协议链路**

按代码路径确认：

```text
CALLING -> landlord_decided -> DOUBLING
DOUBLING -> double_chosen x3 -> doubling_finished -> PLAYING
PLAYING -> cards_played/pass_turn -> SETTLING
```

确认以下字段在 `room_state` 中存在：

```json
{
  "phase": "DOUBLING",
  "landlord": "player_id",
  "bottom_cards": [1, 2, 3],
  "multiplier": 3,
  "doubling_choices": {}
}
```

- [ ] **Step 6: 最终提交**

若 Task 5 有修复：

```bash
git add backend frontend
git commit -m "fix: stabilize doudizhu doubling flow"
```

若没有修复，不创建空提交。

