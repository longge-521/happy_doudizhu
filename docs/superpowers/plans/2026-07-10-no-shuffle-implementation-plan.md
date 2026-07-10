# 🃏 不洗牌玩法 (No-Shuffle Mode) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为欢乐斗地主对战系统新增“不洗牌玩法”，物理隔离不同模式的匹配队列，使用 Redis 公共列表持久化与传递废牌堆，在 DDD 架构下实现切牌、分发和防重防漏的健壮收牌重组算法，并设计高辨识度的火焰暗红烈火战局前端 UI。

**Architecture:** 
1. 应用层和基础设施层闭环处理 Redis 牌堆池（List 存取与 LTRIM 容量裁剪），解耦 Room 领域层。
2. 领域层实现 `cut_cards` 切牌算法，利用手牌切片机制保留牌序相关性。
3. 结算前第一现场同步回收 `all_played_cards` 与手牌剩余牌组合成 54 张，校验一致性防污染入池。

**Tech Stack:** Python 3.10, FastAPI, Vue 3, Pinia, Redis, RabbitMQ, Pytest

## Global Constraints
* 严禁批量删除文件或目录。禁止使用 `rm -rf` 等危险指令。
* **Git 提交确认约束**：完成每一项子任务开发、并通过单测后，智能体必须**先列出本次改动相关的功能点提醒用户手动测试**，并在**用户回复确认无误后**，方可执行 `git commit` 将代码提交。
* 所有的 git commit 提交信息必须全部使用中文书写。
* 所有新增和优化的功能，在本次开发彻底完成后，必须同步记录到项目根目录下的 `README.md`。

---

### Task 1: 领域层算法实现 (Card 与 GameRoom 扩展)

**Files:**
* Modify: `backend/app/domain/game/card.py`
* Modify: `backend/app/domain/game/room.py`
* Create: `backend/tests/test_no_shuffle_domain.py`

**Interfaces:**
* Produces: 
    * `card.cut_cards(deck: List[int]) -> List[int]`
    * `room.deal_with_deck(deck: List[int]) -> Dict[str, List[int]]`
    * `room.recycle_cards() -> List[int]`

- [ ] **Step 1: 编写 Failing 测试用例**
  创建 `backend/tests/test_no_shuffle_domain.py` 文件，包含对切牌和发牌/回收的测试。
  ```python
  # backend/tests/test_no_shuffle_domain.py
  import pytest
  from app.domain.game.card import Card, FULL_DECK
  from app.domain.game.room import GameRoom, Player

  def test_cut_cards_preserves_length():
      from app.domain.game.card import cut_cards
      deck = list(range(54))
      cut = cut_cards(deck)
      assert len(cut) == 54
      assert set(cut) == set(range(54))
      # 验证没有被打乱（相邻关系多半保留）
      diff_count = sum(1 for i in range(53) if abs(cut[i+1] - cut[i]) != 1)
      assert diff_count <= 2  # 仅在切牌分割点会出现不连续

  def test_deal_with_deck():
      players = [
          Player(id="p1", nickname="P1", is_ai=False),
          Player(id="p2", nickname="P2", is_ai=False),
          Player(id="p3", nickname="P3", is_ai=False),
      ]
      room = GameRoom.create("test_room_1", players, base_score=20)
      room.play_mode = "no_shuffle"
      
      custom_deck = list(range(54))
      hands = room.deal_with_deck(custom_deck)
      
      assert len(room.hands["p1"]) == 17
      assert len(room.hands["p2"]) == 17
      assert len(room.hands["p3"]) == 17
      assert len(room.bottom_cards) == 3
      assert room.phase.value == "CALLING"

  def test_recycle_cards_valid():
      players = [
          Player(id="p1", nickname="P1", is_ai=False),
          Player(id="p2", nickname="P2", is_ai=False),
          Player(id="p3", nickname="P3", is_ai=False),
      ]
      room = GameRoom.create("test_room_1", players, base_score=20)
      room.play_mode = "no_shuffle"
      
      custom_deck = list(range(54))
      room.deal_with_deck(custom_deck)
      
      # 模拟玩家出牌和扣牌
      room.all_played_cards = [0, 1, 2, 3] # 玩家打出的牌
      room.hands["p1"] = list(range(4, 17))
      room.hands["p2"] = list(range(17, 34))
      room.hands["p3"] = list(range(34, 51))
      room.bottom_cards = [51, 52, 53]
      room.landlord = None
      
      recycled = room.recycle_cards()
      assert len(recycled) == 54
      assert set(recycled) == set(range(54))
  ```

