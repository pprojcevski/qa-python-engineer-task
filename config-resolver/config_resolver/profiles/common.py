from datetime import datetime
from typing import Any


def parse_json_fields(data: dict[str, Any], target: object) -> None:
    """Parse JSON data and set matching fields on the target object.

    This function iterates through the JSON data and sets attributes
    on the target object for any keys that match existing attributes
    (excluding private attributes and 'last_updated_at' which is handled separately).

    Args:
        data: Dictionary containing the JSON data to parse.
        target: The object on which to set the attributes.
    """
    for key, value in data.items():
        if key.startswith("_") or key == "last_updated_at":
            continue
        if hasattr(target, key):
            setattr(target, key, value)


def parse_datetime(value: str | None) -> datetime | None:
    """Parse a datetime string in ISO format.

    Args:
        value: ISO format datetime string or None.

    Returns:
        Parsed datetime object or None if value is None or invalid.
    """
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None
