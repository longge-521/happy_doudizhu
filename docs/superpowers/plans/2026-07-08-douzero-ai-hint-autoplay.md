# DouZero AI 提示与托管出牌 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将“提示出牌”和真人托管出牌都接入后端 DouZero 模型候选排序，提示可循环切换模型排序候选，托管自动使用最高分候选。

**Architecture:** 后端在 `ai_strategy.py` 中新增 DouZero 候选排序函数，`GameAppService` 提供提示和真人托管出牌编排，WebSocket 增加 `get_ai_hints` 与 `set_auto_play` 协议。前端只请求和展示后端候选，不再用本地规则作为正常提示来源。

**Tech Stack:** FastAPI WebSocket、Python 3.10 `hmp_ai` conda 环境、PyTorch DouZero 权重、Redis 房间状态、Vue 3、Pinia、TypeScript、Vitest。

## Global Constraints

- 禁止批量删除文件或目录；不要使用 `del /s`、`rd /s`、`rmdir /s`、`Remove-Item -Recurse`、`rm -rf`。
- 如需删除文件，只能一次删除一个明确路径的文件。本计划不需要删除文件。
- 当前仓库可能存在用户未提交的改动。不要还原、覆盖或清理自己没有制造的变更。
- 写完需求并由用户人工确认完整无误后，智能体方可执行 `git commit`；本计划的执行任务只记录待提交文件，不主动提交。
- 所有 git commit 提交信息必须全部使用中文。本计划不执行提交。
- 后端必须使用 `D:\ProgramData\miniconda3\envs\hmp_ai\python.exe`，禁止使用系统默认 Python。
- 提示正常来源必须是 DouZero 模型排序候选；旧前端规则只允许作为异常兜底或临时错误恢复。
- 所有真实出牌仍必须经过 `GameRoom.play_cards()` 或 `GameRoom.pass_turn()` 校验。

---

## File Structure

- Modify: `backend/app/domain/game/ai_strategy.py`
  - 新增 `ai_rank_play_candidates()`。
  - 将规则兜底拆成 `_rule_decide_play()`，避免候选排序失败时递归调用 `ai_decide_play()`。
  - 调整 `ai_decide_play()` 优先取 DouZero 排序第一项。
- Modify: `backend/app/domain/game/room.py`
  - 新增 `auto_play_players` 房间状态。
  - 同步 `deal()`、`to_dict()`、`from_dict()`、`get_player_view()`。
- Modify: `backend/app/application/game/game_app_service.py`
  - 新增 `get_ai_play_hints()`、`set_auto_play()`、`handle_auto_play_turn()`。
  - 机器人出牌继续复用 `ai_decide_play()`。
- Modify: `backend/app/interfaces/websocket/game_handler.py`
  - 新增客户端动作 `get_ai_hints`、`set_auto_play`。
  - AI 自动处理循环支持托管真人玩家。
  - 广播 `ai_hints`、`auto_play_changed`。
- Modify: `backend/tests/test_ai_strategy.py`
  - 覆盖 DouZero 候选排序、兜底、`ai_decide_play()` 复用排序第一项。
- Modify: `backend/tests/test_game_app_service.py`
  - 覆盖提示服务、托管状态、托管自动出牌。
- Modify: `backend/tests/test_game_websocket.py`
  - 覆盖 WebSocket 提示和托管协议。
- Modify: `frontend/src/stores/gameStore.ts`
  - 新增 `aiHintCandidates`、`aiHintSource`、`autoPlayPlayers`。
  - 新增候选缓存和托管状态更新方法。
- Modify: `frontend/src/composables/useGameWebSocket.ts`
  - 新增客户端动作和服务端事件类型。
  - 处理 `ai_hints`、`auto_play_changed`。
- Modify: `frontend/src/views/GameRoomView.vue`
  - 提示按钮改为请求后端候选并循环切换。
  - 托管按钮改为通知后端。
  - 托管状态不再在前端本地直接调用 `play_cards`。
- Modify: `frontend/src/stores/__tests__/gameStore.spec.ts`
  - 覆盖候选缓存和托管状态。
- Modify: `frontend/src/composables/__tests__/useGameWebSocket.spec.ts`
  - 覆盖 `ai_hints` 和 `auto_play_changed` 事件。

---

### Task 1: 后端 AI 策略层提供 DouZero 候选排序

**Files:**
- Modify: `backend/app/domain/game/ai_strategy.py`
- Test: `backend/tests/test_ai_strategy.py`