- [ ] **Step 2: 运行测试验证其失败**
  在 `backend` 目录下执行命令：
  `D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest tests/test_no_shuffle_domain.py -v`
  预期：FAIL，因为函数与属性未定义。

- [ ] **Step 3: 修改 `card.py` 写入切牌算法**
  在 `backend/app/domain/game/card.py` 末尾追加 `cut_cards`：
  ```python
  def cut_cards(deck: List[int]) -> List[int]:
      """切牌算法：随机选一切割点分成两段拼接，保留局部牌序"""
      if len(deck) != 54:
          return list(deck)
      cut_idx = random.randint(10, 44)
      return deck[cut_idx:] + deck[:cut_idx]
  ```
  并在 `card.py` 头部导入 `random`。

- [ ] **Step 4: 修改 `room.py` 扩展状态和发/收牌逻辑**
  1. 在 `GameRoom.__init__` (约第60-70行) 或 `create` 方法中，添加 `self.play_mode = "classic"`。
  2. 实现 `deal_with_deck` 接口：
     ```python
     def deal_with_deck(self, deck: List[int]) -> Dict[str, List[int]]:
         """传入预设牌堆发牌，应用切牌并切片分发"""
         ids = self._player_ids()
         from app.domain.game.card import cut_cards
         
         cut_deck = cut_cards(deck)
         h1 = sort_cards(cut_deck[0:17])
         h2 = sort_cards(cut_deck[17:34])
         h3 = sort_cards(cut_deck[34:51])
         bottom = sort_cards(cut_deck[51:54])
         
         self.hands = {ids[0]: h1, ids[1]: h2, ids[2]: h3}
         self.bottom_cards = bottom
         self.phase = GamePhase.CALLING
         self.landlord = None
         self.last_play = LastPlay()
         self.pass_count = 0
         self.doubling_choices = {}
         self.show_cards_players = {}
         self.all_played_cards = []
         self.play_history = []
         self.auto_play_players = set()
         
         import random
         self._first_caller_index = random.randint(0, 2)
         self._call_index = self._first_caller_index
         self.current_turn = ids[self._first_caller_index]
         self.turn_deadline = time.time() + 18
         return dict(self.hands)
     ```
  3. 实现 `recycle_cards` 接口：
     ```python
     def recycle_cards(self) -> List[int]:
         """回收已打出和未打出的牌堆"""
         recycled = list(self.all_played_cards)
         # 按玩家座位顺序收集剩余手牌
         for p in self.players:
             recycled.extend(self.hands.get(p.id, []))
         # 如果底牌没有发给任何人且未出现在出牌/手牌中，则追加底牌
         if self.landlord is None:
             recycled.extend(self.bottom_cards)
         
         # 严格校验是否构成完整的54张牌
         if len(recycled) == 54 and sorted(recycled) == list(range(54)):
             return recycled
         # 失败防御兜底
         return list(range(54))
     ```
  4. 别忘了在 `to_dict` 和 `from_dict` 序列化方法中，保存和加载 `self.play_mode` 属性，以及在 `room.py` 头部引入 `Card` 模块。

- [ ] **Step 5: 运行单元测试验证其通过**
  执行：`D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest tests/test_no_shuffle_domain.py -v`
  预期：PASS。

- [ ] **Step 6: 请求用户人工确认后提交代码**
  * 提醒用户手动测试建议点：验证后端 Room 领域层切牌、分牌和回牌无重漏校验的单元测试。
  * 经确认后执行 `git commit -m "feat: 领域层增加不洗牌切牌分发与回收重组算法"`。

---

### Task 2: 基础设施层 Redis 仓储适配 (匹配队列物理隔离与不洗牌池)

**Files:**
* Modify: `backend/app/infrastructure/redis_game_repository.py`
* Create: `backend/tests/test_no_shuffle_redis.py`

**Interfaces:**
* Consumes: Redis API
* Produces:
    * `redis_game_repository.add_to_match_queue(player_id, base_score, play_mode)`
    * `redis_game_repository.pop_no_shuffle_deck() -> Optional[List[int]]`
    * `redis_game_repository.push_no_shuffle_deck(deck: List[int])`

