"""Unit tests for BaseJsonFileProfile."""
from pathlib import Path

import pytest
from config_resolver.profiles.exceptions import ProfileUnavailableError
from tests.conftest import JsonFileProfile


class TestBaseJsonFileProfile:
    """Tests for JSON file profile functionality."""

    def test_fetch_reads_valid_json_file(
        self, json_file_profile: JsonFileProfile
    ) -> None:
        """Test that fetch successfully reads and parses a valid JSON file."""
        json_file_profile.fetch()

        assert json_file_profile.database_host == "localhost"
        assert json_file_profile.database_port == 5432
        assert json_file_profile.api_key == "test-api-key-123"
        assert json_file_profile.debug_mode is True
        assert json_file_profile.max_connections == 100

    def test_fetch_sets_last_updated_at(
        self, json_file_profile: JsonFileProfile
    ) -> None:
        """Test that fetch populates last_updated_at from file modification
        time."""
        json_file_profile.fetch()

        assert json_file_profile.last_updated_at is not None

    def test_fetch_raises_error_for_missing_file(self, tmp_path: Path) -> None:
        """Test that fetch raises ProfileUnavailableError for non-existent
        file."""
        profile = JsonFileProfile(file_path=tmp_path / "nonexistent.json")

        with pytest.raises(ProfileUnavailableError) as exc_info:
            profile.fetch()

        assert "not found" in str(exc_info.value).lower()

    def test_fetch_raises_error_for_invalid_json(self, invalid_json_file: Path) -> None:
        """Test that fetch raises ProfileUnavailableError for invalid JSON
        content."""
        profile = JsonFileProfile(file_path=invalid_json_file)

        with pytest.raises(ProfileUnavailableError) as exc_info:
            profile.fetch()

        assert "failed to parse" in str(exc_info.value).lower()

    def test_fetch_raises_error_for_non_dict_json(
        self, non_dict_json_file: Path
    ) -> None:
        """Test that fetch raises ProfileUnavailableError when JSON is not an
        object."""
        profile = JsonFileProfile(file_path=non_dict_json_file)

        with pytest.raises(ProfileUnavailableError) as exc_info:
            profile.fetch()

        assert "invalid json structure" in str(exc_info.value).lower()

    def test_fetch_ignores_unknown_fields(self, tmp_path: Path) -> None:
        """Test that fetch ignores fields not defined on the profile class."""
        import json

        json_file = tmp_path / "config.json"
        json_file.write_text(
            json.dumps(
                {
                    "database_host": "localhost",
                    "unknown_field": "should be ignored",
                }
            )
        )

        profile = JsonFileProfile(file_path=json_file)
        profile.fetch()

        assert profile.database_host == "localhost"
        assert (
            not hasattr(profile, "unknown_field")
            or getattr(profile, "unknown_field", None) is None
        )

    def test_fetch_accepts_string_path(self, sample_json_file: Path) -> None:
        """Test that profile accepts string path in addition to Path object."""
        profile = JsonFileProfile(file_path=str(sample_json_file))
        profile.fetch()

        assert profile.database_host == "localhost"

    def test_fetch_handles_empty_dict(self, tmp_path: Path) -> None:
        """Test that fetch handles an empty JSON object gracefully."""
        import json

        json_file = tmp_path / "empty.json"
        json_file.write_text(json.dumps({}))

        profile = JsonFileProfile(file_path=json_file)
        profile.fetch()

        # Should not raise, fields remain None
        assert profile.database_host is None
        assert profile.last_updated_at is not None
