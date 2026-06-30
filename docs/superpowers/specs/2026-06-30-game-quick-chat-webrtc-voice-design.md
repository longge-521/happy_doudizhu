# 斗地主快捷语扩充与 WebRTC 房间语音设计

## 背景

当前对局页只有 5 条快捷语，入口在 `GameRoomView.vue` 右下角，发送时前端通过游戏 WebSocket 发送 `chat` 动作和 `msg_id`，后端在 `game_handler.py` 中广播 `chat_msg`，接收端再用本地预设文本展示气泡。

用户希望快捷语更丰富、更搞笑，并支持真实语音。语音需求已确认采用 WebRTC 实时房间语音，而不是快捷语朗读或录音文件消息。

## 目标

- 扩充一组更有斗地主氛围的搞笑快捷语。
- 保留现有 `msg_id` 快捷语协议，避免破坏已有聊天链路。
- 在牌局房间内增加实时语音开关，支持同房间 3 名玩家之间语音通话。
- 后端只负责 WebRTC 信令转发，不保存、不转发、不录制音频流。
- 麦克风权限失败、浏览器不支持、对端断开时给出明确 UI 状态。

## 非目标

- 不做服务端录音、语音转文字、历史语音回放。
- 不做复杂设备选择、输入音量条、说话人检测。
- 不在第一版接入 TURN 服务；第一版使用公开 STUN 或浏览器默认 P2P 能力，极端 NAT 下允许连接失败并提示。
- 不重构游戏 WebSocket 连接管理、房间状态机或聊天 UI 架构。

## 方案选择

### 方案一：快捷语 TTS 朗读

实现最轻，但只能把文字朗读出来，不满足“真实语音”的需求。

### 方案二：录音消息

录制短音频后广播或上传，适合异步语音消息，但不是实时语音；还会引入文件大小、存储清理和权限边界。

### 方案三：WebRTC 实时语音

使用浏览器 `getUserMedia` 获取麦克风，玩家之间通过 `RTCPeerConnection` 建立 P2P 音频连接。游戏 WebSocket 只承载信令事件。

采用方案三。原因是它符合真实房间语音的交互预期，并且音频数据不经过后端，隐私和服务端压力更可控。

## 快捷语设计

快捷语仍使用数组定义，前端发送 `msg_id`。建议扩充到 16 条左右，语气保持轻松搞笑但不攻击真人：

- 快点吧，牌都快睡着了！
- 我这手牌，地主看了都沉默。
- 别慌，我先假装很会玩。
- 这牌不叫地主，对不起我的勇气。
- 你这操作，有点像地主安插的卧底。
- 我不是不出，我是在酝酿奇迹。
- 炸弹没有，气势先炸一下。
- 让你一手，主要是我没得选。
- 我摊牌了，我全靠感觉。
- 别催，脑子正在重新洗牌。
- 这波我看懂了，但牌没看懂。
- 队友稳住，我正在和命运谈判。
- 地主别笑，春天还没到呢。
- 我有一个大胆的想法，先不实现。
- 牌很好，下把一定赢。
- 好家伙，这都能接上？

后续如果需要支持自定义快捷语，再单独设计持久化和敏感词策略。

## WebRTC 语音交互

对局页右下角在快捷语按钮旁增加麦克风按钮：

- 默认状态：麦克风关闭。
- 点击开启：请求麦克风权限，成功后进入房间语音。
- 开启状态：再次点击关闭，停止本地音轨并断开所有对端连接。
- 权限失败：展示短暂错误提示，不反复弹权限请求。
- 连接中：按钮显示连接状态，避免用户误以为已通话。

玩家离开房间、刷新页面、WebSocket 断开、切回大厅时，前端必须停止本地 `MediaStreamTrack`。

## 信令协议

复用游戏 WebSocket。新增客户端动作：

```json
{ "action": "voice_state", "enabled": true }
```

```json
{
  "action": "voice_signal",
  "target_player": "player_2",
  "signal_type": "offer",
  "payload": { "type": "offer", "sdp": "..." }
}
```

`signal_type` 允许：

- `offer`
- `answer`
- `ice_candidate`

新增服务端事件：

```json
{ "event": "voice_state", "player": "player_1", "enabled": true }
```

```json
{
  "event": "voice_signal",
  "player": "player_1",
  "target_player": "player_2",
  "signal_type": "offer",
  "payload": { "type": "offer", "sdp": "..." }
}
```

