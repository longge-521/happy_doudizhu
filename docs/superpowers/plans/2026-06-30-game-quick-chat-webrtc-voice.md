# 斗地主快捷语与 WebRTC 房间语音 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 扩充斗地主对局快捷语，并为同房间玩家增加 WebRTC 实时语音通话。

**Architecture:** 后端复用游戏 WebSocket 只做 WebRTC 信令校验和转发，不保存音频、不进入房间状态机。前端新增独立语音事件分发器和 `useRoomVoiceChat` composable，`GameRoomView.vue` 只负责按钮和状态展示。快捷语抽到共享常量，发送端和接收端共用同一份文案。

**Tech Stack:** FastAPI WebSocket、pytest、Vue 3、TypeScript、Pinia、Vitest、浏览器 `getUserMedia`、`RTCPeerConnection`。

## Global Constraints

- 禁止批量删除文件或目录，不使用 `del /s`、`rd /s`、`rmdir /s`、`Remove-Item -Recurse`、`rm -rf`。
- 当前仓库可能存在用户未提交的改动；不要还原、覆盖或清理自己没有制造的变更。
- 文档和用户可见说明使用中文。
- 新功能按 TDD 执行：先写失败测试，确认失败，再写最小实现。
- 后端只负责 WebRTC 信令转发，不保存、不转发、不录制音频流。
- 第一版不接入 TURN，不做设备选择、输入音量条、说话人检测、服务端录音或历史回放。

---

## 文件结构

- Create: `backend/tests/test_game_voice_signaling.py`
  - 直接实例化 `GameWebSocketHandler`，用内存 fake manager/service 验证 `voice_state` 和 `voice_signal`。
- Modify: `backend/app/interfaces/websocket/game_handler.py`
  - 增加信令类型白名单、payload 大小限制和两个动作分支。
- Create: `frontend/src/constants/chatPresets.ts`
  - 统一维护快捷语数组，避免 `GameRoomView.vue` 和 `useGameWebSocket.ts` 双份文案漂移。
- Create: `frontend/src/composables/gameVoiceEvents.ts`
  - 提供轻量事件订阅器，承接 WebSocket 收到的 `voice_state` 和 `voice_signal`。
- Modify: `frontend/src/composables/useGameWebSocket.ts`
  - 广播语音事件，聊天气泡读取共享快捷语。
- Create: `frontend/src/composables/useRoomVoiceChat.ts`
  - 管理麦克风、本地流、P2P 连接、远端音频元素和清理。
- Create: `frontend/src/composables/__tests__/gameVoiceEvents.spec.ts`
- Create: `frontend/src/composables/__tests__/useRoomVoiceChat.spec.ts`
- Modify: `frontend/src/composables/__tests__/useGameWebSocket.spec.ts`
- Modify: `frontend/src/views/GameRoomView.vue`
  - 加麦克风按钮、错误提示和快捷语扩充 UI。

---

### Task 1: 后端 WebRTC 信令校验与转发

**Files:**
- Create: `backend/tests/test_game_voice_signaling.py`
- Modify: `backend/app/interfaces/websocket/game_handler.py`

**Interfaces:**
- Consumes: `GameWebSocketHandler._handle_message(text: str)`
- Produces:
  - 客户端动作 `voice_state`: `{ "action": "voice_state", "enabled": boolean }`
  - 客户端动作 `voice_signal`: `{ "action": "voice_signal", "target_player": string, "signal_type": "offer" | "answer" | "ice_candidate", "payload": object }`
  - 服务端事件 `voice_state`
  - 服务端事件 `voice_signal`

- [ ] **Step 1: Write the failing backend tests**

Create `backend/tests/test_game_voice_signaling.py`:

```python
import json
from unittest.mock import AsyncMock

import pytest

from app.domain.game.room import GameRoom, Player
from app.interfaces.websocket.game_handler import GameWebSocketHandler


class FakeManager:
    def __init__(self):
        self.connections = {"p1": object(), "p2": object(), "p3": object()}
        self.sent = []

    async def send_to_player(self, player_id, data):
        self.sent.append((player_id, data))


class FakeService:
    def __init__(self, room):
        self.room = room

    async def _get_player_room(self, player_id):
        if player_id in {p.id for p in self.room.players}:
            return self.room
        return None


def make_handler(player_id="p1"):
    players = [
        Player(id="p1", nickname="玩家1", is_ai=False, is_online=True),
        Player(id="p2", nickname="玩家2", is_ai=False, is_online=True),
        Player(id="p3", nickname="玩家3", is_ai=False, is_online=True),
    ]
    room = GameRoom.create("room_voice", players)
    manager = FakeManager()
    service = FakeService(room)
    handler = GameWebSocketHandler(AsyncMock(), player_id, manager, service)
    return handler, manager


@pytest.mark.asyncio
async def test_voice_state_broadcasts_to_room_players():
    handler, manager = make_handler("p1")

    await handler._handle_message(json.dumps({"action": "voice_state", "enabled": True}))

    recipients = [player_id for player_id, _ in manager.sent]
    assert recipients == ["p1", "p2", "p3"]
    assert all(data["event"] == "voice_state" for _, data in manager.sent)
    assert all(data["player"] == "p1" for _, data in manager.sent)
    assert all(data["enabled"] is True for _, data in manager.sent)
    assert all("room_state" in data for _, data in manager.sent)


@pytest.mark.asyncio
async def test_voice_signal_forwards_only_to_target_room_player():
    handler, manager = make_handler("p1")
    payload = {"type": "offer", "sdp": "v=0"}

    await handler._handle_message(json.dumps({
        "action": "voice_signal",
        "target_player": "p2",
        "signal_type": "offer",
        "payload": payload,
    }))

    assert len(manager.sent) == 1
    target, data = manager.sent[0]
    assert target == "p2"
    assert data == {
        "event": "voice_signal",
        "player": "p1",
        "target_player": "p2",
        "signal_type": "offer",
        "payload": payload,
    }


@pytest.mark.asyncio
async def test_voice_signal_rejects_non_room_target():
    handler, manager = make_handler("p1")

    await handler._handle_message(json.dumps({
        "action": "voice_signal",
        "target_player": "outside",
        "signal_type": "offer",
        "payload": {"type": "offer", "sdp": "v=0"},
    }))

    assert manager.sent == [("p1", {"event": "error", "msg": "语音信令目标不在当前房间"})]


@pytest.mark.asyncio
async def test_voice_signal_rejects_invalid_type_and_large_payload():
    handler, manager = make_handler("p1")

    await handler._handle_message(json.dumps({
        "action": "voice_signal",
        "target_player": "p2",
        "signal_type": "bad",
        "payload": {"type": "offer", "sdp": "v=0"},
    }))

    large_payload = {"candidate": "x" * (16 * 1024)}
    await handler._handle_message(json.dumps({
        "action": "voice_signal",
        "target_player": "p2",
        "signal_type": "ice_candidate",
        "payload": large_payload,
    }))

    assert manager.sent[0] == ("p1", {"event": "error", "msg": "不支持的语音信令类型"})
    assert manager.sent[1] == ("p1", {"event": "error", "msg": "语音信令内容过大"})
```

- [ ] **Step 2: Run backend tests to verify RED**

Run: `python -m pytest backend/tests/test_game_voice_signaling.py -v`

Expected: FAIL because `voice_state` and `voice_signal` are treated as unknown actions.

- [ ] **Step 3: Implement minimal backend signaling**

Modify `backend/app/interfaces/websocket/game_handler.py`.

Near `BASE_SCORE_MIN_BEANS`, add:

```python
VOICE_SIGNAL_TYPES = {"offer", "answer", "ice_candidate"}
VOICE_SIGNAL_MAX_PAYLOAD_BYTES = 16 * 1024
```

Inside `GameWebSocketHandler`, add these methods after `_broadcast_room_event`:

```python
    async def _handle_voice_state(self, data: dict):
        room = await self.service._get_player_room(self.player_id)
        if not room:
            await self._send({"event": "error", "msg": "当前不在房间内，无法使用语音"})
            return

        event = {
            "event": "voice_state",
            "player": self.player_id,
            "enabled": bool(data.get("enabled", False)),
        }
        await self._broadcast_room_event(room, event)

    async def _handle_voice_signal(self, data: dict):
        room = await self.service._get_player_room(self.player_id)
        if not room:
            await self._send({"event": "error", "msg": "当前不在房间内，无法发送语音信令"})
            return

        target_player = data.get("target_player")
        room_player_ids = {p.id for p in room.players if not p.is_ai}
        if target_player not in room_player_ids:
            await self._send({"event": "error", "msg": "语音信令目标不在当前房间"})
            return

        signal_type = data.get("signal_type")
        if signal_type not in VOICE_SIGNAL_TYPES:
            await self._send({"event": "error", "msg": "不支持的语音信令类型"})
            return

        payload = data.get("payload")
        if not isinstance(payload, dict):
            await self._send({"event": "error", "msg": "语音信令内容格式不正确"})
            return

        payload_size = len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        if payload_size > VOICE_SIGNAL_MAX_PAYLOAD_BYTES:
            await self._send({"event": "error", "msg": "语音信令内容过大"})
            return

        await self.manager.send_to_player(target_player, {
            "event": "voice_signal",
            "player": self.player_id,
            "target_player": target_player,
            "signal_type": signal_type,
            "payload": payload,
        })
```

In `_handle_message`, add before `sync_room_state`:

```python
        elif action == "voice_state":
            await self._handle_voice_state(data)

        elif action == "voice_signal":
            await self._handle_voice_signal(data)
```

- [ ] **Step 4: Run backend tests to verify GREEN**

Run: `python -m pytest backend/tests/test_game_voice_signaling.py -v`

Expected: PASS, 4 tests passing.

- [ ] **Step 5: Run related websocket regression tests**

Run: `python -m pytest backend/tests/test_game_websocket.py -v`

Expected: PASS.

- [ ] **Step 6: Commit Task 1**