**Interfaces:**
- Consumes: `generate_legal_actions_dz(hand, last_play, must_play) -> List[List[int]]`
- Consumes: `get_obs_for_douzero(...) -> dict`
- Produces: `ai_rank_play_candidates(hand, last_play, must_play, ctx, limit=12) -> List[List[int]]`
- Produces: `_rule_decide_play(hand, last_play, must_play, ctx) -> Optional[List[int]]`

- [ ] **Step 1: 写 DouZero 候选排序失败测试**

Add to `backend/tests/test_ai_strategy.py` imports:

```python
from app.domain.game.ai_strategy import ai_rank_play_candidates
```

Add test:

```python
def test_ai_rank_play_candidates_orders_by_douzero_score():
    from unittest.mock import patch
    import numpy as np
    import torch

    hand = [0, 1, 2, 3]
    ctx = AIContext(
        ai_id="test_ai",
        role="landlord",
        landlord_id="test_ai",
        teammate_id=None,
        landlord_remaining=4,
        teammate_remaining=0,
        last_play_from=None,
        is_last_play_teammate=False,
        is_last_play_landlord=False,
        play_history=[{"player": "farmer1", "cards": [4]}],
        player_ids=["test_ai", "farmer1", "farmer2"],
    )

    with patch("app.domain.game.ai_strategy.douzero_manager") as mock_manager:
        mock_manager.is_available.return_value = True
        mock_manager.get_action_value.return_value = torch.tensor([[0.1], [0.9], [0.5]])

        with patch("app.domain.game.ai_strategy.generate_legal_actions_dz") as mock_legal:
            mock_legal.return_value = [[0], [0, 1, 2, 3], []]

            with patch("app.domain.game.ai_strategy.get_obs_for_douzero") as mock_obs:
                mock_obs.return_value = {
                    "x_batch": np.zeros((3, 373)),
                    "z_batch": np.zeros((3, 5, 162)),
                    "legal_actions": [[3], [3, 3, 3, 3], []],
                }

                ranked = ai_rank_play_candidates(hand, last_play=None, must_play=True, ctx=ctx)

    assert ranked[0] == [0, 1, 2, 3]
    assert ranked[1] == []
    assert ranked[2] == [0]
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest backend/tests/test_ai_strategy.py::test_ai_rank_play_candidates_orders_by_douzero_score -q
```

Expected: FAIL，错误包含 `cannot import name 'ai_rank_play_candidates'`。

- [ ] **Step 3: 实现最小候选排序函数**

Modify `backend/app/domain/game/ai_strategy.py`:

```python
def _dedupe_candidates(candidates: List[List[int]]) -> List[List[int]]:
    seen = set()
    result = []
    for cards in candidates:
        key = tuple(sorted(cards))
        if key in seen:
            continue
        seen.add(key)
        result.append(cards)
    return result


def _rule_decide_play(
    hand: List[int],
    last_play: Optional[CardPlay],
    must_play: bool,
    ctx: AIContext,
) -> Optional[List[int]]:
    sorted_hand = sort_cards(hand)
    plan = _decompose_hand(sorted_hand)
    if must_play or last_play is None:
        return _pick_lead_play(plan, ctx.role, ctx)
    return _pick_follow_play(sorted_hand, plan, last_play, ctx.role, ctx)


def ai_rank_play_candidates(
    hand: List[int],
    last_play: Optional[CardPlay],
    must_play: bool,
    ctx: AIContext,
    limit: int = 12,
) -> List[List[int]]:
    if not hand:
        return []

    try:
        if ctx and ctx.play_history is not None and douzero_manager.is_available():
            legal_actions = generate_legal_actions_dz(hand, last_play, must_play)
            if not legal_actions:
                return []
            obs = get_obs_for_douzero(
                hand=hand,
                legal_actions=legal_actions,
                role=ctx.role,
                landlord_id=ctx.landlord_id,
                player_ids=ctx.player_ids,
                play_history=ctx.play_history,
            )
            import torch

            z = torch.from_numpy(obs["z_batch"]).float()
            x = torch.from_numpy(obs["x_batch"]).float()
            scores = douzero_manager.get_action_value(ctx.role, z, x).reshape(-1)
            order = torch.argsort(scores, descending=True).tolist()

            ranked = []
            for idx in order:
                action_dz = obs["legal_actions"][idx]
                if not action_dz:
                    ranked.append([])
                    continue
                cards = douzero_to_card_ids(action_dz, hand)
                if cards:
                    ranked.append(cards)
            return _dedupe_candidates(ranked)[:limit]
    except Exception as e:
        logger.warning(f"DouZero ranking failed, falling back to rule engine: {e}")

    fallback = _rule_decide_play(hand, last_play, must_play, ctx)
    return [fallback] if fallback else ([] if must_play else [[]])
```

