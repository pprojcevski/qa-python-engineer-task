from typing import Any
from typing import Dict
from typing import List

from pydantic import BaseModel


class ConflictRecord(BaseModel):
    key: str
    sources: list[str]
    values: dict[str, Any]
    selected: str
    selected_value: Any
    resolution_reason: str
