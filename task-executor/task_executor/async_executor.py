"""
Task Executor Framework
-----------------------
A framework for running operational tasks with logging and error handling.
"""
import abc
import asyncio
import json
import logging
import sys
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from datetime import timezone
from enum import Enum
from typing import Any


# ============================================================================
# Logging Setup (DO NOT MODIFY)
# ============================================================================


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }
        if hasattr(record, "task_id"):
            log_entry["task_id"] = record.task_id
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry)


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger("task_executor")
    logger.setLevel(level)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
    return logger


# ============================================================================
# Core Data Structures
# ============================================================================


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass
class TaskResult:
    task_id: str
    status: TaskStatus
    started_at: datetime
    completed_at: datetime | None = None
    result_data: dict[str, Any] = field(default_factory=dict)
    error_message: str | None = None
    attempts: int = 1


@dataclass
class TaskConfig:
    """Configuration for a single task."""

    task_id: str
    task_type: str
    target: str
    params: dict[str, Any] = field(default_factory=dict)
    # Retry configuration (exponential backoff)
    max_retries: int = 3
    initial_delay: float = 1.0
    max_delay: float = 60.0
    backoff_multiplier: float = 2.0
    # Timeout configuration
    timeout_seconds: float = 300.0


# ============================================================================
# Task Interface and Registry
# ============================================================================


class BaseTask(abc.ABC):
    """Abstract base class for all task types."""

    def __init__(self, config: TaskConfig, logger: logging.Logger):
        self.config = config
        self.logger = logging.LoggerAdapter(logger, {"task_id": config.task_id})

    @abc.abstractmethod
    async def execute(self) -> dict[str, Any]:
        """Execute the task asynchronously."""
        pass

    def validate(self) -> bool:
        return True


_task_registry: dict[str, type[BaseTask]] = {}


def register_task(task_type: str):
    """Decorator to register a task implementation."""

    def decorator(cls: type[BaseTask]) -> type[BaseTask]:
        if task_type in _task_registry:
            raise ValueError(f"Task type '{task_type}' already registered")
        _task_registry[task_type] = cls
        return cls

    return decorator


def get_task_class(task_type: str) -> type[BaseTask]:
    if task_type not in _task_registry:
        raise ValueError(f"Unknown task type: {task_type}")
    return _task_registry[task_type]


# ============================================================================
# Task Implementations
# ============================================================================


@register_task("http_check")
class HttpCheckTask(BaseTask):
    """Performs an HTTP health check against a target URL."""

    async def execute(self) -> dict[str, Any]:
        import urllib.request
        import urllib.error

        target = self.config.target
        expected = self.config.params.get("expected_status", 200)
        method = self.config.params.get("method", "GET")

        self.logger.info(f"Checking {method} {target}")

        request = urllib.request.Request(target, method=method)

        # Run blocking I/O in executor
        loop = asyncio.get_event_loop()
        try:
            actual_status = await loop.run_in_executor(None, self._do_request, request)
        except Exception as e:
            raise RuntimeError(f"Connection failed: {e}")

        if actual_status != expected:
            raise RuntimeError(
                f"Status mismatch: expected {expected}, got {actual_status}"
            )

        return {"url": target, "status_code": actual_status, "healthy": True}

    def _do_request(self, request) -> int:
        import urllib.request
        import urllib.error

        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status
        except urllib.error.HTTPError as e:
            return e.code
        except urllib.error.URLError as e:
            raise RuntimeError(f"Connection failed: {e.reason}")


@register_task("tcp_port_check")
class TcpPortCheckTask(BaseTask):
    """Checks if a TCP port is open and accepting connections."""

    def validate(self) -> bool:
        target = self.config.target
        port = self.config.params.get("port")
        if ":" in target:
            return True
        return port is not None

    async def execute(self) -> dict[str, Any]:
        target = self.config.target

        if ":" in target:
            host, port_str = target.rsplit(":", 1)
            port = int(port_str)
        else:
            host = target
            port = self.config.params["port"]

        self.logger.info(f"Checking TCP connection to {host}:{port}")

        try:
            # Use asyncio's native TCP connection
            reader, writer = await asyncio.open_connection(host, port)
            writer.close()
            await writer.wait_closed()

            return {
                "host": host,
                "port": port,
                "open": True,
                "message": f"Successfully connected to {host}:{port}",
            }
        except OSError as e:
            raise RuntimeError(f"Connection failed to {host}:{port}: {e}")


# ============================================================================
# Task Executor
# ============================================================================


