"""
Tests for error recovery system.
"""

import asyncio
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hls_transcoder.utils import (
    ErrorRecovery,
    NonRetryableError,
    ProcessTimeoutError,
    RecoveryConfig,
    RecoveryStrategy,
    RetryableError,
    TranscodingError,
    create_hardware_fallback,
)


# === Fixtures ===


@pytest.fixture
def recovery_config():
    """Create test recovery configuration."""
    return RecoveryConfig(
        max_retries=3,
        retry_delay=0.1,  # Short delay for tests
        exponential_backoff=True,
        backoff_multiplier=2.0,
        max_retry_delay=1.0,
        timeout=5.0,
        cleanup_on_failure=True,
        hardware_fallback_enabled=True,
    )


@pytest.fixture
def error_recovery(recovery_config):
    """Create error recovery instance."""
    return ErrorRecovery(recovery_config)


@pytest.fixture
def temp_output_file(tmp_path):
    """Create temporary output file."""
    output_file = tmp_path / "output.txt"
    output_file.write_text("partial output")
    return output_file


# === RecoveryConfig Tests ===


def test_recovery_config_defaults():
    """Test default recovery configuration."""
    config = RecoveryConfig()

    assert config.max_retries == 3
    assert config.retry_delay == 1.0
    assert config.exponential_backoff is True
    assert config.backoff_multiplier == 2.0
    assert config.max_retry_delay == 60.0
    assert config.timeout is None
    assert config.cleanup_on_failure is True
    assert config.hardware_fallback_enabled is True
    assert config.skip_on_permanent_failure is False


def test_recovery_config_custom():
    """Test custom recovery configuration."""
    config = RecoveryConfig(
        max_retries=5,
        retry_delay=2.0,
        exponential_backoff=False,
        timeout=10.0,
    )

    assert config.max_retries == 5
    assert config.retry_delay == 2.0
    assert config.exponential_backoff is False
    assert config.timeout == 10.0


# === ErrorRecovery Tests ===


@pytest.mark.asyncio
async def test_error_recovery_success_first_try(error_recovery):
    """Test successful operation on first try."""

    async def successful_operation():
        return "success"

    result = await error_recovery.execute_with_recovery(
        successful_operation, operation_name="test_operation"
    )

    assert result.success is True
    assert result.result == "success"
    assert result.error is None
    assert len(result.attempts) == 0  # No retry attempts
    assert result.strategy_used is None


@pytest.mark.asyncio
async def test_error_recovery_success_after_retries(error_recovery):
    """Test successful operation after retries."""
    call_count = 0

    async def flaky_operation():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise RetryableError("Temporary failure")
        return "success"

    result = await error_recovery.execute_with_recovery(
        flaky_operation, operation_name="flaky_operation"
    )

    assert result.success is True
    assert result.result == "success"
    assert len(result.attempts) == 2  # Failed twice, succeeded on third
    assert result.strategy_used == RecoveryStrategy.RETRY


@pytest.mark.asyncio
async def test_error_recovery_failure_after_max_retries(error_recovery):
    """Test operation fails after max retries."""

    async def failing_operation():
        raise RetryableError("Permanent failure")

    result = await error_recovery.execute_with_recovery(
        failing_operation, operation_name="failing_operation"
    )

    assert result.success is False
    assert result.result is None
    assert result.error is not None
    assert len(result.attempts) == 3  # Max retries
    assert all(a.strategy == RecoveryStrategy.RETRY for a in result.attempts)


@pytest.mark.asyncio
async def test_error_recovery_non_retryable_error(error_recovery):
    """Test non-retryable error stops immediately."""

    async def non_retryable_operation():
        raise NonRetryableError("Cannot retry this")

    result = await error_recovery.execute_with_recovery(
        non_retryable_operation, operation_name="non_retryable"
    )

    assert result.success is False
    assert len(result.attempts) == 1  # Only one attempt
    assert result.error is not None


