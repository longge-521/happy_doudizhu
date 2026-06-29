# 欢乐斗地主 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 HMP WS Service 新增网络版欢乐斗地主对战功能，采用前后端彻底分离架构。

**Architecture:** 后端在现有 FastAPI + DDD 分层中新增 `game` 领域模块，通过独立的 WebSocket 端点 (`/ws/game/{player_id}`) 提供纯事件驱动的实时游戏通信。游戏房间状态存储在 Redis 中以支持分布式部署。前端使用 Vue 3 + Vite 构建独立的 SPA 游戏客户端。

**Tech Stack:** Python 3.10+, FastAPI, SQLAlchemy 2.0, Redis (async), RabbitMQ (aio-pika), Vue 3, Vite, Pinia, Vue Router 4

**Spec:** `docs/superpowers/specs/2026-06-23-doudizhu-game-design.md`

## Global Constraints

- Python ≥ 3.10，使用 `hmp_ai` conda 环境
- 所有后端代码位于 `backend/` 目录
- 所有前端代码位于 `frontend/` 目录
- 遵循现有 DDD 分层：domain → application → infrastructure → interfaces
- 遵循现有代码风格：中文注释，`hmp_ws_service` logger 命名
- 所有新增数据库模型必须在 `models.py` 中注册并通过 `init_db()` 自动建表
- Redis key 统一使用 `game:` 前缀
- WebSocket 事件格式：客户端 `{"action": "xxx"}`，服务端 `{"event": "xxx"}`

---

### Task 1: 项目目录重构 — 迁移至 backend/

**Files:**
- Move: 所有根目录后端文件 → `backend/`
- Modify: `backend/main.py` (调整静态文件路径)
- Modify: `backend/alembic.ini` (调整脚本路径)
- Create: `README.md` (根目录指引文档)

**Interfaces:**
- Consumes: 无
- Produces: `backend/` 目录结构，所有现有功能正常运行

- [ ] **Step 1: 创建 backend 目录并移动所有后端文件**

```bash
cd d:\Project_2023\hmp_ws_service
mkdir backend
# 移动所有后端源码和配置到 backend/
move app backend\app
move alembic backend\alembic
move tests backend\tests
move static backend\static
move templates backend\templates
move log backend\log
move temp_uploads backend\temp_uploads
move uploads backend\uploads
move main.py backend\main.py
move requirements.txt backend\requirements.txt
move alembic.ini backend\alembic.ini
move .env backend\.env
```

- [ ] **Step 2: 修改 backend/main.py 中的静态文件路径**

`main.py` 中的 `StaticFiles(directory="static")` 使用的是相对路径，移动后需要确保工作目录正确。修改为基于 `__file__` 的绝对路径：

```python
# backend/main.py 中修改
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
```

同时修改 `templates` 引用（在 `app/interfaces/web/index_route.py` 中）：

```python
# backend/app/interfaces/web/index_route.py 中
import os
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
```

- [ ] **Step 3: 修改 backend/alembic.ini 中的脚本路径**

```ini
# backend/alembic.ini
script_location = alembic
```

确保 alembic 配置的 `script_location` 是相对于 `backend/` 目录的路径。

- [ ] **Step 4: 创建根目录 README.md**

```markdown
# HMP WS Service — 欢乐斗地主

## 快速开始

### 后端
cd backend
pip install -r requirements.txt
python main.py

### 前端
cd frontend
npm install
npm run dev
```

- [ ] **Step 5: 验证后端功能正常**

```bash
cd d:\Project_2023\hmp_ws_service\backend
python -m pytest tests/ -v
```

Expected: 所有现有测试通过

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor: 将后端源码迁移至 backend/ 目录，为前后端分离做准备"
```

---

### Task 2: 扑克牌领域模型 — 编码、排序与比较

**Files:**
- Create: `backend/app/domain/game/__init__.py`
- Create: `backend/app/domain/game/card.py`
- Test: `backend/tests/test_card.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `Card` dataclass: `card_id: int`, `rank: int`, `suit: int`
  - `Card.from_id(card_id: int) -> Card`
  - `Card.rank_name -> str` (如 "3", "A", "2", "小王")
  - `Card.suit_name -> str` (如 "♠", "♥")
  - `Card.power -> int` (牌力值，用于大小比较)
  - `FULL_DECK: list[int]` 完整一副牌(0~53)
  - `sort_cards(card_ids: list[int]) -> list[int]` 按牌力排序
  - `shuffle_and_deal() -> tuple[list[int], list[int], list[int], list[int]]` 洗牌发牌(三手牌+底牌)

- [ ] **Step 1: 编写扑克牌模型的测试**

```python
# backend/tests/test_card.py
import pytest
from app.domain.game.card import Card, FULL_DECK, sort_cards, shuffle_and_deal


class TestCard:
    """扑克牌编码与属性测试"""

    def test_card_from_id_three_of_spades(self):
        """编号0应为黑桃3"""
        card = Card.from_id(0)
        assert card.rank == 0  # 3
        assert card.suit == 0  # ♠
        assert card.rank_name == "3"
        assert card.suit_name == "♠"

    def test_card_from_id_ace_of_hearts(self):
        """编号45应为红桃A"""
        card = Card.from_id(45)
        assert card.rank == 11  # A
        assert card.suit == 1   # ♥
        assert card.rank_name == "A"

    def test_card_from_id_two_of_diamonds(self):
        """编号51应为方块2"""
        card = Card.from_id(51)
        assert card.rank == 12  # 2
        assert card.suit == 3   # ♦
        assert card.rank_name == "2"

    def test_card_from_id_black_joker(self):
        """编号52应为小王"""
        card = Card.from_id(52)
        assert card.rank_name == "小王"
        assert card.suit_name == ""

    def test_card_from_id_red_joker(self):
        """编号53应为大王"""
        card = Card.from_id(53)
        assert card.rank_name == "大王"
        assert card.suit_name == ""

    def test_power_ordering(self):
        """牌力排序：3 < 4 < ... < K < A < 2 < 小王 < 大王"""
        three = Card.from_id(0)    # 3
        ace = Card.from_id(44)     # A
        two = Card.from_id(48)     # 2
        bj = Card.from_id(52)      # 小王
        rj = Card.from_id(53)      # 大王
        assert three.power < ace.power < two.power < bj.power < rj.power

    def test_full_deck_size(self):
        """一副牌应有54张"""
        assert len(FULL_DECK) == 54

    def test_sort_cards(self):
        """排序后应按牌力从小到大"""
        cards = [53, 0, 48, 44]  # 大王, 3♠, 2♠, A♠
        sorted_ids = sort_cards(cards)
        powers = [Card.from_id(c).power for c in sorted_ids]
        assert powers == sorted(powers)

    def test_shuffle_and_deal(self):
        """发牌: 每人17张, 底牌3张, 总计54张不重复"""
        hand1, hand2, hand3, bottom = shuffle_and_deal()
        assert len(hand1) == 17
        assert len(hand2) == 17
        assert len(hand3) == 17
        assert len(bottom) == 3
        all_cards = hand1 + hand2 + hand3 + bottom
        assert len(set(all_cards)) == 54

    def test_card_invalid_id(self):
        """无效编号应抛出 ValueError"""
        with pytest.raises(ValueError):
            Card.from_id(54)
        with pytest.raises(ValueError):
            Card.from_id(-1)
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd d:\Project_2023\hmp_ws_service\backend
python -m pytest tests/test_card.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.domain.game'`

- [ ] **Step 3: 实现扑克牌领域模型**

```python
# backend/app/domain/game/__init__.py
"""斗地主游戏领域层"""

# backend/app/domain/game/card.py
"""扑克牌领域模型：编码、排序、发牌"""
import random
from dataclasses import dataclass
from typing import Tuple, List

# 点数名称映射 (rank index → display name)
RANK_NAMES = ["3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A", "2"]
# 花色名称映射 (suit index → display name)
SUIT_NAMES = ["♠", "♥", "♣", "♦"]

# 完整一副牌: 0~53
FULL_DECK: List[int] = list(range(54))


@dataclass(frozen=True)
class Card:
    """
    扑克牌值对象。
    编码规则：
      - 0~51: 普通牌，rank = card_id // 4, suit = card_id % 4
      - 52: 小王
      - 53: 大王
    """
    card_id: int
    rank: int     # 0~12 对应 3~2, 13=小王, 14=大王
    suit: int     # 0~3 对应 ♠♥♣♦, -1=王

    @classmethod
    def from_id(cls, card_id: int) -> "Card":
        if card_id < 0 or card_id > 53:
            raise ValueError(f"无效的牌编号: {card_id}，合法范围 0~53")
        if card_id == 52:
            return cls(card_id=52, rank=13, suit=-1)
        if card_id == 53:
            return cls(card_id=53, rank=14, suit=-1)
        return cls(card_id=card_id, rank=card_id // 4, suit=card_id % 4)

    @property
    def rank_name(self) -> str:
        if self.rank == 13:
            return "小王"
        if self.rank == 14:
            return "大王"
        return RANK_NAMES[self.rank]

    @property
    def suit_name(self) -> str:
        if self.suit == -1:
            return ""
        return SUIT_NAMES[self.suit]

    @property
    def power(self) -> int:
        """牌力值，数值越大牌越大。用于排序和比较。"""
        return self.rank

    def __str__(self) -> str:
        return f"{self.suit_name}{self.rank_name}"


def sort_cards(card_ids: List[int]) -> List[int]:
    """按牌力从小到大排序"""
    return sorted(card_ids, key=lambda cid: Card.from_id(cid).power)


def shuffle_and_deal() -> Tuple[List[int], List[int], List[int], List[int]]:
    """洗牌并发牌：返回 (手牌1, 手牌2, 手牌3, 底牌)"""
    deck = FULL_DECK.copy()
    random.shuffle(deck)
    hand1 = sort_cards(deck[0:17])
    hand2 = sort_cards(deck[17:34])
    hand3 = sort_cards(deck[34:51])
    bottom = sort_cards(deck[51:54])
    return hand1, hand2, hand3, bottom
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd d:\Project_2023\hmp_ws_service\backend
python -m pytest tests/test_card.py -v
```

Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(game): 新增扑克牌领域模型 - 编码、排序、发牌"
```

---

### Task 3: 牌型检测与校验引擎

**Files:**
- Create: `backend/app/domain/game/card_type.py`
- Test: `backend/tests/test_card_type.py`

**Interfaces:**
- Consumes: `Card.from_id()`, `Card.power`
- Produces:
  - `CardType` 枚举: `SINGLE, PAIR, TRIPLE, TRIPLE_ONE, TRIPLE_TWO, STRAIGHT, DOUBLE_STRAIGHT, AIRPLANE, AIRPLANE_SINGLE, AIRPLANE_PAIR, BOMB, ROCKET, FOUR_TWO_SINGLE, FOUR_TWO_PAIR`
  - `CardPlay` dataclass: `card_type: CardType`, `main_rank: int`, `length: int`, `cards: list[int]`
  - `detect_card_type(card_ids: list[int]) -> CardPlay | None` 检测牌型，非法返回 None
  - `can_beat(current_play: CardPlay, last_play: CardPlay) -> bool` 判断是否压得过

- [ ] **Step 1: 编写牌型检测测试**

```python
# backend/tests/test_card_type.py
import pytest
from app.domain.game.card_type import detect_card_type, can_beat, CardType


class TestDetectCardType:
    """牌型识别测试"""

    def test_single(self):
        """单张"""
        result = detect_card_type([0])  # 3♠
        assert result is not None
        assert result.card_type == CardType.SINGLE

    def test_pair(self):
        """对子"""
        result = detect_card_type([0, 1])  # 3♠3♥
        assert result is not None
        assert result.card_type == CardType.PAIR

    def test_triple(self):
        """三条"""
        result = detect_card_type([0, 1, 2])  # 3♠3♥3♣
        assert result is not None
        assert result.card_type == CardType.TRIPLE

    def test_triple_with_one(self):
        """三带一"""
        result = detect_card_type([0, 1, 2, 4])  # 333+4
        assert result is not None
        assert result.card_type == CardType.TRIPLE_ONE

    def test_triple_with_two(self):
        """三带二 (一对)"""
        result = detect_card_type([0, 1, 2, 4, 5])  # 333+44
        assert result is not None
        assert result.card_type == CardType.TRIPLE_TWO

    def test_straight(self):
        """顺子 (至少5张连续)"""
        result = detect_card_type([0, 4, 8, 12, 16])  # 3-4-5-6-7
        assert result is not None
        assert result.card_type == CardType.STRAIGHT

    def test_straight_invalid_with_two(self):
        """顺子不能包含2"""
        result = detect_card_type([36, 40, 44, 48, 0])  # K-A-2-?-3 不合法
        # 这不是合法顺子
        assert result is None or result.card_type != CardType.STRAIGHT

    def test_double_straight(self):
        """连对 (至少3对连续)"""
        result = detect_card_type([0, 1, 4, 5, 8, 9])  # 33-44-55
        assert result is not None
        assert result.card_type == CardType.DOUBLE_STRAIGHT

    def test_airplane(self):
        """飞机不带 (至少2组连续三条)"""
        result = detect_card_type([0, 1, 2, 4, 5, 6])  # 333-444
        assert result is not None
        assert result.card_type == CardType.AIRPLANE

    def test_airplane_with_singles(self):
        """飞机带单"""
        result = detect_card_type([0, 1, 2, 4, 5, 6, 8, 12])  # 333-444+5+6 (带两个单张)
        assert result is not None
        assert result.card_type == CardType.AIRPLANE_SINGLE

    def test_bomb(self):
        """炸弹"""
        result = detect_card_type([0, 1, 2, 3])  # 3333
        assert result is not None
        assert result.card_type == CardType.BOMB

    def test_rocket(self):
        """王炸"""
        result = detect_card_type([52, 53])  # 小王+大王
        assert result is not None
        assert result.card_type == CardType.ROCKET

    def test_four_two_single(self):
        """四带二单"""
        result = detect_card_type([0, 1, 2, 3, 4, 8])  # 3333+4+5
        assert result is not None
        assert result.card_type == CardType.FOUR_TWO_SINGLE

    def test_four_two_pair(self):
        """四带二对"""
        result = detect_card_type([0, 1, 2, 3, 4, 5, 8, 9])  # 3333+44+55
        assert result is not None
        assert result.card_type == CardType.FOUR_TWO_PAIR

    def test_invalid_cards(self):
        """非法牌型返回 None"""
        result = detect_card_type([0, 4, 12])  # 3+4+6 (三张不同且非顺子)
        assert result is None

    def test_empty_cards(self):
        """空牌返回 None"""
        result = detect_card_type([])
        assert result is None


