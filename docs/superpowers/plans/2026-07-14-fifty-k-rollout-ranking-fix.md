# 510K Rollout 排序稳定性修复实施计划

> **执行约束：** 本计划由当前智能体在本会话内按测试驱动方式执行；遵守仓库 `AGENTS.md`，用户人工确认前不执行 Git 提交。

**目标：** 修复 rollout 阶段正式胜率从 30% 降至 18% 的问题，防止终局绝对值回归破坏 teacher 已学会的候选动作排序。

**方案：** 保持现有单输出模型、训练产物和线上推理接口不变。rollout 只学习候选动作终局结果的两两相对顺序，训练总损失继续保留完整规则排序；在正式检查点前使用固定牌局一致率保护，低于安全线时恢复最佳 teacher 权重并清空优化器动量。

**技术栈：** Python、PyTorch、pytest。

## 全局约束

- 不修改经典和不洗牌 DouZero 路径。
- 不修改前后端 WebSocket 协议。
- 不删除用户训练产物，不执行 Git 提交。
- 只运行 510K 训练与模型定向测试。

---

### 任务一：用失败测试锁定 rollout 排序目标

**文件：**

- 修改：`backend/tests/test_fifty_k_training.py`
- 修改：`backend/app/training/fifty_k/trainer.py`

- [x] 增加测试：同一候选顺序的 rollout 损失不受终局奖励绝对数值尺度影响。
- [x] 运行测试并确认当前绝对值回归实现失败。
- [x] 将 rollout 损失改为忽略同值候选的两两排序损失。
- [x] 将 teacher 保留权重默认值从 `0.15` 调整为 `1.0`。
- [x] 运行测试并确认通过。

### 任务二：增加 rollout 一致率安全保护

**文件：**

- 修改：`backend/tests/test_fifty_k_training.py`
- 修改：`backend/app/training/fifty_k/trainer.py`

- [x] 增加测试：rollout 固定牌局一致率低于 75% 时恢复最佳 teacher 权重。
- [x] 运行测试并确认当前实现失败。
- [x] 在 rollout 检查点前执行固定牌局一致率评测，触发保护时恢复权重并重建 Adam 优化器。
- [x] 跳过 teacher 阶段已错过的正式胜率检查点，避免 rollout 开始后集中补测旧检查点。
- [x] 运行测试并确认通过。

### 任务三：日志、文档与定向验证

**文件：**

- 修改：`backend/app/training/fifty_k/trainer.py`
- 修改：`README.md`

- [x] 将训练胜率明确标记为“带探索训练胜率”。
- [x] 将“模拟价值损失”改为“模拟排序损失”。
- [x] 在 README 说明 rollout 排序损失、一致率保护和相关参数。
- [x] 运行 `backend/tests/test_fifty_k_training.py` 与 `backend/tests/test_fifty_k_model.py`。
- [x] 检查残留 pytest 进程、`git diff --check` 和本次差异范围。