后端规则：

- 只能向同一房间内的玩家转发信令。
- `target_player` 为空或不是同房间玩家时返回 `error`。
- `signal_type` 不在白名单内时返回 `error`。
- `payload` 必须是对象，大小限制为 16KB，避免滥用 WebSocket。
- `voice_state` 广播给房间内其他玩家，便于 UI 展示谁开启了语音。

## 前端结构

新增一个轻量 composable：`useRoomVoiceChat.ts`。

它负责：

- 管理本地麦克风流。
- 为每个远端玩家维护 `RTCPeerConnection`。
- 发送和接收 WebRTC 信令。
- 创建远端 `<audio>` 元素并播放对端音轨。
- 暴露状态：`isVoiceEnabled`、`isConnecting`、`voiceError`、`speakingPlayers`、`remoteVoicePlayers`。
- 在关闭或卸载时清理音轨、连接和音频元素。

`useGameWebSocket.ts` 负责分发新增 `voice_signal`、`voice_state` 事件。为了避免把 WebSocket composable 和 WebRTC composable 强耦合，可使用简单的事件订阅器或在 `gameStore` 中存储最近一次语音信令事件。第一版推荐事件订阅器，减少 Pinia 中存放 SDP 这类临时数据。

`GameRoomView.vue` 只做 UI：

- 麦克风按钮。
- 状态文案或图标。
- 错误提示。
- 调用 `useRoomVoiceChat` 的开关方法。

## 后端结构

只修改 `backend/app/interfaces/websocket/game_handler.py`：

- 新增 `voice_state` 动作分支。
- 新增 `voice_signal` 动作分支。
- 新增小型校验函数，限制目标玩家、信令类型和 payload 大小。

不修改 `GameRoom` 状态机，不新增数据库表，不新增 Redis 键。

## 错误处理

- 浏览器不支持 `navigator.mediaDevices.getUserMedia`：提示“当前浏览器不支持语音”。
- 用户拒绝麦克风权限：提示“麦克风权限未开启”。
- 对端连接失败：关闭该对端连接并提示“语音连接失败，可重新开启”。
- WebSocket 未连接：禁止开启语音或立即关闭语音状态。
- 页面卸载：清理所有本地和远端媒体资源。

## 测试策略

后端测试：

- `voice_state` 会广播给同房间玩家。
- `voice_signal` 只转发给目标同房间玩家。
- 非同房间目标、非法 `signal_type`、过大 `payload` 会返回错误。

前端测试：

- 开启语音时会请求麦克风并发送 `voice_state enabled=true`。
- 关闭语音时会停止音轨、关闭 peer connection，并发送 `voice_state enabled=false`。
- 收到 `offer` 时会创建 peer connection、设置远端描述并回发 `answer`。
- 收到 `ice_candidate` 时会添加 candidate。
- 权限失败时会设置错误状态且不发送开启状态。

手动验证：

- 两个浏览器窗口登录不同玩家，进入同房间后开启语音，确认能听到对方。
- 关闭麦克风、退出房间、刷新页面后确认麦克风采集停止。
- 快捷语菜单展示新增搞笑短语，发送后其他玩家仍能看到气泡。

## 实施顺序

1. 先为后端信令校验和转发写失败测试。
2. 实现后端 `voice_state` 和 `voice_signal` 分支。
3. 为前端语音 composable 写单元测试，mock `getUserMedia` 和 `RTCPeerConnection`。
4. 实现 `useRoomVoiceChat.ts`。
5. 扩充快捷语，并让发送端和接收端共用同一份快捷语常量。
6. 在 `GameRoomView.vue` 增加麦克风 UI。
7. 跑后端相关测试、前端单元测试和前端构建。

## 风险与取舍

- 没有 TURN 服务时，部分网络环境下 P2P 连接可能失败。第一版通过错误提示处理，后续可新增 TURN 配置。
- WebRTC 测试需要较多 mock，单元测试覆盖状态流转，真实音频连通性仍需要手动联调。
- 浏览器自动播放策略可能阻止远端音频自动播放。语音开启动作本身是用户手势，可用于解锁音频；必要时在 UI 上提示用户点击页面恢复播放。
- 快捷语扩充只做固定文本，不做用户自定义，避免引入审核和存储问题。
