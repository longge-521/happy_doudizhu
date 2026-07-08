# playerStore 错误处理类型收紧实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `playerStore.ts` 中的 `catch (e: any)` 收紧为 `unknown`，并统一提取安全的字符串错误文案。

**Architecture:** 本计划只修改 Pinia store 的错误处理边界。`playerStore.ts` 新增一个内部 helper 处理未知错误；现有 store API 和页面调用方式不变；`playerStore.spec.ts` 增加非标准错误对象的回归测试。

**Tech Stack:** Vue 3、Pinia、TypeScript、Vitest、Vite。

## Global Constraints

- 文档使用中文。
- 禁止批量删除文件或目录。
- 不修改后端 API。
- 不修改 UI 文案。
- 不拆分 `playerStore.ts`。
- 用户人工确认完整无误前不执行 `git commit`。

---

## 文件结构

- 新增：`docs/superpowers/specs/2026-07-08-player-store-error-typing-design.md`
  - 记录本轮错误处理类型收紧设计边界。
- 新增：`docs/superpowers/plans/2026-07-08-player-store-error-typing.md`
  - 记录执行步骤。
- 修改：`frontend/src/stores/playerStore.ts`
  - 新增 `getErrorMessage(error: unknown, fallback: string): string`。
  - 替换所有 `catch (e: any)`。
- 修改：`frontend/src/stores/__tests__/playerStore.spec.ts`
  - 增加非字符串 message 的错误处理测试。

---

### Task 1：新增失败测试

**Files:**
- Modify: `frontend/src/stores/__tests__/playerStore.spec.ts`

**Interfaces:**
- Consumes: `usePlayerStore().login(accountName, password)`
- Produces: 非标准错误对象必须返回 fallback 字符串的行为约束。

- [x] **Step 1：写失败测试**

在 `playerStore avatar profile state` describe 内追加测试：

```ts
  it('falls back to network error text when rejected value has non-string message', async () => {
    setActivePinia(createPinia())
    const store = usePlayerStore()
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue({ message: 123 }))

    const result = await store.login('test-user', 'pass123')

    expect(result).toEqual({ ok: false, error: '网络连接失败' })
  })
```

- [x] **Step 2：运行测试确认失败**

运行：

```powershell
cd frontend
npm.cmd run test:unit -- --run src/stores/__tests__/playerStore.spec.ts
```

预期：失败，当前实现会返回 `error: 123`。

---

### Task 2：实现 unknown catch 和统一错误提取

**Files:**
- Modify: `frontend/src/stores/playerStore.ts`

**Interfaces:**
- Produces:
  - `getErrorMessage(error: unknown, fallback: string): string`
  - 所有网络请求 catch 使用 `catch (e: unknown)`

- [x] **Step 1：新增 helper**

在 `authHeaders()` 后新增：

```ts
  function getErrorMessage(error: unknown, fallback: string): string {
    if (error instanceof Error && error.message) {
      return error.message
    }
    if (
      typeof error === 'object' &&
      error !== null &&
      'message' in error &&
      typeof error.message === 'string' &&
      error.message
    ) {
      return error.message
    }
    return fallback
  }
```

- [x] **Step 2：替换 catch 类型和返回**

将所有：

```ts
    } catch (e: any) {
      return { ok: false, error: e.message || '网络连接失败' }
    }
```

替换为：

```ts
    } catch (e: unknown) {
      return { ok: false, error: getErrorMessage(e, '网络连接失败') }
    }
```

- [x] **Step 3：运行 targeted 测试**

运行：

```powershell
cd frontend
npm.cmd run test:unit -- --run src/stores/__tests__/playerStore.spec.ts
```

预期：通过。

---

### Task 3：前端全量验证

**Files:**
- Verify only.

**Interfaces:**
- Consumes: Task 1 和 Task 2 的改动。
- Produces: 可供用户检查的验证结果。

- [x] **Step 1：运行前端全量单测**

```powershell
cd frontend
npm.cmd run test:unit -- --run
```

预期：全部通过。

- [x] **Step 2：运行前端构建**

```powershell
cd frontend
npm.cmd run build
```

预期：构建通过，没有 TypeScript 错误。

- [x] **Step 3：检查 diff 和 any 清理结果**

```powershell
git diff --check
git diff --stat
rg -n "catch \\(e: any\\)" frontend/src/stores/playerStore.ts
```

预期：无空白错误；`rg` 不再命中 `catch (e: any)`。

## 自查结果

- 设计规约中的目标均有对应任务覆盖。
- 本计划没有占位符或未决项。
- 本计划不包含 commit 步骤，等待用户人工确认后再提交。
