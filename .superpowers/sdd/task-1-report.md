# Task 1 Report: 510K 牌型检测与压制判定

## 1. 任务概述
在牌型引擎 `card_type.py` 中新增对 510K 特殊牌型（真五十K与假五十K）的检测，并扩展其压制逻辑。

*   **修改文件**：`backend/app/domain/game/card_type.py`
*   **创建文件**：`backend/tests/test_fifty_k.py`
*   **同步修改**：`README.md`

---

## 2. 代码详细修改

### 2.1 创建测试文件 `backend/tests/test_fifty_k.py`
```python
# backend/tests/test_fifty_k.py
import pytest
from app.domain.game.card_type import detect_card_type, can_beat, CardType

def test_fifty_k_card_detection():
    # ♠5 (ID=8), ♠10 (ID=28), ♠K (ID=40)
    true_fifty_k = detect_card_type([8, 28, 40])
    assert true_fifty_k is not None
    assert true_fifty_k.card_type == CardType.FIFTY_K_TRUE

    # ♥5 (ID=9), ♦10 (ID=31), ♣K (ID=42)
    false_fifty_k = detect_card_type([9, 31, 42])
    assert false_fifty_k is not None
    assert false_fifty_k.card_type == CardType.FIFTY_K_FALSE

def test_fifty_k_can_beat():
    true_play = detect_card_type([8, 28, 40])
    false_play = detect_card_type([9, 31, 42])
    single_play = detect_card_type([0])  # 单张3
    bomb_play = detect_card_type([0, 1, 2, 3])  # 3333 炸弹

    # 验证压制关系：
    # 假510K大过单张
    assert can_beat(false_play, single_play)
    # 真510K大过假510K
    assert can_beat(true_play, false_play)
    # 炸弹大过真510K
    assert can_beat(bomb_play, true_play)
    # 假510K压不过炸弹
    assert not can_beat(false_play, bomb_play)
```

### 2.2 修改主逻辑 `backend/app/domain/game/card_type.py`
主要修改点包含：
1. 在 `CardType` 枚举中新增 `FIFTY_K_TRUE = "真五十K"` 和 `FIFTY_K_FALSE = "假五十K"`。
2. 在 `detect_card_type` 中，当牌张数 $n == 3$ 时，判断其是否点数构成为 5, 10, K（点数分别对应 5、10、K 的 `rank` 编码 2, 7, 10）。如果是同花则为 `CardType.FIFTY_K_TRUE`，否则为 `CardType.FIFTY_K_FALSE`。
3. 在 `can_beat` 中，加入 510K 相关的压制权重关系：
   - 压制链条为 `ROCKET`（王炸）> `BOMB`（炸弹）> `FIFTY_K_TRUE` > `FIFTY_K_FALSE` > 普通牌型。
   - 若两手牌同为真 510K 或同为假 510K，判定为“要不起”（返回 `False`）。

