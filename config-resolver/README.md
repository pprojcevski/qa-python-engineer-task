
# Config Resolver

A flexible Python configuration resolution library that merges settings from multiple sources with automatic conflict detection and resolution.

## Overview

Config Resolver provides a powerful way to manage application configuration by combining values from different sources:

- **Environment Variables** — Highest priority, ideal for deployment-specific settings
- **JSON File Profiles** — Configuration files that can be version-controlled or dynamically generated
- **API Profiles** — Fetch configuration from remote endpoints (extensible)

### Key Features

- **Multi-source Configuration**: Combine settings from environment variables, JSON files, and custom profile sources
- **Automatic Conflict Resolution**: When the same setting is defined in multiple sources, conflicts are automatically resolved based on priority rules
- **Conflict Tracking**: All conflicts are recorded with detailed information about which sources were involved and why a particular value was selected
- **Type Safety**: Built on Pydantic for robust data validation and type coercion
- **Extensible Architecture**: Create custom profile sources by extending the base profile classes

### Resolution Priority

1. **Environment variables** always take precedence
2. **Profile sources** are resolved by their `last_updated_at` timestamp (most recent wins)

---

## Prerequisites

- **Python 3.13** or higher
- **uv** — Fast Python package manager ([installation guide](https://docs.astral.sh/uv/getting-started/installation/))
- **Docker** (optional) — For containerized deployment

---

## Local Development Setup

### Step 1: Install uv

If you don't have `uv` installed, install it using one of these methods:

**macOS/Linux:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows (PowerShell):**
```bash
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**Via pip:**
```bash
pip install uv
```

### Step 2: Clone and Navigate to the Project
```bash
cd config-resolver
````

### Step 3: Create the Virtual Environment and Install Dependencies
```bash
uv sync
```
This will:
- Create a .venv virtual environment
- Install all project dependencies from uv.lock
- Install the project in editable mode

### Step 4: Install Test Dependencies (Optional)
To install development and test dependencies:
``` bash
uv sync --extra test
```

### Step 5: Activate the Virtual Environment (Optional)
While uv run handles this automatically, you can activate the environment manually:

macOS/Linux:
``` bash
source .venv/bin/activate
```

Windows:
``` powershell
.venv\Scripts\activate
```

## Running the Application
Run the Example
Execute the main example that demonstrates config resolution:
``` bash
uv run python -m config_resolver.main
```

This will:
- Create a temporary JSON configuration file
- Set environment variables for some settings
- Resolve the configuration showing how environment variables take precedence
- Display any detected conflicts and their resolution
Expected Output
```
============================================================
Config Resolution Example
============================================================

Resolved Configuration Values:
----------------------------------------
  database_host:    production-db.example.com
  database_port:    5433
  api_key:          json-secret-key
  debug_mode:       True
  max_connections:  100

Source Priority:
----------------------------------------
  1. Environment variables (highest priority)
  2. JSON profile values

Detected Conflicts:
----------------------------------------
  Field: database_host
    Sources: environment, AppJsonProfile
    Selected: environment -> production-db.example.com
    Reason: Environment variable takes precedence

  Field: database_port
    Sources: environment, AppJsonProfile
    Selected: environment -> 5433
    Reason: Environment variable takes precedence

============================================================
```
### Running Tests
Run All Tests
``` bash
uv run pytest
```

Run Tests with Coverage
``` bash
uv run pytest --cov=config_resolver --cov-report=term-missing
```

Run Specific Test File
``` bash
uv run pytest tests/test_profiles.py -v
```

### Docker Setup
### Step 1: Build the Docker Image
From the config-resolver directory:
``` bash
docker build -t config-resolver .
```
This performs a multi-stage build:
- Base stage: Sets up Python 3.13 with uv and system dependencies
- Build stage: Installs Python dependencies and compiles bytecode
- Runtime stage: Creates a minimal production image
### Step 2: Run the Container
Basic run:
``` bash
docker run --rm config-resolver
```

With environment variables:
``` bash
docker run --rm \
  -e DATABASE_HOST=mydb.example.com \
  -e DATABASE_PORT=5432 \
  -e API_KEY=my-secret-key \
  config-resolver
```

## Project Structure
```
config-resolver/
├── config_resolver/
│   ├── __init__.py
│   ├── main.py              # Example usage
│   ├── models.py            # Data models (ConflictRecord, etc.)
│   ├── configs/
│   │   ├── __init__.py
│   │   └── base.py          # BaseConfig with resolution logic
│   └── profiles/
│       ├── __init__.py
│       ├── base.py          # BaseProfile abstract class
│       ├── json_file.py     # JSON file profile implementation
│       ├── api.py           # API profile implementation
│       ├── common.py        # Shared utilities
│       └── exceptions.py    # Custom exceptions
├── tests/                   # Test suite
├── pyproject.toml           # Project configuration
├── uv.lock                  # Locked dependencies
├── Dockerfile               # Container definition
└── README.md
```
