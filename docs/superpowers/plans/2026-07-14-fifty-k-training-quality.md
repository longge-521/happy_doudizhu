# 510K 训练质量优化实施计划

> **执行方式：** 当前会话内按测试驱动逐项实施，不创建提交。

**目标：** 让 510K 训练持续对规则 AI 产生可衡量的提升，并只保留评测最优权重。

**架构：** 训练器在自博弈时混入固定规则 AI，并将每局奖励转换为相对本局平均奖励；每个检查点以固定随机种子评测模型，仅当指标优于当前最佳时保存内存中的最佳权重，训练结束后将该权重写入模型产物。

**技术栈：** Python、PyTorch、现有 `FiftyKSelfPlayEnv`、现有规则 AI。

## 全局约束

- 继续使用 `D:\ProgramData\miniconda3\envs\hmp_ai\python.exe`。
- 不修改经典和不洗牌的 DouZero 路径。
- 训练权重与日志不提交 Git。
- 只有非法动作率为 0、胜率不少于 40%、平均得分差不小于 0 的权重可以线上加载。

### 任务 1：规则对手和相对奖励

**文件：**

- 修改：`backend/app/training/fifty_k/trainer.py`
- 测试：`backend/tests/test_fifty_k_training.py`

- [ ] 先新增失败测试，证明指定座位可以由规则 AI 行动，且一局三个玩家的归一化训练目标之和为 0。
- [ ] 为 `_collect_episode` 增加 `rule_player_ids` 参数；这些座位使用 `_rank_fifty_k_rule_actions`，其他座位按模型或探索动作行动。
- [ ] 将终局奖励减去该局三个奖励的平均值后再作为训练目标，保留赢家优先的原始奖励定义。
- [ ] 运行定向测试。

### 任务 2：检查点评测与最优权重

**文件：**

- 修改：`backend/app/training/fifty_k/trainer.py`
- 测试：`backend/tests/test_fifty_k_training.py`

- [ ] 先新增失败测试，证明训练中多个检查点只保留评测较优的权重。
- [ ] 为 `TrainingConfig` 增加 `checkpoint_interval` 和 `rule_opponent_ratio`；默认每 2,000 局评测一次，至少一名对手按规则 AI 行动。
- [ ] 以胜率、平均得分差、非法率的字典序比较评测结果；训练结束返回最佳检查点权重。
- [ ] 运行定向测试。

### 任务 3：探索衰减、命令参数和说明

**文件：**

- 修改：`backend/app/training/fifty_k/trainer.py`
- 修改：`README.md`
- 测试：`backend/tests/test_fifty_k_training.py`

- [ ] 先新增失败测试，证明探索率从初始值线性衰减至最低值。
- [ ] 新增 `--checkpoint-interval`、`--rule-opponent-ratio`、`--min-exploration-rate` 参数；日志输出当前探索率和最佳检查点评测。
- [ ] 更新 README 的推荐命令与指标解释。
- [ ] 运行训练测试、510K 规则测试和模型冒烟评测。
