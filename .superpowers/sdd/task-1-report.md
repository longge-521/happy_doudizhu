# Task 1 报告：后端 AI 策略层提供 DouZero 候选排序

## 1. 我实现了什么

本次仅修改了任务限定的两个代码文件：

- `backend/app/domain/game/ai_strategy.py`
- `backend/tests/test_ai_strategy.py`

实现内容如下：

1. 在 AI 策略层新增 `ai_rank_play_candidates(hand, last_play, must_play, ctx, limit=12)`。
2. 新增 `_dedupe_candidates()`，用于对候选出牌去重。
3. 新增 `_rule_decide_play()`，把原有规则引擎决策和“冲刺直接出完”逻辑收拢为独立兜底路径。
4. 调整 `ai_decide_play()`，改为优先消费 `ai_rank_play_candidates(..., limit=1)` 的第一候选；若无结果，再走 `_rule_decide_play()`。
5. 补充 DouZero 不可用时的规则兜底测试。
6. 修复了当前工作区内 `ai_strategy.py` 已存在的编码损坏/导入失败问题，使任务代码可被正常导入和验证。

## 2. TDD red/green 证据

说明：brief 预期的 red 是 “无法导入 `ai_rank_play_candidates`”。但我接手当前工作区时，这两个目标文件里已经存在部分 Task 1 改动，同时 `ai_strategy.py` 被错误编码写坏，导致实际 red 更早发生在模块导入阶段。以下按真实工作区状态记录。

### Red

命令：

```powershell
D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest backend/tests/test_ai_strategy.py::test_ai_rank_play_candidates_orders_by_douzero_score -q
```

结果：

```text
ERROR collecting backend/tests/test_ai_strategy.py
SyntaxError: invalid non-printable character U+E1EE
```

结论：

- 失败已被稳定复现。
- 根因不是断言失败，而是 `backend/app/domain/game/ai_strategy.py` 存在编码损坏，导致测试文件导入失败。

### Green 1：排序测试通过

命令：

```powershell
D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest backend/tests/test_ai_strategy.py::test_ai_rank_play_candidates_orders_by_douzero_score -q
```

结果：

```text
.                                                                        [100%]
1 passed in 13.67s
```

### Green 2：兜底测试通过

命令：

```powershell
D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest backend/tests/test_ai_strategy.py::test_ai_rank_play_candidates_falls_back_to_rule_engine_when_douzero_unavailable -q
```

结果：

```text
.                                                                        [100%]
1 passed in 15.72s
```

## 3. 测试运行与结果

全量 AI 策略测试命令：

```powershell
D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest backend/tests/test_ai_strategy.py -q
```

结果：

```text
.......................                                                  [100%]
23 passed in 16.08s
```

## 4. 变更文件

- `backend/app/domain/game/ai_strategy.py`
- `backend/tests/test_ai_strategy.py`

## 5. 自查结论

自查项：

1. 变更范围是否受控：是，仅落在任务允许的两个代码文件内。
2. DouZero 排序是否为主路径：是，`ai_decide_play()` 现在优先读取 `ai_rank_play_candidates(..., limit=1)`。
3. 旧规则是否只作为异常兜底：是，DouZero 不可用、报错或无候选时才回退 `_rule_decide_play()`。
4. 是否保留后续任务所需边界：是，本任务只做候选排序，不触碰 app service / WebSocket / 前端。
5. 是否完成验证：是，新增定点测试与整份 `test_ai_strategy.py` 均通过。

## 6. concerns

1. 当前工作区的 red 与 brief 中“预期 import 缺失”不一致，因为我接手时目标文件已经含有部分 Task 1 改动，但同时带入了编码损坏；我按真实状态修复并保留了任务要求的最终行为。
2. `git diff --stat` 显示 `ai_strategy.py` 变更量较大，主要原因是修复了同一目标文件中已经存在的损坏内容并将 Task 1 改动重建到健康基线上，不涉及任务外文件。
