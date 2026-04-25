"""Pytest configuration and fixtures for config-resolver tests."""
import json
from datetime import datetime
from datetime import timedelta
from pathlib import Path
from typing import Any
from typing import Dict
from typing import List
from typing import Optional

import pytest
from config_resolver.configs.base import BaseConfig
from config_resolver.profiles.api import BaseAPIProfile
from config_resolver.profiles.base import BaseProfile
from config_resolver.profiles.json_file import BaseJsonFileProfile
from pydantic import BaseModel
from pydantic import ConfigDict
from pytest_httpserver import HTTPServer

# Sample test data
SAMPLE_CONFIG_DATA = {
    "database_host": "localhost",
    "database_port": 5432,
    "api_key": "test-api-key-123",
    "debug_mode": True,
    "max_connections": 100,
}


@pytest.fixture
def sample_config_data() -> dict[str, Any]:
    """Provides sample configuration data for tests."""
    return SAMPLE_CONFIG_DATA.copy()


@pytest.fixture
def sample_json_file(tmp_path: Path, sample_config_data: dict[str, Any]) -> Path:
    """Creates a temporary JSON configuration file.

    Returns:
        Path to the created JSON file.
    """
    json_file = tmp_path / "config.json"
    json_file.write_text(json.dumps(sample_config_data), encoding="utf-8")
    return json_file


@pytest.fixture
def invalid_json_file(tmp_path: Path) -> Path:
    """Creates a temporary file with invalid JSON content."""
    json_file = tmp_path / "invalid.json"
    json_file.write_text("{ invalid json content", encoding="utf-8")
    return json_file


@pytest.fixture
def non_dict_json_file(tmp_path: Path) -> Path:
    """Creates a JSON file with non-object (array) content."""
    json_file = tmp_path / "array.json"
    json_file.write_text('["item1", "item2"]', encoding="utf-8")
    return json_file


@pytest.fixture(scope="session")
def httpserver_listen_address() -> tuple[str, int]:
    """Configure httpserver to listen on localhost with a random available
    port."""
    return ("127.0.0.1", 0)


@pytest.fixture
def mock_api_server(
    httpserver: HTTPServer, sample_config_data: dict[str, Any]
) -> HTTPServer:
    """Provides a mock HTTP server configured with sample config endpoint.

    The server responds to GET /config with sample configuration data.
    """
    config_with_timestamp = {
        **sample_config_data,
        "last_updated_at": datetime.now().isoformat(),
    }
    httpserver.expect_request("/config").respond_with_json(config_with_timestamp)
    return httpserver


@pytest.fixture
def mock_api_server_no_timestamp(
    httpserver: HTTPServer, sample_config_data: dict[str, Any]
) -> HTTPServer:
    """Provides a mock HTTP server that returns config without
    last_updated_at."""
    httpserver.expect_request("/config").respond_with_json(sample_config_data)
    return httpserver


@pytest.fixture
def mock_api_server_invalid_json(httpserver: HTTPServer) -> HTTPServer:
    """Provides a mock HTTP server that returns invalid JSON."""
    httpserver.expect_request("/config").respond_with_data(
        "{ invalid json", content_type="application/json"
    )
    return httpserver


@pytest.fixture
def mock_api_server_non_dict(httpserver: HTTPServer) -> HTTPServer:
    """Provides a mock HTTP server that returns a JSON array instead of
    object."""
    httpserver.expect_request("/config").respond_with_json(["item1", "item2"])
    return httpserver


# =============================================================================
# Profile implementations for unit tests
# =============================================================================


class JsonFileProfile(BaseJsonFileProfile):
    """Concrete JSON file profile for testing."""

    database_host: str | None = None
    database_port: int | None = None
    api_key: str | None = None
    debug_mode: bool | None = None
    max_connections: int | None = None


class APIProfile(BaseAPIProfile):
    """Concrete API profile for testing."""

    database_host: str | None = None
    database_port: int | None = None
    api_key: str | None = None
    debug_mode: bool | None = None
    max_connections: int | None = None


@pytest.fixture
def json_file_profile(sample_json_file: Path) -> JsonFileProfile:
    """Provides a JSON file profile instance configured with sample file."""
    return JsonFileProfile(file_path=sample_json_file)


@pytest.fixture
def api_profile(mock_api_server: HTTPServer) -> APIProfile:
    """Provides an API profile instance configured with mock server."""
    return APIProfile(url=mock_api_server.url_for("/config"))


# =============================================================================
# Mock profile for integration tests (in-memory, no I/O)
# =============================================================================


