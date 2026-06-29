# 斗地主 AI 机器人智能出牌策略设计规格

> 日期: 2026-06-24
> 状态: 待实施

## 1. 背景与问题

当前 AI 机器人（[ai_strategy.py](file:///d:/Project_2023/hmp_ws_service/backend/app/domain/game/ai_strategy.py)）存在以下严重缺陷：

1. **首发只出单张**：`_find_all_plays` 枚举时虽包含对子/三张，但 `ai_decide_play` 在自由出牌时强制筛选 `CardType.SINGLE`，导致永远拆牌出最小单张
2. **无手牌拆解能力**：不理解手牌结构（如顺子、连对），无法制定出牌路线
3. **无角色意识**：不区分地主/农民身份，不知道该攻该守
4. **无农民合作**：不判断上家是队友还是地主，队友出牌也一律压制

## 2. 设计目标

重写 `ai_strategy.py`，实现一个具备中等玩家水平的规则引擎 AI，核心能力：

- ✅ 手牌最优拆解（最少手数）
- ✅ 基于角色的差异化出牌策略（地主/顶牌位/跑牌位）
- ✅ 农民合作与让牌机制
- ✅ 不拆牌保护（跟牌时只用同类型整牌）
- ✅ 智能炸弹使用时机

## 3. 架构设计

### 3.1 模块结构

```
backend/app/domain/game/ai_strategy.py  ← 唯一需要重写的文件
```

重写后的模块包含以下函数层次：

```
ai_decide_call(hand)                    ← 叫地主决策（保留现有逻辑）
ai_decide_play(hand, last_play,         ← 出牌决策入口（签名变更）
               must_play, ctx)

  ├── _get_seat_context(room, ai_id)    ← 座位与角色上下文提取
  ├── _decompose_hand(hand)             ← 手牌最优拆解
  ├── _pick_lead_play(plan, role, ctx)  ← 主动出牌选择
  ├── _pick_follow_play(hand, plan,     ← 被动跟牌选择
  │       last_play, role, ctx)
  └── _should_use_bomb(hand, plan, ctx) ← 炸弹使用判定
```

### 3.2 调用方变更

[game_app_service.py](file:///d:/Project_2023/hmp_ws_service/backend/app/application/game/game_app_service.py) 中 `handle_ai_turn` 需传递更多上下文给 `ai_decide_play`：

```python
# 变更前
cards = ai_decide_play(hand, last_cp, must_play)

# 变更后
ctx = build_ai_context(room, ai_id)
cards = ai_decide_play(hand, last_cp, must_play, ctx)
```

## 4. 详细设计

### 4.1 AI 上下文数据结构

```python
@dataclass
class AIContext:
    ai_id: str                  # 当前 AI 的玩家 ID
    role: str                   # 'landlord' | 'landlord_up' | 'landlord_down'
    landlord_id: str            # 地主玩家 ID
    teammate_id: Optional[str]  # 队友 ID（地主为 None）
    landlord_remaining: int     # 地主剩余手牌数
    teammate_remaining: int     # 队友剩余手牌数（地主为 0）
    last_play_from: Optional[str]  # 上一次出牌的玩家 ID
    is_last_play_teammate: bool    # 上一次出牌是否来自队友
    is_last_play_landlord: bool    # 上一次出牌是否来自地主
```

**座位角色判定逻辑**（3人固定出牌顺序 A→B→C→A）：
- 地主的**上家**（出牌顺序在地主之前）= 顶牌位 `landlord_up`
- 地主的**下家**（出牌顺序在地主之后）= 跑牌位 `landlord_down`

### 4.2 手牌最优拆解算法

```python
@dataclass
class HandPlan:
    plays: List[CardPlay]     # 拆解出的常规牌型列表
    hand_count: int           # 总手数（不含炸弹）
    bombs: List[CardPlay]     # 保留的炸弹/王炸
```

**DFS 拆解流程：**

```
decompose_hand(rank_counts):
    1. 提取并保留所有炸弹（4张同rank）和王炸 → bombs
    2. 从剩余牌中，按优先级尝试提取牌型：
       a. 顺子（≥5张连续，rank < 12即不含2）
       b. 连对（≥3对连续）
       c. 飞机（≥2组连续三张）
       d. 三带二 / 三带一（三张 + 配对/配单）
       e. 对子
       f. 单张
    3. DFS 递归尝试不同提取顺序
    4. 返回手数最少的方案
    
    剪枝策略：
    - 若当前方案手数已 ≥ 已知最优，剪枝
    - 优先尝试长连牌（顺子、连对），因为拆解价值最高
```

### 4.3 主动出牌策略（首发 / 新一轮开始）

```
pick_lead_play(plan, role, ctx):

  所有角色通用 — 冲刺模式：
    手牌 ≤5 张 → 直接出能一次或两次出完的最优牌型

  地主策略：
    从 plan.plays 中选择最小的独立牌型打出
    优先级：单张 → 对子 → 三带 → 顺子/连对

  地主上家（顶牌位）策略：
    地主剩余 ≤3 张 → 出最大的牌抢控制权
    正常阶段 → 出中偏大的牌（主rank ≥ 7 即10以上）
    目的：逼迫地主跟大牌，消耗地主资源
    若手中没有大牌 → 出最小的牌型

  地主下家（跑牌位）策略：
    与地主策略类似，快速跑牌
    从 plan.plays 中选择最小的独立牌型打出
    当队友手牌 ≤2 时 → 出大牌抢牌权，然后出小牌送队友
```

### 4.4 被动跟牌策略（需压过上家）

```
pick_follow_play(hand, plan, last_play, role, ctx):

  上家是地主 → 防守压制模式：
    1. 在 plan.plays 中查找同类型、能压过的最小整牌
       （不拆牌：压单用单，压对用对，压三用三）
    2. 地主剩余 ≤5 张 → 必须压（有什么压什么）
    3. 地主出小牌（rank ≤ 8） → 用最小能压过的牌压
    4. 地主出大牌（rank ≥ 9）：
       - 压牌代价 ≤ A → 压
       - 需要用 2 或王 → 仅在地主剩余 ≤5 张时压
    5. 没有同类型整牌 → 考虑炸弹（见4.5）
    6. 紧急拆牌：地主剩余 ≤3 张且无同类型整牌
       → 允许拆对子出单张顶牌
    7. 以上都不满足 → 不出

  上家是农民队友 → 配合放行模式：
    1. 默认不出（放行）
    2. 例外——接管牌权条件（全部满足才接）：
       a. 队友出的是小牌（rank ≤ 6，即 3~7）
       b. 我手中有不拆牌的同类型整牌（rank ≤ 10 即 K 以下）
       c. 且不是队友快出完的情况（队友剩余 > 2）
       → 用最小同类型整牌接管
    3. 自己手牌 ≤3 张，接上就能出完 → 接管
    4. 绝对红线：
       - 永远不拆牌压队友
       - 永远不炸队友（除非自己接了能直接赢）
```

### 4.5 炸弹使用策略

```
should_use_bomb(hand, plan, ctx):

  使用炸弹的条件（满足任一即可）：
    1. 地主剩余 ≤3 张 → 必须炸，抢回牌权封堵
    2. 自己手牌 ≤5 张，炸完后剩余牌能一手出完 → 炸
    3. 队友手牌 ≤2 张，炸完后出小牌送队友赢 → 炸

  保留炸弹的条件：
    - 以上条件都不满足 → 保留
```

## 5. 修改文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| [ai_strategy.py](file:///d:/Project_2023/hmp_ws_service/backend/app/domain/game/ai_strategy.py) | 重写 | AI 核心策略全部重写，保留 `ai_decide_call` |
| [game_app_service.py](file:///d:/Project_2023/hmp_ws_service/backend/app/application/game/game_app_service.py) | 修改 | `handle_ai_turn` 中构建 `AIContext` 并传递给新接口 |
| [test_ai_strategy.py](file:///d:/Project_2023/hmp_ws_service/backend/tests/test_ai_strategy.py) | 更新 | 适配新接口签名，增加角色策略和农民合作的测试用例 |

## 6. 验证计划

### 自动化测试
```bash
cd backend && python -m pytest tests/test_ai_strategy.py -v
```

测试用例覆盖：
1. **拆解测试**：验证连对、顺子、飞机等组合牌不会被拆散
2. **首发测试**：验证 AI 首发出最小整牌（非单纯单张）
3. **角色测试**：验证地主上家出中大牌、地主下家出小牌
4. **让牌测试**：验证农民不压队友的牌（除非小牌接管）
5. **不拆牌测试**：验证跟牌时不拆对子压单张
6. **炸弹测试**：验证炸弹仅在紧急时使用

### 手动验证
- 开启游戏，观察 AI 是否出对子、顺子等复合牌型
- 作为农民观察 AI 队友是否放行你的牌
- 观察 AI 是否在地主快出完时紧急用大牌/炸弹封堵
