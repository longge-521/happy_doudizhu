# 510K 各自为战 AI“看分下菜”抢分与避战策略设计规格书

## 1. 目标与背景
在 510K 棋牌游戏中，得高分与跑得快同等重要。目前 AI 仅能按基本牌力管牌，无法识别桌面分值。本设计旨在为规则兜底 AI 引入“吃分意识”，实现：
- **无分避战**：桌面无分时，AI 适度保留牌力（选择过牌），让对手互咬。
- **大分抢牌**：桌面积累 $\ge 15$ 分时，AI 直接解锁 2 和王等控制牌去拿牌权。
- **高分轰炸**：桌面积累 $\ge 25$ 分时，AI 直接解锁炸弹强行收割分数。

## 2. 详细变更与逻辑设计

### 2.1 涉及文件
- [ai_strategy.py](file:///d:/Project_2023/happy_doudizhu-欢乐斗地主/backend/app/domain/game/ai_strategy.py)

---

### 2.2 上下文扩展 (`AIContext` & `build_ai_context`)
1.  在 `AIContext` 增加 `current_trick_score: int = 0` 字段。
2.  在 `build_ai_context(room, ai_id)` 中，计算当前 trick 的累积分数：
    ```python
    # 遍历当前桌面已打出的卡牌，累加 5, 10, K 的得分
    current_trick_score = 0
    if getattr(room, "current_trick_cards", None):
        current_trick_score = sum(room._get_card_score(cid) for cid in room.current_trick_cards)
    ```
    并将该值注入 `AIContext`。

---

### 2.3 被动跟牌管牌大牌分流 (`_pick_follow_play`)
在 `_pick_follow_play` 中：
1.  **无分避战**：
    若当前 `play_mode == "fifty_k"` 且 `ctx.current_trick_score == 0`，且上家出的牌较小（`last_play.main_rank <= 5`），且 AI 没有手牌警报（自己和对手手牌均 $> 5$）。
    此时，若 AI 有能管得起的小常规牌，有 **40% 的概率**（使用 `random.random() < 0.4`）选择过牌不压（`return None`），以保留小对子/小单牌，让对手互顶。
2.  **大分抢牌**：
    若 `ctx.current_trick_score >= 15`，则在考虑使用 2 或大王压制对手时，**无视手牌 <= 5 的警报限制，直接予以管牌**：
    ```python
    # 即使 smallest_match.main_rank >= 12 且没有警报，如果分值 >= 15，也允许打出
    if ctx.current_trick_score >= 15:
        return smallest_match.cards
    ```

---

### 2.4 炸弹轰炸解锁 (`_should_use_bomb`)
在 `_should_use_bomb` 逻辑中：
- 增加一重判定：如果 `ctx.play_mode == "fifty_k"` 且当前桌面累积分值 `ctx.current_trick_score >= 25`，则无视手牌剩余长度限制，**无条件返回 `True`**。
  - 这能使得 AI 在面对 25 分以上的超级分池时（如有人出了假五十K或多个分牌堆积），只要手里有比上家大的炸弹，便会直接甩出炸弹去强势收割分牌。

## 3. 验证与测试方案
- **单元测试 1**：验证当桌面有 0 分，AI 手里有小牌管得起时，AI 有一定概率会避战 Pass。
- **单元测试 2**：验证当桌面有 15 分，AI 手里只有 2 能管牌时，即使没有警报，AI 也会毫不犹豫用 2 压制。
- **单元测试 3**：验证当桌面有 25 分，AI 只有炸弹时，AI 会直接引爆炸弹进行拦截。
