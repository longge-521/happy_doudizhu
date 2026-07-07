# 个人资料修改密码功能设计规约 (2026-07-07)

本设计规约旨在为斗地主系统增加玩家自主修改密码的安全机制。

## 目标与安全设计

1. **凭证校验**：修改密码必须提供正确的旧密码（`old_password`），由后端进行严格的 Hash 碰撞比对，防止非本人篡改。
2. **强制重新登录**：修改密码成功后，系统会主动清空本地存储的 `hmp_game_auth_token` 并进行注销拦截，强制玩家重定向至登录界面重新登录，保障账号在修改凭证后的安全态势。
3. **接口越权防范**：强制验证 `player_id` 必须与 Token 提取的 `current_player_id` 保持一致，拒绝一切平行越权行为。

---

## 后端接口设计

### 1. 修改密码 API
- **Endpoint**: `POST /api/game/profile/{player_id}/password`
- **Request Body**:
  ```json
  {
    "old_password": "旧密码",
    "new_password": "新密码"
  }
  ```
- **安全过滤与逻辑**：
  - 检验 `new_password` 长度在 4-100 位。
  - 根据 `player_id` 查询 `UserORM`，若不存在则报 `404 Not Found`。
  - 调用 `verify_password(req.old_password, user.password)`。若失败，报 `400 Bad Request` 并提示 “旧密码输入错误”。
  - 校验新旧密码不能相同，若相同报 `400 Bad Request` 并提示 “新密码不能与旧密码相同”。
  - 对新密码调用 `hash_password`，并将加密后的新 Hash 保存入库。
- **返回值**：
  ```json
  {
    "ok": true,
    "message": "密码修改成功"
  }
  ```

---

## 前端交互设计 (方案 A：折叠面板式原位展开)

1. 在个人资料弹窗的下方，新增“🔐 修改密码”文本链接。
2. 点击后，通过 `v-if` 展开一个折叠面板，平滑地显露：
   - 旧密码输入框
   - 新密码输入框
   - 确认新密码输入框
   - 确认修改 / 取消 按钮
3. 用户填写完并点击“确认修改”时：
   - 客户端提前做非空以及两次新密码一致性的检测。
   - 调用 `playerStore.modifyPassword(old, new)` 方法。
   - 若成功，弹框提示“密码修改成功，请重新登录！”，接着清空本地 Token 等缓存，重定向至 `/login` 登录页。
