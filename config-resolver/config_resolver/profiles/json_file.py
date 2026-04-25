import json
from datetime import datetime
from pathlib import Path
from typing import Union

from config_resolver.profiles.base import BaseProfile
from config_resolver.profiles.common import parse_json_fields
from config_resolver.profiles.exceptions import ProfileUnavailableError


class BaseJsonFileProfile(BaseProfile):
    """Profile that reads configuration from a JSON file.

    The `last_updated_at` field is populated from the file's modification time.
    """

    def __init__(self, file_path: str | Path) -> None:
        """Initialize the JSON file profile.

        Args:
            file_path: Path to the JSON configuration file.
        """
        self._file_path = Path(file_path)

    def fetch(self) -> None:
        """Read and parse the JSON file, populating profile fields.

        Sets `last_updated_at` to the file's modification timestamp.

        Raises:
            ProfileUnavailableError: If the file cannot be read or parsed.
        """
        try:
            if not self._file_path.exists():
                raise ProfileUnavailableError(
                    f"Configuration file not found: {self._file_path}"
                )

            # Get file modification time for last_updated_at
            file_stat = self._file_path.stat()
            self.last_updated_at = datetime.fromtimestamp(file_stat.st_mtime)

            # Read and parse JSON content
            with open(self._file_path, encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, dict):
                raise ProfileUnavailableError(
                    f"Invalid JSON structure in {self._file_path}: expected object"
                )

            # Parse fields from JSON data
            parse_json_fields(data, self)

        except json.JSONDecodeError as e:
            raise ProfileUnavailableError(
                f"Failed to parse JSON file {self._file_path}: {e}"
            ) from e
        except OSError as e:
            raise ProfileUnavailableError(
                f"Failed to read file {self._file_path}: {e}"
            ) from e
