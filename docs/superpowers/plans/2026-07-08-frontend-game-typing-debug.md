# 前端游戏链路类型与调试输出优化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 收紧前端游戏链路中 WebSocket 出站动作、结算数据、手牌动画计时器和调试日志的类型边界。

**Architecture:** 本轮不改运行协议，只在现有文件边界上补充 TypeScript 类型。新增一个小型 debug logger 工具，让目标文件不再直接调用 `console.log`。

**Tech Stack:** Vue 3、TypeScript、Pinia、Vitest、Vite。

## Global Constraints

- 文档使用中文。
- 禁止批量删除文件或目录。
- 不修改后端接口。
- 不修改 WebSocket 协议字段名。
- 不重构大页面。
- 用户人工确认完整无误前不执行 `git commit`。

---

## 文件结构

- 新增：`frontend/src/utils/debugLog.ts`
  - 统一开发环境 debug 输出。
- 修改：`frontend/src/composables/useGameWebSocket.ts`
  - 新增并导出 `GameClientAction`。
  - `sendAction()` 改为接收 `GameClientAction`。
  - 使用统一 debug logger。
- 修改：`frontend/src/stores/gameStore.ts`
  - 新增并导出 `WinnerSide` 和 `GameSettlement`。
  - `settlement` 改为 `GameSettlement | null`。
- 修改：`frontend/src/components/SettlementModal.vue`
  - 复用 `GameSettlement` 类型。
- 修改：`frontend/src/components/HandCards.vue`
  - 计时器类型收紧。
  - 使用统一 debug logger。
- 修改：`frontend/src/composables/__tests__/useGameWebSocket.spec.ts`
  - 补充 `sendAction()` 序列化测试。
- 修改：`frontend/src/stores/__tests__/gameStore.spec.ts`
  - 补充结算数据 reset 测试。
- 新增：`frontend/src/utils/__tests__/debugLog.spec.ts`
  - 覆盖 debug logger 当前开发环境输出行为。

---

### Task 1：记录当前静态扫描命中

**Files:**
- Verify only.

**Interfaces:**
- Consumes: 当前目标文件。
- Produces: 修改前 `any` 和 `console.log` 命中证据。

- [x] **Step 1：运行目标静态扫描**

```powershell
rg -n "\bany\b|console\.log" frontend/src/composables/useGameWebSocket.ts frontend/src/stores/gameStore.ts frontend/src/components/HandCards.vue
```

期望：命中 `sendAction(action: Record<string, any>)`、`settlement = ref<any>(null)`、`ref<any>` 计时器和两个 `console.log`。

---

### Task 2：补充行为保护测试

**Files:**
- Modify: `frontend/src/composables/__tests__/useGameWebSocket.spec.ts`
- Modify: `frontend/src/stores/__tests__/gameStore.spec.ts`
- Create: `frontend/src/utils/__tests__/debugLog.spec.ts`

**Interfaces:**
- Consumes: `useGameWebSocket().sendAction(action)`、`useGameStore().settlement`、`debugLog(...args)`。
- Produces: 修改前后均应保持的运行行为约束。

- [x] **Step 1：给 MockWebSocket 记录发送内容**

在 `frontend/src/composables/__tests__/useGameWebSocket.spec.ts` 的 `MockWebSocket` 中加入：

```ts
  sentMessages: string[] = []

  send(message: string) {
    this.sentMessages.push(message)
  }
```

- [x] **Step 2：补充 sendAction 序列化测试**

在 `useGameWebSocket` describe 内加入：

```ts
  it('serializes typed client actions before sending them', () => {
    const playerStore = usePlayerStore()
    playerStore.playerId = 'p1'
    playerStore.authToken = 'token'

    const { connect, sendAction } = useGameWebSocket()
    connect()
    const socket = MockWebSocket.instances[0]!
    socket.readyState = MockWebSocket.OPEN

    sendAction({ action: 'play_cards', cards: [3, 4, 5] })

    expect(socket.sentMessages).toEqual([
      JSON.stringify({ action: 'play_cards', cards: [3, 4, 5] }),
    ])
  })
```

- [x] **Step 3：补充 settlement reset 测试**

在 `frontend/src/stores/__tests__/gameStore.spec.ts` 中加入：

```ts
  it('resets typed settlement data to null', () => {
    const store = useGameStore()
    store.settlement = {
      winner: 'p1',
      winnerSide: 'landlord',
      scores: { p1: 80, p2: -40, p3: -40 },
      multiplier: 4,
      allHands: { p2: [3, 4] },
    }

    store.reset()

    expect(store.settlement).toBeNull()
  })
```

- [x] **Step 4：新增 debug logger 测试**

创建 `frontend/src/utils/__tests__/debugLog.spec.ts`：

```ts
import { afterEach, describe, expect, it, vi } from 'vitest'
import { debugLog } from '../debugLog'

describe('debugLog', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('writes development debug output through console.debug', () => {
    const debugSpy = vi.spyOn(console, 'debug').mockImplementation(() => {})

    debugLog('message', { ok: true })

    expect(debugSpy).toHaveBeenCalledWith('message', { ok: true })
  })
})
```