```bash
git add backend/tests/test_game_voice_signaling.py backend/app/interfaces/websocket/game_handler.py
git commit -m "feat: add game voice signaling"
```

---

### Task 2: 快捷语共享常量与 WebSocket 事件分发

**Files:**
- Create: `frontend/src/constants/chatPresets.ts`
- Create: `frontend/src/composables/gameVoiceEvents.ts`
- Create: `frontend/src/composables/__tests__/gameVoiceEvents.spec.ts`
- Modify: `frontend/src/composables/useGameWebSocket.ts`
- Modify: `frontend/src/composables/__tests__/useGameWebSocket.spec.ts`

**Interfaces:**
- Produces: `CHAT_PRESETS: readonly string[]`
- Produces: `onVoiceSignal(listener): () => void`
- Produces: `onVoiceState(listener): () => void`
- Produces: `notifyVoiceSignal(event): void`
- Produces: `notifyVoiceState(event): void`

- [ ] **Step 1: Write failing event bus test**

Create `frontend/src/composables/__tests__/gameVoiceEvents.spec.ts`:

```typescript
import { describe, expect, it, vi } from 'vitest'
import {
  notifyVoiceSignal,
  notifyVoiceState,
  onVoiceSignal,
  onVoiceState,
} from '../gameVoiceEvents'

describe('gameVoiceEvents', () => {
  it('notifies and unsubscribes voice signal listeners', () => {
    const listener = vi.fn()
    const unsubscribe = onVoiceSignal(listener)

    notifyVoiceSignal({
      player: 'p1',
      targetPlayer: 'p2',
      signalType: 'offer',
      payload: { type: 'offer', sdp: 'v=0' },
    })
    unsubscribe()
    notifyVoiceSignal({
      player: 'p1',
      targetPlayer: 'p2',
      signalType: 'answer',
      payload: { type: 'answer', sdp: 'v=0' },
    })

    expect(listener).toHaveBeenCalledTimes(1)
    expect(listener).toHaveBeenCalledWith({
      player: 'p1',
      targetPlayer: 'p2',
      signalType: 'offer',
      payload: { type: 'offer', sdp: 'v=0' },
    })
  })

  it('notifies and unsubscribes voice state listeners', () => {
    const listener = vi.fn()
    const unsubscribe = onVoiceState(listener)

    notifyVoiceState({ player: 'p1', enabled: true })
    unsubscribe()
    notifyVoiceState({ player: 'p1', enabled: false })

    expect(listener).toHaveBeenCalledTimes(1)
    expect(listener).toHaveBeenCalledWith({ player: 'p1', enabled: true })
  })
})
```

- [ ] **Step 2: Run event bus test to verify RED**

Run: `cd frontend && npm run test:unit -- src/composables/__tests__/gameVoiceEvents.spec.ts --run`

Expected: FAIL because `../gameVoiceEvents` does not exist.

- [ ] **Step 3: Implement event bus and chat constants**

Create `frontend/src/composables/gameVoiceEvents.ts`:

```typescript
export type VoiceSignalType = 'offer' | 'answer' | 'ice_candidate'

export interface VoiceSignalEvent {
  player: string
  targetPlayer: string
  signalType: VoiceSignalType
  payload: Record<string, unknown>
}

export interface VoiceStateEvent {
  player: string
  enabled: boolean
}

type Listener<T> = (event: T) => void

const voiceSignalListeners = new Set<Listener<VoiceSignalEvent>>()
const voiceStateListeners = new Set<Listener<VoiceStateEvent>>()

export function onVoiceSignal(listener: Listener<VoiceSignalEvent>) {
  voiceSignalListeners.add(listener)
  return () => voiceSignalListeners.delete(listener)
}

export function notifyVoiceSignal(event: VoiceSignalEvent) {
  voiceSignalListeners.forEach(listener => listener(event))
}

export function onVoiceState(listener: Listener<VoiceStateEvent>) {
  voiceStateListeners.add(listener)
  return () => voiceStateListeners.delete(listener)
}

export function notifyVoiceState(event: VoiceStateEvent) {
  voiceStateListeners.forEach(listener => listener(event))
}
```

Create `frontend/src/constants/chatPresets.ts`:

```typescript
export const CHAT_PRESETS = [
  '快点吧，牌都快睡着了！',
  '我这手牌，地主看了都沉默。',
  '别慌，我先假装很会玩。',
  '这牌不叫地主，对不起我的勇气。',
  '你这操作，有点像地主安插的卧底。',
  '我不是不出，我是在酝酿奇迹。',
  '炸弹没有，气势先炸一下。',
  '让你一手，主要是我没得选。',
  '我摊牌了，我全靠感觉。',
  '别催，脑子正在重新洗牌。',
  '这波我看懂了，但牌没看懂。',
  '队友稳住，我正在和命运谈判。',
  '地主别笑，春天还没到呢。',
  '我有一个大胆的想法，先不实现。',
  '牌很好，下把一定赢。',
  '好家伙，这都能接上？',
] as const
```

- [ ] **Step 4: Add failing WebSocket dispatch test**

