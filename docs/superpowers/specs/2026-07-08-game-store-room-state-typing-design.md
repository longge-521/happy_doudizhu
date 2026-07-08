# gameStore 房间状态类型收紧设计规约

## 背景

上一轮已经将 `useGameWebSocket.ts` 中的音效、特效和快捷聊天副作用拆分到 `gameWebSocketEffects.ts`。拆分后，WebSocket 事件分发逻辑更清晰，但核心状态入口 `gameStore.updateFromRoomState()` 仍使用 `any` 接收后端房间状态，并在玩家列表映射中继续使用 `any`。

该入口承接后端 `room_state` 的 snake_case 数据，并转换成前端 Pinia store 的 camelCase 状态。它是前端对局状态的关键边界，如果字段拼写、可空值或数组结构发生变化，当前 TypeScript 很难提前暴露问题。

## 目标

本轮优化只收紧 `frontend/src/stores/gameStore.ts` 的房间状态输入类型，保持运行行为、WebSocket 协议和 UI 展示不变。

具体目标：

1. 为后端房间状态新增清晰的 TypeScript 接口。
2. 将 `updateFromRoomState(state: any)` 改为显式类型参数。
3. 去掉该函数内部玩家映射中的 `any`。
4. 为房间状态映射补充 focused 单元测试，覆盖 snake_case 到前端状态的转换。

## 非目标

本轮不做以下事情：

1. 不修改后端 WebSocket 或 REST 协议。
2. 不重构 `useGameWebSocket.ts` 的事件 payload 类型。
3. 不拆分 `GameRoomView.vue`、`LobbyView.vue` 或其他大页面。
4. 不调整 UI、音效、动画或游戏规则。
5. 不引入新的运行时依赖。

## 方案选择

### 方案 A：只收紧 `gameStore.updateFromRoomState()` 类型

优点是改动小、风险低、验证路径清晰；它先稳住最核心的数据入口，为后续 WebSocket 事件类型化打基础。

缺点是 `useGameWebSocket.ts` 中仍会保留部分 `any`，需要后续专项继续处理。

### 方案 B：一次性收紧所有 WebSocket 事件类型

优点是类型覆盖更完整。

缺点是事件分支多、涉及面广，容易扩大本轮修改范围，也会增加回归风险。

### 方案 C：先处理页面和调试控制台中的 `any`

优点是可以改善整体 TypeScript 质量。

缺点是对核心对局链路的收益不如先处理 `gameStore`，且页面文件较大，容易变成低收益重构。

## 推荐方案

采用方案 A。

本轮只在 `gameStore.ts` 中定义房间状态相关接口，并补充对应测试。这样可以在保持行为不变的前提下，让核心状态转换边界更可检查，也避免把当前优化扩散到 WebSocket 全事件协议或页面拆分。

## 设计细节

### 类型定义

在 `frontend/src/stores/gameStore.ts` 中新增以下类型：

- `GamePhase`：限定 store 当前使用的阶段字符串，包含 `IDLE`、`MATCHING`、`DEALING`、`CALLING`、`DOUBLING`、`PLAYING`、`SETTLING`。
- `RoomStatePlayerPayload`：描述后端传入的玩家视角字段，包括 `id`、`nickname`、`is_ai`、`is_online`、`remaining`、`is_landlord`、`is_self`。
- `RoomStateLastPlayPayload`：描述 `last_play`，包括 `player`、`cards`、`card_type`。
- `RoomStatePayload`：描述 `updateFromRoomState()` 消费的房间状态字段。

这些接口只表达当前前端实际消费的字段，不尝试完整复制后端领域模型，避免过度设计。

### 状态映射

`updateFromRoomState()` 保持现有映射规则：

- `room_id` 映射到 `roomId`。
- `phase` 映射到 `gamePhase`。
- `players[].is_ai` 映射到 `players[].isAi`。
- `players[].is_online` 映射到 `players[].isOnline`。
- `players[].is_landlord` 映射到 `players[].isLandlord`。
- `players[].is_self` 映射到 `players[].isSelf`。
- `last_play.card_type` 映射到 `lastPlay.cardType`。
- `doubling_choices` 映射到 `doublingChoices`。

`remaining` 的兼容逻辑保持不变：当后端没有给出 `remaining` 时，如果是当前玩家则使用 `hand.length`，否则默认为 `0`。

### 测试设计

新增 `frontend/src/stores/__tests__/gameStore.spec.ts`，使用 Pinia 测试 store，重点覆盖：

1. `updateFromRoomState()` 能将后端 snake_case 房间状态映射为前端 store 字段。
2. 当前玩家缺少 `remaining` 时，使用 `hand.length`。
3. `reset()` 后能清理核心对局状态，防止新增类型改动影响原有重置行为。

测试只验证 store 行为，不 mock WebSocket，不引入浏览器交互。

## 验证方式

完成后运行：

```powershell
cd frontend
npm.cmd run test:unit -- --run src/stores/__tests__/gameStore.spec.ts
npm.cmd run test:unit -- --run
npm.cmd run build
```

最后检查：

```powershell
git diff --check
git diff --stat
```

## 风险与控制

主要风险是类型定义过窄，导致 `useGameWebSocket.ts` 中已有调用在构建时暴露类型不兼容。控制方式是只声明当前实际消费字段，并允许字段可选；不强行要求后端每次都提供完整房间状态。

另一个风险是 `GamePhase` 字符串过早收窄。控制方式是覆盖当前项目已使用的阶段值，包括加倍阶段 `DOUBLING`；如果后续新增阶段，应同步扩展该类型和测试。

## 自查结果

- 本规约没有占位符或未决项。
- 修改范围聚焦在 `gameStore` 房间状态入口和对应测试。
- 不改变协议、不改变 UI、不改变游戏规则。
- 验证命令明确，可按单测、全量前端测试、构建和 diff 检查逐步确认。
