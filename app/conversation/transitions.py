from collections.abc import Mapping
from typing import Protocol

from app.conversation.models import ConversationSession, ConversationState
from app.conversation.navigation import (
    NavigationAction,
    get_previous_state,
)


class ConversationStore(Protocol):
    def get(self, sender: str) -> ConversationSession | None: ...

    def update(self, sender: str, **changes) -> ConversationSession: ...

    def pop(self, sender: str) -> ConversationSession | None: ...


class ConversationTransitions:
    """Apply conversation state changes independently of message transport."""

    def __init__(self, store: ConversationStore) -> None:
        self._store = store

    def begin(
        self,
        sender: str,
        profile_name: str | None = None,
    ) -> ConversationSession:
        changes = {"state": ConversationState.WAITING_LANGUAGE}
        if profile_name:
            changes["profile_name"] = profile_name
        return self._store.update(sender, **changes)

    def ensure_started(self, sender: str) -> ConversationSession:
        return self._store.get(sender) or self.begin(sender)

    def reset(self, sender: str) -> ConversationSession:
        return self._store.update(
            sender,
            state=ConversationState.WAITING_LANGUAGE,
            language="en",
            fuel_type="regular",
            sort="best",
            max_distance_miles=None,
        )

    def navigate(
        self,
        sender: str,
        action: NavigationAction,
    ) -> ConversationSession:
        if action == NavigationAction.MENU:
            return self.reset(sender)

        current_session = self._store.get(sender)
        current_state = (
            current_session.state
            if current_session is not None
            else ConversationState.NEW
        )
        return self._store.update(
            sender,
            state=get_previous_state(current_state),
        )

    def apply(
        self,
        sender: str,
        changes: Mapping[str, object],
    ) -> ConversationSession:
        return self._store.update(sender, **changes)

    def select_language(
        self,
        sender: str,
        language: str,
        profile_name: str | None = None,
    ) -> ConversationSession:
        changes = {
            "state": ConversationState.WAITING_FUEL,
            "language": language,
            "fuel_type": "regular",
            "sort": "best",
            "max_distance_miles": None,
        }
        if profile_name:
            changes["profile_name"] = profile_name
        return self._store.update(sender, **changes)

    def select_fuel(
        self,
        sender: str,
        fuel_type: str,
    ) -> ConversationSession:
        return self._store.update(
            sender,
            state=ConversationState.WAITING_SORT,
            fuel_type=fuel_type,
        )

    def select_sort(
        self,
        sender: str,
        sort_option: str,
    ) -> ConversationSession:
        current_session = self._store.get(sender)
        next_state = (
            ConversationState.WAITING_LOCATION
            if current_session is not None
            and current_session.max_distance_miles is not None
            else ConversationState.WAITING_DISTANCE
        )
        return self._store.update(
            sender,
            state=next_state,
            sort=sort_option,
        )

    def select_distance(
        self,
        sender: str,
        distance_miles: float,
    ) -> ConversationSession:
        return self._store.update(
            sender,
            state=ConversationState.WAITING_LOCATION,
            max_distance_miles=distance_miles,
        )

    def request_custom_distance(self, sender: str) -> ConversationSession:
        return self._store.update(
            sender,
            state=ConversationState.WAITING_CUSTOM_DISTANCE,
        )

    def finish(self, sender: str) -> ConversationSession | None:
        return self._store.pop(sender)