- [x] **Step 5：运行相关测试确认新增测试状态**

```powershell
cd frontend
npm.cmd run test:unit -- --run src/composables/__tests__/useGameWebSocket.spec.ts src/stores/__tests__/gameStore.spec.ts src/utils/__tests__/debugLog.spec.ts
```

期望：`debugLog.spec.ts` 在工具文件创建前失败；若先创建空文件，应因 `console.debug` 未调用失败。

---

### Task 3：实现类型和 debug logger 收紧

**Files:**
- Create: `frontend/src/utils/debugLog.ts`
- Modify: `frontend/src/composables/useGameWebSocket.ts`
- Modify: `frontend/src/stores/gameStore.ts`
- Modify: `frontend/src/components/SettlementModal.vue`
- Modify: `frontend/src/components/HandCards.vue`

**Interfaces:**
- Produces:
  - `debugLog(...args: unknown[]): void`
  - `GameClientAction`
  - `GameSettlement`

- [x] **Step 1：创建 debug logger**

```ts
export function debugLog(...args: unknown[]) {
  if (import.meta.env.DEV) {
    console.debug(...args)
  }
}
```

- [x] **Step 2：收紧 useGameWebSocket 出站 action 类型**

在 `useGameWebSocket.ts` 中导入 `debugLog` 和导出：

```ts
export type GameClientAction =
  | { action: 'join_match'; nickname: string; base_score: number }
  | { action: 'cancel_match' }
  | { action: 'sync_room_state' }
  | { action: 'call_landlord'; score: number }
  | { action: 'skip_call' }
  | { action: 'play_cards'; cards: number[] }
  | { action: 'pass_turn' }
  | { action: 'chat'; msg_id: number }
  | { action: 'choose_double'; choice: DoublingChoice }
  | { action: 'voice_state'; enabled: boolean }
  | {
      action: 'voice_signal'
      target_player: string
      signal_type: VoiceSignalType
      payload: Record<string, unknown>
    }
```

并改为：

```ts
  function sendAction(action: GameClientAction) {
```

- [x] **Step 3：收紧 gameStore settlement 类型**

在 `gameStore.ts` 中加入：

```ts
export type WinnerSide = 'landlord' | 'farmer'

export interface GameSettlement {
  winner: string
  winnerSide: WinnerSide
  scores: Record<string, number>
  multiplier: number
  allHands?: Record<string, number[]>
}
```

并改为：

```ts
  const settlement = ref<GameSettlement | null>(null)
```

- [x] **Step 4：让 SettlementModal 复用结算类型**

在 `SettlementModal.vue` 中导入：

```ts
import type { GameSettlement, PlayerInfo } from '@/stores/gameStore'
```

并把 props 改为：

```ts
const props = defineProps<{
  settlement: GameSettlement
  players: Array<Pick<PlayerInfo, 'id' | 'nickname' | 'isLandlord'>>
  lastPlayedCards?: Record<string, number[]>
}>()
```

- [x] **Step 5：收紧 HandCards 计时器并使用 debug logger**

在 `HandCards.vue` 中导入：

```ts
import { debugLog } from '@/utils/debugLog'
```

删除本地 `debugLog()`，并改为：

```ts
let animateTimer = ref<ReturnType<typeof window.setInterval> | null>(null)
let isDealingTimeout = ref<ReturnType<typeof window.setTimeout> | null>(null)
```

- [x] **Step 6：运行相关测试转绿**

```powershell
cd frontend
npm.cmd run test:unit -- --run src/composables/__tests__/useGameWebSocket.spec.ts src/stores/__tests__/gameStore.spec.ts src/utils/__tests__/debugLog.spec.ts
```

期望：相关测试通过。

---

### Task 4：全量验证

**Files:**
- Verify only.

**Interfaces:**
- Consumes: Task 2 和 Task 3 的改动。
- Produces: 用户验收依据。

- [x] **Step 1：运行前端全量单测**

```powershell
cd frontend
npm.cmd run test:unit -- --run
```

- [x] **Step 2：运行前端构建**

```powershell
cd frontend
npm.cmd run build
```

- [x] **Step 3：确认目标文件无 any 和 console.log**

```powershell
rg -n "\bany\b|console\.log" frontend/src/composables/useGameWebSocket.ts frontend/src/stores/gameStore.ts frontend/src/components/HandCards.vue
```

期望：无命中。

- [x] **Step 4：检查 diff**

```powershell
git diff --check
git diff --stat
git -c core.excludesfile= status --short
```

期望：无空白错误，只包含本轮文档、测试和前端类型收紧改动。

## 自查结果

- 本计划覆盖设计文档的全部 4 个目标。
- 没有把 `LobbyView.vue`、`SettingsModal.vue` 或 `DebugConsoleView.vue` 的 `any` 纳入本轮。
- 没有提交步骤，等待用户人工确认后再提交一次。
