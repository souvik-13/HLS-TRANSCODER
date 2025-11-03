"""
Logging utilities with Rich integration.

This module provides logging setup and utilities for beautiful console output.
"""

import logging
import time
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Optional, TypeVar, cast

from rich.console import Console
from rich.logging import RichHandler

# Type variable for generic function decoration
F = TypeVar("F", bound=Callable[..., Any])

# Global reference to active monitor for log integration
_active_monitor: Optional[Any] = None


def set_active_monitor(monitor: Optional[Any]) -> None:
    """
    Set the active TranscodingMonitor for log integration.

    Args:
        monitor: TranscodingMonitor instance or None to clear
    """
    global _active_monitor
    _active_monitor = monitor


def get_active_monitor() -> Optional[Any]:
    """
    Get the active TranscodingMonitor.

    Returns:
        Active monitor or None
    """
    return _active_monitor


class MonitorIntegratedHandler(logging.Handler):
    """
    Custom log handler that integrates with TranscodingMonitor.

    When a monitor is active, logs are displayed in the monitor UI.
    Otherwise, logs are printed normally via RichHandler.
    """

    def __init__(self, rich_handler: RichHandler):
        """
        Initialize the handler.

        Args:
            rich_handler: Fallback RichHandler for when no monitor is active
        """
        super().__init__()
        self.rich_handler = rich_handler
        self.setFormatter(rich_handler.formatter)
        self.setLevel(rich_handler.level)

    def emit(self, record: logging.LogRecord) -> None:
        """
        Emit a log record.

        Args:
            record: Log record to emit
        """
        monitor = get_active_monitor()

        if monitor is not None and hasattr(monitor, "add_log"):
            # Format the message
            try:
                msg = self.format(record)
                # Create a simple formatted message for the monitor
                level_colors = {
                    "DEBUG": "dim",
                    "INFO": "cyan",
                    "WARNING": "yellow",
                    "ERROR": "red",
                    "CRITICAL": "bold red",
                }
                color = level_colors.get(record.levelname, "white")
                formatted = f"[{color}]{record.levelname}[/{color}]: {record.getMessage()}"
                monitor.add_log(formatted)
            except Exception:
                # Fallback to rich handler if monitor fails
                self.rich_handler.emit(record)
        else:
            # No monitor active, use rich handler
            self.rich_handler.emit(record)


def setup_logger(
    name: str = "hls_transcoder",
    level: str = "INFO",
    log_file: Optional[Path] = None,
    verbose: bool = False,
    console: Optional[Console] = None,
) -> logging.Logger:
    """
    Setup logger with Rich handler and optional file output.

    Features:
    - Beautiful console output with Rich
    - Optional file logging for debugging
    - Performance metrics tracking
    - Structured log format
    - Integration with TranscodingMonitor

    Args:
        name: Logger name (use "hls_transcoder" to match package name)
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional path to log file
        verbose: Enable verbose output with file paths
        console: Rich console to use (creates new if None)

    Returns:
        Configured logger instance
    """
    # Get the root logger for the application package
    # Use "hls_transcoder" as the base to match Python package naming
    logger = logging.getLogger("hls_transcoder")

    # Set level
    log_level = logging.DEBUG if verbose else getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(log_level)

    # Remove existing handlers to avoid duplicates
    logger.handlers.clear()

    # Console handler with Rich
    rich_console = console or Console()
    rich_handler = RichHandler(
        console=rich_console,
        rich_tracebacks=True,
        markup=True,
        show_time=True,
        show_path=verbose,
        omit_repeated_times=False,
        level=log_level,  # Set handler level
    )
    rich_handler.setFormatter(logging.Formatter("%(message)s", datefmt="[%X]"))

    # Wrap with monitor-integrated handler
    monitor_handler = MonitorIntegratedHandler(rich_handler)
    monitor_handler.setLevel(log_level)
    logger.addHandler(monitor_handler)

    # File handler for detailed logs
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, mode="w")  # Overwrite mode
        file_handler.setLevel(log_level)  # Set handler level
        file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        logger.addHandler(file_handler)

    # Prevent propagation to root logger to avoid duplicate logs
    logger.propagate = False

    return logger


def log_performance(logger: Optional[logging.Logger] = None) -> Callable[[F], F]:
    """
    Decorator to log function execution time.

    Args:
        logger: Logger instance to use (creates default if None)

    Returns:
        Decorated function that logs execution time
    """
    if logger is None:
        logger = logging.getLogger("hls_transcoder")

    def decorator(func: F) -> F:
        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.time()
            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start
                logger.info(f"[cyan]{func.__name__}[/cyan] completed in {duration:.2f}s")
                return result
            except Exception as e:
                duration = time.time() - start
                logger.error(f"[red]{func.__name__}[/red] failed after {duration:.2f}s: {str(e)}")
                raise

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.time()
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start
                logger.info(f"[cyan]{func.__name__}[/cyan] completed in {duration:.2f}s")
                return result
            except Exception as e:
                duration = time.time() - start
                logger.error(f"[red]{func.__name__}[/red] failed after {duration:.2f}s: {str(e)}")
                raise

        # Check if function is async
        import inspect

        if inspect.iscoroutinefunction(func):
            return cast(F, async_wrapper)
        else:
            return cast(F, sync_wrapper)

    return decorator


# Create default logger
default_logger = setup_logger()


def get_logger(name: str = "hls_transcoder") -> logging.Logger:
    """
    Get a logger instance.

    This function returns a logger that inherits settings from the
    root "hls_transcoder" logger configured by setup_logger().

    When modules call get_logger(__name__), the __name__ will be like
    "hls_transcoder.module.submodule", which automatically inherits from
    the parent "hls_transcoder" logger.

    Args:
        name: Logger name (typically __name__ from the calling module)

    Returns:
        Logger instance that inherits from root logger
    """
    return logging.getLogger(name)
