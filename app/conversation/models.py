from dataclasses import dataclass
from enum import StrEnum


class ConversationState(StrEnum):
    NEW = "new"
    WAITING_LANGUAGE = "waiting_language"
    WAITING_FUEL = "waiting_fuel"
    WAITING_SORT = "waiting_sort"
    WAITING_LOCATION = "waiting_location"


@dataclass(frozen=True, slots=True)
class ConversationSession:
    sender: str
    state: ConversationState = ConversationState.NEW
    language: str = "en"
    fuel_type: str = "regular"
    sort: str = "best"