- [ ] **Step 1: 编写 Failing 测试用例**
  创建 `backend/tests/test_no_shuffle_redis.py` 文件：
  ```python
  # backend/tests/test_no_shuffle_redis.py
  import pytest
  from unittest.mock import AsyncMock, patch
  from app.infrastructure.redis_game_repository import RedisGameRepository

  @pytest.mark.asyncio
  async def test_match_queue_key_isolation():
      mock_redis = AsyncMock()
      repo = RedisGameRepository(mock_redis)
      
      # 传入 play_mode 并验证 key 变化
      with patch.object(repo, "_redis") as mock_r:
          await repo.add_to_match_queue("p1", base_score=20, play_mode="no_shuffle")
          mock_r.rpush.assert_called_once_with("game:match_queue:no_shuffle:20", "p1")

  @pytest.mark.asyncio
  async def test_push_and_pop_deck_pool():
      mock_redis = AsyncMock()
      repo = RedisGameRepository(mock_redis)
      
      # 模拟 pop 返回数据
      import json
      mock_redis.lpop.return_value = json.dumps(list(range(54))).encode("utf-8")
      
      deck = await repo.pop_no_shuffle_deck()
      assert deck == list(range(54))
      mock_redis.lpop.assert_called_once_with("game:noshuffle:deck_pool")
      
      # 测试 push
      await repo.push_no_shuffle_deck(list(range(54)))
      mock_redis.rpush.assert_called_once()
      mock_redis.ltrim.assert_called_once_with("game:noshuffle:deck_pool", -100, -1)
  ```

- [ ] **Step 2: 运行测试验证其失败**
  执行：`D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest tests/test_no_shuffle_redis.py -v`
  预期：FAIL。

- [ ] **Step 3: 修改 `redis_game_repository.py` 实现路由与池接口**
  1. 修改 `_get_queue_key` 支持玩法分类：
     ```python
     def _get_queue_key(self, base_score: int, play_mode: str = "classic") -> str:
         return f"{MATCH_QUEUE_KEY}:{play_mode}:{base_score}"
     ```
  2. 修改 `add_to_match_queue`、`remove_from_match_queue`、`pop_match_players`、`get_match_queue_length` 方法，均新增 `play_mode: str = "classic"` 参数并传给 `_get_queue_key`：
     ```python
     async def add_to_match_queue(self, player_id: str, base_score: int = 10, play_mode: str = "classic") -> None:
         key = self._get_queue_key(base_score, play_mode)
         await self._redis.lrem(key, 0, player_id)
         await self._redis.rpush(key, player_id)
     ```
     (同理修改其它几个方法)
  3. 实现 `pop_no_shuffle_deck` 与 `push_no_shuffle_deck`：
     ```python
     async def pop_no_shuffle_deck(self) -> Optional[List[int]]:
         key = "game:noshuffle:deck_pool"
         raw = await self._redis.lpop(key)
         if not raw:
             return None
         if isinstance(raw, bytes):
             raw = raw.decode("utf-8")
         import json
         return json.loads(raw)

     async def push_no_shuffle_deck(self, deck: List[int]) -> None:
         key = "game:noshuffle:deck_pool"
         import json
         await self._redis.rpush(key, json.dumps(deck))
         # 保留最新的100叠牌，修剪老数据，防止 Redis 内存暴涨
         await self._redis.ltrim(key, -100, -1)
     ```

- [ ] **Step 4: 运行单元测试验证其通过**
  执行：`D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest tests/test_no_shuffle_redis.py -v`
  预期：PASS。

- [ ] **Step 5: 请求用户人工确认后提交代码**
  * 提醒用户手动测试建议点：匹配队列物理路由及 Redis 全局不洗牌池的入队剪裁单元测试。
  * 经确认后执行 `git commit -m "feat: Redis 仓储适配不洗牌匹配路由与全局历史牌池"`。

---

### Task 3: 应用服务层流程编排 (开局与结算回放)

**Files:**
* Modify: `backend/app/application/game/game_app_service.py`
* Create: `backend/tests/test_no_shuffle_integration.py`

**Interfaces:**
* Consumes: `RedisGameRepository`, `GameRoom`
* Produces: `GameAppService` 集成不洗牌开局发牌与结算回牌。

