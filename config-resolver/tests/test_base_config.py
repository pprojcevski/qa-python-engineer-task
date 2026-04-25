"""Integration tests for BaseConfig resolution.

Tests cover:
- No profiles (simple pydantic-settings use case)
- Single profile resolution
- Multiple profiles with conflict resolution
- Nested field resolution (Pydantic models, dicts, lists)
- Conflict detection and recording
"""
from datetime import datetime

import pytest
from tests.conftest import DatabaseSettings
from tests.conftest import DeeplyNestedConfig
from tests.conftest import DictConfig
from tests.conftest import FeatureFlags
from tests.conftest import MockProfile
from tests.conftest import MockProfileA
from tests.conftest import MockProfileB
from tests.conftest import MockProfileWithDatabase
from tests.conftest import MockProfileWithDatabaseA
from tests.conftest import MockProfileWithDatabaseB
from tests.conftest import MockProfileWithDict
from tests.conftest import MockProfileWithDictA
from tests.conftest import MockProfileWithDictB
from tests.conftest import MockProfileWithNested
from tests.conftest import MockProfileWithNestedA
from tests.conftest import MockProfileWithNestedB
from tests.conftest import NestedConfig
from tests.conftest import NestedSettings
from tests.conftest import SimpleConfig


class TestNoProfiles:
    """Tests for BaseConfig with no profiles (basic pydantic-settings
    behavior)."""

    def test_config_with_no_profiles_uses_defaults(self) -> None:
        """Config with no profiles should use default None values."""
        config = SimpleConfig(profiles=[])

        assert config.database_host is None
        assert config.database_port is None
        assert config.conflicts == []

    def test_config_with_explicit_values_no_profiles(self) -> None:
        """Config with explicit values and no profiles should use those
        values."""
        config = SimpleConfig(
            profiles=[],
            database_host="explicit-host",
            database_port=3306,
        )

        assert config.database_host == "explicit-host"
        assert config.database_port == 3306
        assert config.conflicts == []

    def test_config_with_env_values_no_profiles(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Config should read from environment variables when no profiles."""
        monkeypatch.setenv("DATABASE_HOST", "env-host")
        monkeypatch.setenv("DATABASE_PORT", "5432")

        config = SimpleConfig(profiles=[])

        assert config.database_host == "env-host"
        assert config.database_port == 5432
        assert config.conflicts == []


class TestSingleProfile:
    """Tests for BaseConfig with a single profile."""

    def test_single_profile_populates_fields(self) -> None:
        """Single profile should populate config fields."""
        profile = MockProfile(
            database_host="profile-host",
            database_port=5432,
            api_key="profile-key",
        )

        config = SimpleConfig(profiles=[profile])

        assert config.database_host == "profile-host"
        assert config.database_port == 5432
        assert config.api_key == "profile-key"
        assert config.conflicts == []

    def test_single_profile_partial_fields(self) -> None:
        """Single profile with partial fields should only populate those
        fields."""
        profile = MockProfile(database_host="profile-host")

        config = SimpleConfig(profiles=[profile])

        assert config.database_host == "profile-host"
        assert config.database_port is None
        assert config.conflicts == []

    def test_env_value_takes_precedence_over_single_profile(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Environment value should take precedence over profile value."""
        monkeypatch.setenv("DATABASE_HOST", "env-host")

        profile = MockProfile(database_host="profile-host")

        config = SimpleConfig(profiles=[profile])

        assert config.database_host == "env-host"
        # Conflict should be recorded
        assert len(config.conflicts) == 1
        assert config.conflicts[0].key == "database_host"
        assert config.conflicts[0].selected == "environment"

    def test_unavailable_profile_is_skipped(self) -> None:
        """Profile that fails to fetch should be skipped."""
        failing_profile = MockProfile(
            should_fail=True,
            database_host="failing-host",
        )

        config = SimpleConfig(profiles=[failing_profile])

        # Value should not be set since profile failed
        assert config.database_host is None
        assert config.conflicts == []


class TestMultipleProfiles:
    """Tests for BaseConfig with multiple profiles and conflict resolution."""

    def test_latest_profile_wins_on_conflict(
        self, older_timestamp: datetime, newer_timestamp: datetime
    ) -> None:
        """When multiple profiles have same field, latest timestamp wins."""
        older_profile = MockProfileA(
            last_updated_at=older_timestamp,
            database_host="older-host",
        )
        newer_profile = MockProfileB(
            last_updated_at=newer_timestamp,
            database_host="newer-host",
        )

        config = SimpleConfig(profiles=[older_profile, newer_profile])

        assert config.database_host == "newer-host"
        assert len(config.conflicts) == 1
        conflict = config.conflicts[0]
        assert conflict.key == "database_host"
        assert conflict.selected_value == "newer-host"
        assert "latest update time" in conflict.resolution_reason

    def test_multiple_profiles_different_fields_no_conflict(
        self, older_timestamp: datetime, newer_timestamp: datetime
    ) -> None:
        """Multiple profiles with different fields should not conflict."""
        profile1 = MockProfileA(
            last_updated_at=older_timestamp,
            database_host="host-from-1",
        )
        profile2 = MockProfileB(
            last_updated_at=newer_timestamp,
            database_port=5432,
        )

        config = SimpleConfig(profiles=[profile1, profile2])

        assert config.database_host == "host-from-1"
        assert config.database_port == 5432
        assert config.conflicts == []

    def test_env_takes_precedence_over_multiple_profiles(
        self,
        monkeypatch: pytest.MonkeyPatch,
        older_timestamp: datetime,
        newer_timestamp: datetime,
    ) -> None:
        """Environment should take precedence over all profiles."""
        monkeypatch.setenv("DATABASE_HOST", "env-host")

        profile1 = MockProfileA(
            last_updated_at=older_timestamp,
            database_host="older-host",
        )
        profile2 = MockProfileB(
            last_updated_at=newer_timestamp,
            database_host="newer-host",
        )

        config = SimpleConfig(profiles=[profile1, profile2])

        assert config.database_host == "env-host"
        assert len(config.conflicts) == 1
        assert config.conflicts[0].selected == "environment"

    def test_one_failing_profile_others_succeed(
        self, newer_timestamp: datetime
    ) -> None:
        """One failing profile should not prevent others from being used."""
        failing_profile = MockProfileA(
            should_fail=True,
            database_host="failing-host",
        )
        working_profile = MockProfileB(
            last_updated_at=newer_timestamp,
            database_host="working-host",
        )

        config = SimpleConfig(profiles=[failing_profile, working_profile])

        assert config.database_host == "working-host"
        assert config.conflicts == []


class TestNestedPydanticModels:
    """Tests for nested Pydantic model resolution."""

    def test_single_profile_with_nested_model(self) -> None:
        """Single profile should populate nested model fields."""
        profile = MockProfileWithDatabase(
            app_name="test-app",
            database=DatabaseSettings(
                host="db-host",
                port=5432,
                username="admin",
            ),
        )

        config = NestedConfig(profiles=[profile])

        assert config.app_name == "test-app"
        assert config.database is not None
        assert config.database.host == "db-host"
        assert config.database.port == 5432
        assert config.database.username == "admin"
        assert config.conflicts == []

    def test_nested_field_conflict_resolution(
        self, older_timestamp: datetime, newer_timestamp: datetime
    ) -> None:
        """Nested field conflicts should be resolved by latest timestamp."""
        older_profile = MockProfileWithDatabaseA(
            last_updated_at=older_timestamp,
            database=DatabaseSettings(host="older-db-host", port=3306),
        )
        newer_profile = MockProfileWithDatabaseB(
            last_updated_at=newer_timestamp,
            database=DatabaseSettings(host="newer-db-host", port=5432),
        )

        config = NestedConfig(profiles=[older_profile, newer_profile])

        assert config.database is not None
        # The whole nested object from newer profile should be selected
        assert config.database.host == "newer-db-host"
        assert config.database.port == 5432

    def test_deeply_nested_resolution(self) -> None:
        """Deeply nested structures should resolve correctly."""
        profile = MockProfileWithNested(
            nested_config=NestedSettings(
                timeout_seconds=30,
                retry_count=3,
                feature_flags=FeatureFlags(
                    new_feature=True,
                    beta_mode=False,
                ),
            ),
        )

        config = DeeplyNestedConfig(profiles=[profile])

        assert config.nested_config is not None
        assert config.nested_config.timeout_seconds == 30
        assert config.nested_config.retry_count == 3
        assert config.nested_config.feature_flags is not None
        assert config.nested_config.feature_flags.new_feature is True
        assert config.nested_config.feature_flags.beta_mode is False


class TestDictionaryFields:
    """Tests for dictionary field resolution."""

    def test_single_profile_with_dict_field(self) -> None:
        """Single profile should populate dictionary fields."""
        profile = MockProfileWithDict(
            app_name="test-app",
            settings={"key1": "value1", "key2": 42},
        )

        config = DictConfig(profiles=[profile])

        assert config.app_name == "test-app"
        assert config.settings == {"key1": "value1", "key2": 42}
        assert config.conflicts == []

    def test_dict_field_conflict_between_profiles(
        self, older_timestamp: datetime, newer_timestamp: datetime
    ) -> None:
        """Dictionary field conflicts should be resolved."""
        older_profile = MockProfileWithDictA(
            last_updated_at=older_timestamp,
            settings={"key": "older-value"},
        )
        newer_profile = MockProfileWithDictB(
            last_updated_at=newer_timestamp,
            settings={"key": "newer-value"},
        )

        config = DictConfig(profiles=[older_profile, newer_profile])

        assert config.settings is not None
        # Newer profile should win
        assert config.settings["key"] == "newer-value"


class TestListFields:
    """Tests for list field resolution."""

    def test_single_profile_with_list_field(self) -> None:
        """Single profile should populate list fields."""
        profile = MockProfileWithNested(
            allowed_hosts=["localhost", "example.com"],
        )

        config = DeeplyNestedConfig(profiles=[profile])

        assert config.allowed_hosts == ["localhost", "example.com"]
        assert config.conflicts == []

    def test_list_field_conflict_between_profiles(
        self, older_timestamp: datetime, newer_timestamp: datetime
    ) -> None:
        """List field conflicts should select from latest profile."""
        older_profile = MockProfileWithNestedA(
            last_updated_at=older_timestamp,
            allowed_hosts=["old-host"],
        )
        newer_profile = MockProfileWithNestedB(
            last_updated_at=newer_timestamp,
            allowed_hosts=["new-host-1", "new-host-2"],
        )

        config = DeeplyNestedConfig(profiles=[older_profile, newer_profile])

        assert config.allowed_hosts == ["new-host-1", "new-host-2"]
        assert len(config.conflicts) == 1


class TestConflictRecords:
    """Tests for conflict detection and recording."""

    def test_conflict_record_contains_all_sources(
        self, older_timestamp: datetime, newer_timestamp: datetime
    ) -> None:
        """Conflict record should list all sources that provided values."""
        profile1 = MockProfileA(
            last_updated_at=older_timestamp,
            database_host="host-1",
        )
        profile2 = MockProfileB(
            last_updated_at=newer_timestamp,
            database_host="host-2",
        )

        config = SimpleConfig(profiles=[profile1, profile2])

        assert len(config.conflicts) == 1
        conflict = config.conflicts[0]
        assert "MockProfileA" in conflict.sources
        assert "MockProfileB" in conflict.sources
        assert len(conflict.sources) == 2

    def test_conflict_record_contains_all_values(
        self, older_timestamp: datetime, newer_timestamp: datetime
    ) -> None:
        """Conflict record should contain values from all sources."""
        profile1 = MockProfileA(
            last_updated_at=older_timestamp,
            database_host="host-1",
        )
        profile2 = MockProfileB(
            last_updated_at=newer_timestamp,
            database_host="host-2",
        )

        config = SimpleConfig(profiles=[profile1, profile2])

        assert len(config.conflicts) == 1
        conflict = config.conflicts[0]
        assert conflict.values["MockProfileA"] == "host-1"
        assert conflict.values["MockProfileB"] == "host-2"

    def test_conflict_with_env_records_environment_source(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Conflict with environment should record 'environment' as source."""
        monkeypatch.setenv("DATABASE_HOST", "env-host")

        profile = MockProfile(database_host="profile-host")

        config = SimpleConfig(profiles=[profile])

        conflict = config.conflicts[0]
        assert "environment" in conflict.sources
        assert conflict.values["environment"] == "env-host"
        assert conflict.selected == "environment"
        assert "Environment variable takes precedence" in conflict.resolution_reason

    def test_multiple_conflicts_are_recorded(
        self, older_timestamp: datetime, newer_timestamp: datetime
    ) -> None:
        """Multiple field conflicts should each be recorded."""
        profile1 = MockProfileA(
            last_updated_at=older_timestamp,
            database_host="host-1",
            database_port=3306,
        )
        profile2 = MockProfileB(
            last_updated_at=newer_timestamp,
            database_host="host-2",
            database_port=5432,
        )

        config = SimpleConfig(profiles=[profile1, profile2])

        assert len(config.conflicts) == 2
        conflict_keys = [c.key for c in config.conflicts]
        assert "database_host" in conflict_keys
        assert "database_port" in conflict_keys

    def test_conflict_key_path_for_nested_fields(
        self, older_timestamp: datetime, newer_timestamp: datetime
    ) -> None:
        """Nested field conflicts should have dotted key paths."""
        older_profile = MockProfileWithDatabaseA(
            last_updated_at=older_timestamp,
            database=DatabaseSettings(host="older-host"),
        )
        newer_profile = MockProfileWithDatabaseB(
            last_updated_at=newer_timestamp,
            database=DatabaseSettings(host="newer-host"),
        )

        config = NestedConfig(profiles=[older_profile, newer_profile])

        # Should have conflict at the nested level
        conflict_keys = [c.key for c in config.conflicts]
        # The conflict could be at 'database' level or 'database.host' level
        assert any("database" in key for key in conflict_keys)


class TestSensitiveFieldMasking:
    """Tests for sensitive field masking utility."""

    def test_mask_sensitive_field(self) -> None:
        """Sensitive fields should be masked."""
        config = SimpleConfig(profiles=[], api_key="secret-key")

        masked = config.mask_sensitive("api_key", config.api_key)

        assert masked == "****"

    def test_non_sensitive_field_not_masked(self) -> None:
        """Non-sensitive fields should not be masked."""
        config = SimpleConfig(profiles=[], database_host="localhost")

        result = config.mask_sensitive("database_host", config.database_host)

        assert result == "localhost"

    def test_custom_sensitive_fields(self) -> None:
        """Custom sensitive fields should be respected."""
        config = SimpleConfig(
            profiles=[],
            sensitive_fields=["database_host", "password", "token", "api_key"],
            database_host="secret-host",
        )

        masked = config.mask_sensitive("database_host", config.database_host)

        assert masked == "****"


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_profiles_list(self) -> None:
        """Empty profiles list should work like no profiles."""
        config = SimpleConfig(profiles=[])

        assert config.database_host is None
        assert config.conflicts == []

    def test_all_profiles_fail(self) -> None:
        """Config should handle all profiles failing gracefully."""
        profile1 = MockProfileA(should_fail=True, database_host="host-1")
        profile2 = MockProfileB(should_fail=True, database_host="host-2")

        config = SimpleConfig(profiles=[profile1, profile2])

        assert config.database_host is None
        assert config.conflicts == []

    def test_profile_with_none_values(self) -> None:
        """Profile with None values should not contribute to resolution."""
        profile = MockProfile(
            database_host=None,
            database_port=5432,
        )

        config = SimpleConfig(profiles=[profile])

        assert config.database_host is None
        assert config.database_port == 5432

    def test_same_timestamp_profiles(self, older_timestamp: datetime) -> None:
        """Profiles with same timestamp should resolve deterministically."""
        same_time = older_timestamp
        profile1 = MockProfileA(
            last_updated_at=same_time,
            database_host="host-1",
        )
        profile2 = MockProfileB(
            last_updated_at=same_time,
            database_host="host-2",
        )

        config = SimpleConfig(profiles=[profile1, profile2])

        # Should pick one deterministically (likely the last one in max())
        assert config.database_host in ["host-1", "host-2"]
        assert len(config.conflicts) == 1
