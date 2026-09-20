from dataclasses import dataclass
from enum import StrEnum


class ConversationState(StrEnum):
    NEW = "new"
    WAITING_LANGUAGE = "waiting_language"
    MAIN_MENU = "main_menu"
    WAITING_FUEL = "waiting_fuel"
    WAITING_SORT = "waiting_sort"
    WAITING_DISTANCE = "waiting_distance"
    WAITING_CUSTOM_DISTANCE = "waiting_custom_distance"
    WAITING_LOCATION = "waiting_location"
    WAITING_RESULTS = "waiting_results"


@dataclass(frozen=True, slots=True)
class ConversationSession:
    sender: str
    state: ConversationState = ConversationState.NEW
    language: str = "en"
    fuel_type: str = "regular"
    sort: str = "best"
    max_distance_miles: float | None = None
    profile_name: str | None = None
