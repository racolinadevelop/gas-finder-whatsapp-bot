"""Ephemeral, sender-bound TEST Checkout notifications after a verified webhook.

Only the raw WhatsApp sender needed to deliver a confirmation is held in Redis
for up to 22 hours after their own checkout request. It is never persisted in
PostgreSQL or exposed by the browser return page. Stripe's untrusted event
body cannot select a notification recipient.
"""

import logging
from hashlib import sha256

from app.billing.test_store import user_hash
from app.config import REDIS_URL, REDIS_KEY_PREFIX
from app.persistence.redis_client import build_redis_client

logger = logging.getLogger(__name__)
RECIPIENT_TTL_SECONDS = 22 * 60 * 60
CLAIM_TTL_SECONDS = 24 * 60 * 60


def _recipient_key(checkout_session_id: str) -> str:
    return (
        f"{REDIS_KEY_PREFIX}:stripe-test-recipient:"
        + sha256(checkout_session_id.encode("utf-8")).hexdigest()
    )


def remember_test_checkout_recipient(
    sender: str, checkout_session_id: str, *, redis_client=None,
) -> None:
    """Best-effort hint; never make paid access depend on Redis delivery."""
    if not REDIS_URL and redis_client is None:
        return
    if not (
        sender.isascii() and sender.isdigit() and 5 <= len(sender) <= 20
        and checkout_session_id.startswith("cs_test_")
    ):
        return
    try:
        client = redis_client if redis_client is not None else build_redis_client(REDIS_URL)
        client.set(
            _recipient_key(checkout_session_id),
            sender,
            ex=RECIPIENT_TTL_SECONDS,
        )
    except Exception:
        logger.warning("Could not prepare optional Stripe TEST WhatsApp receipt")


def send_verified_test_premium_notice(
    event: dict, *, store, redis_client=None, send_message=None,
) -> bool:
    """Never send on redirect; notify only an applied, signed & verified checkout.

    Called by the Stripe webhook handler *after* authoritative reconciliation
    updates the durable entitlement ledger. Duplicate webhook deliveries
    cannot send multiple notices.
    """
    if event.get("livemode") is not False or event.get("type") not in {
        "checkout.session.completed", "checkout.session.async_payment_succeeded",
    }:
        return False
    session_id = event.get("data", {}).get("object", {}).get("id")
    if not isinstance(session_id, str) or not session_id.startswith("cs_test_"):
        return False
    if not REDIS_URL and redis_client is None:
        return False
    try:
        client = redis_client if redis_client is not None else build_redis_client(REDIS_URL)
        raw = client.get(_recipient_key(session_id))
        if isinstance(raw, bytes):
            raw = raw.decode("ascii")
        if not isinstance(raw, str) or not raw.isascii() or not raw.isdigit():
            return False
        bound = store.find_checkout(session_id)
        if bound is None or bound[0] != user_hash(raw):
            return False
        if not store.has_premium_access(raw):
            return False
        claim_key = _recipient_key(session_id) + ":notified"
        if not client.set(claim_key, "1", ex=CLAIM_TTL_SECONDS, nx=True):
            return False

        if send_message is None:
            from app.services.whatsapp import send_text_message
            send_message = send_text_message
        try:
            send_message(
                to=raw,
                message=(
                    "✅ ¡Tu Premium de prueba ya está activo! ⭐\n"
                    "La inscripción fue confirmada por Stripe TEST. "
                    "Vuelve a WhatsApp y abre «Mi plan» o «Mis favoritas» para continuar.\n"
                    "No se ha cobrado dinero real."
                ),
            )
        except Exception:
            # Do not ask Stripe to replay an already committed payment or
            # falsely claim activation failed just because Meta delivery failed.
            logger.warning("Stripe TEST entitlement verified, WhatsApp notice unavailable")
            return False
        return True
    except Exception:
        logger.warning("Stripe TEST receipt lookup unavailable")
        return False