修改的具体 Diff 如下：
```diff
@@ -23,6 +23,8 @@
     ROCKET = "王炸"
     FOUR_TWO_SINGLE = "四带二单"
     FOUR_TWO_PAIR = "四带二对"
+    FIFTY_K_TRUE = "真五十K"
+    FIFTY_K_FALSE = "假五十K"


 @dataclass
@@ -70,6 +70,16 @@
     if n == 2 and set(card_ids) == {52, 53}:
         return CardPlay(CardType.ROCKET, main_rank=14, length=1, cards=card_ids)

+    # 510K 检测
+    if n == 3:
+        ranks = {Card.from_id(cid).rank for cid in card_ids}
+        if ranks == {2, 7, 10}:
+            suits = {Card.from_id(cid).suit for cid in card_ids}
+            if len(suits) == 1:
+                return CardPlay(CardType.FIFTY_K_TRUE, main_rank=0, length=1, cards=card_ids)
+            else:
+                return CardPlay(CardType.FIFTY_K_FALSE, main_rank=0, length=1, cards=card_ids)
+
     # 按出现次数分组
     count_groups = {}  # count -> [rank, ...]
     for rank, count in rank_counts.items():
@@ -190,7 +190,9 @@
     规则：
       1. 王炸压一切
       2. 炸弹压非炸弹，大炸弹压小炸弹
-      3. 相同牌型 + 相同长度 + 更大的 main_rank
+      3. 510K 相关的压制权重关系：ROCKET > BOMB > FIFTY_K_TRUE > FIFTY_K_FALSE > 普通牌型
+      4. 同为真 510K 或同为假 510K，判定为“要不起”（返回 False）
+      5. 相同牌型 + 相同长度 + 更大的 main_rank
     """
     # 王炸压一切
     if current_play.card_type == CardType.ROCKET:
@@ -197,13 +197,37 @@
     if last_play.card_type == CardType.ROCKET:
         return False

-    # 炸弹 vs 非炸弹
-    if current_play.card_type == CardType.BOMB and last_play.card_type != CardType.BOMB:
-        return True
-    if current_play.card_type != CardType.BOMB and last_play.card_type == CardType.BOMB:
-        return False
-
-    # 相同牌型比较
+    # 炸弹相关比较
+    if current_play.card_type == CardType.BOMB:
+        if last_play.card_type == CardType.BOMB:
+            if current_play.length != last_play.length:
+                return False
+            return current_play.main_rank > last_play.main_rank
+        # 炸弹压真/假510K及普通牌型
+        return True
+    if last_play.card_type == CardType.BOMB:
+        # 当前不是王炸、炸弹，肯定压不过炸弹
+        return False
+
+    # 真五十K比较
+    if current_play.card_type == CardType.FIFTY_K_TRUE:
+        if last_play.card_type == CardType.FIFTY_K_TRUE:
+            return False
+        # 真五十K压假五十K及普通牌型
+        return True
+    if last_play.card_type == CardType.FIFTY_K_TRUE:
+        return False
+
+    # 假五十K比较
+    if current_play.card_type == CardType.FIFTY_K_FALSE:
+        if last_play.card_type == CardType.FIFTY_K_FALSE:
+            return False
+        # 假五十K压普通牌型
+        return True
+    if last_play.card_type == CardType.FIFTY_K_FALSE:
+        return False
+
+    # 相同牌型比较 (针对普通牌型)
     if current_play.card_type != last_play.card_type:
         return False
     if current_play.length != last_play.length:
```

### 2.3 修改 `README.md`
将新增的 510K 牌型说明更新至系统核心功能特性和领域层中，保持说明书与代码功能同步演进。

---

## 3. 测试运行与结果

### 3.1 TDD 失败验证
在未修改 `card_type.py` 前，运行测试命令：
`D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest backend/tests/test_fifty_k.py -v`

测试输出失败日志：
```text
backend/tests/test_fifty_k.py::test_fifty_k_card_detection FAILED        [ 50%]
backend/tests/test_fifty_k.py::test_fifty_k_can_beat FAILED              [100%]

================================== FAILURES ===================================
_________________________ test_fifty_k_card_detection _________________________

    def test_fifty_k_card_detection():
        true_fifty_k = detect_card_type([8, 28, 40])
>       assert true_fifty_k is not None
E       assert None is not None

backend\tests\test_fifty_k.py:8: AssertionError
```

### 3.2 TDD 成功验证
在完成 `card_type.py` 逻辑实现后，运行测试命令：
`D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest backend/tests/test_fifty_k.py -v`

测试输出全部成功通过：
```text
backend/tests/test_fifty_k.py::test_fifty_k_card_detection PASSED        [ 50%]
backend/tests/test_fifty_k.py::test_fifty_k_can_beat PASSED              [100%]

============================== 2 passed in 0.62s ==============================
```

### 3.3 全量回归测试
为确保未造成任何牌型引擎功能回归，运行全量牌型检测单元测试：
`D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest backend/tests/test_card_type.py -v`

测试输出 23 项测试全部成功通过：
```text
backend/tests/test_card_type.py::TestDetectCardType::test_single PASSED  [  4%]
...
backend/tests/test_card_type.py::TestCanBeat::test_different_length_straight_cannot_beat PASSED [100%]

============================= 23 passed in 0.80s ==============================
```

---

## 4. 结论
开发流程严格遵循 TDD 规范，代码结构清晰，测试覆盖完备。
本项目状态：**DONE**。