- [ ] **Step 4: 调整 `ai_decide_play()` 使用排序第一项**

Replace the DouZero branch and rule fallback body in `ai_decide_play()` after default `ctx` creation with:

```python
    ranked = ai_rank_play_candidates(hand, last_play, must_play, ctx, limit=1)
    if ranked:
        best = ranked[0]
        return best if best else None

    return _rule_decide_play(hand, last_play, must_play, ctx)
```

Also move the current “冲刺控制” block into `_rule_decide_play()` before `_decompose_hand()`:

```python
    try:
        hand_play = detect_card_type(hand)
        if hand_play is not None:
            if last_play is None or must_play:
                logger.info(f"AI 冲刺：整手手牌为合法牌型 {hand_play.card_type.value}，直接一次性出完赢牌")
                return hand
            if can_beat(hand_play, last_play):
                logger.info(f"AI 冲刺：整手手牌为 {hand_play.card_type.value} 且可压过上家，直接一次性出完赢牌")
                return hand
    except Exception as e:
        logger.warning(f"AI 冲刺判断异常: {e}")
```

- [ ] **Step 5: 补充兜底测试**

Add:

```python
def test_ai_rank_play_candidates_falls_back_to_rule_engine_when_douzero_unavailable():
    hand = [0, 4, 8, 12, 16]
    ctx = AIContext(
        ai_id="test_ai",
        role="landlord",
        landlord_id="test_ai",
        teammate_id=None,
        landlord_remaining=5,
        teammate_remaining=0,
        last_play_from=None,
        is_last_play_teammate=False,
        is_last_play_landlord=False,
    )

    from unittest.mock import patch
    with patch("app.domain.game.ai_strategy.douzero_manager") as mock_manager:
        mock_manager.is_available.return_value = False
        ranked = ai_rank_play_candidates(hand, last_play=None, must_play=True, ctx=ctx)

    assert ranked
    assert detect_card_type(ranked[0]) is not None
```

- [ ] **Step 6: 更新旧 DouZero 路由测试断言**

In `test_ai_decide_play_douzero_route`, keep the existing mock values and assert:

```python
assert res == [0, 1, 2, 3]
```

The test should continue passing because `ai_decide_play()` now consumes `ai_rank_play_candidates(..., limit=1)`.

- [ ] **Step 7: 运行 AI 策略测试**

Run:

```powershell
D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest backend/tests/test_ai_strategy.py -q
```

Expected: PASS。

- [ ] **Step 8: 记录待提交文件**

Do not commit. Record changed files:

```text
backend/app/domain/game/ai_strategy.py
backend/tests/test_ai_strategy.py
```

---

### Task 2: 房间状态和应用服务支持提示候选与托管出牌

**Files:**
- Modify: `backend/app/domain/game/room.py`
- Modify: `backend/app/application/game/game_app_service.py`
- Test: `backend/tests/test_game_app_service.py`

**Interfaces:**
- Consumes: `ai_rank_play_candidates(hand, last_play, must_play, ctx, limit=12)`
- Produces: `GameRoom.auto_play_players: Set[str]`
- Produces: `GameAppService.get_ai_play_hints(player_id) -> dict`
- Produces: `GameAppService.set_auto_play(player_id, enabled) -> dict`
- Produces: `GameAppService.handle_auto_play_turn(room) -> dict`

- [ ] **Step 1: 写房间序列化测试**

Add to `backend/tests/test_game_app_service.py`:

```python
def test_game_room_serializes_auto_play_players():
    room = GameRoom.create(
        "room_auto",
        [
            Player(id="p1", nickname="玩家1"),
            Player(id="p2", nickname="玩家2"),
            Player(id="p3", nickname="玩家3"),
        ],
    )
    room.auto_play_players.add("p1")

    restored = GameRoom.from_dict(room.to_dict())

    assert restored.auto_play_players == {"p1"}
    assert "p1" in restored.get_player_view("p1")["auto_play_players"]
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest backend/tests/test_game_app_service.py::test_game_room_serializes_auto_play_players -q
```

Expected: FAIL，错误包含 `auto_play_players` 属性不存在。

- [ ] **Step 3: 实现房间状态字段**

Modify `backend/app/domain/game/room.py`:

In `__init__()` add:

```python
        self.auto_play_players: Set[str] = set()
```

In `deal()` reset:

```python
        self.auto_play_players = set()
```

In `to_dict()` add:

```python
            "auto_play_players": list(self.auto_play_players),
```

In `from_dict()` add:

```python
        room.auto_play_players = set(data.get("auto_play_players", []))
```

In `get_player_view()` add:

```python
            "auto_play_players": list(self.auto_play_players),
```

- [ ] **Step 4: 写应用服务提示测试**

Add:

```python
@pytest.mark.asyncio
async def test_get_ai_play_hints_returns_ranked_candidates(service, mock_repo):
    room = GameRoom.create(
        "room_hint",
        [
            Player(id="p1", nickname="玩家1"),
            Player(id="p2", nickname="玩家2"),
            Player(id="p3", nickname="玩家3"),
        ],
    )
    room.phase = GamePhase.PLAYING
    room.landlord = "p1"
    room.current_turn = "p1"
    room.hands = {"p1": [0, 1, 2, 3], "p2": [4], "p3": [8]}
    mock_repo.get_player_room.return_value = "room_hint"
    mock_repo.get_room.return_value = room

    with patch("app.application.game.game_app_service.ai_rank_play_candidates", return_value=[[0, 1, 2, 3], [0]]):
        result = await service.get_ai_play_hints("p1")

    assert result["candidates"] == [[0, 1, 2, 3], [0]]
    assert result["source"] == "douzero"
```

- [ ] **Step 5: 写托管出牌测试**

Add:

```python
@pytest.mark.asyncio
async def test_handle_auto_play_turn_uses_first_ai_candidate(service, mock_repo):
    room = GameRoom.create(
        "room_auto_turn",
        [
            Player(id="p1", nickname="玩家1"),
            Player(id="p2", nickname="玩家2"),
            Player(id="p3", nickname="玩家3"),
        ],
    )
    room.phase = GamePhase.PLAYING
    room.landlord = "p1"
    room.current_turn = "p1"
    room.hands = {"p1": [0, 1, 2, 3], "p2": [4], "p3": [8]}
    room.auto_play_players.add("p1")

    with patch("app.application.game.game_app_service.ai_rank_play_candidates", return_value=[[0, 1, 2, 3]]):
        result = await service.handle_auto_play_turn(room)

    assert result["auto_player"] == "p1"
    assert result["cards_played"] == [0, 1, 2, 3]
    mock_repo.save_room.assert_awaited()
```

- [ ] **Step 6: 运行应用服务新增测试确认失败**

Run:

```powershell
D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest backend/tests/test_game_app_service.py::test_get_ai_play_hints_returns_ranked_candidates backend/tests/test_game_app_service.py::test_handle_auto_play_turn_uses_first_ai_candidate -q
```

Expected: FAIL，错误包含 `get_ai_play_hints` 或 `handle_auto_play_turn` 不存在。

- [ ] **Step 7: 实现应用服务方法**

Modify imports in `backend/app/application/game/game_app_service.py`:

```python
from app.domain.game.ai_strategy import ai_decide_call, ai_decide_play, ai_rank_play_candidates, build_ai_context
```

Add methods to `GameAppService`:

```python
    async def get_ai_play_hints(self, player_id: str) -> dict:
        room = await self._get_player_room(player_id)
        if not room:
            return {"error": "你不在任何房间中"}
        if room.phase != GamePhase.PLAYING:
            return {"error": "当前不在出牌阶段"}
        if room.current_turn != player_id:
            return {"error": "当前还没轮到你出牌"}

        hand = room.hands.get(player_id, [])
        last_cp = room.last_play.card_play
        must_play = room.last_play.player is None
        ctx = build_ai_context(room, player_id)
        candidates = ai_rank_play_candidates(hand, last_cp, must_play, ctx)
        return {"candidates": candidates, "source": "douzero", "room": room}

    async def set_auto_play(self, player_id: str, enabled: bool) -> dict:
        room = await self._get_player_room(player_id)
        if not room:
            return {"error": "你不在任何房间中"}
        if enabled:
            room.auto_play_players.add(player_id)
        else:
            room.auto_play_players.discard(player_id)
        await self._repo.save_room(room)
        return {"room": room, "player": player_id, "enabled": enabled}

    async def handle_auto_play_turn(self, room: GameRoom) -> dict:
        player_id = room.current_turn
        if room.phase != GamePhase.PLAYING:
            return {"error": "托管只处理出牌阶段"}
        if player_id not in room.auto_play_players:
            return {"error": "当前玩家未开启托管"}

        hand = room.hands.get(player_id, [])
        last_cp = room.last_play.card_play
        must_play = room.last_play.player is None
        ctx = build_ai_context(room, player_id)
        candidates = ai_rank_play_candidates(hand, last_cp, must_play, ctx, limit=1)
        cards = candidates[0] if candidates else None

        if cards:
            result = room.play_cards(player_id, cards)
        else:
            result = room.pass_turn(player_id)
        await self._repo.save_room(room)
        result["room"] = room
        result["auto_player"] = player_id
        return result
```

