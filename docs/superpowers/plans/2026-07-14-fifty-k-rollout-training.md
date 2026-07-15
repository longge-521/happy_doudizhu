# 510K 候选动作模拟训练实施计划

> **执行要求：** 在当前会话内按测试先行逐项实施；不提交 Git，等待用户人工验证后再决定提交。

**目标：** 让 510K 模型在达到规则动作一致率门槛后，使用候选动作残局模拟学习可归因的动作价值。

**架构：** `trainer.py` 负责完整排序样本、规则一致率门禁、局面复制模拟和两阶段训练；`environment.py` 保持规则执行入口；测试覆盖排序、复制、门禁和 Windows 双进程路径。

**技术：** Python 3、PyTorch、pytest、Windows `ProcessPoolExecutor`。

## 约束

- 模型推理输入不增加对手隐藏手牌。
- 每局最多一个模拟状态，每状态最多 4 个候选。
- 上线门槛保持胜率不少于 40%、得分差不低于 0、非法率为 0。
- README 必须同步训练阶段、参数和日志字段。

---

### 任务 1：完整规则排序和一致率

**文件：** `backend/app/training/fifty_k/trainer.py`、`backend/tests/test_fifty_k_training.py`

- [ ] 先写失败测试，要求规则样本包含全部候选索引排序。
- [ ] 先写失败测试，要求完整排序正确时损失更低，并能计算 Top-1 一致率。
- [ ] 扩展 `TeacherExample`，实现完整排序损失和固定规则轨迹一致率评测。
- [ ] 运行定向测试并确认转绿。

### 任务 2：候选动作残局模拟

**文件：** `backend/app/training/fifty_k/trainer.py`、`backend/tests/test_fifty_k_training.py`

- [ ] 先写失败测试，复制局面模拟不得修改原房间，并返回有限目标值。
- [ ] 新增 `RolloutExample`，每局只采集一个状态、最多 4 个规则靠前候选。
- [ ] 使用模拟价值损失替换整局共享终局回报损失。
- [ ] 运行采样和损失定向测试。

### 任务 3：门禁、日志、命令和文档

**文件：** `backend/app/training/fifty_k/trainer.py`、`backend/tests/test_fifty_k_training.py`、`README.md`

- [ ] 增加 85% Top-1 一致率门禁，未达标时持续规则训练。
- [ ] 日志显示批次一致率、固定验证一致率以及 `teacher/rollout` 阶段。
- [ ] 增加规则一致率、验证局数和模拟候选数命令行参数。
- [ ] 更新 README，并运行训练与模型定向测试、双进程冒烟、diff 检查和残留进程检查。
