# README.md 优化与 Windows 部署指南补充设计规约 (2026-07-07)

本设计规约说明如何对项目根目录下的 `README.md` 文档进行架构重构与命名修正，并详细补充在 Windows 环境下的完整生产部署和常驻运行流程。

## 目标与背景

1. **命名一致性**：当前 `README.md` 中大量残留了旧的数据库名 `hmp_websocket` 以及旧的服务名，需要统一更替为当前的正式命名 `happy_doudizhu`。
2. **简化数据库初始化说明**：用已实现的自动脚本 `python scripts/create_db.py` 替代原先需要人工连接 MySQL 并手动编写 SQL `CREATE DATABASE ...` 的说明，以降低部署门槛。
3. **运行环境强调**：加入对于专用 `hmp_ai` conda 虚拟环境 (Python 3.10.20) 的强制使用提示，防止第三方库在高版本 Python 下产生不可预测的崩溃。
4. **补充 Windows 部署流程**：目前 README 缺失完整的生产部署手册，需要专门为 Windows 服务器设计一套以 Nginx (前端反代) + Uvicorn 进程管理 (后端常驻) 的部署逻辑，便于生产落地。

## 详细设计

### 1. 修改 `README.md` 基础环境与配置说明
- **运行环境更新**：在 `## ⚙️ 运行环境与先决条件 (Prerequisites)` 中，明确注明必须使用 Conda 激活 `hmp_ai` 虚拟环境，并明确注明 Python 解释器推荐使用 `D:\ProgramData\miniconda3\envs\hmp_ai\python.exe` 路径。
- **配置与初始化修正**：
  - 在快速启动的第一步中，将数据库名改为 `happy_doudizhu`。
  - 修改数据库初始化过程，直接指导运行 `D:\ProgramData\miniconda3\envs\hmp_ai\python.exe scripts/create_db.py` 来一键安全建库和初始化表结构。
  - 修正 `.env` 示例文件中的 `DB_NAME` 从 `hmp_websocket` 为 `happy_doudizhu`。

### 2. 增加 Windows 部署与生产运行指南
在文档的末尾新增一个顶层章节：`## 部署与生产运行指南 (Windows Deployment Guide)`。

本节内容设计包含：
- **2.1 后端后台常驻与开机启动**：
  - 介绍如何使用 `NSSM` (Non-Sucking Service Manager) 将后端注册为 Windows 服务。
  - 提供 NSSM 的注册参数配置（Path 指向 Python 路径，Startup directory 指向 `backend` 目录，Arguments 指向 `main.py`）。
  - 或者提供基于 Windows PowerShell 编写的无控制台启动脚本。
- **2.2 前端生产环境构建**：
  - 说明如何运行 `npm run build`，以及如何清理、打包生成 `dist` 目录。
- **2.3 Windows Nginx 反向代理配置**：
  - 提供用于 Windows 下 Nginx 的 `nginx.conf` 核心配置文件示例，实现：
    - 前端静态文件托管（指向 `frontend/dist`）。
    - 代理后端 REST API `/api` -> `http://127.0.0.1:18088`。
    - 代理 WebSocket 的长连接 `/ws` -> `ws://127.0.0.1:18088`。
    - 支持较大的上传文件限制 `client_max_body_size`。

## 验证与发布

1. **链接可访问性检查**：检查文档内出现的文件跳转链接，确认使用 `file:///` 格式能精确导向项目中的各配置路径。
2. **命令及配置语法合法性校验**：确认添加的 Nginx 配置文件语法没有明显的错误，所涉及的 Windows 命令行和 Python 环境路径完全符合本项目开发指南。
