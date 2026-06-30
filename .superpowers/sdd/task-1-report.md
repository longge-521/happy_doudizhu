# Task 1 报告

## 已实现内容

本次只改了后端 WebSocket 信令层，完成了两类 WebRTC 相关动作：

1. `voice_state`
   - 校验房间状态
   - 将 `enabled` 状态广播给房间内所有在线真人玩家
   - 广播内容保留玩家自己的房间视角

2. `voice_signal`
   - 校验当前玩家是否在房间内
   - 校验目标玩家是否属于当前房间内的真人玩家
   - 校验 `signal_type` 只允许 `offer`、`answer`、`ice_candidate`
   - 校验 `payload` 必须是对象，且序列化后不超过 `16KB`
   - 只转发给目标玩家，不保存、不录制、不做音频流处理

另外，为了避免导入 `game_handler.py` 时把 AI / Torch 依赖链提前拉进来，我把 `GameAppService` 改成了类型检查时引用，运行时不再强制导入。

## RED

执行命令：

```bash
& 'D:\\Program Files\\Python3.10\\Scripts\\pytest.exe' backend/tests/test_game_voice_signaling.py -v
```

失败输出摘要：

```text
FAILED backend/tests/test_game_voice_signaling.py::test_voice_state_broadcasts_to_room_players
FAILED backend/tests/test_game_voice_signaling.py::test_voice_signal_forwards_only_to_target_room_player
FAILED backend/tests/test_game_voice_signaling.py::test_voice_signal_rejects_non_room_target
FAILED backend/tests/test_game_voice_signaling.py::test_voice_signal_rejects_invalid_type_and_large_payload
```

失败原因是预期中的：当时 `voice_state` 和 `voice_signal` 还没有进入 `_handle_message` 分发，服务端仍然把它们当成未知动作处理，所以断言会落到 `未知动作: voice_signal` 这一类错误上。

## GREEN

执行命令：

```bash
& 'D:\\Program Files\\Python3.10\\Scripts\\pytest.exe' backend/tests/test_game_voice_signaling.py -v
```

结果：

```text
4 passed in 1.02s
```

## 回归

执行命令：

```bash
& 'D:\\Program Files\\Python3.10\\Scripts\\pytest.exe' backend/tests/test_game_websocket.py -v
```

结果：

```text
5 passed in 4.78s
```

说明现有游戏 WebSocket 的登录、匹配、叫分、出牌、过牌与欢乐豆校验流程没有被这次改动破坏。

## 修改文件

- `backend/tests/test_game_voice_signaling.py`
- `backend/app/interfaces/websocket/game_handler.py`

## 自检结论

- 信令只做转发和校验，没有新增任何音频存储、录制、回放或 TURN 逻辑。
- `voice_signal` 只会发给同房间目标玩家，不会扩散给整间房。
- 现有 WebSocket 回归测试通过，旧动作分发未受影响。
- 运行时导入链已收敛，避免了测试阶段提前触发重型 AI 依赖。

## 关注点

- 当前只做了第一版直连信令转发，未接入 TURN，也未做设备选择、输入音量条、说话人检测、服务端录音或历史回放。
- `payload` 当前按对象校验并限制为 16KB；如果后续前端信令格式变更，需要同步更新这里的校验规则。
## 修复补充（review findings）

### 本次改动
- 重写 `backend/tests/test_game_voice_signaling.py`，移除模块级 `torch` stub 注入，不再污染 `sys.modules`。
- 保留并整理既有 voice signaling 用例，补充以下错误分支覆盖：
  - 玩家当前不在房间时发送 `voice_state`
  - 玩家当前不在房间时发送 `voice_signal`
  - `voice_signal.payload` 不是对象
- 本次没有修改 `backend/app/interfaces/websocket/game_handler.py` 的语音信令实现，也没有触碰任何非语音玩法逻辑。

### 测试命令与结果
- RED：
  - `& 'D:\\Program Files\\Python3.10\\Scripts\\pytest.exe' backend/tests/test_game_voice_signaling.py -v`
  - 结果：`1 failed, 6 passed`
  - 失败点：新增“当前不在房间时发送 voice_signal”用例，断言文案写成了“语音信令”，而现有实现实际返回“语音信号”。
- GREEN：
  - `& 'D:\\Program Files\\Python3.10\\Scripts\\pytest.exe' backend/tests/test_game_voice_signaling.py -v`
  - 结果：`7 passed`
- 回归：
  - `& 'D:\\Program Files\\Python3.10\\Scripts\\pytest.exe' backend/tests/test_game_websocket.py -v`
  - 结果：`5 passed`
- 环境说明：
  - 直接运行 `python -m pytest ...` 会落到 `D:\\Program Files\\Python27\\python.exe`，该环境没有安装 `pytest`，因此本次实际使用了项目可用的 `D:\\Program Files\\Python3.10\\Scripts\\pytest.exe`。

### Reviewer finding 处理说明
1. `backend/tests/test_game_voice_signaling.py` 全局注入 `torch` stub：
   - 已处理。当前测试文件不再在模块导入时写入 `sys.modules`，也不再依赖 `torch` stub。
   - 之所以可以移除，是因为当前 `game_handler.py` 在运行时不再强制导入 `GameAppService` 的重依赖链。
2. 补齐 non-dict payload 和 no current room 分支：
   - 已处理。新增了 `voice_signal.payload` 非对象、`voice_state` 无当前房间、`voice_signal` 无当前房间三条覆盖。
3. 关于 `game_handler.py` 中 unrelated gameplay/AI/doubling diff 的 critical finding：
   - 本次未处理，也未回退。
   - 原因是该 finding 明确涉及与 Task 1 语音信令无关的既有未提交改动，而仓库与任务说明都禁止回退自己未引入的改动。
   - 本次修复仅限测试文件与报告补充，确保不覆盖用户或其他 agent 的工作。
