from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from app.constants import MAX_DISTANCE_MILES, MIN_DISTANCE_MILES
from app.conversation.models import ConversationSession, ConversationState


class SearchInterpretation(Protocol):
    fuel_type: str | None
    sort: str | None
    max_distance_miles: float | None
    language: str | None

    @property
    def search_preferences(self) -> dict[str, str | float]: ...


class SearchFlowPrompt(StrEnum):
    INVALID_DISTANCE = "invalid_distance"
    FUEL = "fuel"
    SORT = "sort"
    DISTANCE = "distance"
    LOCATION = "location"


@dataclass(frozen=True, slots=True)
class SearchFlowDecision:
    """State transition and prompt selected for one interpreted search."""

    prompt: SearchFlowPrompt
    language: str
    session_changes: dict[str, object] = field(default_factory=dict)
    selected: bool = False
    saved: bool = False


def decide_search_flow(
    session: ConversationSession | None,
    interpretation: SearchInterpretation,
) -> SearchFlowDecision:
    """Choose the next guided-search step without performing side effects."""

    language = (
        session.language
        if session is not None
        and session.state
        not in {ConversationState.NEW, ConversationState.WAITING_LANGUAGE}
        else interpretation.language or "en"
    )
    max_distance = interpretation.max_distance_miles

    if max_distance is not None and not (
        MIN_DISTANCE_MILES <= max_distance <= MAX_DISTANCE_MILES
    ):
        return SearchFlowDecision(
            prompt=SearchFlowPrompt.INVALID_DISTANCE,
            language=language,
        )

    if (
        session is not None
        and session.state == ConversationState.WAITING_FUEL
        and interpretation.fuel_type is not None
        and interpretation.sort is None
    ):
        changes: dict[str, object] = {
            "state": ConversationState.WAITING_SORT,
            "language": language,
            "fuel_type": interpretation.fuel_type,
        }
        if max_distance is not None:
            changes["max_distance_miles"] = max_distance

        return SearchFlowDecision(
            prompt=SearchFlowPrompt.SORT,
            language=language,
            session_changes=changes,
            selected=True,
        )

    if (
        max_distance is not None
        and interpretation.fuel_type is None
        and interpretation.sort is None
    ):
        if (
            session is not None
            and session.state == ConversationState.WAITING_SORT
        ):
            return SearchFlowDecision(
                prompt=SearchFlowPrompt.SORT,
                language=language,
                session_changes={"max_distance_miles": max_distance},
            )

        return SearchFlowDecision(
            prompt=SearchFlowPrompt.FUEL,
            language=language,
            session_changes={
                "state": ConversationState.WAITING_FUEL,
                "language": language,
                "max_distance_miles": max_distance,
            },
        )

    if (
        session is not None
        and session.state == ConversationState.WAITING_SORT
        and interpretation.sort is not None
        and interpretation.fuel_type is None
    ):
        has_distance = (
            max_distance is not None
            or session.max_distance_miles is not None
        )
        next_state = (
            ConversationState.WAITING_LOCATION
            if has_distance
            else ConversationState.WAITING_DISTANCE
        )
        changes = {
            "state": next_state,
            "language": language,
            "sort": interpretation.sort,
        }
        if max_distance is not None:
            changes["max_distance_miles"] = max_distance

        return SearchFlowDecision(
            prompt=(
                SearchFlowPrompt.LOCATION
                if has_distance
                else SearchFlowPrompt.DISTANCE
            ),
            language=language,
            session_changes=changes,
            saved=has_distance,
        )

    preferences = interpretation.search_preferences
    if not preferences:
        return SearchFlowDecision(
            prompt=SearchFlowPrompt.FUEL,
            language=language,
            session_changes={
                "state": ConversationState.WAITING_FUEL,
                "language": language,
            },
        )

    return SearchFlowDecision(
        prompt=SearchFlowPrompt.LOCATION,
        language=language,
        session_changes={
            "state": ConversationState.WAITING_LOCATION,
            "language": language,
            **preferences,
        },
        saved=True,
    )
