"""Run real Stripe sandbox smoke tests without printing secrets or phone IDs.

Usage (from a trusted local shell with the environment set):
    python scripts/stripe_sandbox_smoke.py checkout
    python scripts/stripe_sandbox_smoke.py status
    python scripts/stripe_sandbox_smoke.py portal

Requires GAS_FINDER_BASE_URL, SANDBOX_TEST_WHATSAPP_ID, INTERNAL_API_TOKEN.
Only run against a bot with STRIPE_TEST_MODE_ENABLED=true and sk_test_ key.
"""

import os
import sys
from urllib.parse import urlparse

import httpx


ACTIONS = {"checkout", "status", "portal"}


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in ACTIONS:
        print("Usage: python scripts/stripe_sandbox_smoke.py checkout|status|portal")
        return 2
    action = sys.argv[1]
    base = os.getenv("GAS_FINDER_BASE_URL", "").rstrip("/")
    user = os.getenv("SANDBOX_TEST_WHATSAPP_ID", "")
    token = os.getenv("INTERNAL_API_TOKEN", "")
    url = urlparse(base)
    if url.scheme != "https" or not url.hostname or url.username:
        print("Configure an HTTPS GAS_FINDER_BASE_URL for your Railway bot.")
        return 2
    if not user.isascii() or not user.isdigit() or not 5 <= len(user) <= 20:
        print("Configure SANDBOX_TEST_WHATSAPP_ID as test account phone digits.")
        return 2
    if not token:
        print("Configure INTERNAL_API_TOKEN in your local environment.")
        return 2

    try:
        response = httpx.post(
            base + "/api/v1/billing/test/" + action,
            json={"whatsapp_id": user},
            headers={"Authorization": "Bearer " + token},
            timeout=25.0,
        )
        if response.status_code != 200:
            # Do not display credentials, phone identifiers or provider bodies.
            print("Sandbox request failed: HTTP", response.status_code)
            return 1
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        print("Sandbox request failed:", type(exc).__name__)
        return 1

    if action == "status":
        print("Sandbox linked:", payload.get("linked", False))
        print("Sandbox subscription status:", payload.get("status", "unknown"))
        print("Sandbox Premium feature access:", payload.get("sandbox_premium_access", False))
    else:
        link = payload.get("url")
        if not isinstance(link, str) or not link.startswith("https://"):
            print("No valid sandbox link was returned.")
            return 1
        print("Open this Stripe TEST link in your own browser:")
        print(link)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
