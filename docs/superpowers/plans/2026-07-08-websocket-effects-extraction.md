# WebSocket 前端事件副作用拆分实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `useGameWebSocket.ts` 中的音效、特效、快捷聊天副作用抽到独立模块，保持 WebSocket 协议和游戏状态行为不变。

**Architecture:** 新增 `gameWebSocketEffects.ts` 作为表现层副作用模块。`useGameWebSocket.ts` 继续负责连接、事件分发和 Pinia 状态更新，只在需要时调用副作用函数。

**Tech Stack:** Vue 3、Pinia、Vitest、TypeScript、Vite。

## Global Constraints

- 禁止批量删除文件或目录。
- 不改 WebSocket 服务端协议和前端 store 字段。
- 不引入新依赖。
- 不自动提交，待用户人工确认后再 commit。

---

### Task 1：新增副作用模块测试

**Files:**
- Create: `frontend/src/composables/__tests__/gameWebSocketEffects.spec.ts`

**Interfaces:**
- Produces: 对 `playDoubleChoiceSound`、`playQuickChatMessage`、`playCardPresentationEffects` 的行为约束。

- [x] **Step 1：写失败测试**

新增测试文件，mock `useSoundEngine()`，验证：

- `playDoubleChoiceSound('super', 'p2')` 立即播放 `doubling`，120ms 后播放 `superDouble`。
- `playQuickChatMessage(0, 'p2')` 播放快捷聊天文本。
- `playCardPresentationEffects([36, 37, 38, 39], 'p2', store)` 播放炸弹特效并设置 `activeEffect = 'bomb'`。

- [x] **Step 2：确认测试失败**

运行：

```powershell
cd frontend
npm.cmd run test:unit -- --run src/composables/__tests__/gameWebSocketEffects.spec.ts
```

期望：失败，原因是 `gameWebSocketEffects.ts` 尚不存在。

---

### Task 2：实现 `gameWebSocketEffects.ts`

**Files:**
- Create: `frontend/src/composables/gameWebSocketEffects.ts`

**Interfaces:**
- Produces:
  - `getDoubleChoiceLabel(choice: string): string`
  - `playDoubleChoiceSound(choice: string, playerId: string): void`
  - `playQuickChatMessage(msgId: number, playerId: string): void`
  - `playCardPresentationEffects(cards: number[], playerId: string, gameStore: { activeEffect: 'bomb' | 'plane' | 'shimmer' | '' }): void`
  - `clearCardPresentationEffectTimer(): void`

- [x] **Step 1：实现副作用函数**

将 `useGameWebSocket.ts` 中已有的加倍语音、快捷聊天语音、出牌音效和特效逻辑搬到新模块。

- [x] **Step 2：运行新测试**

运行：

```powershell
cd frontend
npm.cmd run test:unit -- --run src/composables/__tests__/gameWebSocketEffects.spec.ts
```

期望：新增测试通过。

---

### Task 3：改造 `useGameWebSocket.ts`

**Files:**
- Modify: `frontend/src/composables/useGameWebSocket.ts`
- Modify: `frontend/src/composables/__tests__/useGameWebSocket.spec.ts`（仅在导入路径变化导致 mock 需要调整时修改）

**Interfaces:**
- Consumes: Task 2 产出的副作用函数。
- Produces: WebSocket 事件行为保持不变。

- [x] **Step 1：替换直接副作用逻辑**

在 `useGameWebSocket.ts` 中：

- 移除 `CHAT_PRESETS`、`detectCardPlay`、`useSoundEngine` 的直接导入。
- 引入 `getDoubleChoiceLabel`、`playDoubleChoiceSound`、`playQuickChatMessage`、`playCardPresentationEffects`、`clearCardPresentationEffectTimer`。
- `cards_played` 和 `game_over` 最后一手牌都调用 `playCardPresentationEffects()`。
- `chat_msg` 调用 `playQuickChatMessage()`。
- `disconnect()` 中清理出牌特效计时器。

- [x] **Step 2：运行 WebSocket 测试**

运行：

```powershell
cd frontend
npm.cmd run test:unit -- --run src/composables/__tests__/useGameWebSocket.spec.ts
```

期望：现有 WebSocket 测试全部通过。

---

### Task 4：最终验证

**Files:**
- Verify only.

- [x] **Step 1：运行前端单测**

```powershell
cd frontend
npm.cmd run test:unit -- --run
```

期望：全部通过。

- [x] **Step 2：运行前端构建**

```powershell
cd frontend
npm.cmd run build
```

期望：构建通过，无 TypeScript 错误。

- [x] **Step 3：检查 diff**

```powershell
git diff --check
git diff --stat
```

期望：没有空白错误，改动范围只包含本专项文件和文档。