Modify `frontend/src/composables/__tests__/useGameWebSocket.spec.ts`:

```typescript
import { onVoiceSignal, onVoiceState } from '../gameVoiceEvents'
```

Inside `describe('useGameWebSocket', () => { ... })`, add:

```typescript
  it('dispatches voice signaling events from websocket messages', () => {
    const signalListener = vi.fn()
    const stateListener = vi.fn()
    const unsubscribeSignal = onVoiceSignal(signalListener)
    const unsubscribeState = onVoiceState(stateListener)
    const playerStore = usePlayerStore()
    playerStore.playerId = 'p2'
    playerStore.authToken = 'token'

    const { connect } = useGameWebSocket()
    connect()
    const socket = MockWebSocket.instances[0]!

    socket.onmessage?.(new MessageEvent('message', {
      data: JSON.stringify({
        event: 'voice_signal',
        player: 'p1',
        target_player: 'p2',
        signal_type: 'offer',
        payload: { type: 'offer', sdp: 'v=0' },
      }),
    }))
    socket.onmessage?.(new MessageEvent('message', {
      data: JSON.stringify({
        event: 'voice_state',
        player: 'p1',
        enabled: true,
      }),
    }))

    expect(signalListener).toHaveBeenCalledWith({
      player: 'p1',
      targetPlayer: 'p2',
      signalType: 'offer',
      payload: { type: 'offer', sdp: 'v=0' },
    })
    expect(stateListener).toHaveBeenCalledWith({ player: 'p1', enabled: true })
    unsubscribeSignal()
    unsubscribeState()
  })

  it('uses shared funny quick chat presets for chat bubbles', async () => {
    const playerStore = usePlayerStore()
    playerStore.playerId = 'p1'
    playerStore.authToken = 'token'

    const { connect } = useGameWebSocket()
    connect()
    const socket = MockWebSocket.instances[0]!

    socket.onmessage?.(new MessageEvent('message', {
      data: JSON.stringify({
        event: 'chat_msg',
        player: 'p2',
        msg_id: 0,
      }),
    }))

    const { useGameStore } = await import('@/stores/gameStore')
    const gameStore = useGameStore()
    expect(gameStore.playerActions.p2).toBe('快点吧，牌都快睡着了！')
  })
```

- [ ] **Step 5: Run WebSocket tests to verify RED**

Run: `cd frontend && npm run test:unit -- src/composables/__tests__/useGameWebSocket.spec.ts --run`

Expected: FAIL because `useGameWebSocket.ts` does not dispatch voice events and still uses inline old presets.

- [ ] **Step 6: Implement WebSocket dispatch and shared chat presets**

Modify imports in `frontend/src/composables/useGameWebSocket.ts`:

```typescript
import { CHAT_PRESETS } from '@/constants/chatPresets'
import { notifyVoiceSignal, notifyVoiceState } from './gameVoiceEvents'
```

Replace the inline `presets` block in `case 'chat_msg'` with:

```typescript
        const msg = CHAT_PRESETS[data.msg_id] || '...'
```

Add cases before `case 'reconnected':`:

```typescript
      case 'voice_signal':
        notifyVoiceSignal({
          player: data.player,
          targetPlayer: data.target_player,
          signalType: data.signal_type,
          payload: data.payload,
        })
        break
      case 'voice_state':
        notifyVoiceState({
          player: data.player,
          enabled: Boolean(data.enabled),
        })
        break
```

- [ ] **Step 7: Run frontend tests to verify GREEN**

Run: `cd frontend && npm run test:unit -- src/composables/__tests__/gameVoiceEvents.spec.ts src/composables/__tests__/useGameWebSocket.spec.ts --run`

Expected: PASS.

- [ ] **Step 8: Commit Task 2**

```bash
git add frontend/src/constants/chatPresets.ts frontend/src/composables/gameVoiceEvents.ts frontend/src/composables/__tests__/gameVoiceEvents.spec.ts frontend/src/composables/useGameWebSocket.ts frontend/src/composables/__tests__/useGameWebSocket.spec.ts
git commit -m "feat: share quick chat presets and voice events"
```

---

### Task 3: 前端 WebRTC 房间语音 composable

**Files:**
- Create: `frontend/src/composables/useRoomVoiceChat.ts`
- Create: `frontend/src/composables/__tests__/useRoomVoiceChat.spec.ts`

**Interfaces:**
- Consumes: `sendAction(payload: Record<string, unknown>): void`
- Consumes: `onVoiceSignal(listener)` and `onVoiceState(listener)`
- Produces: `useRoomVoiceChat(options)`
- Produces:
  - `isVoiceEnabled: Ref<boolean>`
  - `isConnecting: Ref<boolean>`
  - `voiceError: Ref<string>`
  - `remoteVoicePlayers: Ref<Record<string, boolean>>`
  - `toggleVoice(): Promise<void>`
  - `startVoice(): Promise<void>`
  - `stopVoice(): void`
  - `dispose(): void`

- [ ] **Step 1: Write failing useRoomVoiceChat tests**