- [ ] **Step 8: 运行应用服务测试**

Run:

```powershell
D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest backend/tests/test_game_app_service.py -q
```

Expected: PASS。

- [ ] **Step 9: 记录待提交文件**

Do not commit. Record changed files:

```text
backend/app/domain/game/room.py
backend/app/application/game/game_app_service.py
backend/tests/test_game_app_service.py
```

---

### Task 3: WebSocket 协议接入提示和托管

**Files:**
- Modify: `backend/app/interfaces/websocket/game_handler.py`
- Modify: `backend/tests/test_game_websocket.py`

**Interfaces:**
- Consumes: `GameAppService.get_ai_play_hints(player_id) -> dict`
- Consumes: `GameAppService.set_auto_play(player_id, enabled) -> dict`
- Consumes: `GameAppService.handle_auto_play_turn(room) -> dict`
- Produces client action: `get_ai_hints`
- Produces client action: `set_auto_play`
- Produces server event: `ai_hints`
- Produces server event: `auto_play_changed`

- [ ] **Step 1: 写 WebSocket 提示协议测试**

In fixture `mock_game_service`, add:

```python
    service.get_ai_play_hints = AsyncMock(return_value={"candidates": [[0, 1]], "source": "douzero"})
    service.set_auto_play = AsyncMock()
    service.handle_auto_play_turn = AsyncMock()
```

Add test:

```python
def test_game_websocket_get_ai_hints(monkeypatch, mock_game_service):
    monkeypatch.setattr(auth, "API_TOKEN", "")
    game_token = auth.create_game_auth_token("player1")

    client = TestClient(app)
    with client.websocket_connect(f"/ws/game/player1?auth_token={game_token}") as websocket:
        websocket.send_json({"action": "get_ai_hints"})
        resp = websocket.receive_json()

    assert resp["event"] == "ai_hints"
    assert resp["candidates"] == [[0, 1]]
    assert resp["source"] == "douzero"
    mock_game_service.get_ai_play_hints.assert_called_once_with("player1")
```

- [ ] **Step 2: 写 WebSocket 托管协议测试**

Add:

```python
def test_game_websocket_set_auto_play(monkeypatch, mock_game_service):
    monkeypatch.setattr(auth, "API_TOKEN", "")
    game_token = auth.create_game_auth_token("player1")
    room = GameRoom.create("room_auto_ws", [Player(id="player1", nickname="P1")])
    mock_game_service.set_auto_play.return_value = {"room": room, "player": "player1", "enabled": True}

    client = TestClient(app)
    with client.websocket_connect(f"/ws/game/player1?auth_token={game_token}") as websocket:
        websocket.send_json({"action": "set_auto_play", "enabled": True})
        resp = websocket.receive_json()

    assert resp["event"] == "auto_play_changed"
    assert resp["player"] == "player1"
    assert resp["enabled"] is True
    mock_game_service.set_auto_play.assert_called_once_with("player1", True)
```

- [ ] **Step 3: 运行 WebSocket 新测试确认失败**

Run:

```powershell
D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest backend/tests/test_game_websocket.py::test_game_websocket_get_ai_hints backend/tests/test_game_websocket.py::test_game_websocket_set_auto_play -q
```

Expected: FAIL，错误事件为未知动作。

- [ ] **Step 4: 实现 WebSocket 动作分发**

Modify `backend/app/interfaces/websocket/game_handler.py` inside `_handle_message()` before `chat`:

```python
        elif action == "get_ai_hints":
            result = await self.service.get_ai_play_hints(self.player_id)
            if result.get("error"):
                await self._send({"event": "error", "msg": result["error"]})
            else:
                await self._send({
                    "event": "ai_hints",
                    "candidates": result.get("candidates", []),
                    "source": result.get("source", "douzero"),
                })

        elif action == "set_auto_play":
            enabled = bool(data.get("enabled", False))
            result = await self.service.set_auto_play(self.player_id, enabled)
            if result.get("error"):
                await self._send({"event": "error", "msg": result["error"]})
            else:
                room = result.get("room")
                event = {
                    "event": "auto_play_changed",
                    "player": self.player_id,
                    "enabled": enabled,
                }
                if room:
                    await self._broadcast_room_event(room, event)
                    if enabled:
                        asyncio.create_task(self._process_ai_turns(room))
                else:
                    await self._send(event)
```

- [ ] **Step 5: 让自动处理循环支持托管真人**

In `_do_process_ai_turns()` replace:

