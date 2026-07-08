# WebSocket 前端事件副作用拆分设计

## 背景

`frontend/src/composables/useGameWebSocket.ts` 当前同时承担四类职责：

- WebSocket 连接、重连、鉴权失败处理。
- 服务端事件解析与 Pinia 状态更新。
- 出牌、叫分、加倍、结算等事件的音效和视觉特效。
- 语音信令与快捷聊天语音分发。

这会让单个 composable 继续变胖。特别是 `cards_played` 和 `game_over` 中最后一手牌的音效/特效逻辑高度重复，后续改动牌型音效时容易漏改一处。

## 目标

本次只拆分前端 WebSocket 事件副作用，不改游戏协议、不改后端、不改 UI 布局。

目标包括：

- 将出牌音效、炸弹/飞机/顺子特效、快捷聊天语音、加倍语音抽到独立模块。
- `useGameWebSocket.ts` 保留连接管理、事件分发、状态更新。
- 保持现有测试行为不变，并为新模块补充直接单测。

## 非目标

- 不拆 `LobbyView.vue`、`GameRoomView.vue` 等大页面。
- 不重构 `backend/app/interfaces/websocket/game_handler.py`。
- 不调整 WebSocket 事件字段、状态字段或音效资源映射。
- 不引入新的依赖或全局事件总线。

## 方案

新增 `frontend/src/composables/gameWebSocketEffects.ts`，负责与 WebSocket 事件相关但不属于连接本身的表现层副作用。

该模块提供：

- `getDoubleChoiceLabel(choice: string): string`
- `playDoubleChoiceSound(choice: string, playerId: string): void`
- `playQuickChatMessage(msgId: number, playerId: string): void`
- `playCardPresentationEffects(cards: number[], playerId: string, gameStore: GameEffectStore): void`
- `clearCardPresentationEffectTimer(): void`

`useGameWebSocket.ts` 调用这些函数，但不再直接导入 `CHAT_PRESETS`、`detectCardPlay` 或 `useSoundEngine`。

## 数据流

服务端事件进入 `useGameWebSocket.ts` 后：

1. `handleEvent()` 按事件类型更新 `gameStore`。
2. 需要音效或视觉特效时，调用 `gameWebSocketEffects.ts` 的函数。
3. `gameWebSocketEffects.ts` 只通过传入的 `gameStore.activeEffect` 写入特效状态，不修改房间、玩家、手牌、结算等核心状态。

## 错误处理

本次不新增用户可见错误。副作用函数保持和当前实现一致：

- 未识别的牌型仍播放通用 `playCard`。
- 未匹配的快捷聊天 `msgId` 仍回退为 `...`。
- 未识别的加倍选择仍播放“不加倍”语音。

## 测试策略

- 新增 `frontend/src/composables/__tests__/gameWebSocketEffects.spec.ts`。
- 单测覆盖加倍语音、快捷聊天语音、炸弹特效、普通单牌音效。
- 保留并运行现有 `useGameWebSocket.spec.ts`，证明 WebSocket 事件行为未回归。
- 最终运行 `npm.cmd run test:unit -- --run` 和 `npm.cmd run build`。

## 验收标准

- `useGameWebSocket.ts` 不再直接包含牌型音效分支树。
- `cards_played` 和 `game_over` 复用同一个出牌表现副作用函数。
- 前端单测和构建通过。
