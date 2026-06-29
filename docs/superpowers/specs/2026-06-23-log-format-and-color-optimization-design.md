# 2026-06-23 HMP WS Service 日志定位与彩色格式化设计规范

为了在日常开发、测试及生产运维中更快捷、精确地定位日志打印源码位置，并提供对开发人员更友好的控制台视觉分级，本规范对 HMP WS Service 日志输出结构和配置体系进行整体重构与打磨。

---

## 🎯 业务与系统目标

1. **源码精准定位**：在所有日志行输出中，统一追加 `[文件名:行号 - 函数名]`，能够一秒定位到触发日志的代码源头。
2. **控制台分级彩色渲染**：控制台输出根据 `DEBUG/INFO/WARNING/ERROR/CRITICAL` 五个级别分配不同的 ANSI 颜色，高亮区分错误和警告，提升开发时扫描日志的效率。
3. **文件日志纯净防乱码**：写入 `log/hmp_ws_service.log` 文件的日志剔除所有控制台 ANSI 颜色代码，防止查看文件时出现 `\x1b[31m` 等杂乱字符，保证其干净可搜。
4. **统一 Root 拦截与精细过滤**：将此重构应用于全局 Root Logger，确保不仅是项目代码、第三方的 HTTP 访问和框架底层日志也遵循此定位，且依旧屏蔽 `aiormq` 等嘈杂的心跳调试。

---

## 🏗️ 详细方案设计

### 1. 新增 `ColorFormatter` 格式化器

在 `main.py` 的日志配置块中，新声明一个继承自标准 `logging.Formatter` 的自定义类，专门服务于控制台。其负责在输出时拼接 ANSI 前景颜色和重置字符：

```python
class ColorFormatter(logging.Formatter):
    """自定义控制台彩色日志格式化器"""
    GREY = "\x1b[38;21m"      # DEBUG
    GREEN = "\x1b[32;21m"     # INFO
    YELLOW = "\x1b[33;21m"    # WARNING
    RED = "\x1b[31;21m"       # ERROR
    BOLD_RED = "\x1b[31;1m"   # CRITICAL
    RESET = "\x1b[0m"         # 恢复终端默认颜色
    
    # 格式模版：包含时间、级别、[文件名:行号 - 函数名] 以及具体日志消息
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
```

### 2. 双 Formatter 与 Handler 解耦重构

移除原本的 `logging.basicConfig(...)` 全局调用，改用对 `Root Logger` 的精细控制：

```python
# 1. 自动创建日志目录并配置物理路径
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "log")
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)
log_path = os.path.join(LOG_DIR, "hmp_ws_service.log")

# 2. 声明物理文件输出格式与 Handler (无 ANSI 转义纯文本)
file_format = "%(asctime)s [%(levelname)s] [%(filename)s:%(lineno)d - %(funcName)s]: %(message)s"
file_formatter = logging.Formatter(file_format)
file_handler = RotatingFileHandler(log_path, maxBytes=10*1024*1024, backupCount=5, encoding="utf-8")
file_handler.setFormatter(file_formatter)
file_handler.setLevel(logging.DEBUG)

# 3. 声明控制台输出 Handler (彩色)
console_handler = logging.StreamHandler()
console_handler.setFormatter(ColorFormatter())
console_handler.setLevel(logging.DEBUG)

# 4. 配置 Root Logger 属性并进行 Handlers 绑定
root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)

# 清除 basicConfig 或其他地方预先挂载的默认 Handler 规避重复日志打印
for h in root_logger.handlers[:]:
    root_logger.removeHandler(h)
    
root_logger.addHandler(file_handler)
root_logger.addHandler(console_handler)

# 5. 获取项目主 Logger
logger = logging.getLogger("hmp_ws_service")
```

---

## 🧪 验证与测试方案

### 1. 本地启动自测
运行 `python main.py` 观察控制台输出：
- 确认启动日志中含有诸如 `[main.py:100 - lifespan]` 等精确的文件和行号定位标记。
- 确认不同日志级别（DEBUG、INFO、WARNING、ERROR）在终端中呈现出不同的颜色（如 INFO 为绿色，ERROR 为红色等）。
- 打开 `log/hmp_ws_service.log` 文本文件，确保里面不含有 `\x1b[32m` 等乱码符号，字符表现干净端正。

### 2. 单元测试跑通
运行 `pytest` 确认日志库重构并未影响原有的接口路由测试、大文件上传测试与站内信测试：
```bash
python -m pytest
```