```python
            if not current_player or not current_player.is_ai:
                logger.info(f"游戏WS [room={room.room_id}]: 轮到真人玩家 {current}，跳出 AI 自动处理器")
                break
```

with:

```python
            is_auto_player = bool(current_player and current in getattr(room, "auto_play_players", set()))
            if not current_player or (not current_player.is_ai and not is_auto_player):
                logger.info(f"游戏WS [room={room.room_id}]: 轮到真人玩家 {current}，跳出 AI 自动处理器")
                break
```

Then replace the service call:

```python
                result = await self.service.handle_ai_turn(room)
```

with:

```python
                if current_player.is_ai:
                    result = await self.service.handle_ai_turn(room)
                else:
                    result = await self.service.handle_auto_play_turn(room)
```

Then after result:

```python
            ai_id = result.get("ai_player")
```

replace with:

```python
            ai_id = result.get("ai_player") or result.get("auto_player")
```

- [ ] **Step 6: 运行 WebSocket 测试**

Run:

```powershell
D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest backend/tests/test_game_websocket.py -q
```

Expected: PASS。

- [ ] **Step 7: 记录待提交文件**

Do not commit. Record changed files:

```text
backend/app/interfaces/websocket/game_handler.py
backend/tests/test_game_websocket.py
```

---

### Task 4: 前端 Store 和 WebSocket 类型接入新协议

**Files:**
- Modify: `frontend/src/stores/gameStore.ts`
- Modify: `frontend/src/composables/useGameWebSocket.ts`
- Modify: `frontend/src/stores/__tests__/gameStore.spec.ts`
- Modify: `frontend/src/composables/__tests__/useGameWebSocket.spec.ts`

**Interfaces:**
- Consumes server event: `{ event: 'ai_hints'; candidates: number[][]; source: string }`
- Consumes server event: `{ event: 'auto_play_changed'; player: string; enabled: boolean }`
- Produces store state: `aiHintCandidates: number[][]`
- Produces store state: `autoPlayPlayers: string[]`

- [ ] **Step 1: 写 Store 测试**

Add to `frontend/src/stores/__tests__/gameStore.spec.ts`:

```typescript
it('stores AI hint candidates and auto-play players', () => {
  const store = useGameStore()

  store.setAiHintCandidates([[0, 1], [2, 3]], 'douzero')
  expect(store.aiHintCandidates).toEqual([[0, 1], [2, 3]])
  expect(store.aiHintSource).toBe('douzero')

  store.setAutoPlayPlayer('p1', true)
  expect(store.autoPlayPlayers).toContain('p1')

  store.setAutoPlayPlayer('p1', false)
  expect(store.autoPlayPlayers).not.toContain('p1')
})
```

- [ ] **Step 2: 运行 Store 测试确认失败**

Run:

```powershell
cd frontend
npm run test:unit -- src/stores/__tests__/gameStore.spec.ts
```

Expected: FAIL，错误包含 `setAiHintCandidates is not a function`。

- [ ] **Step 3: 实现 Store 状态**

Modify `frontend/src/stores/gameStore.ts`:

Add to `RoomStatePayload`:

```typescript
  auto_play_players?: string[]
```

Add refs:

```typescript
  const aiHintCandidates = ref<number[][]>([])
  const aiHintSource = ref('')
  const autoPlayPlayers = ref<string[]>([])
```

Add methods:

```typescript
  function setAiHintCandidates(candidates: number[][], source: string) {
    aiHintCandidates.value = candidates.map((cards) => sortCardIds(cards))
    aiHintSource.value = source
  }

  function clearAiHintCandidates() {
    aiHintCandidates.value = []
    aiHintSource.value = ''
  }

  function setAutoPlayPlayer(playerId: string, enabled: boolean) {
    const next = new Set(autoPlayPlayers.value)
    if (enabled) next.add(playerId)
    else next.delete(playerId)
    autoPlayPlayers.value = [...next]
  }
```

In `updateFromRoomState()` add:

```typescript
    if (state.auto_play_players !== undefined) autoPlayPlayers.value = state.auto_play_players
```

In `reset()` add:

```typescript
    aiHintCandidates.value = []
    aiHintSource.value = ''
    autoPlayPlayers.value = []
```

Return the new refs and methods.

- [ ] **Step 4: 写 WebSocket 事件测试**

In `frontend/src/composables/__tests__/useGameWebSocket.spec.ts`, add a test following the file's existing WebSocket mock pattern:

```typescript
it('stores AI hints from websocket event', async () => {
  const { useGameStore } = await import('@/stores/gameStore')
  const { useGameWebSocket } = await import('../useGameWebSocket')
  const gameStore = useGameStore()

  const wsApi = useGameWebSocket()
  wsApi.connect()

  const socket = createdSockets[0]!
  socket.onmessage?.({ data: JSON.stringify({ event: 'ai_hints', candidates: [[0, 1]], source: 'douzero' }) } as MessageEvent)

  expect(gameStore.aiHintCandidates).toEqual([[0, 1]])
  expect(gameStore.aiHintSource).toBe('douzero')
})
```

If the local test helper names differ, use the existing mock socket array name already defined in that spec file.

- [ ] **Step 5: 实现 WebSocket 类型和事件处理**

Modify `frontend/src/composables/useGameWebSocket.ts`:

Extend `GameClientAction`:

```typescript
  | { action: 'get_ai_hints' }
  | { action: 'set_auto_play'; enabled: boolean }
```

Add server event types:

```typescript
type AiHintsEvent = {
  event: 'ai_hints'
  candidates: number[][]
  source?: string
}

type AutoPlayChangedEvent = {
  event: 'auto_play_changed'
  player: string
  enabled: boolean
}
```

Extend `GameServerEvent`:

```typescript
  | AiHintsEvent
  | AutoPlayChangedEvent
```

Add switch cases:

```typescript
      case 'ai_hints':
        gameStore.setAiHintCandidates(data.candidates, data.source || 'douzero')
        break
      case 'auto_play_changed':
        gameStore.setAutoPlayPlayer(data.player, data.enabled)
        break
```

- [ ] **Step 6: 运行前端单元测试**

Run:

```powershell
cd frontend
npm run test:unit -- src/stores/__tests__/gameStore.spec.ts src/composables/__tests__/useGameWebSocket.spec.ts
```

Expected: PASS。

- [ ] **Step 7: 记录待提交文件**

Do not commit. Record changed files:

```text
frontend/src/stores/gameStore.ts
frontend/src/composables/useGameWebSocket.ts
frontend/src/stores/__tests__/gameStore.spec.ts
frontend/src/composables/__tests__/useGameWebSocket.spec.ts
```

---

### Task 5: 前端对局页面接入 DouZero 提示和后端托管

**Files:**
- Modify: `frontend/src/views/GameRoomView.vue`

**Interfaces:**
- Consumes store: `gameStore.aiHintCandidates`
- Consumes action: `sendAction({ action: 'get_ai_hints' })`
- Consumes action: `sendAction({ action: 'set_auto_play', enabled })`

- [ ] **Step 1: 移除正常提示对本地规则的依赖**

Modify imports in `GameRoomView.vue`:

Remove:

```typescript
  findSuggestedPlay,
  findAllPlayableHints,
```

Keep `detectCardPlay` for selected-card validation.

- [ ] **Step 2: 新增提示加载状态**

Near `hintState` add:

```typescript
const isHintLoading = ref(false)
```

Replace `playSuggestion` computed body with backend-candidate based logic:

```typescript
const playSuggestion = computed(() => {
  if (gameStore.gamePhase !== 'PLAYING' || !gameStore.isMyTurn) return null
  const cards = gameStore.aiHintCandidates.find((candidate) => candidate.length > 0) || []
  const play = detectCardPlay(cards)
  const isLeading = lastCardsToBeat.value.length === 0

  if (!cards.length || !play) {
    return {
      canPlay: false,
      cards: [] as number[],
      text: '要不起，建议不出',
    }
  }

  const label = getPlayKindLabel(play.kind)
  return {
    canPlay: true,
    cards,
    text: `${isLeading ? 'AI 建议先出' : 'AI 建议出'}：${formatCardIds(cards)}（${label}）`,
  }
})
```

- [ ] **Step 3: 改造提示按钮逻辑**

Replace `applySuggestion()` with:

```typescript
function selectHintAt(index: number) {
  const playableHints = gameStore.aiHintCandidates.filter((cards) => cards.length > 0)
  if (playableHints.length === 0) return
  hintState.value = {
    allHints: playableHints,
    currentIndex: index % playableHints.length,
  }
  gameStore.selectCards(playableHints[hintState.value.currentIndex] || [])
}

function applySuggestion() {
  if (gameStore.gamePhase !== 'PLAYING' || !gameStore.isMyTurn || isHintLoading.value) return
  playSound('btnClick')

  if (!hintState.value || hintState.value.allHints.length === 0) {
    if (gameStore.aiHintCandidates.length > 0) {
      selectHintAt(0)
      return
    }
    isHintLoading.value = true
    sendAction({ action: 'get_ai_hints' })
    return
  }

  selectHintAt(hintState.value.currentIndex + 1)
}
```

Add watcher:

```typescript
watch(
  () => gameStore.aiHintCandidates,
  (candidates) => {
    isHintLoading.value = false
    if (gameStore.gamePhase === 'PLAYING' && gameStore.isMyTurn && candidates.length > 0 && !hintState.value) {
      selectHintAt(0)
    }
  },
  { deep: true }
)
```

- [ ] **Step 4: 清理提示缓存重置**

In existing watchers that set `hintState.value = null`, also call:

```typescript
  gameStore.clearAiHintCandidates()
  isHintLoading.value = false
```

Apply this to current-turn, hand, last-play, and game-phase reset paths.

- [ ] **Step 5: 改造托管按钮**

Replace `toggleAutoplay()` with:

```typescript
function toggleAutoplay() {
  const next = !isAutoPlay.value
  isAutoPlay.value = next
  sendAction({ action: 'set_auto_play', enabled: next })
}
```

Add watcher to reflect backend event:

```typescript
watch(
  () => gameStore.autoPlayPlayers,
  (players) => {
    isAutoPlay.value = players.includes(playerStore.playerId)
  },
  { immediate: true }
)
```

- [ ] **Step 6: 禁止托管时前端本地自动出牌**

Replace the auto-play watcher body:

```typescript
  ([isMyTurn, autoPlay]) => {
    if (isMyTurn && autoPlay) {
      setTimeout(() => {
        if (gameStore.isMyTurn && isAutoPlay.value) {
          handleTimeout()
        }
      }, 500)
    }
  },
```

with:

```typescript
  ([isMyTurn, autoPlay]) => {
    if (isMyTurn && autoPlay) {
      sendAction({ action: 'set_auto_play', enabled: true })
    }
  },
```

In `handleTimeout()` for `PLAYING`, replace local auto play:

```typescript
    if (isAutoPlay.value) {
      sendAction({ action: 'set_auto_play', enabled: true })
      return
    }
```

then keep manual timeout fallback only for non托管玩家:

```typescript
    handlePass(true)
```

This ensures托管出牌 is driven by backend DouZero instead of front-end `findSuggestedPlay()`.

- [ ] **Step 7: 运行前端构建**

Run:

```powershell
cd frontend
npm run build
```

Expected: PASS。

- [ ] **Step 8: 记录待提交文件**

Do not commit. Record changed files:

```text
frontend/src/views/GameRoomView.vue
```

---

### Task 6: 端到端验证与回归检查

**Files:**
- No planned source edits unless prior tasks reveal a failing assertion.

**Interfaces:**
- Verifies all produced backend and frontend interfaces.

- [ ] **Step 1: 运行后端聚焦测试**

Run:

```powershell
D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest backend/tests/test_ai_strategy.py backend/tests/test_game_app_service.py backend/tests/test_game_websocket.py -q
```

Expected: PASS。

- [ ] **Step 2: 运行后端快速回归**

Run:

```powershell
D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest backend/tests/ -x -q --tb=short
```

Expected: PASS。

- [ ] **Step 3: 运行前端测试和构建**

Run:

```powershell
cd frontend
npm run test:unit
npm run build
```

Expected: PASS。

- [ ] **Step 4: 手动联调检查点**

建议用户手动测试以下功能点：

1. 真人对 AI 对局中，轮到自己时点击“提示”，第一手选中后端 `ai_hints` 返回的第一个非空候选。
2. 连续点击“提示”，候选按 DouZero 排序列表循环切换，按钮显示 `提示 1/N`、`提示 2/N`。
3. 跟牌要不起时，提示显示“要不起”，不选中非法牌。
4. 开启托管后，轮到自己出牌时后端自动出牌或不出，前端不再发送本地规则推荐牌。
5. 退出托管后，轮到自己时不会自动出牌。
6. 对局结算、剩余牌数、最后一手牌展示正常。

- [ ] **Step 5: 提交前状态检查**

Run:

```powershell
git status --short
```

Expected: 只包含本需求相关文件和已确认的文档文件。不要执行 `git commit`，等待用户人工确认。

---

## Self-Review

**Spec coverage:** 本计划覆盖 DouZero 候选排序、提示按钮候选循环、后端托管出牌、WebSocket 协议、Redis 房间状态、前后端测试和手动联调点。

**Placeholder scan:** 本计划没有遗留占位项。每个任务都有明确文件、接口、测试命令和预期结果。

**Type consistency:** 后端统一使用 `ai_rank_play_candidates(...) -> List[List[int]]`；应用层和 WebSocket 都使用 `candidates` 字段；前端 Store 使用 `aiHintCandidates: number[][]`，协议字段保持 snake_case action 与 camelCase store 分离。
