# HMP WS Service 日志定位与彩色格式化重构实施计划 (Implementation Plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重构项目主入口的日志模块，引入源码定位 `[文件名:行号 - 函数名]`，并实现控制台彩色分级与物理日志文件纯文本的双 Formatter 隔离，解决心跳日志杂乱及难以定位的问题。

**Architecture:** 自定义 `ColorFormatter` 类继承自 `logging.Formatter`，在控制台 StreamHandler 中注入 ANSI 颜色代码；在 RotatingFileHandler 中依然使用标准 Formatter 输出纯净日志。配置 Root Logger 注入两个 Handlers。

**Tech Stack:** Python 3.10+, Standard `logging` library, `pytest`

## Global Constraints

- 日志文件必须保持轮转归档限额大小 10MB，保留历史备份 5 个。
- 必须继续屏蔽 `aiormq` 和 `aio_pika` 的 DEBUG 级别日志，避免底层心跳泛滥。
- 代码修改必须经过 `pytest` 100% 验证通过后方可合入。

---

### Task 1: 编写单元测试验证 ColorFormatter 格式化逻辑

**Files:**
- Create: `tests/test_log_formatter.py`

**Interfaces:**
- Consumes: 无
- Produces: 验证 `ColorFormatter` 能够输出含有 `[文件名:行号]` 且带有控制台颜色转义符的文本。

- [ ] **Step 1: 编写失败的单元测试**

  新建测试文件 `tests/test_log_formatter.py` 并写入以下内容：
  ```python
  import logging
  import pytest

  def test_color_formatter_format():
      # 尝试导入我们计划在 main.py 中实现的 ColorFormatter
      from main import ColorFormatter
      
      formatter = ColorFormatter()
      record = logging.LogRecord(
          name="test_logger",
          level=logging.INFO,
          pathname="test_file.py",
          lineno=42,
          msg="Hello Test",
          args=(),
          exc_info=None,
          func="test_function"
      )
      
      formatted = formatter.format(record)
      # 验证控制台日志中是否包含了 ANSI 绿色高亮字符
      assert "\x1b[32;21m" in formatted
      # 验证是否包含重置色
      assert "\x1b[0m" in formatted
      # 验证是否包含了 [文件名:行号]
      assert "test_file.py:42" in formatted
  ```

- [ ] **Step 2: 运行测试并确保其失败**

  运行以下命令验证测试是否如期失败：
  `D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest tests/test_log_formatter.py -v`
  
  **预期结果**：FAIL (抛出 `ImportError: cannot import name 'ColorFormatter' from 'main'`)

---

### Task 2: 在 main.py 中实现双 Formatter 隔离日志配置

**Files:**
- Modify: `main.py`
- Test: `tests/test_log_formatter.py`

**Interfaces:**
- Consumes: `tests/test_log_formatter.py`
- Produces: 运行正常的 Root Logger 配置

- [ ] **Step 1: 在 main.py 中实现 ColorFormatter 与解耦日志配置**

  修改 `main.py` 中的第 24 行至第 37 行：
  ```python
  # 使用自定义 ColorFormatter 控制台格式化与标准文件格式化解耦配置
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

  LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "log")
  if not os.path.exists(LOG_DIR):
      os.makedirs(LOG_DIR)

  log_path = os.path.join(LOG_DIR, "hmp_ws_service.log")

  # 声明文件日志 Formatter (无 ANSI 乱码纯文本)
  file_format = "%(asctime)s [%(levelname)s] [%(filename)s:%(lineno)d - %(funcName)s]: %(message)s"
  file_formatter = logging.Formatter(file_format)

  # 创建文件与控制台 Handlers
  file_handler = RotatingFileHandler(log_path, maxBytes=10*1024*1024, backupCount=5, encoding="utf-8")
  file_handler.setFormatter(file_formatter)
  file_handler.setLevel(logging.DEBUG)

  console_handler = logging.StreamHandler()
  console_handler.setFormatter(ColorFormatter())
  console_handler.setLevel(logging.DEBUG)

  # 全局注入 Root Logger
  root_logger = logging.getLogger()
  root_logger.setLevel(logging.DEBUG)

  # 清理默认 handlers 规避重复打印
  for h in root_logger.handlers[:]:
      root_logger.removeHandler(h)

  root_logger.addHandler(file_handler)
  root_logger.addHandler(console_handler)

  logger = logging.getLogger("hmp_ws_service")
  ```

- [ ] **Step 2: 重新运行单元测试并验证通过**

  运行以下命令进行单元测试验证：
  `D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest tests/test_log_formatter.py -v`
  
  **预期结果**：1 passed

- [ ] **Step 3: 运行全部单元测试以保证向后兼容**

  `D:\ProgramData\miniconda3\envs\hmp_ai\python.exe -m pytest`
  
  **预期结果**：12 passed (之前是 11 个，新增了刚才这一项测试)

- [ ] **Step 4: 本地启动服务并肉眼审查**

  启动服务以验证控制台的颜色和日志文件的干净度：
  `D:\ProgramData\miniconda3\envs\hmp_ai\python.exe main.py`
  
  **预期结果**：
  - 控制台以不同颜色交替打印带有 `[main.py:xxx]` 行号的启动日志。
  - 打开 `log/hmp_ws_service.log` 验证里面是否有 ANSI 控制颜色码。必须无任何诸如 `\x1b[32;21m` 的乱码。
  - 检查完毕后 Ctrl+C 关闭服务。

- [ ] **Step 5: 提交所有代码改动**

  ```bash
  git add tests/test_log_formatter.py main.py
  git commit -m "feat(log): support source-code location tracking and console color formatting"
  ```
