"""
Custom exceptions for HLS transcoder.

This module defines the exception hierarchy used throughout the application.
It also provides error recovery mechanisms for graceful degradation.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Coroutine, Optional, TypeVar

T = TypeVar("T")


class TranscoderError(Exception):
    """Base exception for all transcoder errors."""

    pass


class HardwareError(TranscoderError):
    """Hardware acceleration failed or is unavailable."""

    pass


class MediaInspectionError(TranscoderError):
    """Failed to inspect media file."""

    pass


class TranscodingError(TranscoderError):
    """Transcoding process failed."""

    pass


class ValidationError(TranscoderError):
    """Output validation failed."""

    pass


class ConfigurationError(TranscoderError):
    """Configuration is invalid or missing."""

    pass


class FFmpegError(TranscoderError):
    """FFmpeg command execution failed."""

    def __init__(self, message: str, command: list[str] | None = None, stderr: str | None = None):
        """
        Initialize FFmpeg error with command details.

        Args:
            message: Error message
            command: FFmpeg command that failed
            stderr: Standard error output from FFmpeg
        """
        super().__init__(message)
        self.command = command
        self.stderr = stderr


class ProcessTimeoutError(TranscoderError):
    """Process exceeded timeout threshold."""

    def __init__(self, message: str, timeout: float):
        """
        Initialize timeout error.

        Args:
            message: Error message
            timeout: Timeout value in seconds
        """
        super().__init__(message)
        self.timeout = timeout


class RetryableError(TranscoderError):
    """Error that can be retried."""

    pass


class NonRetryableError(TranscoderError):
    """Error that should not be retried."""

    pass


class RecoveryStrategy(str, Enum):
    """Strategy for error recovery."""

    RETRY = "retry"  # Retry the operation
    FALLBACK = "fallback"  # Fall back to alternative method
    SKIP = "skip"  # Skip this operation
    FAIL = "fail"  # Fail immediately


@dataclass
class RecoveryConfig:
    """Configuration for error recovery."""

    max_retries: int = 3
    """Maximum number of retry attempts."""

    retry_delay: float = 1.0
    """Initial delay between retries in seconds."""

    exponential_backoff: bool = True
    """Use exponential backoff for retry delays."""

    backoff_multiplier: float = 2.0
    """Multiplier for exponential backoff."""

    max_retry_delay: float = 60.0
    """Maximum delay between retries in seconds."""

    timeout: Optional[float] = None
    """Timeout for each operation in seconds."""

    cleanup_on_failure: bool = True
    """Clean up partial output on failure."""

    hardware_fallback_enabled: bool = True
    """Enable fallback to software encoding on hardware failure."""

    skip_on_permanent_failure: bool = False
    """Skip task instead of failing on permanent errors."""


@dataclass
class RecoveryAttempt:
    """Record of a recovery attempt."""

    attempt_number: int
    """Attempt number (1-indexed)."""

    strategy: RecoveryStrategy
    """Recovery strategy used."""

    error: Exception
    """Error that triggered recovery."""

    timestamp: float = field(default_factory=time.time)
    """Timestamp of the attempt."""

    success: bool = False
    """Whether the attempt succeeded."""

    duration: float = 0.0
    """Duration of the attempt in seconds."""

    fallback_method: Optional[str] = None
    """Alternative method used if fallback strategy."""


@dataclass
class RecoveryResult:
    """Result of error recovery."""

    success: bool
    """Whether recovery succeeded."""

    result: Any = None
    """Result of the operation if successful."""

    error: Optional[Exception] = None
    """Final error if recovery failed."""

    attempts: list[RecoveryAttempt] = field(default_factory=list)
    """History of recovery attempts."""

    total_duration: float = 0.0
    """Total time spent on recovery."""

    strategy_used: Optional[RecoveryStrategy] = None
    """Final strategy that succeeded (if any)."""


class ErrorRecovery:
    """
    Error recovery system for graceful degradation.

    This class provides mechanisms for:
    - Retrying failed operations with exponential backoff
    - Falling back to alternative methods (e.g., software encoding)
    - Handling timeouts
    - Cleaning up partial outputs
    - Tracking recovery attempts
    """

    def __init__(
        self, config: Optional[RecoveryConfig] = None, logger: Optional[logging.Logger] = None
    ):
        """
        Initialize error recovery system.

        Args:
            config: Recovery configuration
            logger: Logger instance
        """
        self.config = config or RecoveryConfig()
        self.logger = logger or logging.getLogger(__name__)
        self._recovery_history: list[RecoveryResult] = []

    async def execute_with_recovery(
        self,
        operation: Callable[..., Coroutine[Any, Any, T]],
        *args: Any,
        fallback_operation: Optional[Callable[..., Coroutine[Any, Any, T]]] = None,
        cleanup_func: Optional[Callable[[], Coroutine[Any, Any, None]]] = None,
        operation_name: str = "operation",
        **kwargs: Any,
    ) -> RecoveryResult:
        """
        Execute an operation with error recovery.

        Args:
            operation: Async operation to execute
            *args: Positional arguments for operation
            fallback_operation: Alternative operation if primary fails
            cleanup_func: Cleanup function for partial outputs
            operation_name: Name of operation for logging
            **kwargs: Keyword arguments for operation

        Returns:
            RecoveryResult with outcome
        """
        start_time = time.time()
        attempts: list[RecoveryAttempt] = []

        self.logger.info(f"Starting {operation_name} with recovery")

        # Try primary operation with retries
        for attempt in range(1, self.config.max_retries + 1):
            try:
                result = await self._execute_with_timeout(operation, *args, **kwargs)

                # Success!
                recovery_result = RecoveryResult(
                    success=True,
                    result=result,
                    attempts=attempts,
                    total_duration=time.time() - start_time,
                    strategy_used=RecoveryStrategy.RETRY if attempt > 1 else None,
                )

                if attempt > 1:
                    self.logger.info(f"{operation_name} succeeded on attempt {attempt}")

                self._recovery_history.append(recovery_result)
                return recovery_result

            except asyncio.TimeoutError as e:
                error = ProcessTimeoutError(
                    f"{operation_name} timed out after {self.config.timeout}s",
                    timeout=self.config.timeout or 0,
                )
                attempts.append(
                    RecoveryAttempt(
                        attempt_number=attempt,
                        strategy=RecoveryStrategy.RETRY,
                        error=error,
                        duration=time.time() - start_time,
                    )
                )
                self.logger.warning(
                    f"{operation_name} timed out on attempt {attempt}/{self.config.max_retries}"
                )

            except Exception as e:
                attempts.append(
                    RecoveryAttempt(
                        attempt_number=attempt,
                        strategy=RecoveryStrategy.RETRY,
                        error=e,
                        duration=time.time() - start_time,
                    )
                )

                # Check if error is retryable
                if isinstance(e, NonRetryableError):
                    self.logger.error(f"{operation_name} failed with non-retryable error: {e}")
                    break

                self.logger.warning(
                    f"{operation_name} failed on attempt {attempt}/{self.config.max_retries}: {e}"
                )

            # Wait before retry (except on last attempt)
            if attempt < self.config.max_retries:
                delay = self._calculate_retry_delay(attempt)
                self.logger.debug(f"Waiting {delay:.2f}s before retry")
                await asyncio.sleep(delay)

        # Primary operation failed, try fallback
        if fallback_operation and self.config.hardware_fallback_enabled:
            self.logger.info(f"Attempting fallback for {operation_name}")
            fallback_start = time.time()
            try:
                result = await self._execute_with_timeout(fallback_operation, *args, **kwargs)

                attempts.append(
                    RecoveryAttempt(
                        attempt_number=len(attempts) + 1,
                        strategy=RecoveryStrategy.FALLBACK,
                        error=attempts[-1].error if attempts else Exception("Unknown error"),
                        success=True,
                        duration=time.time() - fallback_start,
                        fallback_method="software encoding",
                    )
                )

                recovery_result = RecoveryResult(
                    success=True,
                    result=result,
                    attempts=attempts,
                    total_duration=time.time() - start_time,
                    strategy_used=RecoveryStrategy.FALLBACK,
                )

                self.logger.info(f"{operation_name} succeeded using fallback")
                self._recovery_history.append(recovery_result)
                return recovery_result

            except Exception as e:
                self.logger.error(f"Fallback for {operation_name} also failed: {e}")
                attempts.append(
                    RecoveryAttempt(
                        attempt_number=len(attempts) + 1,
                        strategy=RecoveryStrategy.FALLBACK,
                        error=e,
                        duration=time.time() - fallback_start,
                        fallback_method="software encoding",
                    )
                )

        # Cleanup partial outputs
        if cleanup_func and self.config.cleanup_on_failure:
            try:
                self.logger.debug(f"Cleaning up partial output for {operation_name}")
                await cleanup_func()
            except Exception as e:
                self.logger.error(f"Cleanup failed for {operation_name}: {e}")

        # All recovery attempts failed
        final_error = attempts[-1].error if attempts else Exception(f"{operation_name} failed")

        recovery_result = RecoveryResult(
            success=False,
            error=final_error,
            attempts=attempts,
            total_duration=time.time() - start_time,
        )

        self.logger.error(f"{operation_name} failed after all recovery attempts")
        self._recovery_history.append(recovery_result)
        return recovery_result

    async def _execute_with_timeout(
        self,
        operation: Callable[..., Coroutine[Any, Any, T]],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """
        Execute operation with timeout.

        Args:
            operation: Operation to execute
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Operation result

        Raises:
            asyncio.TimeoutError: If operation times out
        """
        if self.config.timeout is None:
            return await operation(*args, **kwargs)

        return await asyncio.wait_for(
            operation(*args, **kwargs),
            timeout=self.config.timeout,
        )

    def _calculate_retry_delay(self, attempt: int) -> float:
        """
        Calculate delay before retry.

        Args:
            attempt: Current attempt number (1-indexed)

        Returns:
            Delay in seconds
        """
        if not self.config.exponential_backoff:
            return self.config.retry_delay

        # Exponential backoff: delay * (multiplier ^ (attempt - 1))
        delay = self.config.retry_delay * (self.config.backoff_multiplier ** (attempt - 1))

        # Cap at max delay
        return min(delay, self.config.max_retry_delay)

    async def cleanup_partial_output(self, output_path: Path) -> None:
        """
        Clean up partial output files.

        Args:
            output_path: Path to partial output
        """
        try:
            if output_path.exists():
                if output_path.is_file():
                    output_path.unlink()
                    self.logger.debug(f"Removed partial file: {output_path}")
                elif output_path.is_dir():
                    # Remove directory and contents
                    import shutil

                    shutil.rmtree(output_path)
                    self.logger.debug(f"Removed partial directory: {output_path}")
        except Exception as e:
            self.logger.error(f"Failed to clean up {output_path}: {e}")
            raise

    def get_recovery_history(self) -> list[RecoveryResult]:
        """
        Get history of recovery attempts.

        Returns:
            List of recovery results
        """
        return self._recovery_history.copy()

    def get_recovery_stats(self) -> dict[str, Any]:
        """
        Get statistics about recovery attempts.

        Returns:
            Dictionary with recovery statistics
        """
        if not self._recovery_history:
            return {
                "total_operations": 0,
                "successful_operations": 0,
                "failed_operations": 0,
                "success_rate": 0.0,
                "retry_success_count": 0,
                "fallback_success_count": 0,
                "total_attempts": 0,
                "average_attempts": 0.0,
            }

        total = len(self._recovery_history)
        successful = sum(1 for r in self._recovery_history if r.success)
        failed = total - successful

        retry_success = sum(
            1
            for r in self._recovery_history
            if r.success and r.strategy_used == RecoveryStrategy.RETRY
        )

        fallback_success = sum(
            1
            for r in self._recovery_history
            if r.success and r.strategy_used == RecoveryStrategy.FALLBACK
        )

        total_attempts = sum(len(r.attempts) for r in self._recovery_history)

        return {
            "total_operations": total,
            "successful_operations": successful,
            "failed_operations": failed,
            "success_rate": (successful / total * 100) if total > 0 else 0.0,
            "retry_success_count": retry_success,
            "fallback_success_count": fallback_success,
            "total_attempts": total_attempts,
            "average_attempts": total_attempts / total if total > 0 else 0.0,
        }

    def reset_history(self) -> None:
        """Clear recovery history."""
        self._recovery_history.clear()


def create_hardware_fallback(
    primary_func: Callable[..., Coroutine[Any, Any, T]],
    fallback_func: Callable[..., Coroutine[Any, Any, T]],
    recovery_config: Optional[RecoveryConfig] = None,
    logger: Optional[logging.Logger] = None,
) -> Callable[..., Coroutine[Any, Any, T]]:
    """
    Create a function with automatic hardware fallback.

    Args:
        primary_func: Primary function (e.g., hardware encoding)
        fallback_func: Fallback function (e.g., software encoding)
        recovery_config: Recovery configuration
        logger: Logger instance

    Returns:
        Wrapped function with fallback support
    """

    async def wrapper(*args: Any, **kwargs: Any) -> T:
        recovery = ErrorRecovery(recovery_config, logger)

        result = await recovery.execute_with_recovery(
            primary_func,
            *args,
            fallback_operation=fallback_func,
            operation_name=primary_func.__name__,
            **kwargs,
        )

        if not result.success:
            # Wrap the original error in TranscodingError
            original_error = result.error or Exception("Operation failed")
            raise TranscodingError(str(original_error)) from original_error

        return result.result

    return wrapper