@pytest.mark.asyncio
async def test_error_recovery_with_fallback_success(error_recovery):
    """Test fallback operation succeeds after primary fails."""

    async def primary_operation():
        raise RetryableError("Primary failed")

    async def fallback_operation():
        return "fallback_success"

    result = await error_recovery.execute_with_recovery(
        primary_operation,
        fallback_operation=fallback_operation,
        operation_name="operation_with_fallback",
    )

    assert result.success is True
    assert result.result == "fallback_success"
    assert result.strategy_used == RecoveryStrategy.FALLBACK
    assert any(a.strategy == RecoveryStrategy.FALLBACK for a in result.attempts)


@pytest.mark.asyncio
async def test_error_recovery_fallback_also_fails(error_recovery):
    """Test both primary and fallback operations fail."""

    async def primary_operation():
        raise RetryableError("Primary failed")

    async def fallback_operation():
        raise RetryableError("Fallback also failed")

    result = await error_recovery.execute_with_recovery(
        primary_operation,
        fallback_operation=fallback_operation,
        operation_name="both_fail",
    )

    assert result.success is False
    assert result.error is not None
    assert any(a.strategy == RecoveryStrategy.FALLBACK for a in result.attempts)


@pytest.mark.asyncio
async def test_error_recovery_with_timeout():
    """Test operation timeout handling."""
    config = RecoveryConfig(max_retries=2, retry_delay=0.1, timeout=0.5)
    recovery = ErrorRecovery(config)

    async def slow_operation():
        await asyncio.sleep(2.0)  # Longer than timeout
        return "should not reach here"

    result = await recovery.execute_with_recovery(slow_operation, operation_name="slow_op")

    assert result.success is False
    assert len(result.attempts) == 2  # Max retries
    assert all(isinstance(a.error, ProcessTimeoutError) for a in result.attempts)


@pytest.mark.asyncio
async def test_error_recovery_with_cleanup(error_recovery, temp_output_file):
    """Test cleanup function is called on failure."""
    cleanup_called = False

    async def failing_operation():
        raise RetryableError("Operation failed")

    async def cleanup_func():
        nonlocal cleanup_called
        cleanup_called = True
        temp_output_file.unlink()

    result = await error_recovery.execute_with_recovery(
        failing_operation,
        cleanup_func=cleanup_func,
        operation_name="with_cleanup",
    )

    assert result.success is False
    assert cleanup_called is True
    assert not temp_output_file.exists()


@pytest.mark.asyncio
async def test_error_recovery_cleanup_disabled():
    """Test cleanup can be disabled."""
    config = RecoveryConfig(cleanup_on_failure=False, max_retries=1, retry_delay=0.1)
    recovery = ErrorRecovery(config)

    cleanup_called = False

    async def failing_operation():
        raise RetryableError("Failure")

    async def cleanup_func():
        nonlocal cleanup_called
        cleanup_called = True

    result = await recovery.execute_with_recovery(
        failing_operation,
        cleanup_func=cleanup_func,
        operation_name="no_cleanup",
    )

    assert result.success is False
    assert cleanup_called is False


@pytest.mark.asyncio
async def test_error_recovery_fallback_disabled():
    """Test hardware fallback can be disabled."""
    config = RecoveryConfig(hardware_fallback_enabled=False, max_retries=1, retry_delay=0.1)
    recovery = ErrorRecovery(config)

    async def primary_operation():
        raise RetryableError("Primary failed")

    fallback_called = False

    async def fallback_operation():
        nonlocal fallback_called
        fallback_called = True
        return "fallback"

    result = await recovery.execute_with_recovery(
        primary_operation,
        fallback_operation=fallback_operation,
        operation_name="no_fallback",
    )

    assert result.success is False
    assert fallback_called is False


@pytest.mark.asyncio
async def test_error_recovery_with_args_kwargs(error_recovery):
    """Test operation with arguments and keyword arguments."""

    async def operation_with_params(x, y, z=10):
        return x + y + z

    result = await error_recovery.execute_with_recovery(
        operation_with_params, 5, 10, z=15, operation_name="with_params"
    )

    assert result.success is True
    assert result.result == 30


