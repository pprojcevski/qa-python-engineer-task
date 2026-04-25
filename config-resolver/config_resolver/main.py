"""Example usage of config-resolver with JSON file profile and environment
variables."""
import json
import os
import tempfile
from pathlib import Path

from config_resolver.configs.base import BaseConfig
from config_resolver.profiles.json_file import BaseJsonFileProfile


# Define a JSON file profile with specific fields
class AppJsonProfile(BaseJsonFileProfile):
    """JSON file profile for application configuration."""

    database_host: str | None = None
    database_port: int | None = None
    api_key: str | None = None
    debug_mode: bool | None = None
    max_connections: int | None = None


# Define the application config that uses the profile
class AppConfig(BaseConfig):
    """Application configuration resolved from env vars and JSON profile."""

    database_host: str | None = None
    database_port: int | None = None
    api_key: str | None = None
    debug_mode: bool | None = None
    max_connections: int | None = None


def main():
    """Demonstrate config resolution with JSON profile and environment
    variables."""

    # Create a temporary JSON config file
    config_data = {
        "database_host": "localhost",
        "database_port": 5432,
        "api_key": "json-secret-key",
        "debug_mode": True,
        "max_connections": 100,
    }

    # Create temp file for the JSON config
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    ) as config_file:
        json.dump(config_data, config_file)
        config_path = config_file.name

    try:
        # Set some environment variables to demonstrate precedence
        # Environment variables take priority over JSON profile values
        os.environ["DATABASE_HOST"] = "production-db.example.com"
        os.environ["DATABASE_PORT"] = "5433"

        # Create the JSON profile
        json_profile = AppJsonProfile(file_path=config_path)

        # Create config with the JSON profile
        config = AppConfig(profiles=[json_profile])

        print("=" * 60)
        print("Config Resolution Example")
        print("=" * 60)
        print()
        print("Resolved Configuration Values:")
        print("-" * 40)
        print(f"  database_host:    {config.database_host}")
        print(f"  database_port:    {config.database_port}")
        print(f"  api_key:          {config.api_key}")
        print(f"  debug_mode:       {config.debug_mode}")
        print(f"  max_connections:  {config.max_connections}")
        print()
        print("Source Priority:")
        print("-" * 40)
        print("  1. Environment variables (highest priority)")
        print("  2. JSON profile values")
        print()
        print("Detected Conflicts:")
        print("-" * 40)

        if config._conflicts:
            for conflict in config._conflicts:
                print(f"  Field: {conflict.key}")
                print(f"    Sources: {', '.join(conflict.sources)}")
                print(f"    Selected: {conflict.selected} -> {conflict.selected_value}")
                print(f"    Reason: {conflict.resolution_reason}")
                print()
        else:
            print("  No conflicts detected.")

        print("=" * 60)

    finally:
        # Cleanup
        Path(config_path).unlink(missing_ok=True)
        os.environ.pop("DATABASE_HOST", None)
        os.environ.pop("DATABASE_PORT", None)


if __name__ == "__main__":
    main()
