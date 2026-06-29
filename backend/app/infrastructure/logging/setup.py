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
