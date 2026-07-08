# DouZero AI 提示与托管出牌设计

## 背景

当前前端出牌提示主要由 `frontend/src/utils/cardUtils.ts` 中的规则函数计算，能枚举合法出牌并支持循环提示。但这套逻辑只基于当前手牌和上家出牌判断，缺少完整局面信息，无法利用已经集成的 DouZero 训练模型。

项目后端已经存在 DouZero 权重文件：

- `backend/app/domain/game/weights/landlord.ckpt`
- `backend/app/domain/game/weights/landlord_up.ckpt`
- `backend/app/domain/game/weights/landlord_down.ckpt`

并且 `ai_decide_play()` 已经在 AI 机器人回合中优先尝试 DouZero 推理。用户确认模型推理可用，因此提示出牌和真人托管出牌都应直接使用 DouZero 模型结果。

## 目标

1. 点击“提示”时，使用 DouZero 模型返回的候选出牌，不再以旧前端规则作为正常提示来源。
2. 后端返回按 DouZero 评分从高到低排序的多个候选，前端每次点击“提示”依次切换。
3. 用户进入托管模式后，轮到该用户出牌时直接使用 DouZero 模型自动决策。
4. 所有真实出牌仍经过 `GameRoom.play_cards()` 或 `GameRoom.pass_turn()` 校验，避免非法操作。
5. DouZero 异常时保留兜底机制，不能让游戏卡死。

## 非目标

- 不把 `.ckpt` 权重文件搬到前端。
- 不在前端复刻 DouZero 推理。
- 不改变斗地主牌型合法性规则。
- 不改变机器人玩家身份、房间状态机、结算规则。
- 不重构无关的前端 UI 或游戏流程。

## 方案概述

后端新增一个“DouZero 候选排序”能力。它先基于当前玩家手牌和上家出牌生成合法候选，再交给 DouZero 模型评分，最后按分数从高到低返回候选列表。

提示和托管共用同一套后端能力：

```text
当前房间状态
→ 构造 AIContext
→ 枚举合法候选
→ DouZero 对候选评分
→ 返回排序后的候选
```

提示按钮使用完整候选列表。托管出牌只取第一项，也就是 DouZero 评分最高的一手；如果第一项为空数组，表示“不出”。

## 后端设计

### 1. AI 策略层新增候选排序函数

在 `backend/app/domain/game/ai_strategy.py` 中新增函数，例如：

```python
def ai_rank_play_candidates(
    hand: List[int],
    last_play: Optional[CardPlay],
    must_play: bool,
    ctx: AIContext,
) -> List[List[int]]:
    ...
```

返回值含义：

- `[[...], [...]]`：按 DouZero 分数降序排列的候选出牌。
- `[]`：无可用候选，调用方需要按当前阶段决定是否报错或过牌。
- 候选中的空数组 `[]`：表示 DouZero 认为当前应“不出”。

正常路径：

1. 调用现有 `generate_legal_actions_dz()` 生成合法候选。
2. 调用 `get_obs_for_douzero()` 构造模型输入。
3. 通过 `douzero_manager.get_action_value()` 获取每个候选分数。
4. 按分数从高到低排序。
5. 将 DouZero 动作转换回项目内部牌 ID。

异常兜底：

- 如果 DouZero 不可用、推理异常、候选构造异常，则记录日志。
- 兜底可调用当前规则 AI 的 `ai_decide_play()` 得到一手候选。
- 兜底只保证游戏可继续，不作为正常提示来源。

### 2. 现有机器人出牌复用排序结果

`ai_decide_play()` 可以继续保留现有签名，但内部优先调用 `ai_rank_play_candidates()`：

```text
候选列表非空 → 返回第一个候选
候选列表为空 → 使用规则兜底或返回 None
```

这样机器人、提示、托管三者的最佳出牌来源保持一致。

### 3. 应用服务新增提示接口能力

在 `backend/app/application/game/game_app_service.py` 中新增方法，例如：

```python
async def get_ai_play_hints(self, player_id: str) -> dict:
    ...
```

职责：

1. 根据 `player_id` 找到当前房间。
2. 校验房间处于 `PLAYING` 阶段。
3. 校验当前轮到该玩家。
4. 读取该玩家手牌、`room.last_play.card_play`、`must_play`。
5. 使用 `build_ai_context(room, player_id)` 构造上下文。
6. 调用 `ai_rank_play_candidates()`。
7. 返回候选列表和是否可不出。

### 4. WebSocket 新增提示动作

在 `backend/app/interfaces/websocket/game_handler.py` 中新增客户端动作：

```text
get_ai_hints
```

服务端返回事件：

```json
{
  "event": "ai_hints",
  "candidates": [[1, 2, 3], [4, 5, 6]],
  "source": "douzero"
}
```

异常返回：

```json
{
  "event": "error",
  "msg": "当前无法获取 AI 提示"
}
```

说明：

- `candidates` 中如果包含 `[]`，表示“不出”候选。
- 前端应过滤或特殊处理 `[]`，避免把空牌组选中。
- `source` 用于调试和后续日志观察，正常值为 `douzero`，兜底时可为 `fallback`。

### 5. 托管出牌能力

真人玩家进入托管后，轮到该玩家时后端直接使用与机器人相同的 AI 决策能力：

