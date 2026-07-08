# 前端剩余 any 类型收紧实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 清理 `LobbyView.vue`、`SettingsModal.vue`、`DebugConsoleView.vue` 中剩余的 `any` 类型。

**Architecture:** 本轮只补充局部 TypeScript 类型，不拆分组件、不改变接口和 UI。用静态扫描作为类型债 RED 证据，用前端单测和构建作为回归验证。

**Tech Stack:** Vue 3、TypeScript、Vite、Vitest。

## Global Constraints

- 文档使用中文。
- 禁止批量删除文件或目录。
- 不修改后端接口。
- 不修改 WebSocket 协议字段名。
- 不重构大页面。
- 用户人工确认完整无误前不执行 `git commit`。
- 提交前必须提醒用户本轮优化建议手动测试的功能点。

---

## 文件结构

- 修改：`frontend/src/views/LobbyView.vue`
  - 补 `LeaderboardEntry`、`SidebarItem`、`Tier` 类型。
- 修改：`frontend/src/components/SettingsModal.vue`
  - 补 `PrivacyStorageKey` 和 `Ref<boolean>` 参数。
- 修改：`frontend/src/views/DebugConsoleView.vue`
  - 补站内信、上传文件、审计日志、调试 WebSocket payload、文件事件和音频兼容类型。
- 新增：`docs/superpowers/specs/2026-07-08-frontend-remaining-any-typing-design.md`
  - 记录设计边界。
- 新增：`docs/superpowers/plans/2026-07-08-frontend-remaining-any-typing.md`
  - 记录执行步骤。

---

### Task 1：记录静态扫描 RED

**Files:**
- Verify only.

**Interfaces:**
- Consumes: 目标 3 个 Vue 文件。
- Produces: 修改前 `any` 命中证据。

- [x] **Step 1：运行目标扫描**

```powershell
rg -n "\bany\b" frontend/src/views/LobbyView.vue frontend/src/components/SettingsModal.vue frontend/src/views/DebugConsoleView.vue
```

期望：命中 `leaderboard ref<any[]>`、`handleSidebarClick(item: any)`、`selectTier(tier: any)`、`togglePrivacy(... refObj: any)` 和 DebugConsole 多处 `any`。

---

### Task 2：收紧 LobbyView 类型

**Files:**
- Modify: `frontend/src/views/LobbyView.vue`

**Interfaces:**
- Produces:
  - `LeaderboardEntry`
  - `SidebarItem`
  - `Tier`

- [x] **Step 1：新增局部接口**

在脚本区 `isMockMode` 后加入：

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

- [x] **Step 2：替换 any**

```ts
const leaderboard = ref<LeaderboardEntry[]>([])
const TIERS: Tier[] = [
```

```ts
function handleSidebarClick(item: SidebarItem) {
```

```ts
function selectTier(tier: Tier) {
```

---

### Task 3：收紧 SettingsModal 隐私开关类型

**Files:**
- Modify: `frontend/src/components/SettingsModal.vue`

**Interfaces:**
- Produces:
  - `PrivacyStorageKey`
  - `togglePrivacy(key: PrivacyStorageKey)`

- [x] **Step 1：导入 Ref 并定义 key 联合类型**

```ts
import { ref, onMounted, type Ref } from 'vue'
```

```ts
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

- [x] **Step 2：替换 togglePrivacy 参数**

```ts
function togglePrivacy(key: PrivacyStorageKey) {
```

---

### Task 4：收紧 DebugConsoleView 类型

**Files:**
- Modify: `frontend/src/views/DebugConsoleView.vue`

**Interfaces:**
- Produces:
  - `SiteMessage`
  - `UploadedFileRecord`
  - `AuditLogRecord`
  - `DebugWsPayload`

- [x] **Step 1：新增调试页数据接口**

在 `router` 后加入：

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

interface DebugWsPayload {
  type?: string
  data?: SiteMessage
  upload_id?: string
  status?: string
  completed_chunks?: number[]
  chunk_index?: number
  filename?: string
  path?: string
  message?: string
  id?: number
}

type AudioWindow = Window & typeof globalThis & {
  webkitAudioContext?: typeof AudioContext
}
```

- [x] **Step 2：替换 ref any 数组**

```ts
const siteMessages = ref<SiteMessage[]>([])
const uploadedFilesList = ref<UploadedFileRecord[]>([])
const auditLogs = ref<AuditLogRecord[]>([])
```

- [x] **Step 3：收紧 WebSocket payload**

```ts
function handleWsEvent(payload: DebugWsPayload, rawData: string) {
```

对站内信分支增加：

```ts
    const msg = payload.data
    if (!msg) {
      logToTerminal(rawData, 'received')
      return
    }
```

上传分片 ack 中：

```ts
      const ackIndex = payload.chunk_index
      if (!wsUploadFile || ackIndex === undefined) return
```

- [x] **Step 4：收紧音频兼容字段**

```ts
    const AudioContextConstructor = window.AudioContext || (window as AudioWindow).webkitAudioContext
    if (!AudioContextConstructor) return
    const audioCtx = new AudioContextConstructor()
```

- [x] **Step 5：收紧文件选择和 JSON 格式化**

```ts
function handleFileSelect(event: Event) {
  const target = event.target as HTMLInputElement | null
  const file = target?.files?.[0]
  if (file) {
    handleStartUpload(file)
  }
}
```

```ts
function formatJSON(obj: unknown): string {
```

---

### Task 5：验证

**Files:**
- Verify only.

**Interfaces:**
- Consumes: Task 2、Task 3、Task 4 的改动。
- Produces: 用户验收依据。

- [x] **Step 1：运行目标扫描**

```powershell
rg -n "\bany\b" frontend/src/views/LobbyView.vue frontend/src/components/SettingsModal.vue frontend/src/views/DebugConsoleView.vue
```

期望：无命中。

- [x] **Step 2：运行前端单测**

```powershell
cd frontend
npm.cmd run test:unit -- --run
```

期望：全部通过。

- [x] **Step 3：运行前端构建**

```powershell
cd frontend
npm.cmd run build
```

期望：通过。

- [x] **Step 4：检查 diff**

```powershell
git diff --check
git diff --stat
git -c core.excludesfile= status --short
```

期望：无空白错误；状态中包含本轮文件以及之前未提交的 `AGENTS.md`。

## 自查结果

- 本计划覆盖用户指定的三个类型收紧点。
- 没有新增依赖。
- 没有改变 UI 或后端协议。
- 不包含提交步骤，等待用户人工确认后再提交。
