"""Unit tests for common utility functions."""
from config_resolver.profiles.common import parse_datetime
from config_resolver.profiles.common import parse_json_fields


class TestParseJsonFields:
    """Tests for parse_json_fields function."""

    def test_sets_matching_attributes(self) -> None:
        """Test that matching attributes are set on target object."""

        class Target:
            name: str | None = None
            value: int | None = None

        target = Target()
        data = {"name": "test", "value": 42}

        parse_json_fields(data, target)

        assert target.name == "test"
        assert target.value == 42

    def test_ignores_private_attributes(self) -> None:
        """Test that private attributes (starting with _) are ignored."""

        class Target:
            _private: str | None = None
            public: str | None = None

        target = Target()
        data = {"_private": "secret", "public": "visible"}

        parse_json_fields(data, target)

        assert target._private is None
        assert target.public == "visible"

    def test_ignores_last_updated_at(self) -> None:
        """Test that last_updated_at is handled separately and ignored."""

        class Target:
            last_updated_at: str | None = None
            name: str | None = None

        target = Target()
        data = {"last_updated_at": "2024-01-01T00:00:00", "name": "test"}

        parse_json_fields(data, target)

        assert target.last_updated_at is None
        assert target.name == "test"

    def test_ignores_non_existent_attributes(self) -> None:
        """Test that fields not present on target are ignored."""

        class Target:
            name: str | None = None

        target = Target()
        data = {"name": "test", "nonexistent": "value"}

        parse_json_fields(data, target)

        assert target.name == "test"
        assert (
            not hasattr(target, "nonexistent")
            or getattr(target, "nonexistent", None) is None
        )

    def test_handles_empty_data(self) -> None:
        """Test that empty data dictionary is handled gracefully."""

        class Target:
            name: str | None = None

        target = Target()
        parse_json_fields({}, target)

        assert target.name is None


class TestParseDatetime:
    """Tests for parse_datetime function."""

    def test_parses_iso_format_datetime(self) -> None:
        """Test parsing of ISO format datetime string."""
        result = parse_datetime("2024-01-15T10:30:00")

        assert result is not None
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15
        assert result.hour == 10
        assert result.minute == 30

    def test_parses_iso_format_with_timezone(self) -> None:
        """Test parsing of ISO format datetime with timezone."""
        result = parse_datetime("2024-01-15T10:30:00+00:00")

        assert result is not None
        assert result.year == 2024

    def test_returns_none_for_none_input(self) -> None:
        """Test that None input returns None."""
        result = parse_datetime(None)

        assert result is None

    def test_returns_none_for_invalid_format(self) -> None:
        """Test that invalid datetime string returns None."""
        result = parse_datetime("not-a-datetime")

        assert result is None

    def test_returns_none_for_empty_string(self) -> None:
        """Test that empty string returns None."""
        result = parse_datetime("")

        assert result is None

    def test_parses_date_only(self) -> None:
        """Test parsing of date-only string."""
        result = parse_datetime("2024-01-15")

        assert result is not None
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15
