# 斗地主正式加倍阶段设计

## 背景

当前对局在确定地主后直接进入 `PLAYING`，地主可以立刻出牌。前端虽然已有“加倍 / 超级加倍 / 不加倍”的按钮、展示和语音，但这些状态主要由 `GameRoomView.vue` 本地模拟：不会写入后端房间状态，也不会通过 Redis 序列化保存。

这会带来几个问题：

- 刷新或重连后，加倍选择会丢失。
- 真实多人对局中，其他玩家无法可靠看到每个人的选择。
- AI 加倍只是前端随机模拟，不参与后端流程。
- 结算倍数与前端显示倍数可能不一致。

本设计把“确定地主后的加倍确认”改为服务端正式流程。

## 目标

- 地主确定后，三名玩家都必须确认是否加倍。
- 保留三个选项：`加倍`、`超级加倍`、`不加倍`。
- 每名玩家的选择要在对应出牌位置显示。
- 每名玩家选择后要播放对应语音。
- 加倍结果必须进入服务端房间状态、Redis 序列化、重连视图和最终结算倍数。
- 三人都确认后，才进入真正出牌阶段，由地主先出牌。

## 非目标

- 不调整叫地主/抢地主规则。
- 不新增欢乐豆准入或扣费规则。
- 不重做对局 UI 布局。
- 不改变炸弹、王炸导致的后续翻倍规则。

## 阶段设计

新增游戏阶段：

```text
DOUBLING
```

完整流程调整为：

```text
MATCHING -> DEALING -> CALLING -> DOUBLING -> PLAYING -> SETTLING
```

地主确定时：

- `landlord` 写入地主玩家 ID。
- 底牌加入地主手牌。
- `phase` 设置为 `DOUBLING`。
- `current_turn` 暂时置空，避免任何玩家在加倍确认完成前出牌。
- `turn_deadline` 设置为当前时间加 15 秒，用于前端显示加倍倒计时。
- 初始化 `doubling_choices = {}`。

三人都确认后：

- `phase` 设置为 `PLAYING`。
- `current_turn` 设置为地主。
- `turn_deadline` 重置为当前时间加 15 秒。
- 保留 `doubling_choices`，用于刷新、重连和结算前展示。

## 加倍选择与倍数

服务端保存每个玩家的选择：

```json
{
  "player_id_1": "double",
  "player_id_2": "super",
  "player_id_3": "none"
}
```

选项含义：

| 选择 | 展示文本 | 倍数变化 |
| --- | --- | --- |
| `double` | 加倍 | 当前总倍数乘以 2 |
| `super` | 超级加倍 | 当前总倍数乘以 4 |
| `none` | 不加倍 | 不改变倍数 |

同一玩家只能选择一次。重复选择返回错误。

## WebSocket 协议

### 客户端动作

新增：

```json
{
  "action": "choose_double",
  "choice": "double"
}
```

`choice` 允许值：

- `double`
- `super`
- `none`

### 服务端事件

地主确定事件继续使用 `landlord_decided`，但此时房间视图中的 `phase` 为 `DOUBLING`。

新增单人选择广播：

```json
{
  "event": "double_chosen",
  "player": "player_id",
  "choice": "double",
  "label": "加倍",
  "multiplier": 6,
  "room_state": {}
}
```

新增加倍阶段结束广播：

```json
{
  "event": "doubling_finished",
  "current_turn": "landlord_player_id",
  "multiplier": 24,
  "room_state": {}
}
```

`room_state` 中补充：

```json
{
  "doubling_choices": {
    "player_id_1": "double",
    "player_id_2": "super",
    "player_id_3": "none"
  }
}
```

## 后端设计

### `GameRoom`

新增属性：

- `doubling_choices: Dict[str, str]`

新增方法：

- `choose_double(player_id: str, choice: str) -> dict`
- `_finish_doubling() -> dict`

关键规则：

