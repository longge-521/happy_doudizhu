# 个人资料头像设计

本文档描述如何为玩家档案增加持久化头像图片字段，并允许玩家在大厅个人资料面板中修改头像。

## 目标

- 在现有 `player_profile` 记录中保存每个玩家的头像图片 URL。
- 在玩家档案接口中返回头像字段，让大厅能够渲染头像。
- 让已登录玩家从大厅底部用户卡片打开个人资料详情，并修改头像 URL。
- 将大厅左上角现有退出登录操作的文案改为明确的退出含义，避免继续显示玩法标签造成误解。

## 非目标

- 本次不实现二进制图片上传、裁剪、审核或图片处理。
- 本次不实现公开个人主页或社交资料浏览。
- 本次不修改匹配、房间状态或排位结算规则。

## 数据模型

在 `player_profile` 表中新增 `avatar_url` 字段。

- 类型：可空字符串，长度 500。
- 默认值：`NULL`，表示前端渲染默认头像占位。
- `backend/app/infrastructure/database/session.py` 中增加启动自愈逻辑，为已有开发数据库补齐该字段，方式与当前排位字段一致。

领域实体 `PlayerProfile` 增加可选属性 `avatar_url`。`SQLGameRepository` 在创建用户档案、获取或创建档案、档案返回和排行榜投影中映射该字段。

## API

`GET /api/game/profile/{player_id}` 返回 `avatar_url`。

新增 `POST /api/game/profile/{player_id}/avatar`，用于更新当前登录玩家的头像。

请求体：

```json
{
  "avatar_url": "https://example.com/avatar.png"
}
```

规则：

- 路由复用现有游戏登录 token，并调用 `ensure_player_access` 限制只能修改自己的头像。
- `avatar_url` 允许为空字符串或 `null`，用于清空头像并恢复默认占位。
- 非空值会先 `trim`，并限制最长 500 个字符。
- 允许的 URL 形式为 `http://`、`https://`，或根路径相对地址 `/static/...`、`/api/uploads/...`。
- 非法地址返回 `400`。
- 响应返回 `ok`、`player_id` 和最终保存的 `avatar_url`。

## 前端状态

`frontend/src/stores/playerStore.ts` 增加：

- `avatarUrl` 状态，初始值从 `localStorage` 读取。
- `fetchProfile()` 从接口返回的 `avatar_url` 同步头像。
- `setSession()` 与 `logout()` 同步维护 `hmp_avatar_url` 本地缓存。
- `modifyAvatar(avatarUrl)` action，调用新增头像接口并更新本地状态。

Store 保持现有接口风格，方便 `LobbyView.vue` 直接消费。

## 大厅 UI

底部用户卡片继续作为个人资料入口，但 `handleProfileClick()` 改为打开真实个人资料弹窗，不再展示“功能开发中”提示。

个人资料弹窗展示：

- 头像预览。
- 昵称、账号、玩家 ID。
- 欢乐豆、总局数、胜率、段位头衔和星级。
- 头像 URL 输入框，以及保存和清空操作。

底部用户卡片头像渲染规则：

- `playerStore.avatarUrl` 有值时显示图片。
- 没有头像时显示当前默认头像占位。
- 大厅页和准备页使用同一套渲染规则。

大厅左上角按钮保持现有退出登录行为，但可见文案改成明确的“退出”含义，并增加明确的可访问性标签。

## 错误处理

- 档案加载失败时保留当前 UI 状态。
- 头像保存失败时在弹窗内展示错误信息，不关闭弹窗。
- 清空头像会保存空值，并立即回到默认头像占位。
- 远程图片加载失败时隐藏失败图片，视觉上回退到默认头像占位。

## 测试

后端测试：

- 仓储层能够把 `avatar_url` 映射到 `PlayerProfile`。
- 档案 API 返回 `avatar_url`。
- 头像更新 API 能为已认证玩家保存和清空头像字段。
- 头像更新 API 拒绝其他玩家 token 和非法 URL。

前端测试：

- `playerStore.fetchProfile()` 能保存接口返回的 `avatar_url`。
- `playerStore.modifyAvatar()` 会请求头像接口并更新本地状态。
- 大厅左上角渲染明确的退出文案，而不是当前玩法标签。
- 点击底部用户卡片会打开个人资料弹窗，并渲染头像预览和输入框。

手动验证：

- 打开 `http://localhost:5173/lobby`。
- 确认左上角按钮明确表达退出登录，并且点击后能退出到登录页。
- 点击底部用户卡片，打开个人资料弹窗。
- 保存一个合法头像 URL，确认底部用户卡片头像更新。
- 清空头像，确认恢复默认头像占位。
