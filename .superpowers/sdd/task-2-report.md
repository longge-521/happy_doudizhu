# Task 2: 前端开发 - 大牌型（炸弹、飞机、顺子）特效渲染实现报告

## 1. 任务概述
本任务为斗地主前端游戏房间（`GameRoomView.vue`）添加大牌特效支持。主要实现内容包括：
1. **全局状态扩展**：在 `gameStore.ts` 中新增全局响应式状态 `showRedealNotice`（重新洗牌控制）与 `activeEffect`（大牌型特效类别）。
2. **出牌判定与事件触发**：在 `useGameWebSocket.ts` 中：
   - 当接收到重新洗牌（`redeal`）事件时，在全局设置并展示 1.8 秒的洗牌提示。
   - 当接收到出牌（`cards_played`）事件时，利用 `detectCardPlay` 库函数分析所出牌型。如为炸弹、王炸、飞机、三顺、顺子或连对，则触发对应的全局大牌特效并维持 1.5 秒。
3. **特效样式与图层渲染**：在 `GameRoomView.vue` 中渲染大牌特效浮层并添加相应的精美 CSS 动效（炸弹屏幕震动与能量环波纹、飞机飞过加尾迹烟雾、顺子金色流光扫过）。

## 2. 具体改动点

### 2.1 全局 Store (`frontend/src/stores/gameStore.ts`)
- 新增 `showRedealNotice`（`ref(false)`）和 `activeEffect`（`ref<'bomb' | 'plane' | 'shimmer' | ''>('')`）。
- 在 `reset()` 函数中添加对它们的初始化重置。
- 在 `return` 对象中导出这两个状态变量，以便其他组件 and composables 同步使用。

### 2.2 WebSocket 消息处理 (`frontend/src/composables/useGameWebSocket.ts`)
- 导入 `detectCardPlay` 函数。
- 完善 `case 'redeal'` 分支，置 `gameStore.showRedealNotice = true`，并在 1.8 秒后重置。
- 完善 `case 'cards_played'` 分支，检测出牌类型：
  - 类型为 `'bomb'`（炸弹）或 `'rocket'`（王炸）时，置 `activeEffect` 为 `'bomb'`，并在 1.5 秒后清除。
  - 类型为 `'airplane'`（飞机）、`'airplane_single'`（飞机带单）或 `'airplane_pair'`（飞机带对）时，置 `activeEffect` 为 `'plane'`，并在 1.5 秒后清除。
  - 类型为 `'straight'`（顺子）或 `'double_straight'`（连对）时，置 `activeEffect` 为 `'shimmer'`，并在 1.5 秒后清除。
- 修复了原简报中将英文牌型类型误写作中文导致的 TypeScript 编译类型不匹配报错。

### 2.3 房间视图渲染与特效 CSS (`frontend/src/views/GameRoomView.vue`)
- 移除组件内部的局部 `showRedealNotice` 状态变量，完全改用全局的 `gameStore.showRedealNotice`。
- 修改 `watch` 监听器，在 `gamePhase` 从 `CALLING` 切换为 `DEALING` 时，更新全局 `gameStore.showRedealNotice` 的状态。
- 在页面模板根部新增特效图层容器 `.poker-effects-layer`，配合 `activeEffect` 状态条件展示炸弹能量冲击波 `.effect-bomb-shockwave`（双圈波纹）或飞机飞过特效 `.effect-plane-flyby`（飞机图标带渐变拖尾烟雾）。
- 更改出牌信息列表中的 `.played-cards-row` 容器，配合 `activeEffect` 的 shimmer 流光状态动态添加 `.shimmer-active` 类。
- 添加 CSS 特效动画：
  - **屏幕震动 (`screen-shake`)**：在出炸弹时抖动全屏 0.4 秒，增强震撼感。
  - **炸弹冲击波 (`ripple`)**：通过双层波纹动画向四周扩散并淡出。
  - **飞机飞过 (`plane-fly`)**：使用贝塞尔曲线使飞机从屏幕左侧飞入右侧，并附带拖尾烟雾效果。
  - **顺子金色流光 (`shimmer-flow`)**：在出牌框内从左至右斜向扫过一道金色渐变流光，突出顺子的连续性。配合 `.played-cards-row` 上的 `position: relative` 和 `overflow: hidden` 实现精细裁剪，防流光溢出。

## 3. 测试与验证结果
- 本地执行 TypeScript 类型检查校验 `npm run type-check`，结果显示修改的三个文件 `gameStore.ts`、`useGameWebSocket.ts` 和 `GameRoomView.vue` 均顺利编译通过，没有任何 TS 语法与类型报错，其余不相关文件的历史报错保持原样。

## 4. Git 提交范围
- **Base Commit**: `1cdcf65dc35588c082bcbc8d80446dc2a7c2d9e1`
- **提交文件列表**:
  - `frontend/src/stores/gameStore.ts`
  - `frontend/src/composables/useGameWebSocket.ts`
  - `frontend/src/views/GameRoomView.vue`
