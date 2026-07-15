# 510K 立即下家听牌阻断 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 510K 中立即下家仅剩一张时，当前机器人可能不出或用过小单牌而放走对手的问题。

**Architecture:** 在模型排序之后增加只依赖公开信息的即时输局安全门禁。门禁从全部合法动作中选出保证阻断或最大概率阻断动作，并在命中时跳过随机残局搜索；其他牌局继续使用现有模型、规则和搜索链路。

**Tech Stack:** Python 3.10、PyTorch 推理管理器、pytest、现有 510K 牌型与合法动作生成器。

## Global Constraints

- 不读取对手隐藏手牌，只使用 `AIContext.player_ids`、`player_remaining`、`unseen_cards`、当前手牌和桌面牌型。
- 不修改 `model.pt`、特征版本或网络结构，不重新训练。
- 不影响经典与不洗牌玩法。
- 不执行 Git commit；完成后更新根目录 `README.md`。

---

### Task 1: 用集成测试复现模型放走立即下家的问题

**Files:**
- Modify: `backend/tests/test_fifty_k_model.py`

**Interfaces:**
- Consumes: `ai_rank_play_candidates(hand, last_play, must_play, ctx, room=room)`
- Produces: 模型把 pass/小单排前时仍必须阻断的回归测试。

- [ ] **Step 1: Write the failing test**

构造玩家顺序 `p1 -> p2 -> p3`：当前 AI 为 `p1`，立即下家 `p2` 剩一张，上家 `p3` 已出单 4；mock 模型顺序为 pass、小单、最大单，断言最终 Top-1 是最大安全单张。

- [ ] **Step 2: Run test to verify it fails**

Run: `D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest backend/tests/test_fifty_k_model.py -k immediate_next -q`

Expected: FAIL，当前 Top-1 仍为模型给出的 pass 或小单。

- [ ] **Step 3: 保留失败证据后进入 Task 2**

记录实际 Top-1 与预期动作，确认失败来自模型排序缺少战术门禁，而不是测试数据非法。

### Task 2: 实现公开信息即时阻断门禁

**Files:**
- Modify: `backend/app/domain/game/ai_strategy.py`
- Test: `backend/tests/test_fifty_k_model.py`
- Test: `backend/tests/test_fifty_k_tactics.py`

**Interfaces:**
- Produces: `_choose_immediate_next_player_block(hand, legal_actions, ranked_actions, last_play, ctx) -> Optional[List[int]]`
- Consumes: `CardType.SINGLE`、`detect_card_type`、`ctx.player_ids`、`ctx.player_remaining`、`ctx.unseen_cards`。

- [ ] **Step 1: Implement the minimal helper**

helper 先按相对座次确定立即下家；只有该玩家剩一张且桌面为单张时运行。直接出完动作优先；其次选择不会被一张牌压制的最高单张；若公开未见牌仍可能压制，则选择最低成本合法特殊牌；不存在特殊牌时选择最大合法单张；无响应返回 `None`。

- [ ] **Step 2: Integrate without allowing search to overwrite it**

在 510K 全部合法动作生成且模型排序完成后调用 helper。命中时把动作置为 Top-1 并跳过 `choose_fifty_k_endgame_action`；未命中保持原链路。

- [ ] **Step 3: Run the failing test and verify GREEN**

Run: `D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest backend/tests/test_fifty_k_model.py -k immediate_next -q`

Expected: PASS。

- [ ] **Step 4: Add tactical boundary tests**

在 `test_fifty_k_tactics.py` 覆盖：仅特殊牌可保证阻断、没有合法响应允许 pass、多张桌面牌型不误触发、听牌者不是立即下家不误触发、直接跑完优先。

- [ ] **Step 5: Run tactical tests**

Run: `D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest backend/tests/test_fifty_k_tactics.py backend/tests/test_fifty_k_model.py backend/tests/test_fifty_k_search.py -q`

Expected: 全部 PASS，且无 PyTorch/残局搜索警告。

### Task 3: 回归与文档

**Files:**
- Modify: `README.md`

**Interfaces:**
- Produces: 510K 推理安全门禁说明与无需重训说明。

- [ ] **Step 1: Update README**

记录触发条件、公开信息边界、模型与规则 AI 均受保护、无需重训以及后续训练集应包含该场景。

- [ ] **Step 2: Run broader 510K regression**

Run: `D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest backend/tests/test_fifty_k.py backend/tests/test_fifty_k_tactics.py backend/tests/test_fifty_k_model.py backend/tests/test_fifty_k_search.py backend/tests/test_fifty_k_training.py -q`

Expected: 全部 PASS。

- [ ] **Step 3: Review diff**

Run: `git diff -- backend/app/domain/game/ai_strategy.py backend/tests/test_fifty_k_model.py backend/tests/test_fifty_k_tactics.py README.md docs/superpowers/specs/2026-07-15-fifty-k-immediate-next-player-block-design.md docs/superpowers/plans/2026-07-15-fifty-k-immediate-next-player-block.md`

Expected: 只有本次战术门禁、测试和文档变化，无权重、训练参数或无关格式化变化。