- [ ] **Step 1: 编写 Integration/Service 测试用例**
  创建 `backend/tests/test_no_shuffle_integration.py` 文件：
  ```python
  # backend/tests/test_no_shuffle_integration.py
  import pytest
  from unittest.mock import AsyncMock, patch
  from app.application.game.game_app_service import GameAppService
  from app.domain.game.room import GameRoom

  @pytest.mark.asyncio
  async def test_join_match_and_deal_from_pool():
      mock_repo = AsyncMock()
      service = GameAppService(mock_repo)
      
      # 模拟不洗牌池有一叠牌
      mock_repo.get_player_room.return_value = None
      mock_repo.get_match_queue_length.return_value = 3
      mock_repo.pop_match_players.return_value = ["p1", "p2", "p3"]
      mock_repo.pop_no_shuffle_deck.return_value = list(range(54))
      
      # 拦截开局 Outbox 注入
      with patch("app.infrastructure.config.settings.DISTRIBUTED_MODE", False):
          result = await service.join_match("p1", "玩家1", auto_ai=True, base_score=20)
          
          mock_repo.pop_no_shuffle_deck.assert_called_once()
          # 验证房间创建成功，且发出了手牌
          assert "room_id" in result
  ```

- [ ] **Step 2: 运行测试验证其失败**
  执行：`D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest tests/test_no_shuffle_integration.py -v`
  预期：FAIL。

- [ ] **Step 3: 修改 `game_app_service.py` 中的匹配、开局和出牌流程**
  1. 修改 `join_match` 和 `match_ai_for_player`、`fill_with_ai` 方法，均增加 `play_mode: str = "classic"` 参数：
     ```python
     async def join_match(self, player_id: str, nickname: str, auto_ai: bool = True, base_score: int = 10, play_mode: str = "classic") -> dict:
     ```
     并且在调用 Repository 时透传 `play_mode`。
  2. 修改 `_create_room` 支持不洗牌发牌：
     ```python
     async def _create_room(self, player_ids: List[str], base_score: int = 10, play_mode: str = "classic") -> dict:
         # 创建 Room 阶段
         room = GameRoom.create(room_id, players, base_score=base_score)
         room.play_mode = play_mode
         
         # 尝试从池中拉取牌
         deck = None
         if play_mode == "no_shuffle":
             deck = await self._repo.pop_no_shuffle_deck()
             
         if deck:
             room.deal_with_deck(deck)
         else:
             # 如果池空或经典模式，退避使用经典随机发牌
             room.deal()
     ```
  3. 修改 `play_cards` 方法，在结算且 `no_shuffle` 时，在保存房间前同步回收牌并推入 Redis：
     ```python
     # 检查是否出完 (约在 393 行附近)
     if len(new_hand) == 0:
         settle_res = room._settle(player_id)
         if room.play_mode == "no_shuffle":
             try:
                 recycled = room.recycle_cards()
                 await self._repo.push_no_shuffle_deck(recycled)
             except Exception as e:
                 # 异常保护，不影响主流程结算
                 logger.error(f"回收不洗牌失败: {e}")
         return settle_res
     ```
  4. 修改 WebSocket 网关与 `main.py` 相关的消息路由，使得 WS 的 `join_match` 参数能够正常读取并校验客户端传入的 `play_mode`。
     （修改 `backend/app/interfaces/websocket/game_handler.py:362` 以及 `backend/main.py:575` 附近的逻辑，支持在 Payload 中解析 `play_mode`）

- [ ] **Step 4: 运行测试验证其通过**
  执行：`D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest tests/test_no_shuffle_integration.py -v`
  预期：PASS。

- [ ] **Step 5: 请求用户人工确认后提交代码**
  * 提醒用户手动测试建议点：应用服务层不洗牌开局发牌流与结算期自动回牌机制的集成演练。
  * 经确认后执行 `git commit -m "feat: 应用服务集成不洗牌匹配参数校验与开局/结算收牌流程"`。

---

### Task 4: 前端路由大厅界面与房间适配 (专属主题 UI)

**Files:**
* Modify: `frontend/src/views/LobbyView.vue`
* Modify: `frontend/src/views/GameRoomView.vue`
* Modify: `frontend/src/composables/useGameWebSocket.ts`