class TestCanBeat:
    """牌型比较测试"""

    def test_bigger_single(self):
        """大单张压小单张"""
        small = detect_card_type([0])   # 3
        big = detect_card_type([44])    # A
        assert can_beat(big, small)

    def test_smaller_single_cannot_beat(self):
        """小单张不能压大单张"""
        small = detect_card_type([0])   # 3
        big = detect_card_type([44])    # A
        assert not can_beat(small, big)

    def test_bomb_beats_single(self):
        """炸弹压任意非炸弹牌型"""
        single = detect_card_type([44])        # A
        bomb = detect_card_type([0, 1, 2, 3])  # 3333
        assert can_beat(bomb, single)

    def test_rocket_beats_bomb(self):
        """王炸压炸弹"""
        bomb = detect_card_type([0, 1, 2, 3])  # 3333
        rocket = detect_card_type([52, 53])     # 王炸
        assert can_beat(rocket, bomb)

    def test_different_type_cannot_beat(self):
        """不同牌型（非炸弹）不能互压"""
        single = detect_card_type([0])
        pair = detect_card_type([4, 5])
        assert not can_beat(pair, single)

    def test_same_type_same_length_bigger_rank(self):
        """相同牌型相同长度，大的压小的"""
        small_straight = detect_card_type([0, 4, 8, 12, 16])   # 3-4-5-6-7
        big_straight = detect_card_type([4, 8, 12, 16, 20])     # 4-5-6-7-8
        assert can_beat(big_straight, small_straight)

    def test_different_length_straight_cannot_beat(self):
        """不同长度的顺子不能互压"""
        short = detect_card_type([0, 4, 8, 12, 16])          # 3-4-5-6-7 (5张)
        long = detect_card_type([0, 4, 8, 12, 16, 20])       # 3-4-5-6-7-8 (6张)
        assert not can_beat(long, short)
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd d:\Project_2023\hmp_ws_service\backend
python -m pytest tests/test_card_type.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 实现牌型检测引擎**

```python
# backend/app/domain/game/card_type.py
"""牌型检测与比较引擎"""
from collections import Counter
from enum import Enum
from dataclasses import dataclass
from typing import Optional, List
from app.domain.game.card import Card


class CardType(Enum):
    """合法牌型枚举"""
    SINGLE = "单张"
    PAIR = "对子"
    TRIPLE = "三条"
    TRIPLE_ONE = "三带一"
    TRIPLE_TWO = "三带二"
    STRAIGHT = "顺子"
    DOUBLE_STRAIGHT = "连对"
    AIRPLANE = "飞机"
    AIRPLANE_SINGLE = "飞机带单"
    AIRPLANE_PAIR = "飞机带对"
    BOMB = "炸弹"
    ROCKET = "王炸"
    FOUR_TWO_SINGLE = "四带二单"
    FOUR_TWO_PAIR = "四带二对"


@dataclass
class CardPlay:
    """一次出牌的完整描述"""
    card_type: CardType
    main_rank: int       # 主牌的 rank (用于比较大小)
    length: int          # 主牌序列长度 (顺子5张 length=5)
    cards: List[int]     # 原始牌编号


def _get_rank_counts(card_ids: List[int]) -> Counter:
    """统计每个 rank 出现的次数"""
    ranks = [Card.from_id(cid).rank for cid in card_ids]
    return Counter(ranks)


def _find_consecutive_ranks(ranks: List[int], min_length: int) -> Optional[List[int]]:
    """
    在给定的 rank 列表中找到连续序列。
    rank 必须 < 12 (即不包含2) 且 < 13 (不包含王)。
    返回排序后的连续 rank 列表，或 None。
    """
    valid = sorted([r for r in ranks if r < 12])  # 排除 2(rank=12) 和 王
    if len(valid) < min_length:
        return None
    # 检查是否连续
    for i in range(1, len(valid)):
        if valid[i] != valid[i - 1] + 1:
            return None
    return valid


def detect_card_type(card_ids: List[int]) -> Optional[CardPlay]:
    """
    检测一组牌的牌型。
    返回 CardPlay 描述，非法牌型返回 None。
    """
    if not card_ids:
        return None

    n = len(card_ids)
    rank_counts = _get_rank_counts(card_ids)

    # 王炸: 大小王
    if n == 2 and set(card_ids) == {52, 53}:
        return CardPlay(CardType.ROCKET, main_rank=14, length=1, cards=card_ids)

    # 按出现次数分组
    count_groups = {}  # count -> [rank, ...]
    for rank, count in rank_counts.items():
        count_groups.setdefault(count, []).append(rank)
    for k in count_groups:
        count_groups[k].sort()

    # 单张
    if n == 1:
        rank = Card.from_id(card_ids[0]).rank
        return CardPlay(CardType.SINGLE, main_rank=rank, length=1, cards=card_ids)

    # 对子
    if n == 2 and len(rank_counts) == 1:
        rank = list(rank_counts.keys())[0]
        return CardPlay(CardType.PAIR, main_rank=rank, length=1, cards=card_ids)

    # 炸弹: 4张相同
    if n == 4 and len(rank_counts) == 1:
        rank = list(rank_counts.keys())[0]
        return CardPlay(CardType.BOMB, main_rank=rank, length=1, cards=card_ids)

    # 三条
    if n == 3 and len(rank_counts) == 1:
        rank = list(rank_counts.keys())[0]
        return CardPlay(CardType.TRIPLE, main_rank=rank, length=1, cards=card_ids)

    # 三带一
    if n == 4 and 3 in count_groups and len(count_groups[3]) == 1:
        main_rank = count_groups[3][0]
        return CardPlay(CardType.TRIPLE_ONE, main_rank=main_rank, length=1, cards=card_ids)

    # 三带二 (副牌必须是对子)
    if n == 5 and 3 in count_groups and 2 in count_groups:
        if len(count_groups[3]) == 1 and len(count_groups[2]) == 1:
            main_rank = count_groups[3][0]
            return CardPlay(CardType.TRIPLE_TWO, main_rank=main_rank, length=1, cards=card_ids)

    # 顺子: ≥5张连续单张 (不含2和王)
    if n >= 5 and all(c == 1 for c in rank_counts.values()):
        seq = _find_consecutive_ranks(list(rank_counts.keys()), n)
        if seq and len(seq) == n:
            return CardPlay(CardType.STRAIGHT, main_rank=seq[0], length=n, cards=card_ids)

    # 连对: ≥3对连续 (不含2和王)
    if n >= 6 and n % 2 == 0 and all(c == 2 for c in rank_counts.values()):
        num_pairs = n // 2
        seq = _find_consecutive_ranks(list(rank_counts.keys()), num_pairs)
        if seq and len(seq) == num_pairs:
            return CardPlay(CardType.DOUBLE_STRAIGHT, main_rank=seq[0], length=num_pairs, cards=card_ids)

    # 飞机相关: 先找连续的三条
    triples = sorted(count_groups.get(3, []))
    # 也考虑4张中拆出3张的情况
    fours = sorted(count_groups.get(4, []))

    # 纯飞机 (≥2组连续三条)
    if triples and len(triples) >= 2:
        seq = _find_consecutive_ranks(triples, 2)
        if seq:
            airplane_len = len(seq)
            remaining = n - airplane_len * 3
            if remaining == 0:
                return CardPlay(CardType.AIRPLANE, main_rank=seq[0], length=airplane_len, cards=card_ids)
            if remaining == airplane_len:
                # 飞机带单
                return CardPlay(CardType.AIRPLANE_SINGLE, main_rank=seq[0], length=airplane_len, cards=card_ids)
            if remaining == airplane_len * 2:
                # 飞机带对: 检查副牌是否全是对子
                side_ranks = [r for r, c in rank_counts.items() if r not in seq]
                side_counts = [rank_counts[r] for r in side_ranks]
                if all(c == 2 for c in side_counts) and len(side_ranks) == airplane_len:
                    return CardPlay(CardType.AIRPLANE_PAIR, main_rank=seq[0], length=airplane_len, cards=card_ids)

    # 四带二单
    if n == 6 and 4 in count_groups and len(count_groups[4]) == 1:
        main_rank = count_groups[4][0]
        return CardPlay(CardType.FOUR_TWO_SINGLE, main_rank=main_rank, length=1, cards=card_ids)

    # 四带二对
    if n == 8 and 4 in count_groups and len(count_groups[4]) == 1:
        main_rank = count_groups[4][0]
        side_ranks = [r for r in rank_counts if r != main_rank]
        if all(rank_counts[r] == 2 for r in side_ranks) and len(side_ranks) == 2:
            return CardPlay(CardType.FOUR_TWO_PAIR, main_rank=main_rank, length=1, cards=card_ids)

    return None


def can_beat(current_play: CardPlay, last_play: CardPlay) -> bool:
    """
    判断 current_play 是否能压过 last_play。
    规则：
      1. 王炸压一切
      2. 炸弹压非炸弹，大炸弹压小炸弹
      3. 相同牌型 + 相同长度 + 更大的 main_rank
    """
    # 王炸压一切
    if current_play.card_type == CardType.ROCKET:
        return True
    if last_play.card_type == CardType.ROCKET:
        return False

    # 炸弹 vs 非炸弹
    if current_play.card_type == CardType.BOMB and last_play.card_type != CardType.BOMB:
        return True
    if current_play.card_type != CardType.BOMB and last_play.card_type == CardType.BOMB:
        return False

    # 相同牌型比较
    if current_play.card_type != last_play.card_type:
        return False
    if current_play.length != last_play.length:
        return False
    return current_play.main_rank > last_play.main_rank
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd d:\Project_2023\hmp_ws_service\backend
python -m pytest tests/test_card_type.py -v
```

Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(game): 新增牌型检测与比较引擎 - 支持14种牌型"
```

---

### Task 4: 游戏房间状态与状态机

**Files:**
- Create: `backend/app/domain/game/room.py`
- Test: `backend/tests/test_room.py`

**Interfaces:**
- Consumes: `Card`, `CardPlay`, `detect_card_type`, `can_beat`, `shuffle_and_deal`, `sort_cards`
- Produces:
  - `Player` dataclass: `id, nickname, is_ai, is_online`
  - `GamePhase` 枚举: `MATCHING, DEALING, CALLING, PLAYING, SETTLING`
  - `GameRoom` class:
    - `GameRoom.create(room_id, players) -> GameRoom`
    - `room.deal() -> dict[str, list[int]]` 发牌，返回每个玩家手牌
    - `room.call_landlord(player_id, score) -> dict` 叫地主
    - `room.skip_call(player_id) -> dict` 不叫
    - `room.play_cards(player_id, card_ids) -> dict` 出牌
    - `room.pass_turn(player_id) -> dict` 不出
    - `room.to_dict() -> dict` 序列化
    - `GameRoom.from_dict(data) -> GameRoom` 反序列化
    - `room.get_player_view(player_id) -> dict` 获取该玩家可见的状态

- [ ] **Step 1: 编写游戏房间状态机测试**

```python
# backend/tests/test_room.py
import pytest
from app.domain.game.room import GameRoom, GamePhase, Player


def make_players():
    return [
        Player(id="p1", nickname="玩家1", is_ai=False, is_online=True),
        Player(id="p2", nickname="玩家2", is_ai=False, is_online=True),
        Player(id="p3", nickname="机器人", is_ai=True, is_online=True),
    ]