# === Retry Delay Tests ===


def test_calculate_retry_delay_no_backoff():
    """Test retry delay without exponential backoff."""
    config = RecoveryConfig(retry_delay=2.0, exponential_backoff=False)
    recovery = ErrorRecovery(config)

    assert recovery._calculate_retry_delay(1) == 2.0
    assert recovery._calculate_retry_delay(2) == 2.0
    assert recovery._calculate_retry_delay(3) == 2.0


def test_calculate_retry_delay_exponential_backoff():
    """Test retry delay with exponential backoff."""
    config = RecoveryConfig(
        retry_delay=1.0, exponential_backoff=True, backoff_multiplier=2.0, max_retry_delay=10.0
    )
    recovery = ErrorRecovery(config)

    # delay * (multiplier ^ (attempt - 1))
    assert recovery._calculate_retry_delay(1) == 1.0  # 1.0 * 2^0
    assert recovery._calculate_retry_delay(2) == 2.0  # 1.0 * 2^1
    assert recovery._calculate_retry_delay(3) == 4.0  # 1.0 * 2^2
    assert recovery._calculate_retry_delay(4) == 8.0  # 1.0 * 2^3
    assert recovery._calculate_retry_delay(5) == 10.0  # Capped at max_retry_delay


# === Cleanup Tests ===


@pytest.mark.asyncio
async def test_cleanup_partial_output_file(error_recovery, temp_output_file):
    """Test cleanup of partial output file."""
    assert temp_output_file.exists()

    await error_recovery.cleanup_partial_output(temp_output_file)

    assert not temp_output_file.exists()


@pytest.mark.asyncio
async def test_cleanup_partial_output_directory(error_recovery, tmp_path):
    """Test cleanup of partial output directory."""
    output_dir = tmp_path / "partial_output"
    output_dir.mkdir()
    (output_dir / "file1.txt").write_text("content")
    (output_dir / "file2.txt").write_text("content")

    assert output_dir.exists()

    await error_recovery.cleanup_partial_output(output_dir)

    assert not output_dir.exists()


@pytest.mark.asyncio
async def test_cleanup_nonexistent_path(error_recovery, tmp_path):
    """Test cleanup of nonexistent path doesn't error."""
    nonexistent = tmp_path / "does_not_exist"

    # Should not raise
    await error_recovery.cleanup_partial_output(nonexistent)


# === Recovery History Tests ===


@pytest.mark.asyncio
async def test_recovery_history_tracking(error_recovery):
    """Test recovery history is tracked."""

    async def operation1():
        return "result1"

    async def operation2():
        raise RetryableError("Failure")

    # Execute successful operation
    await error_recovery.execute_with_recovery(operation1, operation_name="op1")

    # Execute failed operation
    await error_recovery.execute_with_recovery(operation2, operation_name="op2")

    history = error_recovery.get_recovery_history()

    assert len(history) == 2
    assert history[0].success is True
    assert history[1].success is False


def test_get_recovery_stats_empty(error_recovery):
    """Test recovery stats with no history."""
    stats = error_recovery.get_recovery_stats()

    assert stats["total_operations"] == 0
    assert stats["successful_operations"] == 0
    assert stats["failed_operations"] == 0
    assert stats["success_rate"] == 0.0


@pytest.mark.asyncio
async def test_get_recovery_stats(error_recovery):
    """Test recovery statistics calculation."""
    call_count = 0

    async def sometimes_fails():
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            raise RetryableError("Fail")
        return "success"

    async def always_fails():
        raise RetryableError("Always fails")

    async def fallback_succeeds():
        return "fallback_result"

    # Execute operations with different outcomes
    await error_recovery.execute_with_recovery(sometimes_fails, operation_name="op1")

    await error_recovery.execute_with_recovery(
        always_fails, fallback_operation=fallback_succeeds, operation_name="op2"
    )

    await error_recovery.execute_with_recovery(always_fails, operation_name="op3")

    stats = error_recovery.get_recovery_stats()

    assert stats["total_operations"] == 3
    assert stats["successful_operations"] == 2
    assert stats["failed_operations"] == 1
    assert stats["success_rate"] == pytest.approx(66.67, rel=0.1)
    assert stats["retry_success_count"] == 1
    assert stats["fallback_success_count"] == 1


