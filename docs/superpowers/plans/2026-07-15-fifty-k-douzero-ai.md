# 510K DouZero 式 AI 优化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 510K 生产决策评估全部合法动作，修复三带与四带机会成本，并将训练器改成三席共享模型的终局回报深度蒙特卡洛训练。

**Architecture:** 牌型引擎只枚举合法动作，规则 AI 作为确定性降级，已验收模型对全部候选评分。训练时 Actor 记录实际轨迹，终局后为每个状态动作赋予玩家自己的终局回报，Learner 用 MSE 更新共享动作价值网络。

**Tech Stack:** Python 3.10、PyTorch、pytest、项目现有 GameRoom 与 510K 自博弈环境。

## Global Constraints

- 保留 K=20、总分140和现有510K压制顺序。
- 三带一、三带一对、四带二单、四带二对继续合法。
- 只使用公开信息，不读取真实对手手牌。
- 使用 `D:\ProgramData\miniconda3\envs\hmp_ai\python.exe`。
- 本轮不执行 Git 提交；完成后更新根目录 `README.md`。

---

### Task 1: 固定战术回归测试

**Files:**
- Modify: `backend/tests/test_fifty_k.py`
- Modify: `backend/tests/test_fifty_k_model.py`

**Interfaces:**
- Consumes: `ai_rank_play_candidates`、`generate_legal_actions_dz`
- Produces: 三带翅膀、四带二、全候选模型排序的行为契约

- [ ] 写入失败测试：`3/10/2` 正常首出 3。
- [ ] 写入失败测试：三条、小单和大对子同时存在时优先三带小单。
- [ ] 写入失败测试：四个 K 和两个大对子同时存在时不得首选四带二对。
- [ ] 写入通过性测试：四带二可以直接跑完时仍然合法且可选。
- [ ] 写入失败测试：模型收到全部合法动作而不是规则前 4 个。
- [ ] 运行：`D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest tests\test_fifty_k.py tests\test_fifty_k_model.py -q`，确认新增用例失败且既有用例状态可解释。

### Task 2: 修正规则降级和生产模型候选

**Files:**
- Modify: `backend/app/domain/game/ai_strategy.py`
- Modify: `backend/app/domain/game/fifty_k_search.py`

**Interfaces:**
- Produces: `_rank_fifty_k_rule_actions(...) -> List[List[int]]` 对全部合法动作的稳定排序
- Produces: `ai_rank_play_candidates(...)` 将全部合法动作交给模型

- [ ] 增加动作后手牌结构评估，计算预计剩余手数和拆牌成本。
- [ ] 三带动作比较翅膀机会成本，优先小单而不是完整大对子。
- [ ] 四带二计入拆普通炸弹成本；直接出完保留最高优先级。
- [ ] 删除规则前 4 候选对生产模型的限制，模型评分全部合法候选。
- [ ] 关闭当前会绕过模型的生产残局搜索覆盖，保留模块供独立实验。
- [ ] 运行 Task 1 定向测试并确认通过。

### Task 3: `public_state_v3` 与历史 LSTM

**Files:**
- Modify: `backend/app/domain/game/fifty_k_model.py`
- Modify: `backend/app/domain/game/ai_strategy.py`
- Modify: `backend/tests/test_fifty_k_model.py`

**Interfaces:**
- Produces: `build_fifty_k_features(...)` 的 v3 状态/动作张量
- Produces: `FiftyKActionValueModel.forward(features, history)` 的动作价值

- [ ] 先写失败测试，验证最近15次动作、不出玩家、动作前后预计手数和拆炸弹标记被编码。
- [ ] 将清单特征版本更新为 `public_state_v3`，旧权重必须明确拒载。
- [ ] 增加历史动作 LSTM 编码和状态动作 MLP，保持三席共享网络。
- [ ] 更新批量推理，使全部合法候选共享同一段历史编码。
- [ ] 运行 `tests/test_fifty_k_model.py` 并确认通过。

### Task 4: 终局回报 DMC 自博弈

**Files:**
- Modify: `backend/app/training/fifty_k/trainer.py`
- Modify: `backend/app/training/fifty_k/environment.py`
- Modify: `backend/tests/test_fifty_k_training.py`

**Interfaces:**
- Produces: `MonteCarloTransition`，包含公开特征、历史特征、动作和终局目标
- Produces: 三席模型自博弈采样与 MSE Learner

- [ ] 先写失败测试，证明一局中每次真实模型动作都获得所属玩家的终局回报。
- [ ] 采样时三席默认使用同一当前模型，规则对手比例默认改为 0。
- [ ] 删除空 `transitions=[]` 行为，收集每席完整轨迹。
- [ ] 终局后使用 `penalty_adjusted_scores` 计算相对收益并回填轨迹。
- [ ] Learner 使用 MSE 回归终局动作价值，加入梯度裁剪。
- [ ] teacher 仅保留为显式可选预热，默认关闭规则一致率门禁。
- [ ] 保持 Windows `spawn` 多进程载荷为模块顶层可序列化类型。
- [ ] 运行 `tests/test_fifty_k_training.py -q` 并确认通过。

### Task 5: 公平评测、模型产物和文档

**Files:**
- Modify: `backend/app/training/fifty_k/trainer.py`
- Modify: `backend/app/domain/game/weights/fifty_k/manifest.json`（仅在新训练通过后）
- Modify: `README.md`
- Test: `backend/tests/test_fifty_k_training.py`

**Interfaces:**
- Produces: 固定牌局三座位轮换评测指标
- Produces: 包含规则、特征、训练局数和校验值的新模型清单

- [ ] 增加同一副牌三座位轮换评测，纯模型路径不得启用旧残局搜索。
- [ ] 增加战术门禁、非法率、胜率和得分差四类指标。
- [ ] 先执行 5,000 局方向验证；门禁通过后执行 20,000 局正式训练。
- [ ] 使用不少于 3,000 局固定牌正式评测，要求胜率 >40%、得分差 >=0、非法率=0。
- [ ] 仅在门禁全部通过后写入新 `model.pt` 和 `manifest.json`。
- [ ] 更新根目录 `README.md`，记录 v3 特征、DMC训练、命令、降级与评测口径。
- [ ] 运行相关定向测试，检查不存在后台残留 pytest 进程。

