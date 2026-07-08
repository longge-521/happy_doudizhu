# gameStore 房间状态类型收紧实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 `gameStore.updateFromRoomState()` 增加明确的房间状态输入类型，并用单元测试固定后端 snake_case 到前端状态的映射行为。

**Architecture:** 本计划只修改 Pinia store 边界。`gameStore.ts` 负责定义当前前端实际消费的房间状态 payload 类型，并继续执行原有状态映射；`gameStore.spec.ts` 负责验证状态映射和 reset 行为。WebSocket 协议、后端接口和 UI 不变。

**Tech Stack:** Vue 3、Pinia、TypeScript、Vitest、Vite。

## Global Constraints

- 文档使用中文。
- 禁止批量删除文件或目录。
- 不修改后端 WebSocket 或 REST 协议。
- 不调整 UI、音效、动画或游戏规则。
- 不引入新的运行时依赖。
- 用户人工确认完整无误前不执行 `git commit`。

---

## 文件结构

- 新建：`frontend/src/stores/__tests__/gameStore.spec.ts`
  - 负责验证 `updateFromRoomState()` 的状态映射、当前玩家剩余牌数兼容逻辑和 `reset()` 行为。
- 修改：`frontend/src/stores/gameStore.ts`
  - 负责新增房间状态 payload 类型，并将 `updateFromRoomState(state: any)` 收紧为 `updateFromRoomState(state: RoomStatePayload)`。

---

### Task 1：新增 gameStore 房间状态映射测试

**Files:**
- Create: `frontend/src/stores/__tests__/gameStore.spec.ts`

**Interfaces:**
- Consumes: `useGameStore()`、`RoomStatePayload`
- Produces: 对 `updateFromRoomState(state: RoomStatePayload)` 的行为约束

- [x] **Step 1：写失败测试**

新增 `frontend/src/stores/__tests__/gameStore.spec.ts`：

```ts
import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useGameStore, type RoomStatePayload } from '../gameStore'

describe('gameStore room state mapping', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('maps backend room state payload into frontend store state', () => {
    const store = useGameStore()
    const state: RoomStatePayload = {
      room_id: 'room-1',
      phase: 'DOUBLING',
      players: [
        {
          id: 'p1',
          nickname: 'Player One',
          is_ai: false,
          is_online: true,
          is_self: true,
          is_landlord: true,
        },
        {
          id: 'p2',
          nickname: 'AI Two',
          is_ai: true,
          is_online: false,
          remaining: 7,
          is_self: false,
          is_landlord: false,
        },
      ],
      hand: [52, 3, 17],
      current_turn: 'p2',
      turn_deadline: 12345,
      multiplier: 4,
      call_round: 2,
      call_scores: { p1: 3 },
      first_bidder: 'p1',
      landlord: 'p1',
      bottom_cards: [1, 2, 3],
      last_play: {
        player: 'p2',
        cards: [10, 11],
        card_type: 'PAIR',
      },
      base_score: 80,
      all_played_cards: [10, 11, 12],
      doubling_choices: {
        p1: 'super',
        p2: 'none',
      },
    }

    store.updateFromRoomState(state)

    expect(store.roomId).toBe('room-1')
    expect(store.gamePhase).toBe('DOUBLING')
    expect(store.myHand).toEqual([52, 17, 3])
    expect(store.players).toEqual([
      {
        id: 'p1',
        nickname: 'Player One',
        isAi: false,
        isOnline: true,
        remaining: 3,
        isLandlord: true,
        isSelf: true,
      },
      {
        id: 'p2',
        nickname: 'AI Two',
        isAi: true,
        isOnline: false,
        remaining: 7,
        isLandlord: false,
        isSelf: false,
      },
    ])
    expect(store.currentTurn).toBe('p2')
    expect(store.turnDeadline).toBe(12345)
    expect(store.multiplier).toBe(4)
    expect(store.callRound).toBe(2)
    expect(store.callScores).toEqual({ p1: 3 })
    expect(store.firstBidder).toBe('p1')
    expect(store.landlord).toBe('p1')
    expect(store.bottomCards).toEqual([1, 2, 3])
    expect(store.lastPlay).toEqual({
      player: 'p2',
      cards: [10, 11],
      cardType: 'PAIR',
    })
    expect(store.baseScore).toBe(80)
    expect(store.allPlayedCards).toEqual([10, 11, 12])
    expect(store.doublingChoices).toEqual({ p1: 'super', p2: 'none' })
  })

  it('resets room state fields after a mapped room state', () => {
    const store = useGameStore()
    store.updateFromRoomState({
      room_id: 'room-1',
      phase: 'PLAYING',
      players: [
        {
          id: 'p1',
          nickname: 'Player One',
          is_ai: false,
          is_online: true,
          remaining: 3,
        },
      ],
      hand: [3, 4, 5],
      current_turn: 'p1',
      multiplier: 8,
      doubling_choices: { p1: 'double' },
    })

    store.reset()

    expect(store.roomId).toBe('')
    expect(store.gamePhase).toBe('IDLE')
    expect(store.players).toEqual([])
    expect(store.myHand).toEqual([])
    expect(store.currentTurn).toBe('')
    expect(store.multiplier).toBe(1)
    expect(store.doublingChoices).toEqual({})
  })
})
```

