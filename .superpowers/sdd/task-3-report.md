# Task 3 报告：前端 WebRTC 房间语音 composable

## 实现内容

本次按任务要求新增了以下两个代码文件：

- `frontend/src/composables/useRoomVoiceChat.ts`
- `frontend/src/composables/__tests__/useRoomVoiceChat.spec.ts`

实现内容如下：

1. 新增 `useRoomVoiceChat(options)` composable，对外提供：
   - `isVoiceEnabled`
   - `isConnecting`
   - `voiceError`
   - `remoteVoicePlayers`
   - `toggleVoice()`
   - `startVoice()`
   - `stopVoice()`
   - `dispose()`
2. 接入 Task 2 已完成的 `gameVoiceEvents` 事件总线：
   - 监听 `onVoiceSignal`
   - 监听 `onVoiceState`
3. 在开启语音时：
   - 申请麦克风权限
   - 发送 `{ action: 'voice_state', enabled: true }`
   - 为房间内其他玩家创建 `RTCPeerConnection`
   - 发送 WebRTC `offer`
4. 在接收信令时支持：
   - 处理远端 `offer`
   - 回发 `answer`
   - 处理 `answer`
   - 处理 `ice_candidate`
5. 在停止语音或销毁时：
   - 停止本地音轨
   - 关闭所有 peer 连接
   - 清理远端音频元素
   - 发送 `{ action: 'voice_state', enabled: false }`
6. 增加单测覆盖：
   - 开启语音并向房间其他玩家发起连接
   - 停止语音时关闭音轨和 peer
   - 接收 `offer` 与 `ice_candidate` 的处理
   - 麦克风权限失败时的错误状态

## RED 命令 + 失败输出 + 预期原因

先新增测试，再运行：

```bash
cd frontend
npm run test:unit -- src/composables/__tests__/useRoomVoiceChat.spec.ts --run
```

说明：在当前 PowerShell 环境里，`npm run` 会先命中执行策略错误，无法实际运行测试，因此改用 `npm.cmd` 执行同一命令。

实际 RED 验证命令：

```bash
cd frontend
npm.cmd run test:unit -- src/composables/__tests__/useRoomVoiceChat.spec.ts --run
```

关键失败输出：

```text
FAIL  src/composables/__tests__/useRoomVoiceChat.spec.ts
Error: Failed to resolve import "../useRoomVoiceChat" from "src/composables/__tests__/useRoomVoiceChat.spec.ts". Does the file exist?
```

这是符合预期的 RED，因为当时 `frontend/src/composables/useRoomVoiceChat.ts` 还不存在，测试失败点正是“待实现模块缺失”，不是测试写错。

补充：实现后首次 GREEN 尝试中，还暴露了一个测试夹具问题：`vi.resetModules()` 会让测试里的 `notifyVoiceSignal` 与 composable 内部订阅的 `gameVoiceEvents` 不再共享同一模块实例，导致事件打不到 composable。这个问题已在测试中修正，随后重新验证通过。

## GREEN 命令 + 通过输出

```bash
cd frontend
npm.cmd run test:unit -- src/composables/__tests__/useRoomVoiceChat.spec.ts --run
```

通过输出：

```text
Test Files  1 passed (1)
Tests       4 passed (4)
```

## 变更文件

代码变更：

- `frontend/src/composables/useRoomVoiceChat.ts`
- `frontend/src/composables/__tests__/useRoomVoiceChat.spec.ts`

报告文件：

- `.superpowers/sdd/task-3-report.md`

## 自检结论

自检后结论：

1. 实现范围保持克制，只改了任务要求的 composable 与对应测试，没有改 UI、后端、事件总线或其他业务模块。
2. 实现遵守了“后端只做信令转发”的边界，没有引入 TURN、设备选择、输入音量条、说话人检测、录音或回放。
3. 错误提示使用了可读中文字符串，没有出现乱码。
4. 远端语音状态和本地资源清理路径完整，`stopVoice()` 与 `dispose()` 都能回收连接和音轨。
5. 单测覆盖了本任务最关键的 4 条行为路径，足以支撑这次最小实现。

## 关注点

1. 当前仓库存在大量与本任务无关的脏改动，因此提交时必须严格只暂存任务指定的两个前端文件。
2. 浏览器自动播放策略在真实环境里可能拦截远端音频播放；当前实现已把这类失败映射为 `语音播放受阻，请点击页面后重试`，但这部分还没有额外单测覆盖。
3. 本次只跑了任务要求的定向 Vitest 用例，未额外执行全量前端测试或类型检查。

