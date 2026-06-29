# 欢乐斗地主欢乐豆管理与准入门槛设计规范

本文档详述了欢乐斗地主游戏中欢乐豆（Beans）的初始化、手动修改、结算保护以及场次门槛限制的设计。

## 1. 业务需求说明

1. **初始欢乐豆**：新注册用户初始分配 `10000` 欢乐豆。支持在页面上手动修改玩家的欢乐豆数量以供测试和充值体验。
2. **场次进入门槛限制**：玩家只有在欢乐豆达到相应场次的最低要求时才能进入该场次并进行匹配。
3. **金豆非负保护**：无论通过何种途径（对局结算、修改、扣减），玩家的欢乐豆均不能为负数（最少为 0）。

---

## 2. 后端数据层与结算逻辑设计

### 2.1 数据库字段与初始化
* **实体表**：`player_profile`（对应 `PlayerProfileORM`）
* **初始默认值**：`beans` 字段默认值为 `10000`（已在 `PlayerProfileORM` schema 定义）。
* **接口变更** (`SQLGameRepository`)：
  * **新增** `update_beans(player_id: str, beans: int) -> None`：
    * 将指定玩家的欢乐豆强制更新为 `beans`，底线防御为 `max(0, beans)`。
  * **修改** `update_profile_stats(player_id: str, beans_delta: int, is_win: bool) -> None`：
    * 对局结束后的欢乐豆增减计算更新为：`orm.beans = max(0, orm.beans + beans_delta)`。
    * 此逻辑实施**破产保护**：如果扣减额度超出玩家所持有的豆数，豆数扣减至 0 即止，不会变成负数。

---

## 3. 后端 API 路由与 WebSocket 匹配校验拦截

### 3.1 欢乐豆修改 API
* **接口地址**：`POST /api/game/profile/{player_id}/beans`
* **请求体**：
  ```json
  {
    "beans": 20000
  }
  ```
* **约束与验证**：使用 Pydantic Model 校验 `beans >= 0`。后端接口再次调用 `max(0, req.beans)` 予以保护。
* **返回格式**：
  ```json
  {
    "ok": true,
    "player_id": "player_123",
    "beans": 20000
  }
  ```

### 3.2 WebSocket 匹配门槛拦截
在 `game_handler.py` 收到 `action: "join_match"` 消息时，根据底分 `base_score` 提取入场限制并进行校验。

**底分与门槛映射关系表 (BASE_SCORE_MIN_BEANS)**：
* 新手场 (底分 20) $\rightarrow$ 最低需 1,000 豆
* 初级场 (底分 80) $\rightarrow$ 最低需 3,000 豆
* 普通场 (底分 300) $\rightarrow$ 最低需 8,000 豆
* 中级场 (底分 900) $\rightarrow$ 最低需 25,000 豆
* 高级场 (底分 2700) $\rightarrow$ 最低需 80,000 豆
* 顶级场 (底分 6000) $\rightarrow$ 最低需 300,000 豆

**校验流程**：
1. 从数据库读取玩家的当前欢乐豆真实数量 `profile.beans`。
2. 匹配底分对应的门槛 `min_beans`，如满足 `profile.beans < min_beans`，则拦截匹配，直接通过 WebSocket 连接向前端下发错误消息事件：
   ```json
   {
     "event": "error",
     "msg": "您的欢乐豆不足，该赛事最低需要 X 欢乐豆"
   }
   ```
3. 校验通过则进入正常的 Redis 匹配队列排队。

---

## 4. 前端状态管理与大厅视图交互设计

### 4.1 Pinia 状态管理扩展
在 `playerStore.ts` 中新增异步 Action `modifyBeans(newBeans: number)`：
* 调用后端接口 `POST /api/game/profile/{player_id}/beans`。
* 请求成功后同步修改本地 `beans.value = newBeans`。

### 4.2 资产框点击修改
* **入口**：在 `LobbyView.vue` 顶部 `.asset-pill.gold-beans` 添加点击事件。
* **修改模态框**：点击后展示毛玻璃拟态的 `edit-beans-modal` 对话框，内置数字输入框，设定 `min="0"`。
* **保存逻辑**：点击“确认”后触发 `modifyBeans`，保存成功后关闭弹窗；若失败则展示警告信息。

### 4.3 准入门槛前置校验
在大厅 `LobbyView.vue` 页面中定义前端门槛表：
* 在点击卡片 `selectTier(tier)`，以及点击“快速开始”时，先检查 `playerStore.beans`。
* 若不满足入场条件，前端直接弹出 Alert/Toast 阻断，不跳转准备页。

---

## 5. 测试与验证计划

### 5.1 自动化测试
* 补充后端 API 单元测试 `backend/tests/test_game_api.py`，验证 `POST /api/game/profile/{player_id}/beans` 修改金币的非负性以及越界校验。
* 补充 WebSocket 测试 `backend/tests/test_game_websocket.py`，模拟发送不同 `base_score` 匹配时低于入场额度的失败返回。
* 补充 `test_room.py` 结算测试，验证破产保护：确保扣除超过限额的欢乐豆时，最终数值能正确截断为 0。

### 5.2 手动测试
* 运行前后端服务，在大厅页面点击欢乐豆旁的 `+`，验证弹窗输入、保存及顶部数值变化。
* 设定金豆数量低于限额（例如设为 500），点击初级场（限额 3000），验证是否能弹出拦截并阻止匹配。
