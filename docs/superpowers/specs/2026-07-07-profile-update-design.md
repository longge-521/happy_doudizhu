# 个人资料修改与本地头像上传设计规约 (2026-07-07)

本设计规约旨在为斗地主系统增加修改个人信息（如昵称）的功能，并将头像设置从原本的手动输入网络 URL 改为支持在本地选择图片文件并上传存储在后端本地目录。

## 目标与背景

1. **修改用户信息**：允许玩家根据需要修改自己的昵称（`nickname`），以便提升交互自主性。
2. **头像本地化存储**：弃用输入第三方不安全 URL 的方式，支持在前端直接选择图片文件上传至后端服务器，将文件统一归档在 `uploads/avatars/` 目录下。
3. **接口防穿越与安全校验**：继续遵循大文件上传模块的安全规范，限制头像文件必须是标准的图片 MIME 类型，并强制限制玩家只能更新自己的档案。

---

## 方案设计

我们提供了 3 种前端交互与接口组合方案：

### 方案 A：原位表单化设计与合并提交（推荐）
* **交互细节**：
  - “个人资料”弹窗中，原先只读的昵称文本保留，但其下方追加一个“修改昵称”的输入框。
  - 头像显示区域的下方，新增一个“上传本地头像”的按钮（或直接点击头像进行图片选择），使用隐藏的 `<input type="file" accept="image/*" />`。
  - 当玩家选中本地文件后，使用 `URL.createObjectURL(file)` 生成临时本地预览地址展示在头像框中，并不立即上传。
  - 将原“保存头像”按钮更名为“保存资料”。点击时执行统一提交：
    1. 若选中了新头像，先以 `multipart/form-data` 形式异步上传到 `/api/game/profile/{player_id}/upload-avatar` 获取后端保存后的网络路径（如 `/api/uploads/avatars/xxxx.png`）。
    2. 将新昵称与（新）头像地址一并发送给 `/api/game/profile/{player_id}/update` 进行终局保存。
* **优点**：开发效率高，逻辑高度合并，用户体验极佳，不需要多次与服务器做未保存的临时文件交互。

### 方案 B：双向即时绑定与即选择即上传
* **交互细节**：
  - 用户一旦选中本地图片，立即在后台静默触发上传接口获取到后端 URL，并实时更新 `avatarInputValue` 并将新地址应用在页面上。
  - 昵称提供一个独立的修改按钮，点击后发送请求更新，更新成功后实时刷新页面。
* **缺点**：如果用户最后关闭弹窗或者点击取消，上传的垃圾文件将已经留在服务器上，容易产生配置孤儿。

---

## 接口设计

### 1. 新增：本地头像文件上传 API
- **Endpoint**: `POST /api/game/profile/{player_id}/upload-avatar`
- **Request Type**: `multipart/form-data` (字段名: `file`)
- **安全过滤与逻辑**：
  - 限制 `file.content_type` 必须以 `image/` 开头。
  - 存放目录：`backend/uploads/avatars/`（若不存在则自动创建）。
  - 文件重命名：`avatar_{player_id}_{uuid.uuid4().hex}{file_ext}`。
  - 返回值：
    ```json
    {
      "ok": true,
      "avatar_url": "/api/uploads/avatars/avatar_xxx.png"
    }
    ```

### 2. 新增：修改个人资料 API
- **Endpoint**: `POST /api/game/profile/{player_id}/update`
- **Request Body**:
  ```json
  {
    "nickname": "新昵称 (可选)",
    "avatar_url": "新头像路径 (可选)"
  }
  ```
- **逻辑**：
  - 校验 `nickname` 不能为空且长度在 1-20 位。
  - 调用 `SQLGameRepository` 更新昵称和头像。
  - 返回更新后的完整 Profile。

### 3. 静态托管路由挂载
- 在 `backend/main.py` 中挂载：
  ```python
  app.mount("/api/uploads", StaticFiles(directory=os.path.join(BASE_DIR, "uploads")), name="uploads")
  ```
  这样前端即可直接通过 `/api/uploads/avatars/xxx.png` 访问图片资源。

---

## 验证与发布

1. **后端验证**：
   - 编写接口测试用例，覆盖文件上传成功、类型限制拦截（非法后缀/格式拒绝）等场景。
2. **前端联调**：
   - 开启前端，在个人资料弹窗中选择不同的 JPG/PNG 图片上传，查看后台是否能够接收并返回正确映射路径，且头像能无缝刷新展示。
