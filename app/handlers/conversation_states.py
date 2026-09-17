from collections.abc import Callable

from app.conversation import (
    ConversationSession,
    ConversationState,
    ConversationTransitions,
    is_distance_in_range,
    parse_distance_input,
)
from app.conversation.options import (
    CUSTOM_DISTANCE_ID,
    DISTANCE_OPTIONS,
    FUEL_BUTTONS,
    SORT_BUTTONS,
)
from app.models import IncomingMessage
from app.presentation import (
    Prompt,
    build_custom_distance_prompt,
    build_distance_prompt,
    build_fuel_prompt,
    build_location_prompt,
    build_sort_prompt,
    build_state_prompt,
)

PromptSender = Callable[[str, Prompt], None]


class ConversationStateHandlers:
    """Handle guided-flow selections for the active conversation state."""

    def __init__(
        self,
        transitions: ConversationTransitions,
        send_prompt: PromptSender,
    ) -> None:
        self._transitions = transitions
        self._send_prompt = send_prompt

    def language_selection(self, sender: str, language: str) -> None:
        self._transitions.select_language(sender, language)
        self._send_prompt(
            sender,
            build_fuel_prompt(language, welcome=True),
        )

    def fuel_selection(self, sender: str, fuel_type: str) -> None:
        session = self._transitions.select_fuel(sender, fuel_type)
        self._send_prompt(
            sender,
            build_sort_prompt(session, selected=True),
        )

    def sort_selection(self, sender: str, sort_option: str) -> None:
        session = self._transitions.select_sort(sender, sort_option)

        if session.state == ConversationState.WAITING_LOCATION:
            prompt = build_location_prompt(session, saved=True)
        else:
            prompt = build_distance_prompt(session)

        self._send_prompt(sender, prompt)

    def distance_selection(self, sender: str, distance: float) -> None:
        session = self._transitions.select_distance(sender, distance)
        self._send_prompt(
            sender,
            build_location_prompt(session, saved=True),
        )

    def distance_text(
        self,
        message: IncomingMessage,
        session: ConversationSession,
    ) -> None:
        distance = parse_distance_input(message.text or "")

        if distance is None:
            if session.state == ConversationState.WAITING_DISTANCE:
                prompt = build_distance_prompt(session, error=True)
            else:
                prompt = build_custom_distance_prompt(
                    session.language,
                    error=True,
                )
            self._send_prompt(message.sender, prompt)
            return

        if not is_distance_in_range(distance):
            self._transitions.request_custom_distance(message.sender)
            self._send_prompt(
                message.sender,
                build_custom_distance_prompt(
                    session.language,
                    range_error=True,
                ),
            )
            return

        self.distance_selection(message.sender, distance)

    def fuel_interaction(
        self,
        message: IncomingMessage,
        session: ConversationSession,
    ) -> None:
        button_id = message.selection_id or ""

        if button_id in FUEL_BUTTONS:
            self.fuel_selection(message.sender, FUEL_BUTTONS[button_id])
            return

        self._send_expected_prompt(message.sender, session)

    def sort_interaction(
        self,
        message: IncomingMessage,
        session: ConversationSession,
    ) -> None:
        button_id = message.selection_id or ""

        if button_id in SORT_BUTTONS:
            self.sort_selection(message.sender, SORT_BUTTONS[button_id])
            return

        self._send_expected_prompt(message.sender, session)

    def distance_interaction(
        self,
        message: IncomingMessage,
        session: ConversationSession,
    ) -> None:
        button_id = message.selection_id or ""

        if button_id in DISTANCE_OPTIONS:
            self.distance_selection(
                message.sender,
                DISTANCE_OPTIONS[button_id],
            )
            return

        if button_id == CUSTOM_DISTANCE_ID:
            self._transitions.request_custom_distance(message.sender)
            self._send_prompt(
                message.sender,
                build_custom_distance_prompt(session.language),
            )
            return

        self._send_expected_prompt(message.sender, session)

    def _send_expected_prompt(
        self,
        sender: str,
        session: ConversationSession,
    ) -> None:
        self._send_prompt(
            sender,
            build_state_prompt(session, error=True),
        )
