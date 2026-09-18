import hashlib
import hmac


def verify_meta_webhook_signature(
    raw_body: bytes,
    signature: str | None,
    app_secret: str,
) -> bool:
    """Validate Meta's X-Hub-Signature-256 against the raw request body."""

    if not signature or not signature.startswith("sha256="):
        return False

    expected_signature = "sha256=" + hmac.new(
        app_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected_signature, signature)
