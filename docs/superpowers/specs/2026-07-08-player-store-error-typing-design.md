# playerStore 错误处理类型收紧设计规约

## 背景

前端状态层已经逐步收紧了 WebSocket 房间状态和服务端事件 payload 类型。继续扫描后发现 `frontend/src/stores/playerStore.ts` 仍有多处 `catch (e: any)`。

TypeScript 中 `catch` 捕获值本质上是未知值。它可能是 `Error`，也可能是字符串、普通对象、数字或其他值。当前代码直接读取 `e.message`，会绕过类型检查；当捕获对象的 `message` 不是字符串时，返回结果也可能不是预期的字符串错误文案。

## 本轮解决的问题

本轮解决的是 `playerStore` 网络请求错误处理缺少类型边界的问题。

目标是在不改变接口、不改变页面行为的前提下，让错误处理从 `any` 收紧为 `unknown`，并统一从未知错误中提取安全的字符串错误信息。

## 目标

1. 新增内部 helper：`getErrorMessage(error: unknown, fallback: string): string`。
2. 将 `playerStore.ts` 中的 `catch (e: any)` 改为 `catch (e: unknown)`。
3. 所有 catch 返回错误文案时都通过 `getErrorMessage()`。
4. 补充测试覆盖非标准错误对象，确保错误文案仍是字符串 fallback。

## 非目标

本轮不做以下事情：

1. 不修改后端 API。
2. 不修改登录、注册、资料、头像、密码等业务流程。
3. 不修改 UI 文案。
4. 不调整 `fetchProfile()` 的 console error 行为。
5. 不拆分 `playerStore.ts`。

## 设计方案

### 方案 A：新增统一 helper 并替换所有 catch

优点是重复逻辑少，所有网络错误处理路径一致；能一次性消掉 `playerStore.ts` 中的 `catch (e: any)`。缺点是新增一个很小的内部函数。

### 方案 B：每个 catch 内部局部判断

优点是不新增函数。缺点是会重复 7 次判断逻辑，后续维护成本更高。

### 方案 C：只保留现状

优点是零改动。缺点是继续保留 `any`，且非字符串 `message` 仍可能流入 UI 错误状态。

## 推荐方案

采用方案 A。

`getErrorMessage()` 只处理最基本的安全提取：

- 如果 `error instanceof Error` 且 `error.message` 非空，返回 `error.message`。
- 如果 `error` 是对象且包含非空字符串 `message`，返回该字符串。
- 其他情况返回传入的 fallback。

这样能保持普通 `Error` 的现有行为，同时避免非字符串 message 破坏返回类型。

## 测试策略

在 `frontend/src/stores/__tests__/playerStore.spec.ts` 中新增一个测试：

- mock `fetch` reject 一个普通对象 `{ message: 123 }`。
- 调用 `store.login('user', 'pass')`。
- 期望 `result.ok === false`。
- 期望 `result.error === '网络连接失败'`。

该测试在当前实现下会失败，因为当前 `catch (e: any)` 会把数字 `123` 作为错误值返回。实现 helper 后应通过。

## 验证方式

完成后运行：

```powershell
cd frontend
npm.cmd run test:unit -- --run src/stores/__tests__/playerStore.spec.ts
npm.cmd run test:unit -- --run
npm.cmd run build
```

最后检查：

```powershell
git diff --check
git diff --stat
rg -n "catch \\(e: any\\)" frontend/src/stores/playerStore.ts
```

## 风险与控制

主要风险是误改已有错误文案。控制方式是 helper 只替换 catch 中读取 `e.message || fallback` 的部分，fallback 文案保持原样。

另一个风险是普通对象字符串 message 的兼容性。控制方式是 helper 支持 `{ message: '...' }`，与当前常见行为保持一致。

## 自查结果

- 本规约没有占位符或未决项。
- 修改范围聚焦在 `playerStore.ts` 和对应测试。
- 不改 API、不改 UI、不改业务流程。
- 验证命令明确，可直接检查 `catch (e: any)` 是否清理完成。