```text
托管玩家回合
→ 调用 ai_rank_play_candidates()
→ 取第一项
→ 非空则 play_cards
→ 空数组或 None 则 pass_turn
```

托管状态可以由前端通过 WebSocket 通知后端保存，例如新增：

```text
set_auto_play
```

载荷：

```json
{
  "action": "set_auto_play",
  "enabled": true
}
```

后端需要记录当前房间内哪些真人玩家处于托管状态。为保持改动克制，优先放在房间状态中，例如 `auto_play_players: Set[str]`，并随 Redis 房间状态持久化。

## 前端设计

### 1. 提示按钮改为请求后端 DouZero 候选

`GameRoomView.vue` 中的提示逻辑调整为：

```text
首次点击提示或当前候选已失效
→ 发送 get_ai_hints
→ 收到 ai_hints 后缓存 candidates
→ 选中第 1 个非空候选

再次点击提示
→ 在缓存 candidates 中切换下一项
```

候选缓存重置时机：

- `currentTurn` 变化。
- `myHand` 变化。
- `lastPlay` 变化。
- `gamePhase` 变化。
- 玩家手动出牌或过牌后。

### 2. 提示按钮文案

保留当前“提示 1/N”的交互，但含义变为 DouZero 排序候选：

```text
提示
提示 1/4
提示 2/4
```

如果后端返回空候选或只有“不出”候选，按钮可显示：

```text
要不起
```

### 3. 托管模式改为后端 AI 执行

当前前端超时托管会使用本地推荐牌自动出牌。改造后：

- 前端负责进入或退出托管状态。
- 托管期间不再由前端计算推荐牌并发送 `play_cards`。
- 后端在轮到托管玩家时自动出牌或过牌。

前端仍可保留倒计时和托管状态展示。

## 数据与协议

新增 WebSocket 客户端动作：

| 动作 | 用途 |
| --- | --- |
| `get_ai_hints` | 获取 DouZero 排序后的候选提示 |
| `set_auto_play` | 设置当前真人玩家是否托管 |

新增服务端事件：

| 事件 | 用途 |
| --- | --- |
| `ai_hints` | 返回 DouZero 候选提示 |
| `auto_play_changed` | 广播或回传托管状态变化 |

房间状态新增字段：

```python
auto_play_players: Set[str]
```

玩家视角中可增加：

```json
{
  "auto_play_players": ["player_1"]
}
```

## 错误处理

- 非自己回合请求提示：返回错误，不生成候选。
- 非 `PLAYING` 阶段请求提示：返回错误。
- DouZero 推理异常：记录日志，使用规则 AI 单手兜底。
- 托管自动出牌失败：尝试过牌；如果规则不允许过牌，则记录错误并停止本次托管动作，避免死循环。
- 后端返回的候选必须经过 `detect_card_type()` 和 `can_beat()` 过滤，避免前端收到非法建议。

## 测试计划

### 后端自动化测试

新增或扩展 `backend/tests/test_ai_strategy.py`：

1. DouZero 候选排序函数返回多个合法候选。
2. 排序结果第一项可被 `ai_decide_play()` 使用。
3. 跟牌场景中候选都能压过上家，或包含合法“不出”。
4. DouZero 异常时能返回兜底候选，不抛出到 WebSocket 层。

新增或扩展 WebSocket/API 相关测试：

1. 当前玩家请求 `get_ai_hints` 能收到 `ai_hints`。
2. 非当前玩家请求提示会收到错误。
3. 托管玩家轮到出牌时，后端自动调用 AI 决策并推进回合。
4. 退出托管后不再自动出牌。

### 前端验证

1. 点击“提示”后选中 DouZero 返回的第一候选。
2. 连续点击“提示”能在后端返回候选中循环切换。
3. 回合变化、手牌变化、上家出牌变化后提示缓存重置。
4. 进入托管后，前端不再本地自动出牌，由后端推进。
5. 退出托管后，玩家恢复手动出牌。

### 手动联调

1. 真人对 AI 对局中，点击提示观察第一手是否来自后端 `ai_hints`。
2. 连续点击提示，确认顺序切换的是 DouZero 排序候选。
3. 进入托管，确认轮到自己时自动出牌且对局不中断。
4. 跟牌要不起时，确认提示和托管都会正确“不出”。
5. DouZero 模型加载正常时，日志不出现规则兜底警告。

## 实施顺序建议

1. 后端先实现 `ai_rank_play_candidates()` 并补单元测试。
2. 调整 `ai_decide_play()` 复用排序结果，确认现有 AI 测试通过。
3. 新增 `get_ai_hints` WebSocket 动作。
4. 前端提示按钮接入 `ai_hints` 事件并保留候选循环 UI。
5. 后端保存真人托管状态并在回合处理器中自动执行。
6. 前端托管模式改为通知后端，不再本地规则自动出牌。

## 风险与取舍

- DouZero 候选评分需要模型推理，点击提示可能比纯前端规则略慢。可通过缓存当前回合候选降低重复请求。
- 候选列表过多时不应全部返回，建议后端限制前 8 到 12 个候选。
- 托管状态放入房间状态会影响 Redis 序列化，需要同步 `to_dict()` 和 `from_dict()`。
- 旧前端规则可以保留作为异常兜底，但正常提示来源必须是 DouZero 模型。