Create `frontend/src/composables/__tests__/useRoomVoiceChat.spec.ts`:

```typescript
// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { notifyVoiceSignal, notifyVoiceState } from '../gameVoiceEvents'

class MockMediaStreamTrack {
  stopped = false
  stop = vi.fn(() => {
    this.stopped = true
  })
}

class MockMediaStream {
  tracks = [new MockMediaStreamTrack()]
  getTracks = vi.fn(() => this.tracks)
}

class MockPeerConnection {
  static instances: MockPeerConnection[] = []
  localDescription: RTCSessionDescriptionInit | null = null
  remoteDescription: RTCSessionDescriptionInit | null = null
  onicecandidate: ((event: RTCPeerConnectionIceEvent) => void) | null = null
  ontrack: ((event: RTCTrackEvent) => void) | null = null
  closed = false
  candidates: RTCIceCandidateInit[] = []

  constructor() {
    MockPeerConnection.instances.push(this)
  }

  addTrack = vi.fn()
  createOffer = vi.fn(async () => ({ type: 'offer', sdp: 'offer-sdp' }) as RTCSessionDescriptionInit)
  createAnswer = vi.fn(async () => ({ type: 'answer', sdp: 'answer-sdp' }) as RTCSessionDescriptionInit)
  setLocalDescription = vi.fn(async (description: RTCSessionDescriptionInit) => {
    this.localDescription = description
  })
  setRemoteDescription = vi.fn(async (description: RTCSessionDescriptionInit) => {
    this.remoteDescription = description
  })
  addIceCandidate = vi.fn(async (candidate: RTCIceCandidateInit) => {
    this.candidates.push(candidate)
  })
  close = vi.fn(() => {
    this.closed = true
  })
}

describe('useRoomVoiceChat', () => {
  let stream: MockMediaStream
  let sendAction: ReturnType<typeof vi.fn>

  beforeEach(() => {
    vi.resetModules()
    stream = new MockMediaStream()
    sendAction = vi.fn()
    MockPeerConnection.instances = []
    vi.stubGlobal('RTCPeerConnection', MockPeerConnection)
    vi.stubGlobal('RTCSessionDescription', function (description: RTCSessionDescriptionInit) {
      return description
    })
    vi.stubGlobal('RTCIceCandidate', function (candidate: RTCIceCandidateInit) {
      return candidate
    })
    Object.defineProperty(globalThis.navigator, 'mediaDevices', {
      value: { getUserMedia: vi.fn(async () => stream) },
      configurable: true,
    })
  })

  it('starts voice, opens peers for room players, and sends voice_state', async () => {
    const { useRoomVoiceChat } = await import('../useRoomVoiceChat')
    const voice = useRoomVoiceChat({
      selfPlayerId: 'p1',
      roomPlayerIds: () => ['p1', 'p2', 'p3'],
      sendAction,
    })

    await voice.startVoice()

    expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalledWith({ audio: true })
    expect(sendAction).toHaveBeenCalledWith({ action: 'voice_state', enabled: true })
    expect(sendAction).toHaveBeenCalledWith({
      action: 'voice_signal',
      target_player: 'p2',
      signal_type: 'offer',
      payload: { type: 'offer', sdp: 'offer-sdp' },
    })
    expect(sendAction).toHaveBeenCalledWith({
      action: 'voice_signal',
      target_player: 'p3',
      signal_type: 'offer',
      payload: { type: 'offer', sdp: 'offer-sdp' },
    })
    expect(voice.isVoiceEnabled.value).toBe(true)
  })

  it('stops tracks and closes peer connections when stopped', async () => {
    const { useRoomVoiceChat } = await import('../useRoomVoiceChat')
    const voice = useRoomVoiceChat({
      selfPlayerId: 'p1',
      roomPlayerIds: () => ['p1', 'p2'],
      sendAction,
    })

    await voice.startVoice()
    voice.stopVoice()

    expect(stream.tracks[0]!.stop).toHaveBeenCalled()
    expect(MockPeerConnection.instances[0]!.close).toHaveBeenCalled()
    expect(sendAction).toHaveBeenLastCalledWith({ action: 'voice_state', enabled: false })
    expect(voice.isVoiceEnabled.value).toBe(false)
  })

  it('answers incoming offers and applies ice candidates', async () => {
    const { useRoomVoiceChat } = await import('../useRoomVoiceChat')
    const voice = useRoomVoiceChat({
      selfPlayerId: 'p2',
      roomPlayerIds: () => ['p1', 'p2'],
      sendAction,
    })

    await voice.startVoice()
    notifyVoiceSignal({
      player: 'p1',
      targetPlayer: 'p2',
      signalType: 'offer',
      payload: { type: 'offer', sdp: 'remote-offer' },
    })
    await Promise.resolve()
    await Promise.resolve()
    notifyVoiceSignal({
      player: 'p1',
      targetPlayer: 'p2',
      signalType: 'ice_candidate',
      payload: { candidate: 'candidate-1' },
    })
    await Promise.resolve()

    const peer = MockPeerConnection.instances.find(item => item.remoteDescription?.sdp === 'remote-offer')
    expect(peer).toBeDefined()
    expect(sendAction).toHaveBeenCalledWith({
      action: 'voice_signal',
      target_player: 'p1',
      signal_type: 'answer',
      payload: { type: 'answer', sdp: 'answer-sdp' },
    })
    expect(peer!.candidates).toEqual([{ candidate: 'candidate-1' }])
  })

  it('sets an error when microphone permission fails', async () => {
    vi.mocked(navigator.mediaDevices.getUserMedia).mockRejectedValueOnce(new Error('denied'))
    const { useRoomVoiceChat } = await import('../useRoomVoiceChat')
    const voice = useRoomVoiceChat({
      selfPlayerId: 'p1',
      roomPlayerIds: () => ['p1', 'p2'],
      sendAction,
    })

    await voice.startVoice()

    expect(voice.voiceError.value).toBe('麦克风权限未开启')
    expect(voice.isVoiceEnabled.value).toBe(false)
    expect(sendAction).not.toHaveBeenCalledWith({ action: 'voice_state', enabled: true })
  })
})
```

