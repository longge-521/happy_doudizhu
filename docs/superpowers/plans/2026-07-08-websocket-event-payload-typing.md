# WebSocket 前端事件 payload 类型化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `useGameWebSocket.ts` 的服务端事件入口从 `any` 收紧为明确的 `GameServerEvent` 联合类型。

**Architecture:** 本计划只修改前端 WebSocket composable 的类型边界。事件处理 switch 保留在 `useGameWebSocket.ts` 内，不拆 dispatcher；`room_state` 复用 `gameStore.ts` 已导出的 `RoomStatePayload`；现有 WebSocket 行为测试用于保护运行行为不变。

**Tech Stack:** Vue 3、Pinia、TypeScript、Vitest、Vite。

## Global Constraints

- 文档使用中文。
- 禁止批量删除文件或目录。
- 不修改后端 WebSocket 事件协议。
- 不修改客户端发送动作 `sendAction(action: Record<string, any>)`。
- 不拆分 `useGameWebSocket.ts` 的事件 dispatcher。
- 不调整 UI、音效、动画或游戏规则。
- 不引入新的运行时依赖。
- 用户人工确认完整无误前不执行 `git commit`。

---

## 文件结构

- 修改：`frontend/src/composables/useGameWebSocket.ts`
  - 新增局部事件 payload 类型。
  - 将 `handleEvent(data: any)` 收紧为 `handleEvent(data: GameServerEvent)`。
  - 将 `game_start.players.map((p: any) => ...)` 改为明确的 `RoomStatePlayerPayload` 类型。
- 验证：`frontend/src/composables/__tests__/useGameWebSocket.spec.ts`
  - 使用现有测试保护双倍、语音、快捷聊天和出牌报警行为。
- 新增：`docs/superpowers/specs/2026-07-08-websocket-event-payload-typing-design.md`
  - 记录设计边界。
- 新增：`docs/superpowers/plans/2026-07-08-websocket-event-payload-typing.md`
  - 记录执行步骤。

---

### Task 1：建立事件类型缺失的构建失败

**Files:**
- Modify: `frontend/src/composables/useGameWebSocket.ts`

**Interfaces:**
- Produces: 一个预期的 TypeScript 构建失败，提示 `GameServerEvent` 尚未定义。

- [x] **Step 1：写入失败点**

在 `frontend/src/composables/useGameWebSocket.ts` 中，只先将：

```ts
function handleEvent(data: any) {
```

改成：

```ts
function handleEvent(data: GameServerEvent) {
```

不要先定义 `GameServerEvent`。

- [x] **Step 2：运行构建确认失败**

运行：

```powershell
cd frontend
npm.cmd run build
```

预期：失败，原因是 `Cannot find name 'GameServerEvent'` 或等价 TypeScript 错误。

---

### Task 2：新增最小服务端事件联合类型

**Files:**
- Modify: `frontend/src/composables/useGameWebSocket.ts`

**Interfaces:**
- Consumes:
  - `RoomStatePayload`
  - `RoomStatePlayerPayload`
  - `DoublingChoice`
- Produces:
  - `type GameServerEvent = ...`
  - `handleEvent(data: GameServerEvent): void`

- [x] **Step 1：导入已存在的 store payload 类型**

将 `useGameWebSocket.ts` 顶部：

```ts
import { useGameStore } from '@/stores/gameStore'
```

改为：

```ts
import {
  useGameStore,
  type DoublingChoice,
  type RoomStatePayload,
  type RoomStatePlayerPayload,
} from '@/stores/gameStore'
```

- [x] **Step 2：新增事件 payload 类型**

在计时器变量之后新增：

```ts
type WinnerSide = 'landlord' | 'farmer'

type BaseRoomStateEvent<TEvent extends string> = {
  event: TEvent
  room_state?: RoomStatePayload
}

type GameStartEvent = {
  event: 'game_start'
  room_id?: string
  hand: number[]
  current_turn: string
  turn_deadline?: number
  players?: RoomStatePlayerPayload[]
}

type DoubleChosenEvent = BaseRoomStateEvent<'double_chosen'> & {
  player: string
  choice: DoublingChoice
  label?: string
  multiplier?: number
}

type CardsPlayedEvent = BaseRoomStateEvent<'cards_played'> & {
  player: string
  cards: number[]
}

type GameOverRoomState = RoomStatePayload & {
  phase?: 'PLAYING'
}

type GameOverEvent = {
  event: 'game_over'
  winner: string
  winner_side: WinnerSide
  scores: Record<string, number>
  multiplier: number
  all_hands?: Record<string, number[]>
  room_state?: GameOverRoomState
}

type VoiceSignalEvent = {
  event: 'voice_signal'
  player: string
  target_player: string
  signal_type: VoiceSignalType
  payload: Record<string, unknown>
}

type VoiceStateEvent = {
  event: 'voice_state'
  player: string
  enabled: boolean
}

type GameServerEvent =
  | { event: 'match_waiting' }
  | { event: 'match_cancelled' }
  | (BaseRoomStateEvent<'match_success'> & { room_id: string })
  | GameStartEvent
  | (BaseRoomStateEvent<'call_made'> & { player: string })
  | (BaseRoomStateEvent<'call_skipped'> & { player: string })
  | (BaseRoomStateEvent<'landlord_decided'> & {
      landlord: string
      bottom_cards?: number[]
      multiplier?: number
    })
  | DoubleChosenEvent
  | (BaseRoomStateEvent<'doubling_finished'> & {
      current_turn?: string | null
      multiplier?: number
    })
  | BaseRoomStateEvent<'redeal'>
  | CardsPlayedEvent
  | (BaseRoomStateEvent<'turn_passed'> & { player: string })
  | GameOverEvent
  | { event: 'chat_msg'; player: string; msg_id: number }
  | VoiceSignalEvent
  | VoiceStateEvent
  | (RoomStatePayload & { event: 'reconnected' })
  | { event: 'error'; msg?: string }
```

- [x] **Step 3：收紧 `JSON.parse()` 到事件类型**

将：

```ts
const data = JSON.parse(event.data)
handleEvent(data)
```

改为：

```ts
const data = JSON.parse(event.data) as GameServerEvent
handleEvent(data)
```

- [x] **Step 4：移除 `game_start.players` 的 `any`**

将：

```ts
gameStore.players = data.players.map((p: any) => ({
```

改为：

```ts
gameStore.players = data.players.map((p) => ({
```

- [x] **Step 5：运行 targeted 测试**

运行：

```powershell
cd frontend
npm.cmd run test:unit -- --run src/composables/__tests__/useGameWebSocket.spec.ts
```

预期：通过，现有 WebSocket 行为不变。

---

### Task 3：前端全量验证

**Files:**
- Verify only.

**Interfaces:**
- Consumes: Task 1 和 Task 2 的改动。
- Produces: 可供用户测试与确认的验证结果。

- [x] **Step 1：运行前端全量单测**

```powershell
cd frontend
npm.cmd run test:unit -- --run
```

预期：全部通过。

- [x] **Step 2：运行前端构建**

```powershell
cd frontend
npm.cmd run build
```

预期：构建通过，没有 TypeScript 错误。

- [x] **Step 3：检查 diff**

```powershell
git diff --check
git diff --stat
```

预期：没有空白错误，改动范围只包含本专项文档和 `useGameWebSocket.ts`。

## 自查结果

- 设计规约中的目标均有对应任务覆盖。
- 本计划没有占位符或未决项。
- 类型名称、事件字段和现有代码消费字段保持一致。
- 本计划不包含 commit 步骤，等待用户人工确认后再提交。
