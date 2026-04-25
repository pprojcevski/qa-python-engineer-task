import json
import urllib.error
import urllib.request
from typing import Optional

from config_resolver.profiles.base import BaseProfile
from config_resolver.profiles.common import parse_datetime
from config_resolver.profiles.common import parse_json_fields
from config_resolver.profiles.exceptions import ProfileUnavailableError


class BaseAPIProfile(BaseProfile):
    """Profile that reads configuration from a web API endpoint.

    The `last_updated_at` field is populated from the JSON response
    if a `last_updated_at` key is present, otherwise it remains None.
    """

    def __init__(self, url: str, timeout: float | None = 30.0) -> None:
        """Initialize the API profile.

        Args:
            url: The URL of the API endpoint returning JSON configuration.
            timeout: Request timeout in seconds. Defaults to 30 seconds.
        """
        self._url = url
        self._timeout = timeout

    def fetch(self) -> None:
        """Fetch and parse JSON from the API endpoint, populating profile
        fields.

        Sets `last_updated_at` from the JSON response if the key is present,
        otherwise leaves it as None.

        Raises:
            ProfileUnavailableError: If the API cannot be reached or returns invalid data.
        """
        try:
            request = urllib.request.Request(
                self._url, headers={"Accept": "application/json"}
            )

            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                content = response.read().decode("utf-8")
                data = json.loads(content)

            if not isinstance(data, dict):
                raise ProfileUnavailableError(
                    f"Invalid JSON structure from {self._url}: expected object"
                )

            # Parse last_updated_at from response if present
            if "last_updated_at" in data:
                self.last_updated_at = parse_datetime(data["last_updated_at"])
            else:
                self.last_updated_at = None

            # Parse other fields from JSON data
            parse_json_fields(data, self)

        except urllib.error.URLError as e:
            raise ProfileUnavailableError(
                f"Failed to reach API endpoint {self._url}: {e}"
            ) from e
        except json.JSONDecodeError as e:
            raise ProfileUnavailableError(
                f"Failed to parse JSON from {self._url}: {e}"
            ) from e
        except TimeoutError as e:
            raise ProfileUnavailableError(f"Request to {self._url} timed out") from e
