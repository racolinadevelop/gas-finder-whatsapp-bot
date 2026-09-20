"""Coordinate a location search and its WhatsApp results.

All dependencies are supplied by the webhook handler so conversation storage,
rate limiting and WhatsApp transports remain unchanged and independently testable.
"""

import logging
from collections.abc import Callable

from app.conversation import ConversationSession, ConversationState
from app.favorites.models import FavoriteStation, SearchReply
from app.i18n import t
from app.models import IncomingMessage
from app.preferences import SearchPreferences
from app.presentation import Prompt, build_results_navigation_prompt
from app.presentation.prompts import build_favorites_result_navigation_prompt
from app.providers import GasStationProviderError
from app.services.whatsapp import WhatsAppServiceError

logger = logging.getLogger(__name__)


def run_location_search(
    incoming_message: IncomingMessage,
    session: ConversationSession,
    *,
    allow_search: Callable[[str], bool],
    search: Callable[..., str | SearchReply],
    send_text: Callable[..., dict],
    update_session: Callable[..., ConversationSession],
    send_prompt: Callable[[str, Prompt], None],
    save_preferences: Callable[[str, SearchPreferences], None] = (
        lambda sender, preferences: None
    ),
    save_recent: Callable[[str, tuple[FavoriteStation, ...]], bool] | None = None,
) -> None:
    """Search and show results while retaining preferences for Back/Menu."""
    sender = incoming_message.sender
    latitude = incoming_message.latitude
    longitude = incoming_message.longitude

    if latitude is None or longitude is None:
        return

    if not allow_search(sender):
        try:
            send_text(
                to=sender,
                message=t(session.language, "search_rate_limited"),
            )
        except WhatsAppServiceError as exc:
            logger.warning("Unable to send search rate-limit reply: %s", exc)
        return

    try:
        reply = search(
            session=session,
            latitude=latitude,
            longitude=longitude,
        )
    except GasStationProviderError as exc:
        logger.warning("Unable to search gas stations: %s", exc)
        try:
            send_text(
                to=sender,
                message=t(session.language, "search_temporarily_unavailable"),
            )
        except WhatsAppServiceError as send_exc:
            logger.warning("Unable to send search error reply: %s", send_exc)
        return

    # The original search returns text; optional Premium captures station
    # snapshots from that same search, without calling a provider twice.
    reply_text = reply.text if isinstance(reply, SearchReply) else reply
    try:
        send_text(to=sender, message=reply_text)
    except WhatsAppServiceError as exc:
        logger.warning("Unable to send WhatsApp reply: %s", exc)
        return

    # Only successful result delivery changes the state. Keep fuel, sorting,
    # distance and language preferences for the next location request.
    update_session(sender, {"state": ConversationState.WAITING_RESULTS})
    if session.state == ConversationState.WAITING_LOCATION:
        # Only completed guided searches update the separate user profile.
        save_preferences(sender, SearchPreferences.from_session(session))
    favorites_ready = False
    if isinstance(reply, SearchReply) and save_recent is not None:
        try:
            favorites_ready = save_recent(sender, reply.stations)
        except Exception:
            logger.warning("Unable to store recent favorite choices")
    if favorites_ready and reply.stations:
        send_prompt(
            sender,
            build_favorites_result_navigation_prompt(
                session.language, len(reply.stations)
            ),
        )
    else:
        send_prompt(sender, build_results_navigation_prompt(session.language))