class TestGameRoom:

    def test_create_room(self):
        """创建房间后状态应为 DEALING"""
        room = GameRoom.create("room_1", make_players())
        assert room.room_id == "room_1"
        assert room.phase == GamePhase.DEALING
        assert len(room.players) == 3

    def test_deal(self):
        """发牌后每人17张，底牌3张，状态变为 CALLING"""
        room = GameRoom.create("room_1", make_players())
        hands = room.deal()
        assert room.phase == GamePhase.CALLING
        for pid in ["p1", "p2", "p3"]:
            assert len(room.hands[pid]) == 17
        assert len(room.bottom_cards) == 3

    def test_call_landlord(self):
        """叫3分直接成为地主"""
        room = GameRoom.create("room_1", make_players())
        room.deal()
        caller = room.current_turn
        result = room.call_landlord(caller, 3)
        assert room.phase == GamePhase.PLAYING
        assert room.landlord == caller
        assert room.multiplier == 3
        # 地主应该有20张牌
        assert len(room.hands[caller]) == 20

    def test_skip_call_all(self):
        """三人都不叫，应重新发牌"""
        room = GameRoom.create("room_1", make_players())
        room.deal()
        for _ in range(3):
            pid = room.current_turn
            result = room.skip_call(pid)
        # 应该重新发牌或标记重发
        assert result.get("redeal") is True or room.phase == GamePhase.DEALING

    def test_play_cards_valid(self):
        """出合法的牌应成功"""
        room = GameRoom.create("room_1", make_players())
        room.deal()
        # 直接叫3分成为地主
        caller = room.current_turn
        room.call_landlord(caller, 3)
        # 地主出牌（出最小的一张）
        landlord = room.landlord
        card_to_play = [room.hands[landlord][0]]
        result = room.play_cards(landlord, card_to_play)
        assert result["success"] is True
        assert card_to_play[0] not in room.hands[landlord]

    def test_play_cards_not_your_turn(self):
        """不是你的回合不能出牌"""
        room = GameRoom.create("room_1", make_players())
        room.deal()
        caller = room.current_turn
        room.call_landlord(caller, 3)
        # 尝试让非当前回合玩家出牌
        other = [p for p in ["p1", "p2", "p3"] if p != room.current_turn][0]
        result = room.play_cards(other, [room.hands[other][0]])
        assert result["success"] is False

    def test_serialization(self):
        """序列化/反序列化应保持状态一致"""
        room = GameRoom.create("room_1", make_players())
        room.deal()
        data = room.to_dict()
        restored = GameRoom.from_dict(data)
        assert restored.room_id == room.room_id
        assert restored.phase == room.phase
        assert restored.hands == room.hands

    def test_player_view_hides_others_hands(self):
        """玩家视图不应包含其他人的手牌"""
        room = GameRoom.create("room_1", make_players())
        room.deal()
        view = room.get_player_view("p1")
        assert "hand" in view  # 自己的手牌
        for p in view["players"]:
            if p["id"] != "p1":
                assert "hand" not in p  # 不应有其他人手牌
                assert "remaining" in p  # 应有剩余牌数
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd d:\Project_2023\hmp_ws_service\backend
python -m pytest tests/test_room.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 实现游戏房间状态机**

```python
# backend/app/domain/game/room.py
"""游戏房间状态机：管理一局斗地主的完整生命周期"""
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, List, Dict, Any
from app.domain.game.card import shuffle_and_deal, sort_cards, Card
from app.domain.game.card_type import detect_card_type, can_beat, CardPlay


class GamePhase(Enum):
    MATCHING = "MATCHING"
    DEALING = "DEALING"
    CALLING = "CALLING"
    PLAYING = "PLAYING"
    SETTLING = "SETTLING"


@dataclass
class Player:
    id: str
    nickname: str
    is_ai: bool = False
    is_online: bool = True


@dataclass
class LastPlay:
    """最近一次出牌记录"""
    player: Optional[str] = None
    cards: List[int] = field(default_factory=list)
    card_type: Optional[str] = None
    card_play: Optional[CardPlay] = None


class GameRoom:
    """
    斗地主游戏房间。
    封装了一局游戏的全部状态和规则逻辑。
    所有状态变更方法返回 dict 描述操作结果。
    """

    MAX_REDEAL = 3  # 最多重新发牌次数

    def __init__(self):
        self.room_id: str = ""
        self.phase: GamePhase = GamePhase.DEALING
        self.players: List[Player] = []
        self.hands: Dict[str, List[int]] = {}
        self.bottom_cards: List[int] = []
        self.landlord: Optional[str] = None
        self.current_turn: Optional[str] = None
        self.turn_deadline: float = 0
        self.last_play: LastPlay = LastPlay()
        self.pass_count: int = 0  # 连续不出次数
        self.multiplier: int = 1
        self.redeal_count: int = 0
        self.created_at: str = ""

        # 叫地主状态
        self._call_index: int = 0       # 当前叫地主的玩家索引
        self._call_scores: Dict[str, int] = {}  # 每个玩家的叫分 (0=不叫)
        self._first_caller_index: int = 0  # 首位叫牌者索引

    @classmethod
    def create(cls, room_id: str, players: List[Player]) -> "GameRoom":
        room = cls()
        room.room_id = room_id
        room.players = players
        room.phase = GamePhase.DEALING
        room.created_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        return room

    def _player_ids(self) -> List[str]:
        return [p.id for p in self.players]

    def _next_player(self, current_id: str) -> str:
        ids = self._player_ids()
        idx = ids.index(current_id)
        return ids[(idx + 1) % 3]

    # ── 发牌 ──

    def deal(self) -> Dict[str, List[int]]:
        """洗牌发牌，状态从 DEALING → CALLING"""
        h1, h2, h3, bottom = shuffle_and_deal()
        ids = self._player_ids()
        self.hands = {ids[0]: h1, ids[1]: h2, ids[2]: h3}
        self.bottom_cards = bottom
        self.phase = GamePhase.CALLING
        self.landlord = None
        self.last_play = LastPlay()
        self.pass_count = 0
        self._call_index = 0
        self._call_scores = {}
        # 随机选择首位叫牌者 (使用第一个玩家索引)
        import random
        self._first_caller_index = random.randint(0, 2)
        self._call_index = self._first_caller_index
        self.current_turn = ids[self._first_caller_index]
        self.turn_deadline = time.time() + 15
        return dict(self.hands)

    # ── 叫地主 ──

    def call_landlord(self, player_id: str, score: int) -> dict:
        """玩家叫地主 (score: 1/2/3)"""
        if self.phase != GamePhase.CALLING:
            return {"success": False, "error": "当前不在叫地主阶段"}
        if player_id != self.current_turn:
            return {"success": False, "error": "不是你的回合"}
        if score < 1 or score > 3:
            return {"success": False, "error": "叫分必须在1~3之间"}
        # 叫分必须高于已有最高分
        current_max = max(self._call_scores.values()) if self._call_scores else 0
        if score <= current_max:
            return {"success": False, "error": f"叫分必须高于当前最高分 {current_max}"}

        self._call_scores[player_id] = score
        self.multiplier = score

        # 叫3分直接成为地主
        if score == 3:
            return self._set_landlord(player_id)

        # 继续轮转
        return self._advance_call()

    def skip_call(self, player_id: str) -> dict:
        """玩家不叫"""
        if self.phase != GamePhase.CALLING:
            return {"success": False, "error": "当前不在叫地主阶段"}
        if player_id != self.current_turn:
            return {"success": False, "error": "不是你的回合"}

        self._call_scores[player_id] = 0
        return self._advance_call()

    def _advance_call(self) -> dict:
        """推进叫地主流程"""
        ids = self._player_ids()
        # 检查是否所有人都叫过了
        if len(self._call_scores) >= 3:
            # 找到最高分的玩家
            max_score = max(self._call_scores.values())
            if max_score == 0:
                # 所有人都不叫，重新发牌
                self.redeal_count += 1
                if self.redeal_count >= self.MAX_REDEAL:
                    # 超过重发次数，随机指定地主
                    import random
                    forced = random.choice(ids)
                    self.multiplier = 1
                    return self._set_landlord(forced)
                self.phase = GamePhase.DEALING
                return {"success": True, "redeal": True}

            # 最高分者成为地主
            winner = [pid for pid, s in self._call_scores.items() if s == max_score][0]
            return self._set_landlord(winner)

        # 还有人没叫，轮到下一个
        self._call_index = (self._call_index + 1) % 3
        self.current_turn = ids[self._call_index]
        self.turn_deadline = time.time() + 15
        return {"success": True, "next_caller": self.current_turn}

    def _set_landlord(self, player_id: str) -> dict:
        """确定地主，分配底牌，进入出牌阶段"""
        self.landlord = player_id
        # 底牌给地主
        self.hands[player_id] = sort_cards(self.hands[player_id] + self.bottom_cards)
        self.phase = GamePhase.PLAYING
        self.current_turn = player_id  # 地主先出
        self.turn_deadline = time.time() + 20
        self.last_play = LastPlay()
        self.pass_count = 0
        return {
            "success": True,
            "landlord": player_id,
            "bottom_cards": self.bottom_cards,
            "multiplier": self.multiplier,
        }

    # ── 出牌 ──

    def play_cards(self, player_id: str, card_ids: List[int]) -> dict:
        """玩家出牌"""
        if self.phase != GamePhase.PLAYING:
            return {"success": False, "error": "当前不在出牌阶段"}
        if player_id != self.current_turn:
            return {"success": False, "error": "不是你的回合"}
        if not card_ids:
            return {"success": False, "error": "出牌不能为空"}

        # 检查玩家是否持有这些牌
        hand = self.hands[player_id]
        for cid in card_ids:
            if cid not in hand:
                return {"success": False, "error": f"你没有牌 {cid}"}

        # 检测牌型
        play = detect_card_type(card_ids)
        if play is None:
            return {"success": False, "error": "不合法的牌型"}

        # 如果有上家出牌，必须压过
        if self.last_play.card_play is not None:
            if not can_beat(play, self.last_play.card_play):
                return {"success": False, "error": "出的牌压不过上家"}

        # 炸弹/王炸翻倍
        from app.domain.game.card_type import CardType
        if play.card_type in (CardType.BOMB, CardType.ROCKET):
            self.multiplier *= 2

        # 从手牌中移除
        new_hand = list(hand)
        for cid in card_ids:
            new_hand.remove(cid)
        self.hands[player_id] = new_hand

        # 更新出牌记录
        self.last_play = LastPlay(
            player=player_id,
            cards=card_ids,
            card_type=play.card_type.value,
            card_play=play
        )
        self.pass_count = 0

        # 检查是否出完
        if len(new_hand) == 0:
            return self._settle(player_id)

        # 轮到下一个玩家
        self.current_turn = self._next_player(player_id)
        self.turn_deadline = time.time() + 20
        return {
            "success": True,
            "cards_played": card_ids,
            "card_type": play.card_type.value,
            "remaining": len(new_hand),
            "next_turn": self.current_turn,
        }

    def pass_turn(self, player_id: str) -> dict:
        """玩家不出（过）"""
        if self.phase != GamePhase.PLAYING:
            return {"success": False, "error": "当前不在出牌阶段"}
        if player_id != self.current_turn:
            return {"success": False, "error": "不是你的回合"}

        # 新一轮的首位出牌者不能不出
        if self.last_play.player is None:
            return {"success": False, "error": "新一轮必须出牌"}

        self.pass_count += 1

        # 如果连续2人不出，最后出牌的人获得新一轮主导权
        if self.pass_count >= 2:
            self.current_turn = self.last_play.player
            self.last_play = LastPlay()  # 清空上家，新一轮
            self.pass_count = 0
            self.turn_deadline = time.time() + 20
            return {"success": True, "new_round": True, "next_turn": self.current_turn}

        self.current_turn = self._next_player(player_id)
        self.turn_deadline = time.time() + 20
        return {"success": True, "next_turn": self.current_turn}

    # ── 结算 ──

    def _settle(self, winner_id: str) -> dict:
        """游戏结算"""
        self.phase = GamePhase.SETTLING
        is_landlord_win = (winner_id == self.landlord)
        winner_side = "landlord" if is_landlord_win else "farmer"

        base_score = self.multiplier * 10
        scores = {}
        for p in self.players:
            if p.id == self.landlord:
                scores[p.id] = base_score * 2 if is_landlord_win else -base_score * 2
            else:
                scores[p.id] = -base_score if is_landlord_win else base_score

        return {
            "success": True,
            "game_over": True,
            "winner": winner_id,
            "winner_side": winner_side,
            "landlord": self.landlord,
            "multiplier": self.multiplier,
            "scores": scores,
            "all_hands": dict(self.hands),
        }

    # ── 序列化 ──

    def to_dict(self) -> dict:
        """序列化为可存入 Redis 的 dict"""
        return {
            "room_id": self.room_id,
            "phase": self.phase.value,
            "players": [
                {"id": p.id, "nickname": p.nickname, "is_ai": p.is_ai, "is_online": p.is_online}
                for p in self.players
            ],
            "hands": self.hands,
            "bottom_cards": self.bottom_cards,
            "landlord": self.landlord,
            "current_turn": self.current_turn,
            "turn_deadline": self.turn_deadline,
            "last_play": {
                "player": self.last_play.player,
                "cards": self.last_play.cards,
                "card_type": self.last_play.card_type,
            },
            "pass_count": self.pass_count,
            "multiplier": self.multiplier,
            "redeal_count": self.redeal_count,
            "created_at": self.created_at,
            "call_index": self._call_index,
            "call_scores": self._call_scores,
            "first_caller_index": self._first_caller_index,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GameRoom":
        """从 dict 反序列化"""
        room = cls()
        room.room_id = data["room_id"]
        room.phase = GamePhase(data["phase"])
        room.players = [
            Player(id=p["id"], nickname=p["nickname"], is_ai=p["is_ai"], is_online=p["is_online"])
            for p in data["players"]
        ]
        room.hands = {k: list(v) for k, v in data["hands"].items()}
        room.bottom_cards = data["bottom_cards"]
        room.landlord = data.get("landlord")
        room.current_turn = data.get("current_turn")
        room.turn_deadline = data.get("turn_deadline", 0)
        lp = data.get("last_play", {})
        room.last_play = LastPlay(
            player=lp.get("player"),
            cards=lp.get("cards", []),
            card_type=lp.get("card_type"),
        )
        # 如果有上家出牌，重建 card_play 对象
        if room.last_play.cards:
            room.last_play.card_play = detect_card_type(room.last_play.cards)
        room.pass_count = data.get("pass_count", 0)
        room.multiplier = data.get("multiplier", 1)
        room.redeal_count = data.get("redeal_count", 0)
        room.created_at = data.get("created_at", "")
        room._call_index = data.get("call_index", 0)
        room._call_scores = data.get("call_scores", {})
        room._first_caller_index = data.get("first_caller_index", 0)
        return room

    def get_player_view(self, player_id: str) -> dict:
        """获取特定玩家可见的房间状态（隐藏他人手牌）"""
        players_view = []
        for p in self.players:
            pv = {"id": p.id, "nickname": p.nickname, "is_ai": p.is_ai, "is_online": p.is_online}
            if p.id == player_id:
                pv["is_self"] = True
            else:
                pv["remaining"] = len(self.hands.get(p.id, []))
            if self.landlord:
                pv["is_landlord"] = (p.id == self.landlord)
            players_view.append(pv)

        view = {
            "room_id": self.room_id,
            "phase": self.phase.value,
            "players": players_view,
            "hand": sort_cards(self.hands.get(player_id, [])),
            "current_turn": self.current_turn,
            "turn_deadline": self.turn_deadline,
            "last_play": {
                "player": self.last_play.player,
                "cards": self.last_play.cards,
                "card_type": self.last_play.card_type,
            },
            "multiplier": self.multiplier,
            "landlord": self.landlord,
        }
        # 地主确定后才公开底牌
        if self.landlord:
            view["bottom_cards"] = self.bottom_cards
        return view
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd d:\Project_2023\hmp_ws_service\backend
python -m pytest tests/test_room.py -v
```

Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(game): 新增游戏房间状态机 - 发牌/叫地主/出牌/结算全流程"
```

---

### Task 5: AI 机器人策略

**Files:**
- Create: `backend/app/domain/game/ai_strategy.py`
- Test: `backend/tests/test_ai_strategy.py`

**Interfaces:**
- Consumes: `Card`, `CardPlay`, `detect_card_type`, `can_beat`, `CardType`, `sort_cards`
- Produces:
  - `ai_decide_call(hand: list[int]) -> int` 返回叫分 (0=不叫, 1~3)
  - `ai_decide_play(hand: list[int], last_play: CardPlay | None, must_play: bool) -> list[int] | None` 返回要出的牌或 None(不出)

- [ ] **Step 1: 编写 AI 策略测试**

```python
# backend/tests/test_ai_strategy.py
import pytest
from app.domain.game.ai_strategy import ai_decide_call, ai_decide_play
from app.domain.game.card_type import detect_card_type


