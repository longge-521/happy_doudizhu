import logging
import pytest

def test_color_formatter_format():
    # 尝试导入我们计划在基础设施包中实现的 ColorFormatter
    from app.infrastructure.logging.setup import ColorFormatter
    
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
