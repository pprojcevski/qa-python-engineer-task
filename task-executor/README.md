
# Task Executor

A Python framework for running operational tasks such as health checks, cleanup jobs, and data syncs, with built-in retry logic, timeout handling, and structured JSON logging.

## Overview

Task Executor provides a pluggable architecture for defining and running operational tasks. Each task type is registered via a decorator and executed through a central `TaskExecutor` that handles:

- **Retry logic** — Exponential backoff with configurable max retries, initial delay, and backoff multiplier
- **Timeout handling** — Per-task timeout using POSIX signals, with a dedicated `TIMEOUT` status
- **Structured logging** — JSON-formatted logs with timestamps, log level, and task ID
- **Extensible task types** — Register custom task implementations with `@register_task`

### Built-in Task Types

- `http_check` — Performs an HTTP health check against a target URL
- `tcp_port_check` — Checks if a TCP port is open and accepting connections

---

## Prerequisites

- **Python 3.13** or higher
- **uv** — Fast Python package manager ([installation guide](https://docs.astral.sh/uv/getting-started/installation/))
- **Docker** (optional) — For containerized deployment

---

## Local Development Setup

### Step 1: Install uv

**macOS/Linux:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows (PowerShell):**
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**Via pip:**
```bash
pip install uv
```

### Step 2: Navigate to the Project
```bash
cd task-executor
```

### Step 3: Create the Virtual Environment and Install Dependencies
```bash
uv sync
```

### Step 4: Install Test Dependencies (Optional)
```bash
uv sync --extra test
```

---

## Running the Application

Execute the built-in example that runs a set of sample tasks:
```bash
uv run python -m task_executor.executor
```

This will run a few preconfigured tasks (HTTP checks, TCP port checks) and print a JSON summary to stdout.

### Running Tests
```bash
uv run pytest
```

Run with coverage:
```bash
uv run pytest --cov=task_executor --cov-report=term-missing
```

---

## Docker Setup

### Step 1: Build the Docker Image

From the `task-executor` directory:
```bash
docker build -t task-executor .
```

### Step 2: Run the Container
```bash
docker run --rm task-executor
```

---

## Project Structure
```
task-executor/
├── task_executor/
│   ├── __init__.py
│   └── executor.py       # Core framework: tasks, registry, executor, CLI
├── tests/                # Test suite
├── pyproject.toml        # Project configuration
├── uv.lock               # Locked dependencies
├── Dockerfile            # Container definition
└── README.md
```