- [ ] **Step 1: 前端大厅 UI (LobbyView.vue) 升级**
  1. 新增玩法响应式状态：
     ```typescript
     const playMode = ref<'classic' | 'no_shuffle'>('classic')
     ```
  2. 在场次卡片上方，增加玻璃态切换页签 HTML/CSS：
     ```html
     <div class="mode-tabs glass-panel">
       <button :class="{ active: playMode === 'classic' }" @click="playMode = 'classic'">经典玩法</button>
       <button :class="{ active: playMode === 'no_shuffle' }" @click="playMode = 'no_shuffle'">不洗牌场</button>
     </div>
     ```
  3. 为卡片添加动态类：
     当 `playMode.value === 'no_shuffle'` 时，各卡片添加 `.no-shuffle-tier`。
     并在 CSS 中实现 `.no-shuffle-tier` 的暗红金框与霓虹微光样式。
  4. 新增角标：
     ```html
     <div class="tier-badge" v-if="playMode === 'no_shuffle'">炸弹多</div>
     ```
  5. 修改匹配请求：在点击场次执行 `handleJoinMatch` 时，将 `play_mode: playMode.value` 填入 WS payload 发送。
  6. 在 `matching-overlay` 弹窗中动态改变提示文字并为匹配背景添加火焰暗红毛玻璃特效：
     ```html
     <div class="matching-board glass-panel" :class="{ 'no-shuffle-matching': playMode === 'no_shuffle' }">
     ```

- [ ] **Step 2: 前端游戏房间 (GameRoomView.vue) 专属主题适配**
  1. 在 `GameRoomView.vue` 从 `gameStore` 或路由读取当前对局的 `playMode`（确保后端在 `game_start` 中下发了该字段，并保存在前端 Store 中）。
  2. 为房间主容器绑定动态类：
     ```html
     <div class="game-room-page" :class="{ 'no-shuffle-room': gameStore.playMode === 'no_shuffle' }">
     ```
  3. CSS 背景切换：
     ```css
     .game-room-page.no-shuffle-room {
       background: linear-gradient(135deg, #1d0909 0%, #3a1616 50%, #4e1919 100%) !important;
     }
     ```
  4. 牌桌中央印章：
     在牌桌正中央渲染一个金色暗雕圆形印章：
     ```html
     <div class="no-shuffle-stamp" v-if="gameStore.playMode === 'no_shuffle'">
       <span>不洗牌模式</span>
     </div>
     ```
     并在 CSS 中增加立体暗金描边的印花效果。
  5. 顶栏标识：在头部显示带红色霓虹灯字效的“不洗牌场”。
  6. Mock 模式适配：修改前端 `?mock=true` 下的发牌 Mock 算法（如 `cardUtils.ts`），当匹配进入不洗牌场时，自动将卡牌数组排序并优先分段，确保 Mock 出炸弹牌。

- [ ] **Step 3: 前端代码静态单元测试**
  在前端目录执行：`npm run test:unit`
  确保没有因为类型定义或语法导致编译失败。

- [ ] **Step 4: 请求用户人工确认后提交代码**
  * 提醒用户手动测试建议点：大厅主题瞬变、不洗牌红金战局背景、中央印花及匹配请求参数。
  * 经确认后执行 `git commit -m "style: 前端大厅玩法切换与不洗牌烈火战局专属 UI 适配"`。

---

### Task 5: 规范文档同步 README.md

**Files:**
* Modify: `README.md`

- [ ] **Step 1: 更新 README.md 特性与协议部分**
  1. 在 **✨ 核心功能特性** 章节中添加“不洗牌多人玩法机制”的说明。
  2. 在 **2. WebSocket 长连接交互协议** 章节的 `join_match` 客户端动作说明中添加 `play_mode` 入参规范；在服务端广播 `game_start` 事件说明中加入 `play_mode` 返回说明。
  
- [ ] **Step 2: 全量 pytest 回归测试**
  in `backend` directory:
  `D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest tests/ -v`

- [ ] **Step 3: 请求用户人工确认后提交代码**
  * 提醒用户手动测试建议点：README 文档更新同步以及后端 pytest 全量回归通过性。
  * 经确认后执行 `git commit -m "docs: 同步更新 README.md 不洗牌功能特性与 WebSocket 协议映射说明"`。
