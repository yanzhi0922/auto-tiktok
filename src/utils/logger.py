# -*- coding: utf-8 -*-
"""
日志配置工具
提供统一的日志配置和管理功能
"""

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from src.utils.redaction import redact_text


class RedactingFormatter(logging.Formatter):
    """统一脱敏日志消息，避免 Key、Bearer token 和签名 URL 落盘。"""

    def format(self, record: logging.LogRecord) -> str:
        rendered = super().format(record)
        return redact_text(rendered)


def setup_logger(
    name: str = "auto_tiktok",
    level: str = "INFO",
    log_file: Optional[str] = None,
    format_string: Optional[str] = None,
    log_level: Optional[str] = None,
    configure_root: bool = False,
) -> logging.Logger:
    """
    配置并返回日志记录器

    Args:
        name: 日志记录器名称
        level: 日志级别（DEBUG, INFO, WARNING, ERROR, CRITICAL）
        log_file: 日志文件路径，None 表示不写入文件
        format_string: 日志格式字符串

    Returns:
        配置好的日志记录器

    Example:
        >>> logger = setup_logger("my_app", "DEBUG", "logs/app.log")
        >>> logger.info("应用启动")
    """
    if log_level is not None:
        level = log_level

    logger = logging.getLogger(name)
    resolved_level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(resolved_level)

    if format_string is None:
        format_string = (
            "%(asctime)s | %(levelname)-8s | %(name)s | "
            "%(filename)s:%(lineno)d | %(message)s"
        )

    formatter = RedactingFormatter(format_string, datefmt="%Y-%m-%d %H:%M:%S")

    def reset_handlers(target_logger: logging.Logger) -> None:
        if target_logger.handlers:
            for handler in list(target_logger.handlers):
                target_logger.removeHandler(handler)
                handler.close()

    def attach_handlers(target_logger: logging.Logger) -> None:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(resolved_level)
        console_handler.setFormatter(formatter)
        target_logger.addHandler(console_handler)

        if log_file:
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)

            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setLevel(resolved_level)
            file_handler.setFormatter(formatter)
            target_logger.addHandler(file_handler)

    reset_handlers(logger)
    attach_handlers(logger)

    logger.propagate = False

    if configure_root:
        root_logger = logging.getLogger()
        root_logger.setLevel(resolved_level)
        reset_handlers(root_logger)
        attach_handlers(root_logger)

    return logger


def get_logger(name: str) -> logging.Logger:
    """
    获取已配置的日志记录器

    Args:
        name: 日志记录器名称

    Returns:
        日志记录器
    """
    return logging.getLogger(name)


class TaskLogger:
    """任务日志记录器，用于跟踪任务执行过程"""

    def __init__(self, task_name: str, log_file: Optional[str] = None):
        """
        初始化任务日志记录器

        Args:
            task_name: 任务名称
            log_file: 日志文件路径
        """
        self.task_name = task_name
        self.logger = setup_logger(f"task.{task_name}", log_file=log_file)
        self.start_time: Optional[datetime] = None
        self.steps: list[dict[str, Any]] = []

    def start(self, message: str = "任务开始"):
        """记录任务开始"""
        self.start_time = datetime.now()
        self.logger.info(f"[{self.task_name}] {message}")

    def step(self, step_name: str, status: str = "进行中", details: str = ""):
        """
        记录任务步骤

        Args:
            step_name: 步骤名称
            status: 状态（进行中、完成、失败）
            details: 详细信息
        """
        step_info = {
            "name": step_name,
            "status": status,
            "time": datetime.now().isoformat(),
            "details": details,
        }
        self.steps.append(step_info)

        log_message = f"[{self.task_name}] 步骤: {step_name} - {status}"
        if details:
            log_message += f" | {details}"

        if status == "失败":
            self.logger.error(log_message)
        else:
            self.logger.info(log_message)

    def complete(self, message: str = "任务完成"):
        """记录任务完成"""
        if self.start_time:
            duration = (datetime.now() - self.start_time).total_seconds()
            self.logger.info(f"[{self.task_name}] {message} | 耗时: {duration:.2f}秒")
        else:
            self.logger.info(f"[{self.task_name}] {message}")

    def error(self, error_message: str, exception: Optional[Exception] = None):
        """记录错误"""
        if exception:
            self.logger.error(
                f"[{self.task_name}] 错误: {error_message}", exc_info=exception
            )
        else:
            self.logger.error(f"[{self.task_name}] 错误: {error_message}")

    def get_summary(self) -> dict:
        """获取任务摘要"""
        summary = {
            "task_name": self.task_name,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "steps": self.steps,
            "total_steps": len(self.steps),
            "completed_steps": sum(1 for s in self.steps if s["status"] == "完成"),
            "failed_steps": sum(1 for s in self.steps if s["status"] == "失败"),
        }

        if self.start_time:
            summary["duration_seconds"] = (
                datetime.now() - self.start_time
            ).total_seconds()

        return summary


class ProgressTracker:
    """进度跟踪器"""

    def __init__(self, total: int, description: str = "进度"):
        """
        初始化进度跟踪器

        Args:
            total: 总任务数
            description: 进度描述
        """
        self.total = total
        self.description = description
        self.current = 0
        self.logger = get_logger("progress")

    def update(self, increment: int = 1, message: str = ""):
        """
        更新进度

        Args:
            increment: 增量
            message: 附加消息
        """
        self.current += increment
        percentage = (self.current / self.total) * 100

        log_message = (
            f"[{self.description}] {self.current}/{self.total} ({percentage:.1f}%)"
        )

        if message:
            log_message += f" | {message}"

        self.logger.info(log_message)

    def complete(self):
        """标记完成"""
        self.logger.info(f"[{self.description}] 完成！共处理 {self.total} 个任务")
