# 前端游戏链路类型与调试输出优化设计

## 背景

当前前端游戏链路已完成 WebSocket 入站事件、房间状态和玩家状态错误处理的多轮类型收紧，但仍有几个低风险技术债：

- `useGameWebSocket.ts` 的 `sendAction(action: Record<string, any>)` 仍允许任意出站 payload。
- `gameStore.ts` 的 `settlement = ref<any>(null)` 让结算数据缺少明确结构。
- `HandCards.vue` 的发牌动画计时器使用 `ref<any>`。
- `useGameWebSocket.ts` 与 `HandCards.vue` 内部各自定义 `debugLog()`，并直接调用 `console.log`。

本轮只处理以上 4 点，不扩大到大厅、设置弹窗或调试控制台的 `any` 清理。

## 目标

1. 为游戏 WebSocket 客户端出站动作定义联合类型，覆盖当前真实调用的动作。
2. 为结算数据定义 `GameSettlement` 类型，并让 store、结算弹窗和调用端复用同一结构。
3. 将手牌动画计时器类型收紧为浏览器计时器 ID，不再使用 `any`。
4. 新增统一的前端 debug logger，用 `console.debug` 承载开发环境日志，移除目标文件内的直接 `console.log`。

## 非目标

- 不修改 WebSocket 协议字段名。
- 不修改后端接口。
- 不重构 `LobbyView.vue`、`GameRoomView.vue` 或 `DebugConsoleView.vue` 的整体结构。
- 不清理本轮目标外的 `any`。
- 不改变游戏 UI 文案和交互行为。

## 设计方案

### 方案选择

采用小步类型收紧方案：

- 在 `useGameWebSocket.ts` 中导出 `GameClientAction` 联合类型，让 `sendAction()` 接收该类型。
- 在 `gameStore.ts` 中导出 `WinnerSide` 和 `GameSettlement`，把 `settlement` 改为 `ref<GameSettlement | null>(null)`。
- 在 `SettlementModal.vue` 中复用 `GameSettlement` 和 `PlayerInfo` 的必要字段，避免结算数据结构重复定义。
- 新增 `frontend/src/utils/debugLog.ts`，提供 `debugLog(...args: unknown[]): void`，内部仅在开发环境调用 `console.debug`。
- `HandCards.vue` 的 `animateTimer` 和 `isDealingTimeout` 改为 `ReturnType<typeof window.setInterval> | null` 与 `ReturnType<typeof window.setTimeout> | null`。

### 取舍

- 不把 `GameClientAction` 拆到单独协议文件，避免为一个小范围类型修复新增过多结构。
- `voice_signal.payload` 仍使用 `Record<string, unknown>`，因为 WebRTC payload 来源可能是 offer、answer 或 ICE candidate，字段形状由浏览器对象决定。
- debug logger 使用 `console.debug` 而不是 `console.log`，方便扫描中区分调试输出和普通日志。

## 数据结构

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

## 验证策略

先运行静态扫描确认当前问题存在：

```powershell
rg -n "\bany\b|console\.log" frontend/src/composables/useGameWebSocket.ts frontend/src/stores/gameStore.ts frontend/src/components/HandCards.vue
```

修改后验证：

```powershell
npm.cmd run test:unit -- --run
npm.cmd run build
rg -n "\bany\b|console\.log" frontend/src/composables/useGameWebSocket.ts frontend/src/stores/gameStore.ts frontend/src/components/HandCards.vue
git diff --check
```

期望：

- 前端单测全部通过。
- 前端构建和类型检查通过。
- 目标 3 个文件不再命中 `any` 或 `console.log`。
- diff 空白检查通过。

## 自查结果

- 本设计只覆盖用户指定的 1、2、3、4 四个优化点。
- 没有引入新依赖。
- 没有修改后端或 WebSocket 协议字段。
- 没有包含单独提交步骤，等待用户人工确认后再按仓库约束提交。
