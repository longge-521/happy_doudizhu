# 2026-06-23 HMP WS Service 日志模块基础设施层解耦设计规范

本规范旨在将日志系统的配置、格式化（控制台彩色/文件纯文本）及第三方日志级别过滤逻辑，从服务入口 `main.py` 中解耦，并沉淀到系统的 **基础设施层 (Infrastructure Layer)**。以提高代码的内聚性、单一职责性以及在其他独立脚本和测试工具中的复用能力。

---

## 🎯 业务与系统目标

1. **入口精简 (SRP)**：使主入口 `main.py` 仅保留启动、生命周期编排与核心路由声明，剥离大段具体的日志格式化与装配逻辑。
2. **沉淀基础设施层 (DDD)**：按 DDD 规范，将 Logging 集成划归为基础设施，存放在新模块 `app/infrastructure/logging/` 下。
3. **全局复用**：让独立的单元测试、数据迁移、后台离线脚本能够无阻碍地从基础设施层导入相同的日志配置。
4. **屏蔽心跳日志**：在日志装配内统一配置并限制第三方库 `aiormq` 和 `aio_pika` 的 DEBUG 心跳帧日志输出。

---

## 📂 目录与文件变动设计

### 1. 结构划分
- **NEW**: `app/infrastructure/logging/__init__.py` （空文件，声明为 Python 包）
- **NEW**: `app/infrastructure/logging/setup.py` （包含日志格式化器与 `setup_logging` 初始化器）
- **MODIFY**: `main.py` （简化日志导入与装配逻辑）

---

## 🏗️ 详细方案设计

### 1. 日志基础设施组件：`app/infrastructure/logging/setup.py`

在基础设施层的 logging 包中，定义自定义 `ColorFormatter` 与 `setup_logging()` 入口函数。为保证绝对路径在不同运行入口（如 `main.py` 或测试脚本）下的通用性，利用此模块位置动态计算出项目根目录 `project_root`，并在根目录下统一归档物理日志文件 `log/hmp_ws_service.log`。

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
    # 动态定位项目根目录，保障任何脚本入口在加载此函数时，生成的 log 目录均在根目录下
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(current_dir, "..", "..", ".."))
    
    log_dir = os.path.join(project_root, "log")
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    log_path = os.path.join(log_dir, "hmp_ws_service.log")

    # 1. 声明纯文本物理文件 Formatter 与 Handler (无 ANSI 转义纯文本)
    file_format = "%(asctime)s [%(levelname)s] [%(filename)s:%(lineno)d - %(funcName)s]: %(message)s"
    file_formatter = logging.Formatter(file_format)
    file_handler = RotatingFileHandler(log_path, maxBytes=10*1024*1024, backupCount=5, encoding="utf-8")
    file_handler.setFormatter(file_formatter)
    file_handler.setLevel(default_level)

    # 2. 声明彩色控制台 Formatter 与 Handler (彩色)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(ColorFormatter())
    console_handler.setLevel(default_level)

    # 3. 注入全局 Root Logger，并清理已有 handlers 规避重复打印
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

### 2. 入口文件重构：`main.py`

在 `main.py` 中，移除大段的日志逻辑，简化为：

```python
# 加载环境变量
load_dotenv()

# 初始化全局日志（从基础设施层加载）
from app.infrastructure.logging.setup import setup_logging
setup_logging()

logger = logging.getLogger("hmp_ws_service")
```

---

## 🧪 验证与测试方案

### 1. 单元测试自测
通过运行 `pytest` 来验证：
- 确认现有的 12 项单元测试 100% 通过，没有任何因日志模块重构和分层导致的导入错误。
- 特别是在 `tests/test_log_formatter.py` 中，修改它的导入来源为 `from app.infrastructure.logging.setup import ColorFormatter` 重新测试，确保测试依然绿灯通过。

### 2. 本地服务启动与文件日志验证
启动服务 `python main.py`：
- 确认启动日志中，控制台仍然以彩色呈现，物理日志文件 `log/hmp_ws_service.log` 仍然正常追加，且不带任何 ANSI 乱码。
- 确认第三方库心跳日志依然被静默屏蔽。
