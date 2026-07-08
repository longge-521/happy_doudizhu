# WebSocket 前端事件 payload 类型化设计规约

## 背景

前两轮已经完成两项相关优化：

1. 将 `useGameWebSocket.ts` 中的音效、特效和快捷聊天副作用拆分到 `gameWebSocketEffects.ts`。
2. 将 `gameStore.updateFromRoomState()` 的房间状态输入收紧为 `RoomStatePayload`。

当前仍然存在一层未收紧的边界：`useGameWebSocket.ts` 里 `handleEvent(data: any)` 直接消费 `JSON.parse()` 得到的服务端事件，`game_start` 分支中的 `data.players.map((p: any) => ...)` 也仍使用 `any`。

这意味着服务端事件字段拼写、可选字段、数组元素结构发生变化时，TypeScript 很难在构建阶段暴露问题，容易把错误推迟到实际对局运行时。

## 本轮解决的问题

本轮解决的是前端 WebSocket 服务端事件入口缺少类型边界的问题。

目标不是改变 WebSocket 协议，也不是改变页面表现，而是让前端事件处理代码具备更明确的编译期约束：

- 事件名必须来自已知服务端事件集合。
- `room_state` 复用上一轮已有的 `RoomStatePayload`。
- `game_start.players` 使用明确的玩家 payload 类型。
- `voice_signal`、`voice_state`、`chat_msg`、`cards_played` 等已有事件字段在代码中有可读的结构定义。

## 目标

1. 在 `useGameWebSocket.ts` 中新增局部服务端事件类型。
2. 将 `handleEvent(data: any)` 改为 `handleEvent(data: GameServerEvent)`。
3. 将 `game_start` 分支中的 `players.map((p: any) => ...)` 改为明确类型。
4. 保持现有测试、运行行为和 WebSocket 协议不变。

## 非目标

本轮不做以下事情：

1. 不修改后端 WebSocket 事件协议。
2. 不修改客户端发送动作 `sendAction(action: Record<string, any>)`。
3. 不拆分 `useGameWebSocket.ts` 的事件 dispatcher。
4. 不重构 `GameRoomView.vue` 或其他页面调用方。
5. 不引入运行时 schema 校验库。

## 方案选择

### 方案 A：在 `useGameWebSocket.ts` 内部新增局部事件联合类型

优点是改动小、文件边界清晰，能直接消掉当前最关键的 `handleEvent(data: any)`。因为事件处理逻辑仍在原文件内，测试和回归风险都较低。

缺点是事件类型会让 `useGameWebSocket.ts` 稍微变长，后续如果继续拆 dispatcher，需要再搬迁类型定义。

### 方案 B：新建 `gameWebSocketEvents.ts` 专门放事件类型

优点是类型定义更独立，未来可以给后端协议文档或页面调用方复用。

缺点是本轮只处理一个 composable 的内部边界，新建文件会略显提前抽象。

### 方案 C：一次性同时类型化客户端发送动作

优点是协议两端更完整。

缺点是会牵动页面里的 `sendAction()` 调用，扩大修改范围，不适合作为本轮小步优化。

## 推荐方案

采用方案 A。

本轮只在 `useGameWebSocket.ts` 内部定义局部事件类型，复用 `gameStore.ts` 已导出的 `RoomStatePayload`、`RoomStatePlayerPayload` 和 `DoublingChoice`。这样可以用最小改动强化服务端事件入口，避免提前拆文件或牵动页面发送动作。

## 设计细节

### 类型定义

新增以下局部类型：

- `GameServerEvent`：服务端事件联合类型。
- `BaseRoomStateEvent`：带可选 `room_state` 的通用事件结构。
- `GameStartEvent`：`game_start` 事件，包含 `players`、`hand`、`current_turn` 等字段。
- `VoiceSignalEvent`、`VoiceStateEvent`：语音事件结构，其中 `signal_type` 对齐 `gameVoiceEvents.ts` 已有的 `VoiceSignalType`。
- `GameOverEvent`：结算事件结构。

简单事件可以保留轻量结构，例如：

- `match_waiting`
- `match_cancelled`
- `redeal`
- `error`
- `chat_msg`

### 数据流

`socket.onmessage` 仍然执行：

1. `JSON.parse(event.data)`
2. 将结果作为 `GameServerEvent` 传入 `handleEvent()`
3. `handleEvent()` 保持原有 switch 分支和副作用逻辑

本轮不增加运行时类型守卫。原因是当前项目已有测试覆盖主要事件行为，本轮目标是编译期约束；运行时校验可以作为后续更完整的协议防御专项。

### 测试策略

沿用现有 `frontend/src/composables/__tests__/useGameWebSocket.spec.ts`：

1. 保持 `double_chosen` 测试，确认 `room_state` 和加倍音效行为不变。
2. 保持 `voice_signal`、`voice_state` 测试，确认语音事件派发不变。
3. 保持 `chat_msg` 测试，确认快捷聊天仍只播放语音，不污染桌面状态。
4. 保持 `cards_played` 测试，确认剩余牌报警逻辑不变。

如果类型收紧导致测试编译失败，应优先修正事件类型，而不是改动行为。

## 验证方式

完成后运行：

```powershell
cd frontend
npm.cmd run test:unit -- --run src/composables/__tests__/useGameWebSocket.spec.ts
npm.cmd run test:unit -- --run
npm.cmd run build
```

最后检查：

```powershell
git diff --check
git diff --stat
```

## 风险与控制

主要风险是事件类型写得过窄，导致现有合法事件在构建阶段被误判。控制方式是按当前代码实际消费字段声明为可选，不强行完整建模后端所有字段。

另一个风险是 `JSON.parse()` 结果本质上仍是未知外部输入。由于本轮不引入运行时 schema 校验，类型断言不能防止非法服务端数据；但它能约束前端内部处理逻辑，仍然能减少协议字段拼写和分支维护错误。

## 自查结果

- 本规约没有占位符或未决项。
- 修改范围聚焦在 `useGameWebSocket.ts` 服务端事件入口。
- 不改变协议、不改变 UI、不改变游戏规则。
- 验证命令明确，可按 targeted 测试、全量前端测试、构建和 diff 检查逐步确认。