def test_reset_history(error_recovery):
    """Test resetting recovery history."""
    error_recovery._recovery_history.append(MagicMock())
    error_recovery._recovery_history.append(MagicMock())

    assert len(error_recovery.get_recovery_history()) == 2

    error_recovery.reset_history()

    assert len(error_recovery.get_recovery_history()) == 0


# === Hardware Fallback Helper Tests ===


@pytest.mark.asyncio
async def test_create_hardware_fallback_success():
    """Test hardware fallback wrapper with primary success."""

    async def primary_encoding():
        return "hardware_result"

    async def fallback_encoding():
        return "software_result"

    wrapped = create_hardware_fallback(
        primary_encoding,
        fallback_encoding,
        RecoveryConfig(max_retries=1, retry_delay=0.1),
    )

    result = await wrapped()

    assert result == "hardware_result"


@pytest.mark.asyncio
async def test_create_hardware_fallback_uses_fallback():
    """Test hardware fallback wrapper uses fallback on primary failure."""

    async def primary_encoding():
        raise RetryableError("Hardware encoding failed")

    async def fallback_encoding():
        return "software_result"

    wrapped = create_hardware_fallback(
        primary_encoding,
        fallback_encoding,
        RecoveryConfig(max_retries=1, retry_delay=0.1),
    )

    result = await wrapped()

    assert result == "software_result"


@pytest.mark.asyncio
async def test_create_hardware_fallback_both_fail():
    """Test hardware fallback wrapper when both fail."""

    async def primary_encoding():
        raise RetryableError("Hardware failed")

    async def fallback_encoding():
        raise RetryableError("Software also failed")

    wrapped = create_hardware_fallback(
        primary_encoding,
        fallback_encoding,
        RecoveryConfig(max_retries=1, retry_delay=0.1),
    )

    with pytest.raises(TranscodingError):
        await wrapped()


@pytest.mark.asyncio
async def test_create_hardware_fallback_with_args():
    """Test hardware fallback wrapper with arguments."""

    async def primary_encoding(x, y, z=0):
        return x + y + z

    async def fallback_encoding(x, y, z=0):
        return (x + y + z) * 2

    wrapped = create_hardware_fallback(
        primary_encoding,
        fallback_encoding,
        RecoveryConfig(max_retries=1, retry_delay=0.1),
    )

    result = await wrapped(10, 20, z=5)

    assert result == 35


# === Edge Cases ===


@pytest.mark.asyncio
async def test_error_recovery_empty_attempts_list():
    """Test recovery with no attempts recorded (edge case)."""
    config = RecoveryConfig(max_retries=0)  # No retries
    recovery = ErrorRecovery(config)

    async def operation():
        raise RetryableError("Immediate failure")

    result = await recovery.execute_with_recovery(operation, operation_name="no_retries")

    assert result.success is False
    assert result.error is not None


@pytest.mark.asyncio
async def test_error_recovery_duration_tracking(error_recovery):
    """Test that recovery tracks duration correctly."""

    async def slow_operation():
        await asyncio.sleep(0.2)
        return "done"

    result = await error_recovery.execute_with_recovery(slow_operation, operation_name="slow")

    assert result.success is True
    assert result.total_duration >= 0.2


@pytest.mark.asyncio
async def test_error_recovery_attempt_timestamps():
    """Test that recovery attempts have timestamps."""
    config = RecoveryConfig(max_retries=2, retry_delay=0.1)
    recovery = ErrorRecovery(config)

    call_count = 0

    async def flaky_operation():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise RetryableError("Fail")
        return "success"

    result = await recovery.execute_with_recovery(flaky_operation, operation_name="timestamped")

    assert len(result.attempts) == 1
    assert result.attempts[0].timestamp > 0
    assert result.attempts[0].attempt_number == 1
