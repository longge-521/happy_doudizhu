# 数据库配置更改与建表设计规约 (2026-07-07)

本规约旨在变更当前系统的数据库名称配置，并在本地 MySQL 中自动创建新的数据库及对应的所有数据表。

## 目标与背景

由于业务需求，需要将当前的数据库名称由默认的 `hmp_ws_service` 修改为游戏项目名称 `happy_doudizhu`。为保证新环境或现有环境能够无缝切换，我们需要实现以下目标：
1. 更新后端配置以读取新的数据库名称。
2. 自动化地完成对该新数据库的建库和建表。

## 详细设计

### 1. 配置文件修改
- **文件**：`backend/.env`
- **更改**：
  将 `DB_NAME=hmp_ws_service` 修改为 `DB_NAME=happy_doudizhu`。

### 2. 自动建库与建表脚本
由于在数据库不存在时直接调用 `create_engine(..., database='happy_doudizhu')` 会发生 "Unknown database" 错误，我们需要在初始化前先以不指定具体数据库的方式连接 MySQL 实例。

- **脚本路径**：`backend/scripts/create_db.py`
- **实现逻辑**：
  1. 导入 `dotenv` 并加载 `backend/.env`。
  2. 读取数据库主机的基本连接参数（`DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`）以及要创建的数据库名称 `DB_NAME`（值为 `happy_doudizhu`）。
  3. 构造基础连接 URL（不包含数据库名）：`mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/`。
  4. 使用 SQLAlchemy 的 `create_engine` 建立临时连接。
  5. 执行 SQL 语句：
     ```sql
     CREATE DATABASE IF NOT EXISTS happy_doudizhu CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
     ```
  6. 数据库创建成功后，导入 `backend/app/infrastructure/database/session.py` 中的 `init_db()` 方法。
  7. 调用 `init_db()` 进行完整的表结构创建与基准迁移。

## 验证与回滚方案

### 验证方法
1. 查看 `backend/.env` 确认 `DB_NAME` 是否已被更新。
2. 运行 `python scripts/create_db.py` 并检查终端输出，确保无异常抛出。
3. 运行现有的后端单元测试 `python -m pytest backend/tests`，确保配置变更后测试仍能通过。

### 回滚方案
1. 将 `backend/.env` 中的 `DB_NAME` 恢复为 `hmp_ws_service`。
2. 手动在 MySQL 中删除新创建的 `happy_doudizhu` 数据库（若有必要）：
   ```sql
   DROP DATABASE IF EXISTS happy_doudizhu;
   ```