- 只有 `DOUBLING` 阶段允许选择加倍。
- `choice` 必须是 `double | super | none`。
- 玩家必须属于当前房间。
- 每名玩家只能选择一次。
- 选择 `double` 时 `multiplier *= 2`。
- 选择 `super` 时 `multiplier *= 4`。
- 三名玩家都选择后进入 `PLAYING`。

序列化与视图：

- `to_dict()` 写入 `doubling_choices`。
- `from_dict()` 读取 `doubling_choices`。
- `get_player_view()` 返回 `doubling_choices`。

### `GameAppService`

新增：

- `handle_double_choice(player_id: str, choice: str) -> dict`

AI 流程：

- `_process_ai_turns()` 在 `DOUBLING` 阶段也会处理 AI。
- AI 默认根据简单策略选择：
  - 地主或手牌较强时可选择 `double`。
  - 暂不让 AI 选择 `super`，避免倍率过度膨胀。
  - 否则选择 `none`。

## 前端设计

### Store

`gameStore` 新增：

- `doublingChoices: Record<string, 'double' | 'super' | 'none'>`

`updateFromRoomState()` 同步 `doubling_choices`。

`reset()` 清空 `doublingChoices`。

### WebSocket 事件处理

新增处理：

- `double_chosen`
  - 同步 `room_state`。
  - 写入 `playerActions[player]` 为“加倍 / 超级加倍 / 不加倍”。
  - 播放对应语音。
- `doubling_finished`
  - 同步 `room_state`。
  - 设置阶段为 `PLAYING`。
  - 当前回合变为地主。

`landlord_decided` 不再直接强制设置为 `PLAYING`，而是尊重 `room_state.phase`。

### 对局页

移除本地模拟状态：

- `localDoublingState`
- `myDoublingChoice`
- 前端随机 AI 加倍模拟
- 前端直接修改 `gameStore.multiplier`

加倍面板显示条件改为：

- `gameStore.gamePhase === 'DOUBLING'`
- 当前玩家还没有选择

按钮点击改为发送：

```ts
sendAction({ action: 'choose_double', choice: 'double' })
```

出牌位置显示：

- 继续使用 `gameStore.playerActions[playerId]` 展示刚发生的选择。
- 玩家头像附近的加倍标识改为从 `gameStore.doublingChoices` 计算。

超时逻辑：

- `DOUBLING` 阶段倒计时为 0 时，自动发送 `none`。
- 进入 `PLAYING` 后恢复原出牌超时逻辑。

## 语音设计

复用已有音效：

| 选择 | 语音 |
| --- | --- |
| `double` | `doubling` 后接 `jiabei` |
| `super` | `doubling` 后接 `superDouble` |
| `none` | `bujiabei` |

语音播放由 `double_chosen` 事件触发，这样自己、其他真人玩家和 AI 的选择都使用同一套逻辑。

## 测试计划

后端：

- 地主确定后进入 `DOUBLING`，不是直接进入 `PLAYING`。
- 三名玩家选择完成前不能出牌。
- `double` 会让倍数乘以 2。
- `super` 会让倍数乘以 4。
- `none` 不改变倍数。
- 重复选择会失败。
- 三名玩家都选择后进入 `PLAYING`，由地主先出牌。
- `to_dict()` / `from_dict()` 保留 `doubling_choices`。
- `get_player_view()` 返回 `doubling_choices`。

前端：

- 收到 `landlord_decided` 后进入 `DOUBLING`。
- 收到 `double_chosen` 后显示对应文字并播放对应语音。
- 收到 `doubling_finished` 后进入 `PLAYING`。
- `DOUBLING` 阶段超时自动发送 `none`。

## 风险与取舍

- 新增阶段会影响所有判断 `PLAYING` 的地方，需要逐处确认是否应包含 `DOUBLING`。
- AI 加倍先用保守规则，不引入复杂牌力评估，避免扩大改动。
- 保留 `landlord_decided` 事件名可减少前端协议改动，但需要明确它现在表示“地主已确定，进入加倍确认”，不是“可以立刻出牌”。
