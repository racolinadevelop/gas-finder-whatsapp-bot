"""Process incoming WhatsApp webhook events without conversation-specific logic."""

import logging
from collections.abc import Callable

from app.models import IncomingMessage

logger = logging.getLogger(__name__)


def process_webhook(
    payload: dict,
    *,
    parse_message: Callable[[dict], IncomingMessage | None],
    claim_message: Callable[[str | None], bool],
    release_message: Callable[[str | None], None],
    ensure_user: Callable[[str], object],
    dispatch_message: Callable[[IncomingMessage], object],
) -> dict:
    """Parse, deduplicate and dispatch one webhook event, preserving retry rules."""
    incoming_message = parse_message(payload)

    if not incoming_message:
        logger.info("WhatsApp webhook event without a user message")
        return {"status": "ok"}

    if not claim_message(incoming_message.message_id):
        logger.info("Ignoring duplicate WhatsApp message")
        return {"status": "ok"}

    logger.info(
        "Incoming WhatsApp message type=%s",
        incoming_message.message_type,
    )

    try:
        ensure_user(incoming_message.sender)
        dispatch_message(incoming_message)
    except Exception:
        release_message(incoming_message.message_id)
        raise

    return {"status": "ok"}
