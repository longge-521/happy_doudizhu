# HMP WS Service 日志模块基础设施层解耦实施计划 (Implementation Plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将日志配置与彩色格式化逻辑从入口 `main.py` 中解耦，转移到独立的 `app/infrastructure/logging/` 包中，使主入口简洁规范并实现日志模块在全局范围的可复用性。

**Architecture:** 新建 `app/infrastructure/logging/` 包，定义 `setup_logging` 接口。在 `main.py` 和测试套件中改从新包导入并完成全局日志装配，利用绝对路径动态计算保证不同运行场景下的路径鲁棒性。

**Tech Stack:** Python 3.10+, Standard `logging` library, `pytest`

## Global Constraints

- 任何新建文件的操作应完全遵循 DDD 分层规范。
- 物理日志输出目录必须仍然保持在项目根目录的 `log/` 文件夹下。
- 第三方驱动（aiormq, aio_pika）的警告限制必须同样随之迁移并在解耦包内生效。
- 必须跑通所有单元测试保障系统零故障运行。

---

### Task 1: 修改单元测试，使其从基础设施层 logging 包中加载格式化器

**Files:**
- Modify: `tests/test_log_formatter.py`

**Interfaces:**
- Consumes: 无
- Produces: 声明单元测试的测试靶标为 `app.infrastructure.logging.setup.ColorFormatter`。

- [ ] **Step 1: 修改测试用例的导入路径**

  修改 `tests/test_log_formatter.py` 的第 6 行为从基础设施包导入：
  ```python
  # 修改前: from main import ColorFormatter
  # 修改后:
  from app.infrastructure.logging.setup import ColorFormatter
  ```

- [ ] **Step 2: 运行测试并确保其失败**

  运行以下命令触发预期的失败（模块未找到）：
  `D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest tests/test_log_formatter.py -v`
  
  **预期结果**：FAIL (抛出 `ModuleNotFoundError: No module named 'app.infrastructure.logging'`)

---

### Task 2: 建立基础设施层日志解耦模块

**Files:**
- Create: `app/infrastructure/logging/__init__.py`
- Create: `app/infrastructure/logging/setup.py`
- Test: `tests/test_log_formatter.py`

**Interfaces:**
- Consumes: 无
- Produces: `app.infrastructure.logging.setup` 模块，包含 `ColorFormatter` 与 `setup_logging`。

- [ ] **Step 1: 创建 app/infrastructure/logging/__init__.py**

  在对应路径下建立一个空文件，确保 Python 将其识别为模块包。

- [ ] **Step 2: 创建 app/infrastructure/logging/setup.py**

  新建文件并写入完整的日志模块解耦代码：
  ```python
  import os
  import logging
  from logging.handlers import RotatingFileHandler

  class ColorFormatter(logging.Formatter):
      """自定义控制台彩色日志格式化器"""
      GREY = "\x1b[38;21m"      # DEBUG
      GREEN = "\x1b[32;21m"     # INFO
      YELLOW = "\x1b[33;21m"    # WARNING
      RED = "\x1b[31;21m"       # ERROR
      BOLD_RED = "\x1b[31;1m"   # CRITICAL
      RESET = "\x1b[0m"
      
      FORMAT_TEMPLATE = "%(asctime)s [%(levelname)s] [%(filename)s:%(lineno)d - %(funcName)s]: %(message)s"
      
      LEVEL_COLORS = {
          logging.DEBUG: GREY,
          logging.INFO: GREEN,
          logging.WARNING: YELLOW,
          logging.ERROR: RED,
          logging.CRITICAL: BOLD_RED
      }

      def format(self, record):
          color = self.LEVEL_COLORS.get(record.levelno, self.RESET)
          log_fmt = color + self.FORMAT_TEMPLATE + self.RESET
          formatter = logging.Formatter(log_fmt)
          return formatter.format(record)


  def setup_logging(default_level=logging.DEBUG):
      """全局初始化日志系统，解耦控制台与文件的 Formatter，并配置第三方库过滤"""
      # 动态计算根目录，防止多入口下路径发生偏移
      current_dir = os.path.dirname(os.path.abspath(__file__))
      project_root = os.path.abspath(os.path.join(current_dir, "..", "..", ".."))
      
      log_dir = os.path.join(project_root, "log")
      if not os.path.exists(log_dir):
          os.makedirs(log_dir)

      log_path = os.path.join(log_dir, "hmp_ws_service.log")

      # 1. 声明纯文本物理文件 Formatter 与 Handler
      file_format = "%(asctime)s [%(levelname)s] [%(filename)s:%(lineno)d - %(funcName)s]: %(message)s"
      file_formatter = logging.Formatter(file_format)
      file_handler = RotatingFileHandler(log_path, maxBytes=10*1024*1024, backupCount=5, encoding="utf-8")
      file_handler.setFormatter(file_formatter)
      file_handler.setLevel(default_level)

      # 2. 声明彩色控制台 Formatter 与 Handler
      console_handler = logging.StreamHandler()
      console_handler.setFormatter(ColorFormatter())
      console_handler.setLevel(default_level)

      # 3. 注入全局 Root Logger
      root_logger = logging.getLogger()
      root_logger.setLevel(default_level)

      for h in root_logger.handlers[:]:
          root_logger.removeHandler(h)

      root_logger.addHandler(file_handler)
      root_logger.addHandler(console_handler)

      # 4. 屏蔽第三方 AMQP 驱动嘈杂的 DEBUG 心跳及交互日志
      logging.getLogger("aiormq").setLevel(logging.WARNING)
      logging.getLogger("aio_pika").setLevel(logging.WARNING)
  ```

- [ ] **Step 3: 重新运行单元测试并验证通过**

  运行测试命令确认新模块功能完备：
  `D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest tests/test_log_formatter.py -v`
  
  **预期结果**：1 passed

- [ ] **Step 4: 提交新增的解耦模块文件与测试更新**

  ```bash
  git add app/infrastructure/logging/__init__.py app/infrastructure/logging/setup.py tests/test_log_formatter.py
  git commit -m "feat(log): move logging formatter and setup to infrastructure layer"
  ```

---

### Task 3: 在 main.py 中引入基础设施日志服务并进行最终验证

**Files:**
- Modify: `main.py`
- Test: 全局单元测试

**Interfaces:**
- Consumes: `app/infrastructure/logging/setup.py`
- Produces: 重构完成的系统主入口

- [ ] **Step 1: 重构 main.py，移除旧日志代码并引入新 setup_logging**

  修改 `main.py` 的日志配置段（第 24 行至第 73 行）：
  ```python
  # 修改前: 自定义 ColorFormatter 类与 Handlers 配置代码
  # 修改后:
  # 初始化全局日志系统 (从基础设施层导入并装配)
  from app.infrastructure.logging.setup import setup_logging
  setup_logging()

  logger = logging.getLogger("hmp_ws_service")
  ```

- [ ] **Step 2: 运行全部单元测试以保证向后兼容性**

  验证整体系统状态：
  `D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest`
  
  **预期结果**：12 passed

- [ ] **Step 3: 检查物理日志文件是否正常输出**

  检查日志文件的末尾输出以确保没有乱码且写入正常：
  `Get-Content log/hmp_ws_service.log -Tail 10`
  
  **预期结果**：日志行具有 `[文件名:行号 - 函数名]` 定位数据，且不包含 ANSI 彩色字符。

- [ ] **Step 4: 提交主入口重构改动**

  ```bash
  git add main.py
  git commit -m "refactor(log): clean up main.py by decoupling logging setup"
  ```
