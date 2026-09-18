import os

from dotenv import load_dotenv

load_dotenv()

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
HERE_API_KEY = os.getenv("HERE_API_KEY")
GAS_STATION_PROVIDER = os.getenv("GAS_STATION_PROVIDER", "google").lower()

WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
WHATSAPP_BUSINESS_ACCOUNT_ID = os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID")
WHATSAPP_API_VERSION = os.getenv("WHATSAPP_API_VERSION", "v25.0")
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN")
META_APP_SECRET = os.getenv("META_APP_SECRET")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-6-astra")
AI_INTENT_ENABLED = os.getenv("AI_INTENT_ENABLED", "false").lower() in {
    "1",
    "true",
    "yes",
}

REDIS_URL = os.getenv("REDIS_URL")
REDIS_KEY_PREFIX = os.getenv("REDIS_KEY_PREFIX", "gas-finder")
DATABASE_URL = os.getenv("DATABASE_URL")


def positive_int_setting(name: str, default: int) -> int:
    raw_value = os.getenv(name, str(default))
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a positive integer") from exc

    if value <= 0:
        raise RuntimeError(f"{name} must be a positive integer")

    return value


CONVERSATION_TTL_SECONDS = positive_int_setting(
    "CONVERSATION_TTL_SECONDS",
    7 * 24 * 60 * 60,
)
WHATSAPP_DEDUP_TTL_SECONDS = positive_int_setting(
    "WHATSAPP_DEDUP_TTL_SECONDS",
    24 * 60 * 60,
)

if GAS_STATION_PROVIDER not in {"google", "here"}:
    raise RuntimeError("GAS_STATION_PROVIDER must be 'google' or 'here'")

if GAS_STATION_PROVIDER == "google" and not GOOGLE_MAPS_API_KEY:
    raise RuntimeError("GOOGLE_MAPS_API_KEY is not configured")

if GAS_STATION_PROVIDER == "here" and not HERE_API_KEY:
    raise RuntimeError("HERE_API_KEY is not configured")