class TestAIDecideCall:
    def test_strong_hand_calls_high(self):
        """有王炸和炸弹的强牌应叫高分"""
        hand = [52, 53, 0, 1, 2, 3, 44, 45, 46, 47, 40, 41, 42, 43, 36, 37, 38]
        score = ai_decide_call(hand)
        assert score >= 2

    def test_weak_hand_skips(self):
        """全是小牌的弱牌应不叫"""
        hand = [0, 4, 8, 12, 16, 20, 1, 5, 9, 13, 17, 21, 2, 6, 10, 14, 18]
        score = ai_decide_call(hand)
        assert score == 0


class TestAIDecidePlay:
    def test_must_play_returns_cards(self):
        """必须出牌时应返回合法的牌"""
        hand = [0, 4, 8, 12, 16, 20, 24, 28, 32, 36, 40, 44, 48, 1, 5, 9, 13]
        cards = ai_decide_play(hand, last_play=None, must_play=True)
        assert cards is not None
        assert len(cards) > 0
        # 出的牌应是合法牌型
        assert detect_card_type(cards) is not None

    def test_can_pass_when_not_must_play(self):
        """有上家大牌时AI可选择不出"""
        hand = [0, 1]  # 只有两张3
        last = detect_card_type([48])  # 上家出了2
        result = ai_decide_play(hand, last_play=last, must_play=False)
        # 3压不过2，应返回 None (不出)
        assert result is None

    def test_play_smallest_single(self):
        """自由出牌时应优先出最小的"""
        hand = [0, 4, 8, 44, 48, 52]  # 3,4,5,A,2,小王
        cards = ai_decide_play(hand, last_play=None, must_play=True)
        assert cards is not None
        # 应该出最小的单张
        assert len(cards) == 1
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd d:\Project_2023\hmp_ws_service\backend
python -m pytest tests/test_ai_strategy.py -v
```

Expected: FAIL

- [ ] **Step 3: 实现 AI 策略**

```python
# backend/app/domain/game/ai_strategy.py
"""AI 机器人出牌策略 (MVP版本: 简单规则策略)"""
from typing import Optional, List
from app.domain.game.card import Card, sort_cards
from app.domain.game.card_type import detect_card_type, can_beat, CardPlay, CardType
from collections import Counter


def ai_decide_call(hand: List[int]) -> int:
    """
    根据手牌强度决定叫分。
    评分规则：大王+10, 小王+8, 2+3, A+2, 炸弹+8
    总分 >= 18 叫3分, >= 12 叫2分, >= 8 叫1分, 否则不叫
    """
    score = 0
    rank_counts = Counter(Card.from_id(c).rank for c in hand)

    for cid in hand:
        card = Card.from_id(cid)
        if card.rank == 14:   # 大王
            score += 10
        elif card.rank == 13: # 小王
            score += 8
        elif card.rank == 12: # 2
            score += 3
        elif card.rank == 11: # A
            score += 2

    # 炸弹加分
    for rank, count in rank_counts.items():
        if count == 4:
            score += 8

    if score >= 18:
        return 3
    elif score >= 12:
        return 2
    elif score >= 8:
        return 1
    return 0


def _find_all_plays(hand: List[int]) -> List[CardPlay]:
    """枚举手牌中所有可出的牌型组合 (仅单张、对子、三条及其变体、炸弹)"""
    plays = []
    rank_counts = Counter(Card.from_id(c).rank for c in hand)
    rank_to_cards = {}
    for cid in hand:
        r = Card.from_id(cid).rank
        rank_to_cards.setdefault(r, []).append(cid)

    for rank, cards_of_rank in rank_to_cards.items():
        count = len(cards_of_rank)
        # 单张
        plays.append(detect_card_type([cards_of_rank[0]]))
        # 对子
        if count >= 2:
            plays.append(detect_card_type(cards_of_rank[:2]))
        # 三条
        if count >= 3:
            plays.append(detect_card_type(cards_of_rank[:3]))
        # 炸弹
        if count == 4:
            plays.append(detect_card_type(cards_of_rank[:4]))

    # 王炸
    if 52 in hand and 53 in hand:
        plays.append(detect_card_type([52, 53]))

    return [p for p in plays if p is not None]


def ai_decide_play(
    hand: List[int],
    last_play: Optional[CardPlay],
    must_play: bool
) -> Optional[List[int]]:
    """
    AI 决定出什么牌。
    - must_play=True 时必须出牌（新一轮首位）
    - 返回 None 表示不出
    """
    if not hand:
        return None

    sorted_hand = sort_cards(hand)
    all_plays = _find_all_plays(sorted_hand)

    if must_play or last_play is None:
        # 自由出牌：出最小的单张
        all_plays.sort(key=lambda p: (p.main_rank, len(p.cards)))
        if all_plays:
            return list(all_plays[0].cards)
        return [sorted_hand[0]]

    # 需要压过上家
    valid_plays = [p for p in all_plays if can_beat(p, last_play)]
    if not valid_plays:
        return None  # 压不过就不出

    # 选最小的能压过的牌 (非炸弹优先)
    non_bombs = [p for p in valid_plays if p.card_type not in (CardType.BOMB, CardType.ROCKET)]
    if non_bombs:
        non_bombs.sort(key=lambda p: p.main_rank)
        return list(non_bombs[0].cards)

    # 只剩炸弹了，如果手牌不多就炸
    if len(hand) <= 5:
        valid_plays.sort(key=lambda p: p.main_rank)
        return list(valid_plays[0].cards)

    return None  # 手牌多时保留炸弹
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd d:\Project_2023\hmp_ws_service\backend
python -m pytest tests/test_ai_strategy.py -v
```

Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(game): 新增 AI 机器人策略 - 叫地主评估与简单出牌"
```

---

### Task 6: Redis 游戏状态仓储

**Files:**
- Create: `backend/app/infrastructure/redis_game_repository.py`
- Test: `backend/tests/test_redis_game_repository.py`

**Interfaces:**
- Consumes: `redis_client` (from `redis_client.py`), `GameRoom.to_dict()`, `GameRoom.from_dict()`
- Produces:
  - `RedisGameRepository`:
    - `async save_room(room: GameRoom) -> None`
    - `async get_room(room_id: str) -> GameRoom | None`
    - `async delete_room(room_id: str) -> None`
    - `async set_player_room(player_id: str, room_id: str) -> None`
    - `async get_player_room(player_id: str) -> str | None`
    - `async remove_player_room(player_id: str) -> None`
    - `async add_to_match_queue(player_id: str) -> None`
    - `async remove_from_match_queue(player_id: str) -> None`
    - `async pop_match_players(count: int) -> list[str]`
    - `async get_match_queue_length() -> int`

- [ ] **Step 1: 编写 Redis 仓储测试**

```python
# backend/tests/test_redis_game_repository.py
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from app.infrastructure.redis_game_repository import RedisGameRepository
from app.domain.game.room import GameRoom, Player


@pytest.fixture
def mock_redis():
    """创建 mock Redis 客户端"""
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock()
    redis.delete = AsyncMock()
    redis.rpush = AsyncMock()
    redis.lrem = AsyncMock()
    redis.llen = AsyncMock(return_value=0)
    redis.expire = AsyncMock()
    return redis


@pytest.fixture
def repo(mock_redis):
    return RedisGameRepository(mock_redis)


@pytest.fixture
def sample_room():
    players = [
        Player(id="p1", nickname="玩家1", is_ai=False, is_online=True),
        Player(id="p2", nickname="玩家2", is_ai=False, is_online=True),
        Player(id="p3", nickname="机器人", is_ai=True, is_online=True),
    ]
    room = GameRoom.create("room_test", players)
    room.deal()
    return room


class TestRedisGameRepository:

    @pytest.mark.asyncio
    async def test_save_and_get_room(self, repo, mock_redis, sample_room):
        """保存房间后应能正确读取"""
        await repo.save_room(sample_room)
        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        assert "game:room:room_test" in str(call_args)

    @pytest.mark.asyncio
    async def test_set_player_room(self, repo, mock_redis):
        """设置玩家-房间映射"""
        await repo.set_player_room("p1", "room_test")
        mock_redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_to_match_queue(self, repo, mock_redis):
        """加入匹配队列"""
        await repo.add_to_match_queue("p1")
        mock_redis.rpush.assert_called_once_with("game:match_queue", "p1")

    @pytest.mark.asyncio
    async def test_remove_from_match_queue(self, repo, mock_redis):
        """从匹配队列移除"""
        await repo.remove_from_match_queue("p1")
        mock_redis.lrem.assert_called_once_with("game:match_queue", 1, "p1")
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd d:\Project_2023\hmp_ws_service\backend
python -m pytest tests/test_redis_game_repository.py -v
```

Expected: FAIL

- [ ] **Step 3: 实现 Redis 游戏仓储**

