"""Route incoming location messages without owning conversation storage."""

from collections.abc import Callable

from app.conversation import ConversationSession
from app.models import IncomingMessage


def process_location_message(
    incoming_message: IncomingMessage,
    *,
    get_session: Callable[[str], ConversationSession | None],
    search_from_location: Callable[[IncomingMessage, ConversationSession], None],
    dispatch_state_location: Callable[[IncomingMessage, ConversationSession], bool],
    send_expected: Callable[[str, ConversationSession], None],
) -> None:
    """Keep missing-coordinate and unexpected-state behavior unchanged."""
    if (
        incoming_message.latitude is None
        or incoming_message.longitude is None
    ):
        return

    sender = incoming_message.sender
    session = get_session(sender)

    # Preserve the existing direct-location search for first-time users.
    if session is None:
        search_from_location(incoming_message, ConversationSession(sender=sender))
        return

    if not dispatch_state_location(incoming_message, session):
        send_expected(sender, session)
