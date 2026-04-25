"""Unit tests for BaseAPIProfile."""
import pytest
from config_resolver.profiles.exceptions import ProfileUnavailableError
from pytest_httpserver import HTTPServer
from tests.conftest import APIProfile


class TestBaseAPIProfile:
    """Tests for API profile functionality."""

    def test_fetch_reads_from_api_endpoint(self, api_profile: APIProfile) -> None:
        """Test that fetch successfully reads and parses JSON from API."""
        api_profile.fetch()

        assert api_profile.database_host == "localhost"
        assert api_profile.database_port == 5432
        assert api_profile.api_key == "test-api-key-123"
        assert api_profile.debug_mode is True
        assert api_profile.max_connections == 100

    def test_fetch_sets_last_updated_at_from_response(
        self, api_profile: APIProfile
    ) -> None:
        """Test that fetch populates last_updated_at from API response."""
        api_profile.fetch()

        assert api_profile.last_updated_at is not None

    def test_fetch_without_timestamp_in_response(
        self, mock_api_server_no_timestamp: HTTPServer
    ) -> None:
        """Test that fetch works when API response lacks last_updated_at."""
        profile = APIProfile(url=mock_api_server_no_timestamp.url_for("/config"))
        profile.fetch()

        assert profile.database_host == "localhost"
        assert profile.last_updated_at is None

    def test_fetch_raises_error_for_unreachable_server(self) -> None:
        """Test that fetch raises ProfileUnavailableError for unreachable
        URL."""
        profile = APIProfile(url="http://localhost:59999/nonexistent", timeout=1.0)

        with pytest.raises(ProfileUnavailableError) as exc_info:
            profile.fetch()

        assert "failed to reach" in str(exc_info.value).lower()

    def test_fetch_raises_error_for_invalid_json(
        self, mock_api_server_invalid_json: HTTPServer
    ) -> None:
        """Test that fetch raises ProfileUnavailableError for invalid JSON
        response."""
        profile = APIProfile(url=mock_api_server_invalid_json.url_for("/config"))

        with pytest.raises(ProfileUnavailableError) as exc_info:
            profile.fetch()

        assert "failed to parse" in str(exc_info.value).lower()

    def test_fetch_raises_error_for_non_dict_response(
        self, mock_api_server_non_dict: HTTPServer
    ) -> None:
        """Test that fetch raises ProfileUnavailableError when response is not
        an object."""
        profile = APIProfile(url=mock_api_server_non_dict.url_for("/config"))

        with pytest.raises(ProfileUnavailableError) as exc_info:
            profile.fetch()

        assert "invalid json structure" in str(exc_info.value).lower()

    def test_fetch_respects_timeout_setting(self, httpserver: HTTPServer) -> None:
        """Test that fetch uses configured timeout."""
        import time

        def slow_handler(request):
            time.sleep(2)
            return '{"database_host": "localhost"}'

        httpserver.expect_request("/slow").respond_with_handler(slow_handler)

        profile = APIProfile(url=httpserver.url_for("/slow"), timeout=0.5)

        with pytest.raises(ProfileUnavailableError):
            profile.fetch()

    def test_fetch_sends_accept_json_header(self, httpserver: HTTPServer) -> None:
        """Test that fetch sends Accept: application/json header."""
        received_headers = {}

        def capture_headers(request):
            nonlocal received_headers
            received_headers = dict(request.headers)
            return '{"database_host": "localhost"}'

        httpserver.expect_request("/headers").respond_with_handler(capture_headers)

        profile = APIProfile(url=httpserver.url_for("/headers"))
        profile.fetch()

        assert received_headers.get("Accept") == "application/json"

    def test_fetch_handles_404_response(self, httpserver: HTTPServer) -> None:
        """Test that fetch raises ProfileUnavailableError for 404 response."""
        httpserver.expect_request("/notfound").respond_with_data(
            "Not Found", status=404
        )

        profile = APIProfile(url=httpserver.url_for("/notfound"))

        with pytest.raises(ProfileUnavailableError):
            profile.fetch()

    def test_default_timeout_is_30_seconds(self) -> None:
        """Test that default timeout is 30 seconds."""
        profile = APIProfile(url="http://example.com/config")

        assert profile._timeout == 30.0