class TaskExecutor:
    """Executes tasks asynchronously with proper timeout handling."""

    DEFAULT_MAX_WORKERS = 2

    def __init__(
        self, logger: logging.Logger | None = None, max_workers: int | None = None
    ):
        self.logger = logger or setup_logging()
        self.results: list[TaskResult] = []
        self.max_workers = max_workers or self.DEFAULT_MAX_WORKERS

    async def _execute_with_retry(
        self, task: BaseTask, config: TaskConfig
    ) -> tuple[dict[str, Any], int]:
        """Execute task with exponential backoff retry."""
        last_exception = None
        delay = config.initial_delay

        for attempt in range(1, config.max_retries + 1):
            try:
                result = await task.execute()
                return result, attempt
            except asyncio.CancelledError:
                raise  # Don't retry on cancellation
            except Exception as e:
                last_exception = e
                if attempt < config.max_retries:
                    self.logger.warning(
                        f"Task {config.task_id} failed on attempt {attempt}/{config.max_retries}: {e}. "
                        f"Retrying in {delay:.2f}s..."
                    )
                    await asyncio.sleep(delay)
                    delay = min(delay * config.backoff_multiplier, config.max_delay)
                else:
                    self.logger.error(
                        f"Task {config.task_id} failed after {attempt} attempts: {e}"
                    )

        raise last_exception

    async def _run_task(self, config: TaskConfig) -> TaskResult:
        """Execute a single task with retry logic."""
        started_at = datetime.now(timezone.utc)

        try:
            task_class = get_task_class(config.task_type)
            task = task_class(config, self.logger)

            if not task.validate():
                raise ValueError(f"Task validation failed: {config.task_id}")

            self.logger.info(f"Starting task: {config.task_id}")

            result_data, attempts = await self._execute_with_retry(task, config)

            return TaskResult(
                task_id=config.task_id,
                status=TaskStatus.SUCCESS,
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
                result_data=result_data,
                attempts=attempts,
            )

        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.logger.error(f"Task failed: {config.task_id} - {e}")
            return TaskResult(
                task_id=config.task_id,
                status=TaskStatus.FAILED,
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
                error_message=str(e),
                attempts=config.max_retries,
            )

    async def run_task(self, config: TaskConfig) -> TaskResult:
        """Execute a single task with timeout handling."""
        started_at = datetime.now(timezone.utc)

        try:
            result = await asyncio.wait_for(
                self._run_task(config), timeout=config.timeout_seconds
            )
            return result
        except TimeoutError:
            self.logger.error(
                f"Task timed out: {config.task_id} after {config.timeout_seconds}s"
            )
            return TaskResult(
                task_id=config.task_id,
                status=TaskStatus.TIMEOUT,
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
                error_message=f"Task timed out after {config.timeout_seconds} seconds",
            )

    async def run_all(self, configs: list[TaskConfig]) -> list[TaskResult]:
        """Execute multiple tasks concurrently with semaphore limiting."""
        self.results = []

        if not configs:
            return self.results

        semaphore = asyncio.Semaphore(self.max_workers)

        async def run_with_semaphore(config: TaskConfig) -> TaskResult:
            async with semaphore:
                return await self.run_task(config)

        tasks = [run_with_semaphore(config) for config in configs]
        self.results = await asyncio.gather(*tasks)

        return self.results

    def summary(self) -> dict[str, Any]:
        """Return aggregate statistics about executed tasks."""
        total = len(self.results)
        by_status = {}
        for result in self.results:
            status = result.status.value
            by_status[status] = by_status.get(status, 0) + 1

        return {
            "total": total,
            "by_status": by_status,
            "success_rate": by_status.get("success", 0) / total if total else 0,
        }


# ============================================================================
# CLI Entry Point
# ============================================================================


async def main():
    executor = TaskExecutor()

    test_configs = [
        TaskConfig(
            task_id="check-google",
            task_type="http_check",
            target="https://www.google.com",
            params={"expected_status": 200},
            max_retries=1,
        ),
        TaskConfig(
            task_id="check-fake",
            task_type="http_check",
            target="https://this-does-not-exist.invalid",
            params={"expected_status": 200},
            max_retries=1,
        ),
        TaskConfig(
            task_id="check-tcp-google-dns",
            task_type="tcp_port_check",
            target="8.8.8.8:53",
            timeout_seconds=10.0,
            max_retries=1,
        ),
        TaskConfig(
            task_id="check-tcp-timeout",
            task_type="tcp_port_check",
            target="10.255.255.1:80",
            timeout_seconds=5.0,
            max_retries=1,
        ),
    ]

    results = await executor.run_all(test_configs)

    print("\n" + "=" * 60)
    print("RESULTS:")
    print("=" * 60)
    for result in results:
        print(f"  {result.task_id}: {result.status.value}")
        if result.error_message:
            print(f"    Error: {result.error_message}")
    print("=" * 60)
    print(json.dumps(executor.summary(), indent=2))


if __name__ == "__main__":
    asyncio.run(main())