- [ ] **Step 2: Run useRoomVoiceChat tests to verify RED**

Run: `cd frontend && npm run test:unit -- src/composables/__tests__/useRoomVoiceChat.spec.ts --run`

Expected: FAIL because `../useRoomVoiceChat` does not exist.

- [ ] **Step 3: Implement useRoomVoiceChat**

Create `frontend/src/composables/useRoomVoiceChat.ts`:

```typescript
import { ref } from 'vue'
import {
  type VoiceSignalEvent,
  type VoiceSignalType,
  onVoiceSignal,
  onVoiceState,
} from './gameVoiceEvents'

interface UseRoomVoiceChatOptions {
  selfPlayerId: string
  roomPlayerIds: () => string[]
  sendAction: (payload: Record<string, unknown>) => void
}

const rtcConfig: RTCConfiguration = {
  iceServers: [{ urls: 'stun:stun.l.google.com:19302' }],
}

export function useRoomVoiceChat(options: UseRoomVoiceChatOptions) {
  const isVoiceEnabled = ref(false)
  const isConnecting = ref(false)
  const voiceError = ref('')
  const remoteVoicePlayers = ref<Record<string, boolean>>({})
  const peers = new Map<string, RTCPeerConnection>()
  let localStream: MediaStream | null = null

  function sendSignal(targetPlayer: string, signalType: VoiceSignalType, payload: Record<string, unknown>) {
    options.sendAction({
      action: 'voice_signal',
      target_player: targetPlayer,
      signal_type: signalType,
      payload,
    })
  }

  function getRemotePlayerIds() {
    return options.roomPlayerIds().filter(playerId => playerId && playerId !== options.selfPlayerId)
  }

  function attachRemoteAudio(playerId: string, stream: MediaStream) {
    const id = `voice-audio-${playerId}`
    let audio = document.getElementById(id) as HTMLAudioElement | null
    if (!audio) {
      audio = document.createElement('audio')
      audio.id = id
      audio.autoplay = true
      document.body.appendChild(audio)
    }
    audio.srcObject = stream
    void audio.play?.().catch(() => {
      voiceError.value = '语音播放受阻，请点击页面后重试'
    })
  }

  function removeRemoteAudio(playerId: string) {
    document.getElementById(`voice-audio-${playerId}`)?.remove()
  }

  function createPeer(playerId: string) {
    const existing = peers.get(playerId)
    if (existing) return existing

    const peer = new RTCPeerConnection(rtcConfig)
    peers.set(playerId, peer)

    localStream?.getTracks().forEach(track => {
      peer.addTrack(track, localStream as MediaStream)
    })

    peer.onicecandidate = event => {
      if (event.candidate) {
        sendSignal(playerId, 'ice_candidate', event.candidate.toJSON())
      }
    }
    peer.ontrack = event => {
      const [stream] = event.streams
      if (stream) {
        remoteVoicePlayers.value = { ...remoteVoicePlayers.value, [playerId]: true }
        attachRemoteAudio(playerId, stream)
      }
    }
    peer.onconnectionstatechange = () => {
      if (['failed', 'closed', 'disconnected'].includes(peer.connectionState)) {
        remoteVoicePlayers.value = { ...remoteVoicePlayers.value, [playerId]: false }
        removeRemoteAudio(playerId)
      }
    }

    return peer
  }

  async function createOfferFor(playerId: string) {
    const peer = createPeer(playerId)
    const offer = await peer.createOffer()
    await peer.setLocalDescription(offer)
    sendSignal(playerId, 'offer', offer as unknown as Record<string, unknown>)
  }

  async function handleVoiceSignal(event: VoiceSignalEvent) {
    if (event.targetPlayer !== options.selfPlayerId || !isVoiceEnabled.value) return

    const peer = createPeer(event.player)
    if (event.signalType === 'offer') {
      await peer.setRemoteDescription(new RTCSessionDescription(event.payload as RTCSessionDescriptionInit))
      const answer = await peer.createAnswer()
      await peer.setLocalDescription(answer)
      sendSignal(event.player, 'answer', answer as unknown as Record<string, unknown>)
      return
    }

    if (event.signalType === 'answer') {
      await peer.setRemoteDescription(new RTCSessionDescription(event.payload as RTCSessionDescriptionInit))
      return
    }

    if (event.signalType === 'ice_candidate') {
      await peer.addIceCandidate(new RTCIceCandidate(event.payload as RTCIceCandidateInit))
    }
  }

  const unsubscribeSignal = onVoiceSignal(event => {
    void handleVoiceSignal(event).catch(() => {
      voiceError.value = '语音连接失败，可重新开启'
    })
  })

  const unsubscribeState = onVoiceState(event => {
    if (event.player === options.selfPlayerId) return
    remoteVoicePlayers.value = { ...remoteVoicePlayers.value, [event.player]: event.enabled }
    if (!event.enabled) {
      const peer = peers.get(event.player)
      peer?.close()
      peers.delete(event.player)
      removeRemoteAudio(event.player)
    }
  })

  async function startVoice() {
    if (isVoiceEnabled.value || isConnecting.value) return
    voiceError.value = ''

    if (!navigator.mediaDevices?.getUserMedia || typeof RTCPeerConnection === 'undefined') {
      voiceError.value = '当前浏览器不支持语音'
      return
    }

    isConnecting.value = true
    try {
      localStream = await navigator.mediaDevices.getUserMedia({ audio: true })
      isVoiceEnabled.value = true
      options.sendAction({ action: 'voice_state', enabled: true })
      await Promise.all(getRemotePlayerIds().map(playerId => createOfferFor(playerId)))
    } catch {
      voiceError.value = '麦克风权限未开启'
      stopLocalTracks()
    } finally {
      isConnecting.value = false
    }
  }

  function stopLocalTracks() {
    localStream?.getTracks().forEach(track => track.stop())
    localStream = null
  }

  function stopVoice() {
    const wasEnabled = isVoiceEnabled.value
    stopLocalTracks()
    peers.forEach((peer, playerId) => {
      peer.close()
      removeRemoteAudio(playerId)
    })
    peers.clear()
    remoteVoicePlayers.value = {}
    isVoiceEnabled.value = false
    isConnecting.value = false
    if (wasEnabled) {
      options.sendAction({ action: 'voice_state', enabled: false })
    }
  }

  async function toggleVoice() {
    if (isVoiceEnabled.value) {
      stopVoice()
    } else {
      await startVoice()
    }
  }

  function dispose() {
    stopVoice()
    unsubscribeSignal()
    unsubscribeState()
  }

  return {
    isVoiceEnabled,
    isConnecting,
    voiceError,
    remoteVoicePlayers,
    toggleVoice,
    startVoice,
    stopVoice,
    dispose,
  }
}
```

