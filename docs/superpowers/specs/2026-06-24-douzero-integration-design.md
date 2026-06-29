# DouZero 强化学习 AI 集成设计规格书

本文档规定了如何将 DouZero (基于深度强化学习的斗地主 AI 模型) 集成到当前斗地主游戏服务中的具体系统设计。

## 1. 背景与目标
在标准的斗地主中，纯规则决策的 AI（Heuristic Rule Engine）容易出现合作博弈判断失误、近视决策（放水）等问题。为了实现更高棋力、合作默契的 AI，项目决定引入 DouZero 官方训练好的预训练权重，利用 PyTorch 在 CPU 环境下进行决策推理。
为确保系统稳定性，AI 会引入优雅降级设计：当缺少权重或加载失败时，自动退回到原有的规则 DFS 分解出牌逻辑。

---

## 2. 状态历史流水设计 (GamePlay History)
为了重现斗地主不完全信息博弈的动态历史局势，AI 在决策时必须依赖自发牌以来的完整出牌历史。

### Room.py 状态扩展
*   **属性新增**：
    在 `GameRoom` 类初始化时新增 `self.play_history`。
    ```python
    self.play_history: List[Dict[str, Any]] = []
    ```
*   **清空历史**：
    在发牌阶段 `deal()` 时清空：
    ```python
    self.play_history = []
    ```
*   **记录时序动作**：
    *   在出牌成功 `play_cards()` 时记录：
        ```python
        self.play_history.append({"player": player_id, "cards": card_ids})
        ```
    *   在过牌 `pass_turn()` 时记录：
        ```python
        self.play_history.append({"player": player_id, "cards": []})
        ```
*   **持久化与反序列化**：
    在 `to_dict` 和 `from_dict` 方法中新增 `play_history` 的存储映射，以保障 Redis 状态同步。

---

## 3. 神经网络结构定义 (Model Definitions)
我们需要在后端定义与官方预训练模型（`.ckpt` 权重文件）参数完全对齐的 PyTorch 网络结构。

*   **模型文件**：新建 `backend/app/domain/game/douzero_model.py`。
*   **网络定义**：
    *   **时序特征网 (LSTM)**：地主和农民均使用相同规格的 `nn.LSTM(162, 128, batch_first=True)` 抽取历史动作序列特征。
    *   **地主模型 (`LandlordLstmModel`)**：全连接首层输入为 `373 + 128`，隐藏层维度为 `512`，使用 6 层 Linear 层进行胜率估算，输出 Q 值。
    *   **农民模型 (`FarmerLstmModel`)**：全连接首层输入为 `484 + 128`，其余隐层同上。
*   **权重加载器 (`DouZeroAgentManager`)**：
    在项目启动或 AI 初始化时，尝试从本地 `backend/app/domain/game/weights/` 读取 `landlord.ckpt`、`landlord_up.ckpt` 和 `landlord_down.ckpt` 并加载至模型。如果任何文件缺失或加载报错，提供 `is_available() -> False` 作为优雅降级的前提信号。

---

## 4. 特征适配器设计 (DouZero Adapter)
适配器充当规则数据结构与张量特征（Tensor）之间的桥梁。

*   **适配器文件**：新建 `backend/app/domain/game/douzero_adapter.py`。
*   **点数翻译 (0..53 -> 3..30)**：
    *   转换映射规则：
        *   普通牌 3..A（我们的 rank 0..11）：转换为 `rank + 3`
        *   普通牌 2（我们的 rank 12）：转换为 `17`
        *   小王 (52)：转换为 `20`
        *   大王 (53)：转换为 `30`
*   **局势还原器 (`Infoset`)**：
    基于当前 `AIContext`、自己手牌 and `play_history` 流水，在内存中还原以下特征：
    *   `player_hand_cards`: AI 自身持有的牌值列表。
    *   `other_hand_cards`: 余牌集合 = `54张牌 - 自己的牌 - 已打出的牌`。
    *   `played_cards`: 每家已出牌的汇总字典。
    *   `last_move`: 桌面最后一手出牌牌值列表。
    *   `last_move_dict`: 三家各自最后一次出牌记录。
    *   `num_cards_left_dict`: 三家余牌数。
    *   `bomb_num`: 局面至今打出的炸弹数。
    *   `card_play_action_seq`: 完整出牌时序列表。
*   **特征编码拼接**：
    *   **54维单牌编码**：使用 13个点数列 (Col priority) 的 4 通道 flattened array 加上 2 维 Joker。
    *   **162维时序编码**：将一轮三个动作（各 54维）拼接。历史记录最近 15 手会被 reshape 为 `5 x 162` 矩阵输入给 LSTM。
    *   **静态特征 `x` 拼接**：
        *   地主 (373)：拼接自身手牌、他人手牌、最后一次出牌、两家农民已出牌、两家农民牌数、炸弹数、候选动作。
        *   农民 (484)：同上并增加队友农民已出牌、队友最后一次出牌、地主牌数与队友牌数特征。

---

## 5. 双轨决策与降级机制 (Fallback)
*   **决策入口**：修改 `ai_strategy.py` 中的 `ai_decide_play`。
*   **双轨选择**：
    1.  **神经网络分支**：若 `play_history` 可用且 `DouZeroAgentManager.is_available()` 为 `True`，则进入神经网络推理。在局势生成的“所有绝对合法的出牌动作”（由规则引擎生成，如单张、对子、顺子等）中，利用前向传播预测每个动作得分，打出 Q 值最高的一手牌。
    2.  **优雅降级分支**：一旦神经网络抛出异常（如权重版本不一致、Tensor 错误）或缺失权重文件，则捕获异常输出日志，并在毫秒级内自动退回现有的规则 DFS 决策，保障游戏绝对不报错不卡死。

---

## 6. 验证方案
*   **自动化回归测试**：
    运行 `pytest tests/test_ai_strategy.py`。集成神经网络模块后，应确保现有的 17 个启发式规则策略单测无任何报错，全部维持通过状态。
*   **测试日志观察**：
    在权重文件未放入 `weights/` 目录下时，观察启动日志是否打印正确的优雅降级警告。当权重放入后，观察斗地主 AI 对局的实际出牌流水和速度是否符合预期。
