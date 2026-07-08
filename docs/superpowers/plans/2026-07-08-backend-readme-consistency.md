# backend README 命名与部署说明一致性清理实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 清理 `backend/README.md` 中旧项目名、旧数据库名和旧路径说明，让后端文档与当前项目结构一致。

**Architecture:** 本计划只修改文档。`backend/README.md` 继续作为后端局部说明文档，本轮只做精确替换和必要运行环境补充，不重写整篇文档。

**Tech Stack:** Markdown、PowerShell、ripgrep。

## Global Constraints

- 文档使用中文。
- 禁止批量删除文件或目录。
- 不修改后端代码。
- 不修改根目录 `README.md`。
- 不新增部署脚本。
- 用户人工确认完整无误前不执行 `git commit`。

---

## 文件结构

- 新增：`docs/superpowers/specs/2026-07-08-backend-readme-consistency-design.md`
  - 记录本轮 README 清理设计边界。
- 新增：`docs/superpowers/plans/2026-07-08-backend-readme-consistency.md`
  - 记录本轮执行步骤。
- 修改：`backend/README.md`
  - 清理旧项目名、旧数据库名、旧 file URI。
  - 补充专用 Python 环境运行说明。

---

### Task 1：复现旧命名残留

**Files:**
- Read: `backend/README.md`

**Interfaces:**
- Produces: 当前旧命名残留清单。

- [x] **Step 1：扫描旧命名**

运行：

```powershell
rg -n "hmp_websocket|hmp_ws_service|file:///d:/Project_2023/hmp_ws_service" backend/README.md
```

预期：命中旧目录名、旧数据库名和旧模型路径。

---

### Task 2：修正 backend README

**Files:**
- Modify: `backend/README.md`

**Interfaces:**
- Consumes: Task 1 的旧命名残留清单。
- Produces: 与当前项目一致的后端 README。

- [x] **Step 1：替换旧目录和数据库名**

在 `backend/README.md` 中：

```text
hmp_ws_service/
```

改为：

```text
backend/
```

并将：

```ini
DB_NAME=hmp_websocket
```

改为：

```ini
DB_NAME=happy_doudizhu
```

- [x] **Step 2：修正旧 models.py 链接**

将旧链接：

```text
file:///d:/Project_2023/hmp_ws_service/app/infrastructure/database/models.py
```

改为仓库相对路径说明：

```text
`backend/app/infrastructure/database/models.py`
```

- [x] **Step 3：补充专用 Python 环境说明**

在“安装项目依赖”和“运行单元测试”命令附近补充说明：后端必须使用：

```text
D:\ProgramData\miniconda3\envs\hmp_ai\python.exe
```

示例命令使用：

```powershell
D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pip install -r requirements.txt
D:\ProgramData\miniconda3\envs\hmp_ai\python.exe main.py
D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest tests/ -q --tb=short
```

---

### Task 3：验证文档清理结果

**Files:**
- Verify only.

**Interfaces:**
- Consumes: Task 2 的 README 修改。
- Produces: 可供用户检查的验证结果。

- [x] **Step 1：确认旧命名不再残留**

运行：

```powershell
rg -n "hmp_websocket|hmp_ws_service|file:///d:/Project_2023/hmp_ws_service" backend/README.md
```

预期：没有输出，退出码为 1。

- [x] **Step 2：确认新命名和 Python 环境说明存在**

运行：

```powershell
rg -n "happy_doudizhu|hmp_ai|D:\\ProgramData\\miniconda3\\envs\\hmp_ai\\python.exe" backend/README.md
```

预期：命中数据库名和专用 Python 路径。

- [x] **Step 3：检查 diff**

运行：

```powershell
git diff --check
git diff -- backend/README.md
```

预期：没有空白错误，diff 只包含本轮文档修正。

## 自查结果

- 设计规约中的目标均有对应任务覆盖。
- 本计划没有占位符或未决项。
- 本计划不包含 commit 步骤，等待用户人工确认后再提交。
