from abc import ABC
from abc import abstractmethod
from datetime import datetime
from typing import Optional


class BaseProfile(ABC):
    """Abstract base class for a configuration profile source. Subclasses fill
    in concrete fields and fetch logic.

    Fetching is intentionally not triggered during object creation. The
    config base class should explicitly call fetch() when resolving
    profiles.
    """

    last_updated_at: datetime | None = None

    @abstractmethod
    def fetch(self) -> None:
        """Retrieve and populate profile fields from the source.

        Fetch method should populate each field, including
        last_updated_at. Raise a custom ProfileUnavailableError if
        source is unreachable.
        """
        pass