## 修复补充（Review Findings 处理）

### 本次改动

1. 在 `useRoomVoiceChat.ts` 内新增启动代际控制、`isDisposed` 标记、每个 peer 的 `makingOffer` 跟踪，以及待刷新的 `pendingIceCandidates` 缓存。
2. 收紧 `startVoice()` / `stopVoice()` / `dispose()` 的时序处理，避免 `getUserMedia()` 晚返回后错误重开语音。
3. 为双 offer 冲突增加最小 polite/impolite 协商规则：按 `selfPlayerId.localeCompare(remotePlayerId)` 决定谁回滚本地 offer，谁忽略冲突 offer。
4. 在设置远端 description 后刷新缓存的 ICE candidate。
5. 扩展 `useRoomVoiceChat.spec.ts`，补上资源清理、远端关麦、answer 分支、ICE 提前到达、启动竞态、offer collision 等单测。

### 测试命令与结果

执行命令：

```bash
cd frontend
npm.cmd run test:unit -- src/composables/__tests__/useRoomVoiceChat.spec.ts --run
```

结果：

```text
Test Files  1 passed (1)
Tests       11 passed (11)
```

### 评审意见对应处理

1. **start/stop 竞态**
   - 通过 `sessionGeneration` 在 `startVoice()` 开始时生成本次会话代号，并在 `stopVoice()`、`dispose()` 时递增。
   - `getUserMedia()` 返回后会再次校验代号和 `isDisposed`；如果已经 stop/dispose，则立即停止刚拿到的音轨，不发送 `voice_state: true`，也不再创建 offer。

2. **offer collision**
   - 新增 `makingOffer` 按 peer 跟踪本地是否正在发 offer。
   - 收到远端 offer 时，如果检测到 collision，则用最小规则决定：
     - polite 端：先 `rollback` 本地 description，再接收远端 offer 并返回 answer。
     - impolite 端：直接忽略这次冲突 offer。

3. **ICE 早于 remote description**
   - 新增 `pendingIceCandidates: Map<string, RTCIceCandidateInit[]>`。
   - ICE 如果先到且当前 peer 还没有 `remoteDescription`，先入队。
   - 在 `offer` / `answer` 分支设置完远端 description 后统一 flush。

4. **测试补充**
   - 已新增并通过以下覆盖：
     - `dispose()` 的订阅解绑与资源清理
     - 远端 `voice_state: false` 的关闭处理
     - 本地主动发 offer 后接收远端 `answer`
     - ICE 先于 `offer` 与先于 `answer`
     - `startVoice()` 与 `stopVoice()` 的竞态
     - polite / impolite 两种 offer collision 行为

## 修复补充（Review 3 剩余 Critical）

### What changed

1. 在 `frontend/src/composables/useRoomVoiceChat.ts` 中新增按 peer 追踪的 `offerGenerations`。
2. 每次开始本地 `createOffer()` 前，都会为该 peer 生成新的本地 offer 代号。
3. 当本端在 `makingOffer` 窗口内接受远端 offer 时，会先使当前本地 offer 代号失效，再继续远端 offer -> 本地 answer 的流程。
4. `createOffer()` 异步返回后，在 `setLocalDescription()` 和发送 `voice_signal: offer` 之前，都会再次校验这次本地 offer 是否仍然是当前有效代号；如果已经因远端 offer 被取消，则直接退出，不再发送旧 offer。
5. 在 `frontend/src/composables/__tests__/useRoomVoiceChat.spec.ts` 中补了一条定向回归测试，覆盖“`createOffer()` 挂起时收到远端 offer，随后本地旧 offer 才 resolve”的时序。

### Test command and result

命令：

```bash
cd frontend
npm.cmd run test:unit -- src/composables/__tests__/useRoomVoiceChat.spec.ts --run
```

结果：

```text
Test Files  1 passed (1)
Tests       12 passed (12)
```

### How the reviewer finding was handled

- Reviewer 指出的剩余 Critical 是：当前代码虽然能在 collision 时接受远端 offer 并回 answer，但如果本地 `createOffer()` 还在进行中，稍后 resolve 的旧 offer 仍可能继续走完 `setLocalDescription()` 和发送信令。
- 这次修复把“本地 offer 是否仍有效”做成了显式校验条件，而不是只依赖 `makingOffer` 和 `signalingState`。
- 因此在 “pending `createOffer()` -> 收到远端 offer -> 接受并 answer -> 本地旧 offer resolve” 这条路径上，现在只会发送 answer，不会再补发旧的本地 offer。
