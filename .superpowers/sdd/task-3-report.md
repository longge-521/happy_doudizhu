# Task 3: 应用服务层流程编排 (开局与结算回放) - 执行报告

## 1. 任务背景与目标
本任务是“不洗牌模式”的第三阶段。在此阶段中，我们将之前实现的 Domain 层逻辑（不洗牌切牌与分发、回收牌堆）和 Infrastructure 层逻辑（Redis 不洗牌队列及不洗牌池管理）无缝嵌入到应用服务层（Application Service）及接口层（WebSocket / API）的实际对局流程中，实现完整物理闭环。

主要目标包括：
- 更新 `GameAppService` 相关匹配与发牌接口，使其能根据匹配的模式（`classic` / `no_shuffle`）动态处理。
- 更新 `_create_room` 流程：如果是不洗牌模式，尝试从 Redis 池中弹出最新的一叠不洗牌牌堆。若为空则优雅退避至经典随机发牌。
- 更新对局出牌与结算流程：在某玩家出完最后一张手牌触发结算时，在保存房间前，同步回收对局中的所有 54 张扑克牌并推回 Redis 的不洗牌历史池。
- 更新 WebSocket 网关与持久化调度器：对客户端传入的匹配模式 `play_mode` 进行参数提取和合法性校验，并在 `game_start` 事件中回传当前玩法，以使用户客户端能感知到真实的对战玩法状态。

---

## 2. 代码改动清单

### 后端服务核心与网关修改
1. **[game_app_service.py](file:///D:/Project_2023/happy_doudizhu-欢乐斗地主/backend/app/application/game/game_app_service.py)**
   - 修改 `join_match`、`match_ai_for_player`、`fill_with_ai` 以及 `_create_room` 参数列表，增加 `play_mode: str = "classic"` 参数。
   - 在向仓储层调用匹配队列、匹配长度及弹出匹配玩家时，将 `play_mode` 进行参数透传。
   - 在 `_create_room` 中，如果 `play_mode == "no_shuffle"` 则尝试调用 `_repo.pop_no_shuffle_deck()` 提取牌堆，有则调用领域实体的 `deal_with_deck(deck)` 发牌，否则退避执行 `deal()`。
   - 增加辅助方法 `_check_and_recycle_no_shuffle(self, room)`：判断当房间状态为 `GamePhase.SETTLING` 且玩法为不洗牌模式时，安全调用 `room.recycle_cards()` 并将结果通过 `_repo.push_no_shuffle_deck(recycled)` 回收到 Redis 中，并设置防重复回收的标志位 `room._has_recycled = True`。
   - 在 `handle_play`、`handle_auto_play_turn` 和 `handle_ai_turn` 结算保存房间前调用上述回收方法。
   - 在分布式 `game_start` 事件广播 payload 中注入 `"play_mode": room.play_mode`。

2. **[game_handler.py](file:///D:/Project_2023/happy_doudizhu-欢乐斗地主/backend/app/interfaces/websocket/game_handler.py)**
   - 在解析 WebSocket 对局指令 `action == "join_match"` 时，提取 `play_mode` 字段并校验其是否在合法模式（`classic`, `no_shuffle`）中，若不合法直接返回 error 报错。
   - 在发送客户端通知事件 `game_start` 的 payload 中，回传玩法模式 `"play_mode": getattr(room, "play_mode", "classic")`。
   - 在 `_handle_delayed_ai_match` 延迟匹配 AI 方法及其调用的 `match_ai_for_player` 处透传 `play_mode`。

3. **[main.py](file:///D:/Project_2023/happy_doudizhu-欢乐斗地主/backend/main.py)**
   - 在持久化调度器轮询 `task.task_type == "match_ai"` 进行 AI 强制补位匹配时，从任务 payload 中提取 `play_mode` 并传递给服务层的 `match_ai_for_player` 接口，以保持模式一致性。

---

## 3. 测试与验证

### 编写集成测试用例
我们在 **[test_no_shuffle_integration.py](file:///D:/Project_2023/happy_doudizhu-欢乐斗地主/backend/tests/test_no_shuffle_integration.py)** 中编写了以下两个核心集成测试用例：
1. `test_join_match_and_deal_from_pool`:
   - 模拟不洗牌池（Redis）中已有一叠历史牌堆。
   - 模拟 3 名玩家加入匹配，触发房间创建。
   - 验证服务层调用了 `pop_no_shuffle_deck` 正确弹出发牌堆。
2. `test_play_cards_and_recycle_to_pool`:
   - 模拟一个进行中的不洗牌房间，且给地主玩家仅剩下一张单牌，其余两家留存各三张手牌。
   - 模拟调用服务层的 `handle_play` 动作，令该玩家打出最后一张牌，从而触发游戏终局结算。
   - 验证服务层成功拦截并在保存房间前，调用 `recycle_cards()`，将拼接还原出来的 54 张原始牌堆成功通过 `push_no_shuffle_deck` 推回 Redis 回收池。

### 测试执行结果
我们使用以下命令运行了测试用例：
`D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest tests/test_no_shuffle_integration.py -v`

测试结果输出：
```text
tests\test_no_shuffle_integration.py::test_join_match_and_deal_from_pool PASSED [ 50%]
tests\test_no_shuffle_integration.py::test_play_cards_and_recycle_to_pool PASSED [100%]

======================== 2 passed in 6.21s =========================
```
测试完全通过，说明开局发牌及终局结算回牌逻辑完备正确。

---

## 4. 文档演进说明
我们根据仓库规范，同步更新了根目录下的 **[README.md](file:///D:/Project_2023/happy_doudizhu-欢乐斗地主/README.md)**。在 **🃏 不洗牌模式算法与基础设施支持** 章节下新增了以下小节，确保开发文档与代码实现完美对齐：
- **流程编排与网关集成**：支持通过 `play_mode` 路由匹配队列，开局优先从 Redis 弹回不洗牌历史牌堆（若为空则优雅退避经典发牌）；终局结算时在保存房间前自动同步回收 54 张手牌和底牌，推回 Redis 不洗牌历史池以完成闭环；在 WebSocket 的 `game_start` 事件中回传当前玩法，以供前端正确感知。
