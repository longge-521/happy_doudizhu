# 前端剩余 any 类型收紧设计

## 背景

前端游戏主链路的 WebSocket、房间状态、玩家状态和结算类型已经分批收紧。当前 `frontend/src` 中仍有少量 `any`，集中在：

- `LobbyView.vue`：排行榜数据、侧边栏菜单项、场次配置。
- `SettingsModal.vue`：隐私开关的 ref 参数。
- `DebugConsoleView.vue`：调试控制台的站内信、上传文件、审计日志、WebSocket payload、文件选择事件和浏览器音频兼容字段。

本轮只处理这些 `any` 类型，不做视觉调整、不拆大文件、不修改接口协议。

## 目标

1. `LobbyView.vue` 不再使用 `any`，为排行榜、侧边栏、场次配置补明确类型。
2. `SettingsModal.vue` 不再使用 `any`，隐私开关只接收布尔 ref 和已知 localStorage key。
3. `DebugConsoleView.vue` 不再使用 `any`，调试页数据结构改为可读的接口和联合类型。
4. 保持现有 UI、接口字段和运行行为不变。

## 非目标

- 不拆分 `LobbyView.vue`、`SettingsModal.vue`、`DebugConsoleView.vue`。
- 不新增业务功能。
- 不改后端接口。
- 不改 WebSocket 消息字段名。
- 不处理其它历史文档中的未实施功能计划。

## 设计方案

### LobbyView

新增局部类型：

```ts
interface LeaderboardEntry {
  player_id: string
  nickname: string
  beans: number
  rank_title: string
  win_rate: number
  total_games: number
}

interface SidebarItem {
  name: string
  badge: string
  active?: boolean
}

interface Tier {
  id: string
  name: string
  baseScore: number
  limit: string
  online: number
  colorClass: string
}
```

`leaderboard` 改为 `ref<LeaderboardEntry[]>([])`，`TIERS` 改为 `Tier[]`，`handleSidebarClick()` 和 `selectTier()` 使用对应类型。

### SettingsModal

新增：

```ts
import type { Ref } from 'vue'

type PrivacyStorageKey =
  | 'hmp_privacy_show_record'
  | 'hmp_privacy_receive_emoji'
  | 'hmp_privacy_show_honor'
  | 'hmp_privacy_show_rank'
  | 'hmp_privacy_show_geo'
  | 'hmp_privacy_recommend_friend'
  | 'hmp_privacy_friend_apply'
  | 'hmp_privacy_nearby_invite'
```

新增 `privacyRefs: Record<PrivacyStorageKey, Ref<boolean>>` 映射，模板只传已知 key，`togglePrivacy()` 改为：

```ts
function togglePrivacy(key: PrivacyStorageKey) {
```

### DebugConsoleView

新增局部接口：

```ts
interface SiteMessage {
  id: number
  sender: string
  receiver?: string
  content: string
  is_read: number
  created_at: string
}

interface UploadedFileRecord {
  id: number
  filename: string
  file_size_mb: number
  created_at: string
}

interface AuditLogRecord {
  id: number
  created_at: string
  operator: string
  action: string
  resource_type: string
  ip_address: string
  status: string
  execution_time?: number | null
  method?: string | null
  request_params?: unknown
}
```

WebSocket payload 使用 `DebugWsPayload` 类型，基础字段允许 `unknown`，在分支中用类型保护收窄。`formatJSON()` 接收 `unknown`。文件选择事件使用 `Event` 并检查 `HTMLInputElement`。

## 验证策略

修改前先记录目标扫描命中：

```powershell
rg -n "\bany\b" frontend/src/views/LobbyView.vue frontend/src/components/SettingsModal.vue frontend/src/views/DebugConsoleView.vue
```

修改后运行：

```powershell
cd frontend
npm.cmd run test:unit -- --run
npm.cmd run build
```

并检查：

```powershell
rg -n "\bany\b" frontend/src/views/LobbyView.vue frontend/src/components/SettingsModal.vue frontend/src/views/DebugConsoleView.vue
git diff --check
```

期望：

- 前端单测通过。
- 前端构建通过。
- 目标 3 个文件不再命中 `any`。
- 只包含本轮文档和类型收紧改动，另有之前未提交的 `AGENTS.md` 改动需保留。

## 自查结果

- 本设计覆盖用户指定的三个优化点。
- 没有修改 UI 文案、协议字段或后端接口。
- 没有新增依赖。
- 不包含提交步骤，等待用户确认后再提交。
