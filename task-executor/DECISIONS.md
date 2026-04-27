# Decisions

## Retry Strategy

**Implemented:** Exponential backoff

**Why:**
- Best fit for tasks that access third-party or external resources
- Increasing delay between retries gives the remote server more time to recover before the next attempt
- Avoids hammering a struggling service with rapid back-to-back requests

**Alternatives considered:**
- **Fixed delay** — Simple, but doesn't account for server recovery time; can cause unnecessary load
- **Jitter** — Adds randomness to avoid retry storms in distributed systems; useful at scale but adds complexity not needed here

**Configurable parameters per task (`TaskConfig`):**
- `max_retries` — Maximum number of attempts
- `initial_delay` — Starting delay in seconds
- `max_delay` — Cap on the delay between retries
- `backoff_multiplier` — Multiplier applied to the delay after each failure

---

## Timeout Handling

**Implemented:** POSIX signals (`SIGALRM`) with a per-task timeout defined in `TaskConfig`

**How it works:**
- Before each task runs, `signal.alarm(timeout_seconds)` is set
- If the task exceeds the timeout, a `TimeoutError` is raised by the signal handler
- The alarm is always cleared in the `finally` block
- Default timeout is 5 minutes, configurable per task via `timeout_seconds`

**Tradeoffs:**
- Works well for the common case — simple and no external dependencies
- **No graceful cleanup on timeout** — The task is interrupted abruptly; open connections, transactions, or other held resources may not be released properly (see also: [What was skipped](#what-was-skipped))
- `SIGALRM` is Unix-only — this approach does not work on Windows

---

## Additional Task Type

**Implemented:** `tcp_port_check`

**What it does:**
- Checks whether a TCP port is open and accepting connections on a given host
- Target can be provided as `"host:port"` or as separate `target` + `params.port`
- Returns connection status and a descriptive message

**Why this task type:**
- TCP port checks are a common operational health check, complementing the existing HTTP check
- HTTP checks verify application-level responses; TCP checks verify basic network reachability, useful for databases, message brokers, or any non-HTTP service

**Framework extensibility:**
- Adding this task required only two things: implement `BaseTask` and apply `@register_task("tcp_port_check")`
- No changes to `TaskExecutor`, `TaskConfig`, or the registry were needed
- This shows that new task types can be added in isolation without touching the core framework

---

## Sequential vs. Concurrent Execution

**Implemented:** Sequential execution

**Why:**
- The framework's starting point uses sequential execution, and changing to async would require significant restructuring of the core classes
- Mixing sync and async task implementations in the same executor cleanly is not straightforward
- Sequential execution is easier to reason about, debug, and test

**Future path:**
- A separate async executor could be introduced later for tasks that benefit from concurrency
- This keeps the sequential executor simple and stable as the default baseline

> Note: I included an executor that uses concurrency in the repo, but it's not currently in use. It can be used as a reference for implementing async executors.

---

## Task Failure After All Retries

**What happens:**
- After all retry attempts are exhausted, the last exception is re-raised
- The task is marked with `TaskStatus.FAILED` and the error message is stored in `TaskResult.error_message`

**How it is surfaced:**
- **Logs** — Each failed attempt is logged with the attempt number, total retries, and error message; the final failure is logged at `ERROR` level
- **Summary** — `executor.summary()` includes a breakdown by status, so failed tasks are visible in the aggregate output
- **Result object** — `TaskResult` contains the full error message for downstream inspection

---

## What Was Skipped

**Resource cleanup on interruption:**
- When a task times out or raises an exception, there is no explicit cleanup step
- Open connections, in-flight transactions, or other held resources may not be released properly
- Some of this is handled automatically by Python's garbage collector or context managers, but not all — and not necessarily in the way the task requires

**Production impact:**
- Resource leaks could accumulate over time, especially for long-running executor processes
- In production, each task type should implement a `cleanup()` or use context managers to guarantee resource release on any exit path

---

## Changes to the Original Code

The only modifications made outside of what was explicitly required are related to signal handling:

- `signal.signal(signal.SIGALRM, timeout_handler)` is registered at module level so the handler is always in place before any task runs
- `signal.alarm(0)` is called in the `finally` block of `run_task` to ensure the alarm is always cleared, even if the task fails or raises unexpectedly

These changes are minimal and do not affect the existing task interface, registry, or logging setup.
