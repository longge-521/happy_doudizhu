# Task 1 执行报告: 领域层算法实现 (Card 与 GameRoom 扩展)

## 1. 任务概述

本任务在欢乐斗地主对战系统的领域层（Domain Layer）实现了“不洗牌”（No-Shuffle）模式的核心底座算法：
- 增加了切牌算法 `cut_cards`，保留局部牌序的完整性。
- 在 `GameRoom` 中增加了对 `play_mode` 属性的初始化（默认 `"classic"`）和序列化支持。
- 实现了 `deal_with_deck` 算法以支持基于不洗牌/自定义牌堆的分发。
- 实现了 `recycle_cards` 算法以准确重组所有已打出和手牌，支持游戏流的物理重用。

## 2. 修改文件及核心代码

### 2.1 `backend/app/domain/game/card.py`
在文件末尾追加了 `cut_cards` 函数：
```python
def cut_cards(deck: List[int]) -> List[int]:
    """切牌算法：随机选一切割点分成两段拼接，保留局部牌序"""
    if len(deck) != 54:
        return list(deck)
    cut_idx = random.randint(10, 44)
    return deck[cut_idx:] + deck[:cut_idx]
```

### 2.2 `backend/app/domain/game/room.py`
- 在 `GameRoom.__init__` 中初始化 `self.play_mode: str = "classic"`。
- 在 `to_dict` 与 `from_dict` 方法中添加 `play_mode` 字段的序列化与反序列化。
- 实现了 `deal_with_deck` 与 `recycle_cards`：
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
        self._call_index = 0
        self._call_scores = {}
        self._call_round = 1
        self._first_bidder = None
        self._round2_queue = []
        self._round2_scores = {}
        self._grab_count = {}
        self._declined_players = set()
        
        import random
        self._first_caller_index = random.randint(0, 2)
        self._call_index = self._first_caller_index
        self.current_turn = ids[self._first_caller_index]
        self.turn_deadline = time.time() + 18
        return dict(self.hands)

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

### 2.3 `README.md`
在 **✨ 核心功能特性 (Key Features)** 中添加了不洗牌模式算法的说明：
- **🃏 不洗牌模式算法支持**：领域层新增不洗牌（No-Shuffle）游戏模式支持。实现切牌（`cut_cards`）保留局部牌序、基于自定义/已回收牌堆的发牌分发（`deal_with_deck`）以及带有完整性校验的残局回收重组（`recycle_cards`）算法。

## 3. 单元测试验证

创建了独立的测试文件 `backend/tests/test_no_shuffle_domain.py`。
运行命令：
```bash
D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest tests/test_no_shuffle_domain.py -v
```
测试结果：
- `test_cut_cards_preserves_length`: **PASSED** (验证切牌长度为 54，相邻关系除分割点外均保持连续)
- `test_deal_with_deck`: **PASSED** (验证通过外部牌堆分发手牌和底牌，房间进入叫牌阶段)
- `test_recycle_cards_valid`: **PASSED** (验证从玩家手牌、底牌、以及打出牌中成功无重漏回收完整的 54 张牌堆)

## 4. Git 提交记录

- **Commit ID**: `0aebc19`
- **提交信息**: `feat: 领域层增加不洗牌切牌分发与回收重组算法`

---

## 5. 修复与优化 (FIX)

根据反馈，对领域层算法和单元测试进行了如下修复和扩展：
- **`backend/app/domain/game/room.py`**：在 `get_player_view` 方法返回的 `view` 字典中添加了 `"play_mode": self.play_mode`，以确保客户端能够正常获取房间的玩法模式。
- **`backend/tests/test_no_shuffle_domain.py`**：新增测试用例 `test_recycle_cards_with_landlord`，模拟地主拿走底牌并进行出牌的流程，以此验证 `recycle_cards()` 依然能严格重构出 54 张不重复的完整牌堆。

### 5.1 运行测试验证
再次运行测试：
```bash
D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest tests/test_no_shuffle_domain.py -v
```
测试结果：
- `test_cut_cards_preserves_length`: **PASSED**
- `test_deal_with_deck`: **PASSED**
- `test_recycle_cards_valid`: **PASSED**
- `test_recycle_cards_with_landlord`: **PASSED** (新增)

测试全部通过。

### 5.2 提交记录
- **Commit ID**: `b9005a9`
- **提交信息**: `fix: 修复房间状态视图中 play_mode 丢失并扩展回收算法测试用例`