```python
# backend/app/infrastructure/redis_game_repository.py
"""Redis 游戏状态仓储：房间状态、玩家映射、匹配队列的 CRUD"""
import json
import logging
from typing import Optional, List
from app.domain.game.room import GameRoom

logger = logging.getLogger("hmp_ws_service")

ROOM_KEY_PREFIX = "game:room:"
PLAYER_ROOM_PREFIX = "game:player_room:"
MATCH_QUEUE_KEY = "game:match_queue"
ROOM_TTL = 7200       # 房间状态 2 小时过期
PLAYER_ROOM_TTL = 3600  # 玩家映射 1 小时过期


class RedisGameRepository:
    """基于 Redis 的游戏状态持久化适配器"""

    def __init__(self, redis_client):
        self._redis = redis_client

    # ── 房间状态 ──

    async def save_room(self, room: GameRoom) -> None:
        key = f"{ROOM_KEY_PREFIX}{room.room_id}"
        data = json.dumps(room.to_dict(), ensure_ascii=False)
        await self._redis.set(key, data, ex=ROOM_TTL)

    async def get_room(self, room_id: str) -> Optional[GameRoom]:
        key = f"{ROOM_KEY_PREFIX}{room_id}"
        data = await self._redis.get(key)
        if not data:
            return None
        return GameRoom.from_dict(json.loads(data))

    async def delete_room(self, room_id: str) -> None:
        key = f"{ROOM_KEY_PREFIX}{room_id}"
        await self._redis.delete(key)

    # ── 玩家-房间映射 ──

    async def set_player_room(self, player_id: str, room_id: str) -> None:
        key = f"{PLAYER_ROOM_PREFIX}{player_id}"
        await self._redis.set(key, room_id, ex=PLAYER_ROOM_TTL)

    async def get_player_room(self, player_id: str) -> Optional[str]:
        key = f"{PLAYER_ROOM_PREFIX}{player_id}"
        return await self._redis.get(key)

    async def remove_player_room(self, player_id: str) -> None:
        key = f"{PLAYER_ROOM_PREFIX}{player_id}"
        await self._redis.delete(key)

    # ── 匹配队列 ──

    async def add_to_match_queue(self, player_id: str) -> None:
        await self._redis.rpush(MATCH_QUEUE_KEY, player_id)

    async def remove_from_match_queue(self, player_id: str) -> None:
        await self._redis.lrem(MATCH_QUEUE_KEY, 1, player_id)

    async def pop_match_players(self, count: int = 3) -> List[str]:
        """原子性地从队列头部弹出 count 个玩家"""
        players = []
        for _ in range(count):
            pid = await self._redis.lpop(MATCH_QUEUE_KEY)
            if pid is None:
                break
            players.append(pid)
        return players

    async def get_match_queue_length(self) -> int:
        return await self._redis.llen(MATCH_QUEUE_KEY)
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd d:\Project_2023\hmp_ws_service\backend
python -m pytest tests/test_redis_game_repository.py -v
```

Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(game): 新增 Redis 游戏状态仓储 - 房间/玩家/匹配队列"
```

---

### Task 7: 游戏应用服务层 (编排层)

**Files:**
- Create: `backend/app/application/game/__init__.py`
- Create: `backend/app/application/game/game_app_service.py`
- Test: `backend/tests/test_game_app_service.py`

**Interfaces:**
- Consumes: `GameRoom`, `RedisGameRepository`, `ai_decide_call`, `ai_decide_play`, `Player`
- Produces:
  - `GameAppService`:
    - `async join_match(player_id: str, nickname: str) -> dict`
    - `async cancel_match(player_id: str) -> dict`
    - `async handle_call(player_id: str, score: int) -> dict`
    - `async handle_skip_call(player_id: str) -> dict`
    - `async handle_play(player_id: str, card_ids: list[int]) -> dict`
    - `async handle_pass(player_id: str) -> dict`
    - `async get_room_state(player_id: str) -> dict | None`
    - `async handle_ai_turn(room_id: str) -> dict`

- [ ] **Step 1: 编写游戏应用服务测试**

```python
# backend/tests/test_game_app_service.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.application.game.game_app_service import GameAppService
from app.domain.game.room import GameRoom, Player, GamePhase


@pytest.fixture
def mock_repo():
    repo = AsyncMock()
    repo.get_player_room = AsyncMock(return_value=None)
    repo.get_match_queue_length = AsyncMock(return_value=0)
    repo.add_to_match_queue = AsyncMock()
    repo.remove_from_match_queue = AsyncMock()
    repo.set_player_room = AsyncMock()
    repo.save_room = AsyncMock()
    repo.get_room = AsyncMock(return_value=None)
    repo.pop_match_players = AsyncMock(return_value=[])
    repo.delete_room = AsyncMock()
    repo.remove_player_room = AsyncMock()
    return repo


@pytest.fixture
def service(mock_repo):
    return GameAppService(mock_repo)


class TestGameAppService:

    @pytest.mark.asyncio
    async def test_join_match_adds_to_queue(self, service, mock_repo):
        """加入匹配应添加到队列"""
        mock_repo.pop_match_players.return_value = ["p1"]  # 不够3人
        result = await service.join_match("p1", "玩家1")
        mock_repo.add_to_match_queue.assert_called_once_with("p1")

    @pytest.mark.asyncio
    async def test_join_match_already_in_room(self, service, mock_repo):
        """已在房间中的玩家不能再匹配"""
        mock_repo.get_player_room.return_value = "room_existing"
        result = await service.join_match("p1", "玩家1")
        assert result.get("error") is not None

    @pytest.mark.asyncio
    async def test_cancel_match(self, service, mock_repo):
        """取消匹配应从队列移除"""
        result = await service.cancel_match("p1")
        mock_repo.remove_from_match_queue.assert_called_once_with("p1")
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd d:\Project_2023\hmp_ws_service\backend
python -m pytest tests/test_game_app_service.py -v
```

Expected: FAIL

- [ ] **Step 3: 实现游戏应用服务**

```python
# backend/app/application/game/__init__.py
"""游戏应用服务层"""

# backend/app/application/game/game_app_service.py
"""游戏编排服务：匹配、房间管理、游戏流程控制"""
import uuid
import logging
from typing import Optional, List, Dict
from app.domain.game.room import GameRoom, Player, GamePhase
from app.domain.game.ai_strategy import ai_decide_call, ai_decide_play
from app.infrastructure.redis_game_repository import RedisGameRepository

logger = logging.getLogger("hmp_ws_service")

AI_NAMES = ["机器人小明", "机器人小红", "机器人小刚", "机器人小芳", "机器人小李"]


class GameAppService:
    """游戏应用层编排服务"""

    MATCH_TIMEOUT_SECONDS = 10

    def __init__(self, repo: RedisGameRepository):
        self._repo = repo
        # 维护一份等待中的玩家信息 (player_id -> nickname)
        self._pending_players: Dict[str, str] = {}

    async def join_match(self, player_id: str, nickname: str) -> dict:
        """玩家加入匹配队列"""
        # 检查是否已在房间中
        existing_room = await self._repo.get_player_room(player_id)
        if existing_room:
            return {"error": "你已在游戏房间中", "room_id": existing_room}

        self._pending_players[player_id] = nickname
        await self._repo.add_to_match_queue(player_id)
        queue_len = await self._repo.get_match_queue_length()

        if queue_len >= 3:
            # 凑够3人，创建房间
            player_ids = await self._repo.pop_match_players(3)
            if len(player_ids) >= 3:
                return await self._create_room(player_ids)

        return {"status": "waiting", "queue_length": queue_len}

    async def fill_with_ai(self, player_ids: List[str]) -> dict:
        """用 AI 填充不足的玩家位并创建房间"""
        import random
        ai_count = 3 - len(player_ids)
        ai_names = random.sample(AI_NAMES, ai_count)
        for i in range(ai_count):
            ai_id = f"ai_bot_{uuid.uuid4().hex[:8]}"
            player_ids.append(ai_id)
            self._pending_players[ai_id] = ai_names[i]
        return await self._create_room(player_ids)

    async def _create_room(self, player_ids: List[str]) -> dict:
        """创建游戏房间并发牌"""
        room_id = f"room_{uuid.uuid4().hex[:12]}"
        players = []
        for pid in player_ids:
            is_ai = pid.startswith("ai_bot_")
            nickname = self._pending_players.get(pid, pid)
            players.append(Player(id=pid, nickname=nickname, is_ai=is_ai, is_online=True))
            # 清理临时数据
            self._pending_players.pop(pid, None)

        room = GameRoom.create(room_id, players)
        room.deal()

        # 保存到 Redis
        await self._repo.save_room(room)
        for pid in player_ids:
            await self._repo.set_player_room(pid, room_id)

        logger.info(f"游戏房间 {room_id} 已创建: {[p.nickname for p in players]}")
        return {
            "status": "room_created",
            "room_id": room_id,
            "players": [{"id": p.id, "nickname": p.nickname, "is_ai": p.is_ai} for p in players],
        }

    async def cancel_match(self, player_id: str) -> dict:
        """取消匹配"""
        await self._repo.remove_from_match_queue(player_id)
        self._pending_players.pop(player_id, None)
        return {"status": "cancelled"}

    async def _get_player_room(self, player_id: str) -> Optional[GameRoom]:
        """获取玩家所在的房间"""
        room_id = await self._repo.get_player_room(player_id)
        if not room_id:
            return None
        return await self._repo.get_room(room_id)

    async def handle_call(self, player_id: str, score: int) -> dict:
        """处理叫地主"""
        room = await self._get_player_room(player_id)
        if not room:
            return {"error": "你不在任何房间中"}
        result = room.call_landlord(player_id, score)
        if result.get("redeal"):
            room.deal()
        await self._repo.save_room(room)
        result["room"] = room
        return result

    async def handle_skip_call(self, player_id: str) -> dict:
        """处理不叫"""
        room = await self._get_player_room(player_id)
        if not room:
            return {"error": "你不在任何房间中"}
        result = room.skip_call(player_id)
        if result.get("redeal"):
            room.deal()
        await self._repo.save_room(room)
        result["room"] = room
        return result

    async def handle_play(self, player_id: str, card_ids: List[int]) -> dict:
        """处理出牌"""
        room = await self._get_player_room(player_id)
        if not room:
            return {"error": "你不在任何房间中"}
        result = room.play_cards(player_id, card_ids)
        await self._repo.save_room(room)
        result["room"] = room
        return result

    async def handle_pass(self, player_id: str) -> dict:
        """处理不出"""
        room = await self._get_player_room(player_id)
        if not room:
            return {"error": "你不在任何房间中"}
        result = room.pass_turn(player_id)
        await self._repo.save_room(room)
        result["room"] = room
        return result

    async def handle_ai_turn(self, room: GameRoom) -> dict:
        """处理 AI 回合"""
        ai_id = room.current_turn
        if room.phase == GamePhase.CALLING:
            hand = room.hands[ai_id]
            score = ai_decide_call(hand)
            if score > 0:
                # 确保叫分高于当前最高分
                current_max = max(room._call_scores.values()) if room._call_scores else 0
                if score <= current_max:
                    score = 0
            if score > 0:
                result = room.call_landlord(ai_id, score)
            else:
                result = room.skip_call(ai_id)
            if result.get("redeal"):
                room.deal()
            await self._repo.save_room(room)
            result["room"] = room
            result["ai_player"] = ai_id
            return result

        elif room.phase == GamePhase.PLAYING:
            hand = room.hands[ai_id]
            last_cp = room.last_play.card_play
            must_play = (room.last_play.player is None)
            cards = ai_decide_play(hand, last_cp, must_play)
            if cards:
                result = room.play_cards(ai_id, cards)
            else:
                result = room.pass_turn(ai_id)
            await self._repo.save_room(room)
            result["room"] = room
            result["ai_player"] = ai_id
            return result

        return {"error": "AI 当前无法操作"}

    async def get_room_state(self, player_id: str) -> Optional[dict]:
        """获取玩家可见的房间状态 (用于断线重连)"""
        room = await self._get_player_room(player_id)
        if not room:
            return None
        return room.get_player_view(player_id)

    async def cleanup_room(self, room_id: str, player_ids: List[str]) -> None:
        """清理已结束的游戏房间"""
        await self._repo.delete_room(room_id)
        for pid in player_ids:
            if not pid.startswith("ai_bot_"):
                await self._repo.remove_player_room(pid)
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd d:\Project_2023\hmp_ws_service\backend
python -m pytest tests/test_game_app_service.py -v
```

Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(game): 新增游戏应用服务层 - 匹配/房间管理/AI回合处理"
```

---

### Task 8: 数据库模型 — 玩家档案与对局记录

**Files:**
- Create: `backend/app/domain/game/entities.py`
- Modify: `backend/app/infrastructure/database/models.py` (新增 ORM 模型)
- Create: `backend/app/infrastructure/database/game_repository.py`
- Modify: `backend/app/infrastructure/database/__init__.py` (导出新仓储)
- Test: `backend/tests/test_game_models.py`

**Interfaces:**
- Consumes: `Base` (SQLAlchemy), `transactional_session`
- Produces:
  - `PlayerProfile` 领域实体: `id, player_id, nickname, beans, total_games, wins, win_rate`
  - `GameRecord` 领域实体: `id, room_id, player_id, role, result, score_change, multiplier, created_at`
  - `PlayerProfileORM`, `GameRecordORM` (ORM 模型)
  - `SQLGameRepository`:
    - `get_or_create_profile(player_id, nickname) -> PlayerProfile`
    - `update_profile_stats(player_id, beans_delta, is_win) -> None`
    - `save_game_record(record: GameRecord) -> None`
    - `get_history(player_id, limit) -> list[GameRecord]`
    - `get_leaderboard(limit) -> list[PlayerProfile]`