- [x] **Step 2：确认失败原因**

运行：

```powershell
cd frontend
npm.cmd run build
```

预期：失败，原因是 `frontend/src/stores/gameStore.ts` 尚未导出 `RoomStatePayload`。

---

### Task 2：实现房间状态 payload 类型并收紧 store 入口

**Files:**
- Modify: `frontend/src/stores/gameStore.ts`

**Interfaces:**
- Consumes: Task 1 中测试声明的 `RoomStatePayload`
- Produces:
  - `export type GamePhase = 'IDLE' | 'MATCHING' | 'DEALING' | 'CALLING' | 'DOUBLING' | 'PLAYING' | 'SETTLING'`
  - `export interface RoomStatePlayerPayload`
  - `export interface RoomStateLastPlayPayload`
  - `export interface RoomStatePayload`
  - `updateFromRoomState(state: RoomStatePayload): void`

- [x] **Step 1：实现最小类型收紧**

在 `frontend/src/stores/gameStore.ts` 的 `DoublingChoice` 附近增加类型：

```ts
export type GamePhase = 'IDLE' | 'MATCHING' | 'DEALING' | 'CALLING' | 'DOUBLING' | 'PLAYING' | 'SETTLING'

export interface RoomStatePlayerPayload {
  id: string
  nickname: string
  is_ai: boolean
  is_online: boolean
  remaining?: number
  is_landlord?: boolean
  is_self?: boolean
}

export interface RoomStateLastPlayPayload {
  player: string | null
  cards?: number[]
  card_type: string | null
}

export interface RoomStatePayload {
  room_id?: string
  phase?: GamePhase
  players?: RoomStatePlayerPayload[]
  hand?: number[]
  current_turn?: string | null
  turn_deadline?: number | null
  multiplier?: number
  call_round?: number
  call_scores?: Record<string, number> | null
  first_bidder?: string | null
  landlord?: string | null
  bottom_cards?: number[]
  last_play?: RoomStateLastPlayPayload | null
  base_score?: number
  all_played_cards?: number[]
  doubling_choices?: Record<string, DoublingChoice> | null
}
```

并将：

```ts
const gamePhase = ref<string>('IDLE')
function updateFromRoomState(state: any) {
  if (state.players) players.value = state.players.map((p: any) => ({
```

改为：

```ts
const gamePhase = ref<GamePhase>('IDLE')
function updateFromRoomState(state: RoomStatePayload) {
  if (state.players) players.value = state.players.map((p) => ({
```

- [x] **Step 2：运行 targeted 测试**

运行：

```powershell
cd frontend
npm.cmd run test:unit -- --run src/stores/__tests__/gameStore.spec.ts
```

预期：通过。

---

### Task 3：全量前端验证

**Files:**
- Verify only.

**Interfaces:**
- Consumes: Task 1 和 Task 2 的改动
- Produces: 可提交前的验证结果

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

预期：没有空白错误，改动范围只包含本专项文档、`gameStore.ts` 和 `gameStore.spec.ts`。

## 自查结果

- 设计规约中的目标均有对应任务覆盖。
- 本计划没有占位符或未决项。
- 类型名称、函数签名和测试中的导入路径保持一致。
- 本计划不包含 commit 步骤，等待用户人工确认后再提交。
