"""
日志模块

提供统一的日志接口，支持文件和控制台输出
日志级别可通过环境变量 LOG_LEVEL 配置
"""

import logging
import os
import sys
from pathlib import Path
from typing import Optional

# 默认日志级别，可通过环境变量覆盖
DEFAULT_LOG_LEVEL = "INFO"
ENV_LOG_LEVEL = "LOG_LEVEL"


def _ensure_utf8_stdout():
    """确保 stdout 使用 UTF-8 编码"""
    if sys.platform == "win32":
        try:
            if hasattr(sys.stdout, "reconfigure"):
                sys.stdout.reconfigure(encoding="utf-8")
            if hasattr(sys.stderr, "reconfigure"):
                sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass


class Logger:
    """日志包装器"""

    _instances: dict = {}

    def __init__(self, name: str, level: str = "INFO", log_file: Optional[str] = None):
        _ensure_utf8_stdout()

        self.logger = logging.getLogger(name)
        self.logger.setLevel(getattr(logging, level.upper()))

        # 避免重复添加handler
        if self.logger.handlers:
            return

        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        # 控制台handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

        # 文件handler
        if log_file:
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)

    @classmethod
    def get_logger(
        cls, name: str, level: str = "INFO", log_file: Optional[str] = None
    ) -> logging.Logger:
        """获取日志实例"""
        if name not in cls._instances:
            cls._instances[name] = cls(name, level, log_file)
        return cls._instances[name].logger


def get_logger(
    name: str, level: Optional[str] = None, log_file: Optional[str] = None
) -> logging.Logger:
    """便捷函数：获取日志实例
    
    日志级别优先级：参数 > 环境变量 LOG_LEVEL > 默认值 INFO
    
    Args:
        name: 日志器名称
        level: 日志级别（可选，默认从环境变量读取）
        log_file: 日志文件路径（可选）
        
    Returns:
        logging.Logger: 配置好的日志实例
    """
    if level is None:
        level = os.environ.get(ENV_LOG_LEVEL, DEFAULT_LOG_LEVEL)
    return Logger.get_logger(name, level, log_file)
