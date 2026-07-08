# backend README 命名与部署说明一致性清理设计规约

## 背景

近期项目已经完成多轮代码质量和前端 WebSocket 类型收紧优化，当前工作区干净。继续扫描文档时发现 `backend/README.md` 仍残留旧项目结构与旧数据库命名，例如：

- `hmp_ws_service/`
- `DB_NAME=hmp_websocket`
- 指向旧路径的 `file:///d:/Project_2023/hmp_ws_service/...`

这些残留不会影响程序运行，但会误导后续部署、数据库初始化和模型迁移操作。尤其是数据库名错误时，新环境可能连到旧库或创建错误库名。

## 本轮解决的问题

本轮解决的是后端 README 与当前项目实际结构不一致的问题。

目标是让 `backend/README.md` 与当前项目约束保持一致：

- 后端目录示例使用当前 `backend/` 结构。
- `.env` 示例中的数据库名使用 `happy_doudizhu`。
- 数据库模型路径指向当前仓库内的 `backend/app/infrastructure/database/models.py`。
- 运行、测试命令强调使用专用 conda 环境 `hmp_ai` 的 Python。

## 目标

1. 清理 `backend/README.md` 中旧项目名和旧路径残留。
2. 修正 `.env` 示例中的 `DB_NAME`。
3. 补充后端运行和测试必须使用 `D:\ProgramData\miniconda3\envs\hmp_ai\python.exe` 的说明。
4. 保持文档变更小范围，不重写整篇 README。

## 非目标

本轮不做以下事情：

1. 不修改后端代码。
2. 不修改根目录 `README.md`。
3. 不新增部署脚本。
4. 不重写 `backend/README.md` 的整体结构。
5. 不验证外部 MySQL、Redis、RabbitMQ 服务连通性。

## 设计方案

### 方案 A：小范围替换旧命名和关键命令

只处理已扫描到的旧名、旧路径和 Python 环境说明。优点是风险低、diff 小、容易验证；缺点是不会顺手改善整篇 README 的排版和历史乱码问题。

### 方案 B：完整重写 `backend/README.md`

优点是可以一次性提升文档质量。缺点是 diff 很大，容易掺入不必要改写，也不利于检查本轮目标。

### 方案 C：只记录问题，不修改

优点是零风险。缺点是继续留下错误部署指引，实际收益很低。

## 推荐方案

采用方案 A。

本轮只做精确替换和必要补充，不大规模改写。这样能快速消除部署误导，同时保持变更可审查。

## 验证方式

完成后运行：

```powershell
rg -n "hmp_websocket|hmp_ws_service|file:///d:/Project_2023/hmp_ws_service" backend/README.md
rg -n "happy_doudizhu|hmp_ai|D:\\ProgramData\\miniconda3\\envs\\hmp_ai\\python.exe" backend/README.md
git diff --check
git diff -- backend/README.md
```

预期：

- 第一个 `rg` 不再命中旧数据库名和旧路径。
- 第二个 `rg` 能命中当前数据库名和专用 Python 环境说明。
- `git diff --check` 没有空白错误。

## 风险与控制

主要风险是后端 README 当前存在历史编码显示问题，整篇重写容易扩大改动并引入额外噪声。控制方式是只修改 ASCII 可定位的旧名、旧路径和命令块，不改动无关段落。

另一个风险是根目录 README 与 backend README 的职责重叠。控制方式是本轮只修正后端 README 的明显错误；根目录 README 的完整部署指南仍可作为后续独立专项。

## 自查结果

- 本规约没有占位符或未决项。
- 修改范围只包含 `backend/README.md` 和本轮文档。
- 不改代码、不改运行行为、不改数据库结构。
- 验证命令明确，可直接检查旧命名是否清理完成。
