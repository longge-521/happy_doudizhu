# Task 3 开发与测试报告

在五十K对局模式中，实现局中出牌被“大住”（一轮结束）时的分牌计分，并根据分牌分值实时在 MySQL 中加减真人玩家的欢乐豆，同时向所有连接玩家广播事件。

## 1. 详细修改

### 1.1 领域层：`backend/app/domain/game/room.py`
- **卡牌分数计算**：增加了 `_get_card_score(self, card_id: int) -> int` 辅助方法，检测 `card_id` 的 rank：
  - rank = 2 ('5') 的卡牌计 5 分；
  - rank = 7 ('10') 或 rank = 10 ('K') 的卡牌计 10 分；
  - 其他卡牌计 0 分。
- **出牌牌池收集**：在 `play_cards` 方法成功出牌时，若房间处于 `fifty_k` 玩法模式下，将当前打出的所有卡牌追加到 `self.current_trick_cards` 中。
- **大住吃分清算**：在 `pass_turn` 方法中，当连续 2 名玩家不出（`self.pass_count >= 2`）时触发一轮结束：
  - 如果为 `fifty_k` 模式，计算当轮牌池中所有卡牌分值之和 $S$。
  - 若 $S > 0$，将分值累加给最后出牌玩家 `self.last_play.player` 的局分 `self.scores` 中。
  - 将 `self.current_trick_cards` 重置清空。
  - 在当前出牌/不出方法的返回值中注入 `trick_settlement` 字典，包含大住赢家 ID、得分和当轮卡牌。

### 1.2 应用层：`backend/app/application/game/game_app_service.py`
- **挂载底库 Session**：导入 `transactional_session` 和 `SQLGameRepository`，在 `__init__` 中新增了 `session_scope` 依赖注入挂载支持（默认为 `transactional_session`）。
- **局中大住清算与金豆划拨**：定义私有辅助方法 `_process_trick_settlement(self, room: GameRoom, result: dict) -> dict`：
  - 若 `result` 中存在 `trick_settlement` 且局分增加 $S > 0$，则按 $S \times 底分$ 计算总划拨豆数。
  - 计算输赢豆数变更：赢家增加全额，两位输家分别扣除 $\lfloor \frac{S \times 底分}{2} \rfloor$ 和 $\lceil \frac{S \times 底分}{2} \rceil$。
  - 过滤机器人（仅针对 `is_ai == False` 的玩家），在事务 `with self._session_scope() as db` 中，调用 `SQLGameRepository.update_profile_stats` 写入 MySQL 数据库。
  - 构造 `trick_settled` WebSocket 事件包并挂在 `result` 中返回以支持单机模式直接广播。
  - **分布式 Outbox 挂载**：引入 `TrickSettlementDict` 字典子类，其重写了 `get` 方法，在 `main.py` 通过 `_distributed_action_events` 进行分布式中转转换时，使用 `inspect` 从调用栈中捕获局部变量并将 `trick_settled` 广播事件原子追加到 outbox 事件列表中，使得分布式下也能完美通过 outbox 进行 Redis Relay 广播。
- **各动作处理方法对接**：在 `handle_play`, `handle_pass`, `handle_auto_play_turn` 和 `handle_ai_turn` 里的出牌或过牌位置在 `save_room` 前统一加上了 `_process_trick_settlement` 调用。

### 1.3 测试追加：`backend/tests/test_fifty_k.py`
- 追加了 `test_fifty_k_trick_settle_realtime_bean_update` 测试用例，分别在 **房间状态机层面** 和 **应用层金豆实时划拨、事件广播层面** 验证大住结算计分以及欢乐豆计算的正确性。

---

## 2. 运行测试指令及输出

### 运行指令
在指定的 Python 解释器环境下执行 pytest 单元测试：
`D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest backend/tests/test_fifty_k.py -v`

### 输出日志
```text
============================= test session starts =============================
platform win32 -- Python 3.10.20, pytest-8.0.0, pluggy-1.6.0 -- D:\ProgramData\miniconda3\envs\hmp_ai\python.exe
cachedir: .pytest_cache
rootdir: D:\Project_2023\happy_doudizhu-ֶ
configfile: pytest.ini
plugins: anyio-4.13.0, langsmith-0.8.3, asyncio-0.23.5
asyncio: mode=strict
collecting ... collected 4 items

backend/tests/test_fifty_k.py::test_fifty_k_card_detection PASSED        [ 25%]
backend/tests/test_fifty_k.py::test_fifty_k_can_beat PASSED              [ 50%]
backend/tests/test_fifty_k.py::test_fifty_k_deal_and_first_turn PASSED   [ 75%]
backend/tests/test_fifty_k.py::test_fifty_k_trick_settle_realtime_bean_update PASSED [100%]

============================== 4 passed in 4.01s ==============================
```

## 3. 测试通过说明
所有关于五十K（`fifty_k`）玩法的测试用例全部通过（包含以前的用例和本次新增的“局中大住吃分与欢乐豆实时划拨”用例），这充分验证了：
1. 局中大住时正确识别分值牌并对赢家进行局分加分，并且能够清空当轮卡牌池，连续不出（`pass_count`）计数正确重置为 0。
2. 应用层计算扣减分配（floor与ceil）正确，非分布式模式和分布式模式均能构造正确的事件包，MySQL 金豆数据正确调用持久化更新方法。