class MockProfile(BaseProfile):
    """In-memory mock profile for integration testing.

    Allows setting field values directly without file or network I/O.
    The fetch() method simply sets last_updated_at to simulate
    successful fetch.
    """

    def __init__(
        self,
        last_updated_at: datetime | None = None,
        should_fail: bool = False,
        **field_values: Any
    ) -> None:
        """Initialize mock profile with optional field values.

        Args:
            last_updated_at: Timestamp to set on fetch. Defaults to now.
            should_fail: If True, fetch() will raise ProfileUnavailableError.
            **field_values: Field values to set on this profile.
        """
        self._mock_last_updated_at = last_updated_at or datetime.now()
        self._should_fail = should_fail
        # Set all provided field values as attributes
        for key, value in field_values.items():
            setattr(self, key, value)

    def fetch(self) -> None:
        """Simulate fetching by setting last_updated_at."""
        from config_resolver.profiles.exceptions import ProfileUnavailableError

        if self._should_fail:
            raise ProfileUnavailableError("Mock profile fetch failed")
        self.last_updated_at = self._mock_last_updated_at


# Uniquely named mock profiles for conflict testing


class MockProfileA(MockProfile):
    """First mock profile for conflict testing."""

    pass


class MockProfileB(MockProfile):
    """Second mock profile for conflict testing."""

    pass


# =============================================================================
# Nested model for testing nested field resolution
# =============================================================================


class DatabaseSettings(BaseModel):
    """Nested model for database configuration."""

    model_config = ConfigDict(extra="allow")

    host: str | None = None
    port: int | None = None
    username: str | None = None
    password: str | None = None


class FeatureFlags(BaseModel):
    """Nested model for feature flags."""

    model_config = ConfigDict(extra="allow")

    new_feature: bool | None = None
    beta_mode: bool | None = None


class NestedSettings(BaseModel):
    """Deeply nested model for testing recursive resolution."""

    model_config = ConfigDict(extra="allow")

    timeout_seconds: int | None = None
    retry_count: int | None = None
    feature_flags: FeatureFlags | None = None


# =============================================================================
# Mock profiles with nested fields
# =============================================================================


class MockProfileWithDatabase(MockProfile):
    """Mock profile with nested database settings."""

    database: DatabaseSettings | None = None
    app_name: str | None = None


class MockProfileWithDatabaseA(MockProfileWithDatabase):
    """First mock profile with database for conflict testing."""

    pass


class MockProfileWithDatabaseB(MockProfileWithDatabase):
    """Second mock profile with database for conflict testing."""

    pass


class MockProfileWithNested(MockProfile):
    """Mock profile with deeply nested settings."""

    nested_config: NestedSettings | None = None
    allowed_hosts: list[str] | None = None


class MockProfileWithNestedA(MockProfileWithNested):
    """First mock profile with nested settings for conflict testing."""

    pass


class MockProfileWithNestedB(MockProfileWithNested):
    """Second mock profile with nested settings for conflict testing."""

    pass


class MockProfileWithDict(MockProfile):
    """Mock profile with dictionary field."""

    settings: dict[str, Any] | None = None
    tags: list[str] | None = None


class MockProfileWithDictA(MockProfileWithDict):
    """First mock profile with dict for conflict testing."""

    pass


class MockProfileWithDictB(MockProfileWithDict):
    """Second mock profile with dict for conflict testing."""

    pass


# =============================================================================
# Config implementations for integration tests
# =============================================================================


class SimpleConfig(BaseConfig):
    """Simple config with basic scalar fields for testing."""

    database_host: str | None = None
    database_port: int | None = None
    api_key: str | None = None
    debug_mode: bool | None = None
    max_connections: int | None = None


class NestedConfig(BaseConfig):
    """Config with nested Pydantic model fields."""

    app_name: str | None = None
    database: DatabaseSettings | None = None


class DeeplyNestedConfig(BaseConfig):
    """Config with deeply nested structures."""

    app_name: str | None = None
    nested_config: NestedSettings | None = None
    allowed_hosts: list[str] | None = None


class DictConfig(BaseConfig):
    """Config with dictionary fields."""

    app_name: str | None = None
    settings: dict[str, Any] | None = None
    tags: list[str] | None = None


# =============================================================================
# Fixtures for creating profiles with specific timestamps
# =============================================================================


@pytest.fixture
def older_timestamp() -> datetime:
    """Returns a timestamp from 1 hour ago."""
    return datetime.now() - timedelta(hours=1)


@pytest.fixture
def newer_timestamp() -> datetime:
    """Returns a timestamp from 1 minute ago (more recent)."""
    return datetime.now() - timedelta(minutes=1)


@pytest.fixture
def oldest_timestamp() -> datetime:
    """Returns a timestamp from 1 day ago."""
    return datetime.now() - timedelta(days=1)
