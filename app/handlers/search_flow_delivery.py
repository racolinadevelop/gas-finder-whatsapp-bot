"""Apply a guided-search decision using the handler's existing dependencies."""

import logging
from collections.abc import Callable

from app.constants import MAX_DISTANCE_MILES, MIN_DISTANCE_MILES
from app.conversation import ConversationSession, SearchFlowDecision, SearchFlowPrompt
from app.i18n import t
from app.services.whatsapp import WhatsAppServiceError

logger = logging.getLogger(__name__)


def deliver_search_flow_decision(
    sender: str,
    decision: SearchFlowDecision,
    *,
    apply_changes: Callable[[str, dict], ConversationSession],
    send_text: Callable[..., object],
    send_fuel: Callable[..., None],
    send_sort: Callable[..., None],
    send_distance: Callable[..., None],
    send_location: Callable[..., None],
) -> None:
    """Validate distance before changing state, then show exactly one step."""
    if decision.prompt == SearchFlowPrompt.INVALID_DISTANCE:
        try:
            send_text(
                to=sender,
                message=t(
                    decision.language,
                    "invalid_max_distance",
                    minimum=MIN_DISTANCE_MILES,
                    maximum=MAX_DISTANCE_MILES,
                ),
            )
        except WhatsAppServiceError as exc:
            logger.warning("Could not send distance validation message: %s", exc)
        return

    session = apply_changes(sender, decision.session_changes)

    if decision.prompt == SearchFlowPrompt.FUEL:
        send_fuel(sender, decision.language)
    elif decision.prompt == SearchFlowPrompt.SORT:
        send_sort(sender, session, selected=decision.selected)
    elif decision.prompt == SearchFlowPrompt.DISTANCE:
        send_distance(sender, session)
    elif decision.prompt == SearchFlowPrompt.LOCATION:
        send_location(sender, session, saved=decision.saved)