- [ ] **Step 1: 编写领域实体和数据库模型测试**

```python
# backend/tests/test_game_models.py
import pytest
from app.domain.game.entities import PlayerProfile, GameRecord


class TestPlayerProfile:
    def test_create_profile(self):
        p = PlayerProfile(player_id="p1", nickname="玩家1")
        assert p.beans == 10000  # 初始欢乐豆
        assert p.total_games == 0
        assert p.wins == 0

    def test_win_rate_zero_games(self):
        p = PlayerProfile(player_id="p1", nickname="玩家1")
        assert p.win_rate == 0.0

    def test_win_rate_calculation(self):
        p = PlayerProfile(player_id="p1", nickname="玩家1", total_games=10, wins=6)
        assert p.win_rate == 0.6


class TestGameRecord:
    def test_create_record(self):
        r = GameRecord(
            room_id="room_1", player_id="p1",
            role="landlord", result="win",
            score_change=60, multiplier=2
        )
        assert r.role == "landlord"
        assert r.result == "win"
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd d:\Project_2023\hmp_ws_service\backend
python -m pytest tests/test_game_models.py -v
```

Expected: FAIL

- [ ] **Step 3: 实现领域实体**

```python
# backend/app/domain/game/entities.py
"""游戏领域实体：玩家档案与对局记录"""
import datetime
from typing import Optional


class PlayerProfile:
    """玩家档案领域实体"""
    DEFAULT_BEANS = 10000

    def __init__(
        self,
        player_id: str,
        nickname: str,
        id: Optional[int] = None,
        beans: int = DEFAULT_BEANS,
        total_games: int = 0,
        wins: int = 0,
        created_at: Optional[datetime.datetime] = None,
    ):
        self.id = id
        self.player_id = player_id
        self.nickname = nickname
        self.beans = beans
        self.total_games = total_games
        self.wins = wins
        self.created_at = created_at or datetime.datetime.now()

    @property
    def win_rate(self) -> float:
        if self.total_games == 0:
            return 0.0
        return round(self.wins / self.total_games, 2)


class GameRecord:
    """对局记录领域实体"""

    def __init__(
        self,
        room_id: str,
        player_id: str,
        role: str,         # "landlord" / "farmer"
        result: str,        # "win" / "lose"
        score_change: int,
        multiplier: int,
        id: Optional[int] = None,
        created_at: Optional[datetime.datetime] = None,
    ):
        self.id = id
        self.room_id = room_id
        self.player_id = player_id
        self.role = role
        self.result = result
        self.score_change = score_change
        self.multiplier = multiplier
        self.created_at = created_at or datetime.datetime.now()
```

- [ ] **Step 4: 新增 ORM 模型到 models.py**

在 `backend/app/infrastructure/database/models.py` 末尾追加：

```python
class PlayerProfileORM(Base):
    __tablename__ = "player_profile"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    player_id = Column(String(100), nullable=False, unique=True, index=True, comment="玩家ID")
    nickname = Column(String(100), nullable=False, comment="昵称")
    beans = Column(Integer, default=10000, nullable=False, comment="欢乐豆")
    total_games = Column(Integer, default=0, nullable=False, comment="总对局数")
    wins = Column(Integer, default=0, nullable=False, comment="胜场数")
    created_at = Column(DateTime, default=datetime.datetime.now, comment="创建时间")


class GameRecordORM(Base):
    __tablename__ = "game_record"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    room_id = Column(String(100), nullable=False, index=True, comment="房间ID")
    player_id = Column(String(100), nullable=False, index=True, comment="玩家ID")
    role = Column(String(20), nullable=False, comment="角色: landlord/farmer")
    result = Column(String(20), nullable=False, comment="结果: win/lose")
    score_change = Column(Integer, nullable=False, comment="欢乐豆变化")
    multiplier = Column(Integer, default=1, comment="倍数")
    created_at = Column(DateTime, default=datetime.datetime.now, index=True, comment="对局时间")
```

- [ ] **Step 5: 实现数据库仓储**

```python
# backend/app/infrastructure/database/game_repository.py
"""游戏数据库仓储：玩家档案与对局记录的持久化"""
import logging
from typing import Optional, List
from sqlalchemy.orm import Session
from app.infrastructure.database.models import PlayerProfileORM, GameRecordORM
from app.domain.game.entities import PlayerProfile, GameRecord

logger = logging.getLogger("hmp_ws_service")


class SQLGameRepository:

    def __init__(self, db: Session):
        self._db = db

    def get_or_create_profile(self, player_id: str, nickname: str) -> PlayerProfile:
        orm = self._db.query(PlayerProfileORM).filter_by(player_id=player_id).first()
        if not orm:
            orm = PlayerProfileORM(player_id=player_id, nickname=nickname)
            self._db.add(orm)
            self._db.flush()
        return PlayerProfile(
            id=orm.id, player_id=orm.player_id, nickname=orm.nickname,
            beans=orm.beans, total_games=orm.total_games, wins=orm.wins,
            created_at=orm.created_at
        )

    def update_profile_stats(self, player_id: str, beans_delta: int, is_win: bool) -> None:
        orm = self._db.query(PlayerProfileORM).filter_by(player_id=player_id).first()
        if orm:
            orm.beans += beans_delta
            orm.total_games += 1
            if is_win:
                orm.wins += 1

    def save_game_record(self, record: GameRecord) -> None:
        orm = GameRecordORM(
            room_id=record.room_id, player_id=record.player_id,
            role=record.role, result=record.result,
            score_change=record.score_change, multiplier=record.multiplier,
        )
        self._db.add(orm)

    def get_history(self, player_id: str, limit: int = 20) -> List[GameRecord]:
        rows = (self._db.query(GameRecordORM)
                .filter_by(player_id=player_id)
                .order_by(GameRecordORM.created_at.desc())
                .limit(limit).all())
        return [GameRecord(
            id=r.id, room_id=r.room_id, player_id=r.player_id,
            role=r.role, result=r.result, score_change=r.score_change,
            multiplier=r.multiplier, created_at=r.created_at
        ) for r in rows]

    def get_leaderboard(self, limit: int = 20) -> List[PlayerProfile]:
        rows = (self._db.query(PlayerProfileORM)
                .order_by(PlayerProfileORM.beans.desc())
                .limit(limit).all())
        return [PlayerProfile(
            id=r.id, player_id=r.player_id, nickname=r.nickname,
            beans=r.beans, total_games=r.total_games, wins=r.wins,
            created_at=r.created_at
        ) for r in rows]
```

- [ ] **Step 6: 更新 `__init__.py` 导出**

```python
# backend/app/infrastructure/database/__init__.py
from .message_repository import SQLMessageRepository
from .upload_repository import SQLUploadedFileRepository
from .game_repository import SQLGameRepository

__all__ = [
    "SQLMessageRepository",
    "SQLUploadedFileRepository",
    "SQLGameRepository",
]
```

- [ ] **Step 7: 运行测试确认通过**

```bash
cd d:\Project_2023\hmp_ws_service\backend
python -m pytest tests/test_game_models.py -v
```

Expected: 全部 PASS

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "feat(game): 新增玩家档案与对局记录的领域实体、ORM模型与数据库仓储"
```

---

### Task 9: WebSocket 游戏端点与 Handler

**Files:**
- Create: `backend/app/interfaces/websocket/game_routes.py`
- Create: `backend/app/interfaces/websocket/game_handler.py`
- Modify: `backend/main.py` (注册游戏路由, 添加 CORS)

**Interfaces:**
- Consumes: `GameAppService`, `RedisGameRepository`, `WSConnectionManager`, `verify_ws_token`, `redis_client`
- Produces:
  - WebSocket endpoint: `/ws/game/{player_id}`
  - `GameWSConnectionManager`: 管理游戏 WebSocket 连接
  - `GameWebSocketHandler`: 处理游戏事件的 handler

- [ ] **Step 1: 实现游戏 WebSocket 连接管理器与路由**

```python
# backend/app/interfaces/websocket/game_routes.py
"""斗地主游戏 WebSocket 端点"""
import logging
from typing import Dict, List
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends

logger = logging.getLogger("hmp_ws_service")
router = APIRouter(tags=["Game WebSocket"])


class GameWSConnectionManager:
    """管理游戏 WebSocket 连接。按 player_id 维护连接映射。"""

    def __init__(self):
        self.connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, player_id: str):
        await websocket.accept()
        self.connections[player_id] = websocket
        logger.info(f"游戏WS: 玩家 '{player_id}' 已连接. 在线: {len(self.connections)}")

    def disconnect(self, player_id: str):
        self.connections.pop(player_id, None)
        logger.info(f"游戏WS: 玩家 '{player_id}' 已断开. 在线: {len(self.connections)}")

    async def send_to_player(self, player_id: str, data: dict):
        import json
        ws = self.connections.get(player_id)
        if ws:
            try:
                await ws.send_text(json.dumps(data, ensure_ascii=False))
            except Exception as e:
                logger.error(f"游戏WS: 发送给 '{player_id}' 失败: {e}")
                self.disconnect(player_id)

    async def broadcast_to_room(self, player_ids: List[str], data: dict):
        for pid in player_ids:
            await self.send_to_player(pid, data)


def get_game_ws_manager(websocket: WebSocket) -> GameWSConnectionManager:
    return websocket.app.state.game_ws_manager


def get_game_service(websocket: WebSocket):
    return websocket.app.state.game_service


@router.websocket("/ws/game/{player_id}")
async def game_websocket_endpoint(
    websocket: WebSocket,
    player_id: str,
    manager: GameWSConnectionManager = Depends(get_game_ws_manager),
    game_service = Depends(get_game_service),
):
    # Token 校验
    from app.infrastructure.auth import verify_ws_token
    if not verify_ws_token(websocket.query_params):
        await websocket.accept()
        await websocket.close(code=1008, reason="Unauthorized")
        return

    from app.interfaces.websocket.game_handler import GameWebSocketHandler
    handler = GameWebSocketHandler(websocket, player_id, manager, game_service)
    await handler.run()
```

- [ ] **Step 2: 实现游戏 Handler**

```python
# backend/app/interfaces/websocket/game_handler.py
"""斗地主游戏 WebSocket Handler：事件接收、分发与广播"""
import json
import asyncio
import logging
from fastapi import WebSocket, WebSocketDisconnect
from app.interfaces.websocket.game_routes import GameWSConnectionManager
from app.application.game.game_app_service import GameAppService
from app.domain.game.room import GamePhase

logger = logging.getLogger("hmp_ws_service")


