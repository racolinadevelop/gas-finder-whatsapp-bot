from dataclasses import dataclass
from enum import StrEnum


class IntentType(StrEnum):
    SEARCH_GAS = "search_gas"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class MessageInterpretation:
    """Structured meaning extracted from a user's natural-language message."""

    intent: IntentType
    fuel_type: str | None = None
    sort: str | None = None
    max_distance_miles: float | None = None
    language: str | None = None
    confidence: float = 0.0
    source: str = "rules"

    @property
    def search_preferences(self) -> dict[str, str | float]:
        preferences = {}

        if self.fuel_type is not None:
            preferences["fuel_type"] = self.fuel_type
        if self.sort is not None:
            preferences["sort"] = self.sort
        if self.max_distance_miles is not None:
            preferences["max_distance_miles"] = self.max_distance_miles

        return preferences