- [ ] **Step 4: Run useRoomVoiceChat tests to verify GREEN**

Run: `cd frontend && npm run test:unit -- src/composables/__tests__/useRoomVoiceChat.spec.ts --run`

Expected: PASS.

- [ ] **Step 5: Commit Task 3**

```bash
git add frontend/src/composables/useRoomVoiceChat.ts frontend/src/composables/__tests__/useRoomVoiceChat.spec.ts
git commit -m "feat: add room voice chat composable"
```

---

### Task 4: 对局页麦克风 UI 与快捷语扩充展示

**Files:**
- Modify: `frontend/src/views/GameRoomView.vue`

**Interfaces:**
- Consumes: `CHAT_PRESETS`
- Consumes: `useRoomVoiceChat({ selfPlayerId, roomPlayerIds, sendAction })`

- [ ] **Step 1: Modify GameRoomView script**

In `frontend/src/views/GameRoomView.vue`, add imports:

```typescript
import { CHAT_PRESETS } from '@/constants/chatPresets'
import { useRoomVoiceChat } from '@/composables/useRoomVoiceChat'
```

Delete the local `const CHAT_PRESETS = [...]` block.

After `const showChatMenu = ref(false)`, add:

```typescript
const roomPlayerIds = () => gameStore.players.map(player => player.id).filter(Boolean)
const roomVoice = useRoomVoiceChat({
  selfPlayerId: playerStore.playerId,
  roomPlayerIds,
  sendAction,
})

async function handleToggleVoice() {
  playSound('btnClick')
  await roomVoice.toggleVoice()
}
```

In `onUnmounted`, add:

```typescript
  roomVoice.dispose()
```

- [ ] **Step 2: Modify GameRoomView template**

Replace the existing chat trigger area with:

```vue
    <div class="chat-trigger-area">
      <button
        class="btn-voice"
        :class="{ active: roomVoice.isVoiceEnabled.value, connecting: roomVoice.isConnecting.value }"
        :title="roomVoice.isVoiceEnabled.value ? '关闭语音' : '开启语音'"
        @click="handleToggleVoice"
      >
        {{ roomVoice.isConnecting.value ? '连接中' : roomVoice.isVoiceEnabled.value ? '麦克风开' : '麦克风' }}
      </button>
      <button class="btn-chat" @click="showChatMenu = !showChatMenu">
        快捷语
      </button>
      <div v-if="roomVoice.voiceError.value" class="voice-error">
        {{ roomVoice.voiceError.value }}
      </div>
      <div v-if="showChatMenu" class="chat-menu glass-panel">
        <div
          v-for="(text, idx) in CHAT_PRESETS"
          :key="idx"
          class="chat-menu-item"
          @click="handleSendChat(idx)"
        >
          {{ text }}
        </div>
      </div>
    </div>
```

- [ ] **Step 3: Modify GameRoomView styles**

Replace `.chat-trigger-area`, `.btn-chat`, and `.chat-menu` related CSS with:

```css
.chat-trigger-area {
  position: absolute;
  bottom: 20px;
  right: 20px;
  z-index: 100;
  display: flex;
  align-items: flex-end;
  gap: 8px;
}

.btn-chat,
.btn-voice {
  border: 1px solid #ffd54f;
  color: #3e2723;
  min-width: 76px;
  min-height: 34px;
  padding: 6px 12px;
  border-radius: 20px;
  font-weight: bold;
  cursor: pointer;
  white-space: nowrap;
}

.btn-chat {
  background: linear-gradient(to bottom, #ffb300, #ff8f00);
}

.btn-voice {
  background: linear-gradient(to bottom, #b3e5fc, #4fc3f7);
  border-color: #e1f5fe;
}

.btn-voice.active {
  background: linear-gradient(to bottom, #81c784, #43a047);
  color: #fff;
  border-color: #c8e6c9;
}

.btn-voice.connecting {
  opacity: 0.78;
}

.voice-error {
  position: absolute;
  right: 0;
  bottom: 44px;
  width: 220px;
  padding: 8px 10px;
  border-radius: 6px;
  background: rgba(86, 19, 19, 0.9);
  color: #fff3e0;
  font-size: 0.8rem;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
}

.chat-menu {
  position: absolute;
  right: 0;
  bottom: 44px;
  width: min(300px, calc(100vw - 40px));
  max-height: min(420px, calc(100vh - 140px));
  overflow-y: auto;
  padding: 8px 0;
  display: flex;
  flex-direction: column;
  z-index: 50;
}
```

- [ ] **Step 4: Run TypeScript build check**

Run: `cd frontend && npm run build`

Expected: PASS. If Vue template unwrapping rejects `.value`, change template bindings from `roomVoice.isVoiceEnabled.value` to `roomVoice.isVoiceEnabled` and rerun.

- [ ] **Step 5: Commit Task 4**

```bash
git add frontend/src/views/GameRoomView.vue
git commit -m "feat: add room voice controls"
```

---

### Task 5: 综合验证与手动联调

**Files:**
- No new production files.

**Interfaces:**
- Verifies all previous tasks.

- [ ] **Step 1: Run backend verification**

Run: `python -m pytest backend/tests/test_game_voice_signaling.py backend/tests/test_game_websocket.py -v`

Expected: PASS.

- [ ] **Step 2: Run frontend verification**

Run: `cd frontend && npm run test:unit -- src/composables/__tests__/gameVoiceEvents.spec.ts src/composables/__tests__/useGameWebSocket.spec.ts src/composables/__tests__/useRoomVoiceChat.spec.ts --run`

Expected: PASS.

- [ ] **Step 3: Run frontend build**

Run: `cd frontend && npm run build`

Expected: PASS.

- [ ] **Step 4: Manual browser smoke test**

Run backend:

```bash
cd backend
python main.py
```

Run frontend:

```bash
cd frontend
npm run dev
```

Open two browser windows with different test accounts. Verify:

- 两个玩家进入同一房间后，快捷语菜单显示 16 条搞笑短语。
- 玩家 A 发送快捷语，玩家 B 能看到对应气泡。
- 玩家 A 点击“麦克风”，浏览器请求麦克风权限。
- 玩家 B 点击“麦克风”后，两边能建立语音。
- 任一方关闭语音后，对端状态不再显示开启。
- 刷新或离开对局页后，浏览器麦克风指示消失。

- [ ] **Step 5: Final commit if manual fixes were needed**

If Step 4 required code fixes, commit only those files:

```bash
git add <fixed-files>
git commit -m "fix: stabilize room voice chat"
```

If no fixes were needed, do not create an empty commit.

---

## 自审记录

- Spec coverage: 快捷语扩充由 Task 2 和 Task 4 覆盖；WebRTC 信令由 Task 1 覆盖；前端 P2P 语音由 Task 3 覆盖；UI 和清理由 Task 4 覆盖；验证由 Task 5 覆盖。
- Placeholder scan: 本计划不包含占位式说明或未落到具体代码与命令的步骤。
- Type consistency: `signal_type` 是后端 JSON 字段；前端事件对象中映射为 `signalType`。`target_player` 映射为 `targetPlayer`。`voice_state`、`voice_signal` 的动作名和事件名保持一致。