class GameWebSocketHandler:
    """处理单个游戏 WebSocket 连接的所有事件"""

    def __init__(
        self,
        websocket: WebSocket,
        player_id: str,
        manager: GameWSConnectionManager,
        game_service: GameAppService,
    ):
        self.ws = websocket
        self.player_id = player_id
        self.manager = manager
        self.service = game_service
        self._timeout_task = None

    async def run(self):
        await self.manager.connect(self.ws, self.player_id)

        # 检查是否有断线重连的房间
        room_state = await self.service.get_room_state(self.player_id)
        if room_state:
            await self._send({"event": "reconnected", **room_state})

        try:
            while True:
                text = await self.ws.receive_text()
                await self._handle_message(text)
        except WebSocketDisconnect:
            self.manager.disconnect(self.player_id)
            logger.info(f"游戏WS: 玩家 '{self.player_id}' 断开连接")
            # TODO: 触发离线事件，启动托管倒计时
        except Exception as e:
            logger.error(f"游戏WS: 玩家 '{self.player_id}' 错误: {e}")
            self.manager.disconnect(self.player_id)

    async def _send(self, data: dict):
        await self.manager.send_to_player(self.player_id, data)

    async def _broadcast_room_event(self, room, event_data: dict):
        """向房间内所有在线真人玩家广播事件"""
        for p in room.players:
            if not p.is_ai and p.id in self.manager.connections:
                # 每个玩家收到自己的视角
                player_view = room.get_player_view(p.id)
                msg = {**event_data, "room_state": player_view}
                await self.manager.send_to_player(p.id, msg)

    async def _handle_message(self, text: str):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            await self._send({"event": "error", "msg": "无效的 JSON 格式"})
            return

        action = data.get("action")

        if action == "join_match":
            nickname = data.get("nickname", self.player_id)
            result = await self.service.join_match(self.player_id, nickname)
            if result.get("error"):
                await self._send({"event": "error", "msg": result["error"]})
            elif result.get("status") == "waiting":
                await self._send({"event": "match_waiting", "count": result["queue_length"]})
            elif result.get("status") == "room_created":
                await self._on_room_created(result)

        elif action == "cancel_match":
            result = await self.service.cancel_match(self.player_id)
            await self._send({"event": "match_cancelled"})

        elif action == "call_landlord":
            score = data.get("score", 1)
            result = await self.service.handle_call(self.player_id, score)
            if result.get("error"):
                await self._send({"event": "error", "msg": result["error"]})
            else:
                room = result.get("room")
                if room:
                    event = {"event": "call_made", "player": self.player_id, "score": score}
                    if result.get("landlord"):
                        event["event"] = "landlord_decided"
                        event["landlord"] = result["landlord"]
                        event["bottom_cards"] = result["bottom_cards"]
                        event["multiplier"] = result["multiplier"]
                    await self._broadcast_room_event(room, event)
                    # 如果下一个是 AI，自动处理
                    await self._process_ai_turns(room)

        elif action == "skip_call":
            result = await self.service.handle_skip_call(self.player_id)
            if result.get("error"):
                await self._send({"event": "error", "msg": result["error"]})
            else:
                room = result.get("room")
                if room:
                    event = {"event": "call_skipped", "player": self.player_id}
                    if result.get("redeal"):
                        event["event"] = "redeal"
                    elif result.get("landlord"):
                        event["event"] = "landlord_decided"
                        event["landlord"] = result["landlord"]
                        event["bottom_cards"] = result["bottom_cards"]
                        event["multiplier"] = result["multiplier"]
                    await self._broadcast_room_event(room, event)
                    await self._process_ai_turns(room)

        elif action == "play_cards":
            cards = data.get("cards", [])
            result = await self.service.handle_play(self.player_id, cards)
            if result.get("error"):
                await self._send({"event": "error", "msg": result["error"]})
            else:
                room = result.get("room")
                if room:
                    if result.get("game_over"):
                        event = {
                            "event": "game_over",
                            "winner": result["winner"],
                            "winner_side": result["winner_side"],
                            "scores": result["scores"],
                            "multiplier": result["multiplier"],
                            "all_hands": result["all_hands"],
                        }
                        await self._broadcast_room_event(room, event)
                        await self._on_game_over(room, result)
                    else:
                        event = {
                            "event": "cards_played",
                            "player": self.player_id,
                            "cards": result["cards_played"],
                            "card_type": result["card_type"],
                            "remaining": result["remaining"],
                        }
                        await self._broadcast_room_event(room, event)
                        await self._process_ai_turns(room)

        elif action == "pass_turn":
            result = await self.service.handle_pass(self.player_id)
            if result.get("error"):
                await self._send({"event": "error", "msg": result["error"]})
            else:
                room = result.get("room")
                if room:
                    event = {"event": "turn_passed", "player": self.player_id}
                    if result.get("new_round"):
                        event["new_round"] = True
                    await self._broadcast_room_event(room, event)
                    await self._process_ai_turns(room)

        elif action == "chat":
            msg_id = data.get("msg_id", 0)
            # 直接广播聊天给房间其他人
            room = await self.service._get_player_room(self.player_id)
            if room:
                event = {"event": "chat_msg", "player": self.player_id, "msg_id": msg_id}
                await self._broadcast_room_event(room, event)

        else:
            await self._send({"event": "error", "msg": f"未知动作: {action}"})

    async def _on_room_created(self, result: dict):
        """房间创建后的广播逻辑"""
        room_id = result["room_id"]
        from app.infrastructure.redis_client import redis_client
        from app.infrastructure.redis_game_repository import RedisGameRepository
        repo = RedisGameRepository(redis_client)
        room = await repo.get_room(room_id)
        if room:
            event = {
                "event": "match_success",
                "room_id": room_id,
                "players": result["players"],
            }
            await self._broadcast_room_event(room, event)
            # 发送 game_start（包含各自手牌）
            for p in room.players:
                if not p.is_ai and p.id in self.manager.connections:
                    view = room.get_player_view(p.id)
                    await self.manager.send_to_player(p.id, {
                        "event": "game_start",
                        "hand": view["hand"],
                        "players": view["players"],
                        "current_turn": room.current_turn,
                    })
            # 如果首位叫牌者是 AI
            await self._process_ai_turns(room)

    async def _process_ai_turns(self, room):
        """循环处理 AI 回合，直到轮到真人玩家"""
        while room.phase in (GamePhase.CALLING, GamePhase.PLAYING):
            current = room.current_turn
            current_player = next((p for p in room.players if p.id == current), None)
            if not current_player or not current_player.is_ai:
                break
            # AI 延迟 1~2 秒模拟思考
            await asyncio.sleep(1.0)
            result = await self.service.handle_ai_turn(room)
            if result.get("error"):
                break
            room = result.get("room", room)
            # 广播 AI 的操作
            ai_id = result.get("ai_player")
            if room.phase == GamePhase.SETTLING or result.get("game_over"):
                event = {
                    "event": "game_over",
                    "winner": result.get("winner"),
                    "winner_side": result.get("winner_side"),
                    "scores": result.get("scores", {}),
                    "multiplier": result.get("multiplier", 1),
                    "all_hands": result.get("all_hands", {}),
                }
                await self._broadcast_room_event(room, event)
                await self._on_game_over(room, result)
                break
            elif result.get("redeal"):
                await self._broadcast_room_event(room, {"event": "redeal"})
                # 重发后继续处理可能的 AI 叫地主
                continue
            elif result.get("landlord"):
                event = {
                    "event": "landlord_decided",
                    "landlord": result["landlord"],
                    "bottom_cards": result.get("bottom_cards", []),
                    "multiplier": result.get("multiplier", 1),
                }
                await self._broadcast_room_event(room, event)
            elif result.get("cards_played"):
                event = {
                    "event": "cards_played",
                    "player": ai_id,
                    "cards": result["cards_played"],
                    "card_type": result.get("card_type"),
                    "remaining": result.get("remaining"),
                }
                await self._broadcast_room_event(room, event)
            elif result.get("next_turn"):
                event = {"event": "turn_passed" if not result.get("cards_played") else "call_skipped", "player": ai_id}
                await self._broadcast_room_event(room, event)

    async def _on_game_over(self, room, result: dict):
        """游戏结束后的清理与结算入库"""
        try:
            from app.infrastructure.database.session import transactional_session
            from app.infrastructure.database.game_repository import SQLGameRepository
            from app.domain.game.entities import GameRecord

            scores = result.get("scores", {})
            with transactional_session() as db:
                repo = SQLGameRepository(db)
                for p in room.players:
                    if p.is_ai:
                        continue
                    is_landlord = (p.id == room.landlord)
                    score_change = scores.get(p.id, 0)
                    is_win = score_change > 0
                    repo.get_or_create_profile(p.id, p.nickname)
                    repo.update_profile_stats(p.id, score_change, is_win)
                    repo.save_game_record(GameRecord(
                        room_id=room.room_id,
                        player_id=p.id,
                        role="landlord" if is_landlord else "farmer",
                        result="win" if is_win else "lose",
                        score_change=score_change,
                        multiplier=room.multiplier,
                    ))
        except Exception as e:
            logger.error(f"游戏结算入库失败: {e}")

        # 清理 Redis 房间
        player_ids = [p.id for p in room.players]
        await self.service.cleanup_room(room.room_id, player_ids)
```

- [ ] **Step 3: 修改 main.py 注册游戏路由和 CORS**

在 `backend/main.py` 中添加：

```python
# 导入游戏路由和管理器
from app.interfaces.websocket.game_routes import router as game_ws_router, GameWSConnectionManager
from app.application.game.game_app_service import GameAppService
from app.infrastructure.redis_game_repository import RedisGameRepository
from app.infrastructure.redis_client import redis_client

# CORS 中间件 (支持 Vue 前端跨域访问)
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册游戏 WebSocket 路由
app.include_router(game_ws_router)

# 在 lifespan 函数中添加游戏服务初始化:
# game_ws_manager = GameWSConnectionManager()
# game_repo = RedisGameRepository(redis_client)
# game_service = GameAppService(game_repo)
# app_instance.state.game_ws_manager = game_ws_manager
# app_instance.state.game_service = game_service
```

- [ ] **Step 4: 运行全量测试确认通过**

```bash
cd d:\Project_2023\hmp_ws_service\backend
python -m pytest tests/ -v
```

Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(game): 新增游戏 WebSocket 端点、Handler 和 main.py 集成"
```

---

### Task 10: HTTP 游戏 REST API

**Files:**
- Create: `backend/app/interfaces/api/game_routes.py`
- Modify: `backend/main.py` (注册 HTTP 路由)

**Interfaces:**
- Consumes: `SQLGameRepository`, `transactional_session`, `AuditLogRoute`
- Produces:
  - `GET /api/game/profile/{player_id}` → 玩家档案
  - `GET /api/game/history/{player_id}` → 历史记录
  - `GET /api/game/leaderboard` → 排行榜

- [ ] **Step 1: 实现游戏 HTTP API 路由**

```python
# backend/app/interfaces/api/game_routes.py
"""斗地主游戏 HTTP REST API"""
from fastapi import APIRouter, Depends, HTTPException
from app.infrastructure.database.session import get_db
from app.infrastructure.database.game_repository import SQLGameRepository
from app.infrastructure.audit_route import AuditLogRoute
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/game", tags=["Game API"], route_class=AuditLogRoute)


@router.get("/profile/{player_id}")
def get_player_profile(player_id: str, db: Session = Depends(get_db)):
    repo = SQLGameRepository(db)
    profile = repo.get_or_create_profile(player_id, player_id)
    return {
        "player_id": profile.player_id,
        "nickname": profile.nickname,
        "beans": profile.beans,
        "total_games": profile.total_games,
        "wins": profile.wins,
        "win_rate": profile.win_rate,
    }


@router.get("/history/{player_id}")
def get_game_history(player_id: str, limit: int = 20, db: Session = Depends(get_db)):
    repo = SQLGameRepository(db)
    records = repo.get_history(player_id, limit)
    return [{
        "room_id": r.room_id,
        "role": r.role,
        "result": r.result,
        "score_change": r.score_change,
        "multiplier": r.multiplier,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in records]


@router.get("/leaderboard")
def get_leaderboard(limit: int = 20, db: Session = Depends(get_db)):
    repo = SQLGameRepository(db)
    profiles = repo.get_leaderboard(limit)
    return [{
        "rank": i + 1,
        "player_id": p.player_id,
        "nickname": p.nickname,
        "beans": p.beans,
        "total_games": p.total_games,
        "win_rate": p.win_rate,
    } for i, p in enumerate(profiles)]
```

- [ ] **Step 2: 在 main.py 中注册路由**

```python
from app.interfaces.api.game_routes import router as game_api_router
app.include_router(game_api_router)
```

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "feat(game): 新增游戏 HTTP API - 玩家档案/历史记录/排行榜"
```

---

### Task 11: 前端 Vue 3 项目初始化

**Files:**
- Create: `frontend/` (通过 `create-vue` 脚手架)
- Modify: `frontend/vite.config.js` (WebSocket 代理)
- Modify: `frontend/package.json` (安装 pinia, vue-router)

**Interfaces:**
- Consumes: Node.js, npm
- Produces: 可运行的 Vue 3 + Vite 前端项目框架

- [ ] **Step 1: 使用 create-vue 初始化项目**

```bash
cd d:\Project_2023\hmp_ws_service
npx -y create-vue@latest frontend --ts --router --pinia --vitest --no-eslint --no-playwright --no-jsx
```

- [ ] **Step 2: 安装依赖**

```bash
cd d:\Project_2023\hmp_ws_service\frontend
npm install
```

- [ ] **Step 3: 配置 Vite 代理**

```javascript
// frontend/vite.config.js
import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  server: {
    port: 5173,
    proxy: {
      '/ws/game': {
        target: 'ws://127.0.0.1:18088',
        ws: true,
      },
      '/api/game': {
        target: 'http://127.0.0.1:18088',
        changeOrigin: true,
      },
    },
  },
})
```

- [ ] **Step 4: 验证项目启动**

```bash
cd d:\Project_2023\hmp_ws_service\frontend
npm run dev
```

Expected: 浏览器访问 `http://localhost:5173` 显示 Vue 欢迎页

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(frontend): 初始化 Vue 3 + Vite 前端项目"
```

---

### Task 12: 前端工具层 — WebSocket Composable 与 Pinia Store

**Files:**
- Create: `frontend/src/composables/useGameWebSocket.ts`
- Create: `frontend/src/stores/playerStore.ts`
- Create: `frontend/src/stores/gameStore.ts`
- Create: `frontend/src/utils/cardUtils.ts`

**Interfaces:**
- Consumes: Vue 3 Composition API, Pinia
- Produces:
  - `useGameWebSocket()`: `connect(), disconnect(), sendAction(), isConnected`
  - `usePlayerStore`: `playerId, nickname, beans, login()`
  - `useGameStore`: `gamePhase, players, myHand, selectedCards, ...` 及所有事件处理 action
  - `cardUtils`: `getCardDisplay(cardId)`, `getCardColor(cardId)`, `sortCards()`

- [ ] **Step 1: 实现扑克牌工具函数**

```typescript
// frontend/src/utils/cardUtils.ts
const RANK_NAMES = ['3','4','5','6','7','8','9','10','J','Q','K','A','2']
const SUIT_SYMBOLS = ['♠','♥','♣','♦']
const SUIT_NAMES = ['spade','heart','club','diamond']

export interface CardDisplay {
  id: number
  rank: string
  suit: string
  suitSymbol: string
  color: 'red' | 'black'
  power: number
}

export function getCardDisplay(cardId: number): CardDisplay {
  if (cardId === 52) return { id: 52, rank: '小', suit: 'joker', suitSymbol: '🃏', color: 'black', power: 13 }
  if (cardId === 53) return { id: 53, rank: '大', suit: 'joker', suitSymbol: '🃏', color: 'red', power: 14 }
  const rank = Math.floor(cardId / 4)
  const suit = cardId % 4
  return {
    id: cardId,
    rank: RANK_NAMES[rank],
    suit: SUIT_NAMES[suit],
    suitSymbol: SUIT_SYMBOLS[suit],
    color: (suit === 1 || suit === 3) ? 'red' : 'black',
    power: rank,
  }
}

export function sortCardIds(cardIds: number[]): number[] {
  return [...cardIds].sort((a, b) => {
    const pa = getCardDisplay(a).power
    const pb = getCardDisplay(b).power
    return pa - pb
  })
}
```

- [ ] **Step 2: 实现 Pinia Store**

```typescript
// frontend/src/stores/playerStore.ts
import { defineStore } from 'pinia'
import { ref } from 'vue'

export const usePlayerStore = defineStore('player', () => {
  const playerId = ref('')
  const nickname = ref('')
  const beans = ref(10000)
  const totalGames = ref(0)
  const winRate = ref(0)

  function login(id: string, name: string) {
    playerId.value = id
    nickname.value = name
  }

  return { playerId, nickname, beans, totalGames, winRate, login }
})

// frontend/src/stores/gameStore.ts
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export interface PlayerInfo {
  id: string
  nickname: string
  isAi: boolean
  isOnline: boolean
  remaining?: number
  isLandlord?: boolean
  isSelf?: boolean
}

export interface LastPlay {
  player: string | null
  cards: number[]
  cardType: string | null
}

export const useGameStore = defineStore('game', () => {
  const wsConnected = ref(false)
  const roomId = ref('')
  const gamePhase = ref<string>('IDLE')  // IDLE | MATCHING | DEALING | CALLING | PLAYING | SETTLING
  const players = ref<PlayerInfo[]>([])
  const myHand = ref<number[]>([])
  const selectedCards = ref<number[]>([])
  const bottomCards = ref<number[]>([])
  const lastPlay = ref<LastPlay>({ player: null, cards: [], cardType: null })
  const currentTurn = ref('')
  const turnTimeout = ref(20)
  const multiplier = ref(1)
  const landlord = ref('')
  const settlement = ref<any>(null)
  const errorMsg = ref('')

  const isMyTurn = computed(() => {
    const playerStore = usePlayerStore()
    return currentTurn.value === playerStore.playerId
  })

  function toggleCard(cardId: number) {
    const idx = selectedCards.value.indexOf(cardId)
    if (idx >= 0) {
      selectedCards.value.splice(idx, 1)
    } else {
      selectedCards.value.push(cardId)
    }
  }

  function clearSelection() {
    selectedCards.value = []
  }

  function updateFromRoomState(state: any) {
    if (state.room_id) roomId.value = state.room_id
    if (state.phase) gamePhase.value = state.phase
    if (state.players) players.value = state.players.map((p: any) => ({
      id: p.id, nickname: p.nickname, isAi: p.is_ai, isOnline: p.is_online,
      remaining: p.remaining, isLandlord: p.is_landlord, isSelf: p.is_self,
    }))
    if (state.hand) myHand.value = state.hand
    if (state.current_turn) currentTurn.value = state.current_turn
    if (state.multiplier) multiplier.value = state.multiplier
    if (state.landlord) landlord.value = state.landlord
    if (state.bottom_cards) bottomCards.value = state.bottom_cards
    if (state.last_play) lastPlay.value = {
      player: state.last_play.player,
      cards: state.last_play.cards || [],
      cardType: state.last_play.card_type,
    }
  }

  function reset() {
    roomId.value = ''
    gamePhase.value = 'IDLE'
    players.value = []
    myHand.value = []
    selectedCards.value = []
    bottomCards.value = []
    lastPlay.value = { player: null, cards: [], cardType: null }
    currentTurn.value = ''
    multiplier.value = 1
    landlord.value = ''
    settlement.value = null
  }

  return {
    wsConnected, roomId, gamePhase, players, myHand, selectedCards,
    bottomCards, lastPlay, currentTurn, turnTimeout, multiplier,
    landlord, settlement, errorMsg, isMyTurn,
    toggleCard, clearSelection, updateFromRoomState, reset,
  }
})

import { usePlayerStore } from './playerStore'
```

- [ ] **Step 3: 实现 WebSocket Composable**

```typescript
// frontend/src/composables/useGameWebSocket.ts
import { ref } from 'vue'
import { useGameStore } from '@/stores/gameStore'
import { usePlayerStore } from '@/stores/playerStore'

export function useGameWebSocket() {
  const isConnected = ref(false)
  let ws: WebSocket | null = null
  let reconnectAttempt = 0
  let reconnectTimer: number | null = null

  function connect() {
    const playerStore = usePlayerStore()
    const host = window.location.host
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const url = `${protocol}//${host}/ws/game/${playerStore.playerId}`
    ws = new WebSocket(url)

    ws.onopen = () => {
      isConnected.value = true
      reconnectAttempt = 0
      const gameStore = useGameStore()
      gameStore.wsConnected = true
    }

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data)
      handleEvent(data)
    }

    ws.onclose = () => {
      isConnected.value = false
      const gameStore = useGameStore()
      gameStore.wsConnected = false
      scheduleReconnect()
    }

    ws.onerror = (err) => {
      console.error('WebSocket error:', err)
    }
  }

  function disconnect() {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    if (ws) {
      ws.close()
      ws = null
    }
    isConnected.value = false
  }

  function scheduleReconnect() {
    reconnectAttempt++
    const delay = Math.min(1000 * Math.pow(2, reconnectAttempt), 30000)
    reconnectTimer = window.setTimeout(() => connect(), delay)
  }

  function sendAction(action: Record<string, any>) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(action))
    }
  }

  function handleEvent(data: any) {
    const gameStore = useGameStore()
    const event = data.event

    switch (event) {
      case 'match_waiting':
        gameStore.gamePhase = 'MATCHING'
        break
      case 'match_success':
        gameStore.roomId = data.room_id
        break
      case 'match_cancelled':
        gameStore.gamePhase = 'IDLE'
        break
      case 'game_start':
        gameStore.gamePhase = 'CALLING'
        gameStore.myHand = data.hand
        gameStore.currentTurn = data.current_turn
        if (data.players) {
          gameStore.players = data.players.map((p: any) => ({
            id: p.id, nickname: p.nickname, isAi: p.is_ai,
            isOnline: p.is_online, remaining: p.remaining,
            isLandlord: false, isSelf: p.is_self,
          }))
        }
        break
      case 'call_made':
      case 'call_skipped':
      case 'landlord_decided':
      case 'redeal':
      case 'cards_played':
      case 'turn_passed':
      case 'game_over':
        if (data.room_state) {
          gameStore.updateFromRoomState(data.room_state)
        }
        if (event === 'landlord_decided') {
          gameStore.gamePhase = 'PLAYING'
          gameStore.landlord = data.landlord
          gameStore.bottomCards = data.bottom_cards || []
          gameStore.multiplier = data.multiplier || 1
        }
        if (event === 'game_over') {
          gameStore.gamePhase = 'SETTLING'
          gameStore.settlement = {
            winner: data.winner,
            winnerSide: data.winner_side,
            scores: data.scores,
            multiplier: data.multiplier,
          }
        }
        break
      case 'reconnected':
        gameStore.updateFromRoomState(data)
        break
      case 'error':
        gameStore.errorMsg = data.msg || '未知错误'
        break
    }
  }

  return { isConnected, connect, disconnect, sendAction }
}
```

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "feat(frontend): 新增 WebSocket composable、Pinia store 和扑克牌工具"
```

---

### Task 13: 前端核心组件 — PokerCard & HandCards

**Files:**
- Create: `frontend/src/components/PokerCard.vue`
- Create: `frontend/src/components/HandCards.vue`
- Create: `frontend/src/assets/main.css` (游戏主题样式)

**Interfaces:**
- Consumes: `cardUtils.getCardDisplay()`
- Produces: `<PokerCard>`, `<HandCards>` Vue 组件

- [ ] **Step 1: 实现游戏主题 CSS**

创建 `frontend/src/assets/game.css`，包含牌桌、扑克牌等核心视觉样式。

- [ ] **Step 2: 实现 PokerCard 组件**

`<PokerCard :card-id="0" :selected="false" :face-down="false" size="md" />`

使用纯 CSS 绘制牌面：白色圆角矩形 + 左上角点数 + 花色符号，红色(♥♦) / 黑色(♠♣)。选中时 `transform: translateY(-20px)`。

- [ ] **Step 3: 实现 HandCards 组件**

`<HandCards :cards="[0,4,8,12]" @play="onPlay" />`

横向排列重叠牌组，每张露出左侧 30px。点击选中/取消。

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "feat(frontend): 新增 PokerCard 和 HandCards 核心组件"
```

---

### Task 14: 前端页面 — 登录、大厅、游戏房间

**Files:**
- Create: `frontend/src/views/LoginView.vue`
- Create: `frontend/src/views/LobbyView.vue`
- Create: `frontend/src/views/GameRoomView.vue`
- Create: `frontend/src/components/PlayerSeat.vue`
- Create: `frontend/src/components/ActionBar.vue`
- Create: `frontend/src/components/SettlementModal.vue`
- Create: `frontend/src/components/GameBoard.vue`
- Modify: `frontend/src/router/index.ts`

**Interfaces:**
- Consumes: 所有前置组件、composables、stores
- Produces: 完整的 3 个可导航页面

- [ ] **Step 1: 配置 Vue Router**

```typescript
// frontend/src/router/index.ts
import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/login' },
    { path: '/login', name: 'Login', component: () => import('@/views/LoginView.vue') },
    { path: '/lobby', name: 'Lobby', component: () => import('@/views/LobbyView.vue') },
    { path: '/game/:roomId?', name: 'Game', component: () => import('@/views/GameRoomView.vue') },
  ],
})

export default router
```

- [ ] **Step 2: 实现 LoginView**

简约的深色主题登录页：一个昵称输入框 + "进入大厅"按钮。

- [ ] **Step 3: 实现 LobbyView**

显示玩家信息卡片（昵称、欢乐豆、胜率）+ 大号"开始匹配"按钮 + 排行榜列表。

- [ ] **Step 4: 实现 GameBoard + PlayerSeat + ActionBar**

GameBoard: 深绿色牌桌背景 (100vw × 100vh)。三个 PlayerSeat (底部/左侧/右侧)。ActionBar 根据 gamePhase 切换叫地主/出牌按钮。

- [ ] **Step 5: 实现 GameRoomView**

整合 GameBoard + HandCards + ActionBar + SettlementModal，连接 WebSocket composable 和 gameStore，实现完整的游戏交互流程。

- [ ] **Step 6: 实现 SettlementModal**

游戏结束后弹出的结算弹窗：显示胜负、倍数、各玩家得分变化，"返回大厅"按钮。

- [ ] **Step 7: 验证前端完整流程**

```bash
cd d:\Project_2023\hmp_ws_service\frontend
npm run dev
```

同时启动后端：

```bash
cd d:\Project_2023\hmp_ws_service\backend
python main.py
```

在浏览器中访问 `http://localhost:5173`，完成一局完整的斗地主游戏流程。

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "feat(frontend): 完成游戏大厅、游戏房间页面与结算弹窗"
```

---

### Task 15: 端到端集成验证与文档更新

**Files:**
- Modify: `README.md` (根目录更新)
- Modify: `backend/README.md` (后端说明)

**Interfaces:**
- Consumes: 全部前后端代码
- Produces: 通过端到端测试验证的完整游戏功能

- [ ] **Step 1: 运行后端全量测试**

```bash
cd d:\Project_2023\hmp_ws_service\backend
python -m pytest tests/ -v
```

Expected: 全部 PASS

- [ ] **Step 2: 运行前端单元测试**

```bash
cd d:\Project_2023\hmp_ws_service\frontend
npm run test:unit
```

- [ ] **Step 3: 端到端手动验证**

启动后端和前端，在浏览器中完成以下流程：

1. 打开 `http://localhost:5173`，输入昵称进入大厅
2. 点击"开始匹配"，等待 AI 填充
3. 完成叫地主流程
4. 出牌交互，观察 AI 自动出牌
5. 游戏结束，查看结算弹窗
6. 返回大厅，确认欢乐豆变化

- [ ] **Step 4: 更新根目录 README.md**

补充完整的项目说明、启动方式和功能特性列表。

- [ ] **Step 5: Final Commit**

```bash
git add -A
git commit -m "feat: 欢乐斗地主功能开发完成 - 端到端集成验证通过"
```
