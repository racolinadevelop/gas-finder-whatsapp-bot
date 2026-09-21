import os

from dotenv import load_dotenv

load_dotenv()

APP_ENV = os.getenv("APP_ENV", "development").strip().lower()

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
HERE_API_KEY = os.getenv("HERE_API_KEY")
GAS_STATION_PROVIDER = os.getenv("GAS_STATION_PROVIDER", "google").lower()

WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
WHATSAPP_BUSINESS_ACCOUNT_ID = os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID")
WHATSAPP_API_VERSION = os.getenv("WHATSAPP_API_VERSION", "v25.0")
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN")
META_APP_SECRET = os.getenv("META_APP_SECRET")
INTERNAL_API_TOKEN = os.getenv("INTERNAL_API_TOKEN")

# Stripe integration is TEST ONLY and disabled by default. No entitlement
# transitions or live billing are enabled by this configuration switch.
STRIPE_TEST_MODE_ENABLED = os.getenv(
    "STRIPE_TEST_MODE_ENABLED", "false"
).lower() in {"1", "true", "yes"}
# Opt-in for sending Stripe TEST Checkout links to verified WhatsApp senders.
# This never permits live Stripe keys or public real-money billing.
STRIPE_TEST_WHATSAPP_LINKS_ENABLED = os.getenv(
    "STRIPE_TEST_WHATSAPP_LINKS_ENABLED", "false"
).lower() in {"1", "true", "yes"}
STRIPE_TEST_SECRET_KEY = os.getenv("STRIPE_TEST_SECRET_KEY", "")
STRIPE_TEST_PRICE_ID = os.getenv("STRIPE_TEST_PRICE_ID", "")
STRIPE_TEST_WEBHOOK_SECRET = os.getenv("STRIPE_TEST_WEBHOOK_SECRET", "")
STRIPE_TEST_SUCCESS_URL = os.getenv("STRIPE_TEST_SUCCESS_URL", "")
STRIPE_TEST_CANCEL_URL = os.getenv("STRIPE_TEST_CANCEL_URL", "")
STRIPE_TEST_PORTAL_RETURN_URL = os.getenv(
    "STRIPE_TEST_PORTAL_RETURN_URL", ""
)

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
API_DOCS_ENABLED = os.getenv("API_DOCS_ENABLED", "true").lower() in {
    "1",
    "true",
    "yes",
}


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
SEARCH_RATE_LIMIT_MAX = positive_int_setting(
    "SEARCH_RATE_LIMIT_MAX",
    10,
)
SEARCH_RATE_LIMIT_WINDOW_SECONDS = positive_int_setting(
    "SEARCH_RATE_LIMIT_WINDOW_SECONDS",
    5 * 60,
)

# Places Text Search can return up to three pages. Prefer full coverage
# so candidates on later pages (including Sam's Club) are not skipped.
GOOGLE_TEXT_MAX_PAGES = positive_int_setting("GOOGLE_TEXT_MAX_PAGES", 3)
if GOOGLE_TEXT_MAX_PAGES > 3:
    raise RuntimeError("GOOGLE_TEXT_MAX_PAGES must be between 1 and 3")

# Routes API is separately billable (matrix elements = destinations).
# Never enable extra API requests without an explicit opt-in.
ROUTES_API_ENABLED = os.getenv("ROUTES_API_ENABLED", "false").lower() in {
    "1", "true", "yes",
}
ROUTES_MAX_DESTINATIONS = positive_int_setting("ROUTES_MAX_DESTINATIONS", 5)
if ROUTES_MAX_DESTINATIONS > 5:
    raise RuntimeError("ROUTES_MAX_DESTINATIONS must be between 1 and 5")

# Budget is based on billable matrix elements, NOT on HTTP request count.
# Defaults deliberately conservative for initial user testing. UTC calendar
# daily/monthly counters are shared by all production workers through Redis.
ROUTES_DAILY_ELEMENT_LIMIT = positive_int_setting(
    "ROUTES_DAILY_ELEMENT_LIMIT", 25
)
ROUTES_MONTHLY_ELEMENT_LIMIT = positive_int_setting(
    "ROUTES_MONTHLY_ELEMENT_LIMIT", 150
)
if ROUTES_DAILY_ELEMENT_LIMIT > ROUTES_MONTHLY_ELEMENT_LIMIT:
    raise RuntimeError(
        "ROUTES_DAILY_ELEMENT_LIMIT must not exceed ROUTES_MONTHLY_ELEMENT_LIMIT"
    )

if GAS_STATION_PROVIDER not in {"google", "here"}:
    raise RuntimeError("GAS_STATION_PROVIDER must be 'google' or 'here'")

if GAS_STATION_PROVIDER == "google" and not GOOGLE_MAPS_API_KEY:
    raise RuntimeError("GOOGLE_MAPS_API_KEY is not configured")

if GAS_STATION_PROVIDER == "here" and not HERE_API_KEY:
    raise RuntimeError("HERE_API_KEY is not configured")


PRODUCTION_REQUIRED_SETTINGS = (
    "WHATSAPP_ACCESS_TOKEN",
    "WHATSAPP_PHONE_NUMBER_ID",
    "WHATSAPP_VERIFY_TOKEN",
    "META_APP_SECRET",
    "INTERNAL_API_TOKEN",
    "REDIS_URL",
    "DATABASE_URL",
)


def validate_production_configuration(
    settings: dict[str, str | None],
    *,
    api_docs_enabled: bool,
) -> None:
    missing = [
        name
        for name in PRODUCTION_REQUIRED_SETTINGS
        if not settings.get(name)
    ]

    if missing:
        raise RuntimeError(
            "Missing required production settings: "
            + ", ".join(missing)
        )

    if api_docs_enabled:
        raise RuntimeError(
            "API_DOCS_ENABLED must be false in production"
        )


if APP_ENV not in {"development", "test", "production"}:
    raise RuntimeError(
        "APP_ENV must be 'development', 'test', or 'production'"
    )

if APP_ENV == "production":
    validate_production_configuration(
        {
            "WHATSAPP_ACCESS_TOKEN": WHATSAPP_ACCESS_TOKEN,
            "WHATSAPP_PHONE_NUMBER_ID": WHATSAPP_PHONE_NUMBER_ID,
            "WHATSAPP_VERIFY_TOKEN": WHATSAPP_VERIFY_TOKEN,
            "META_APP_SECRET": META_APP_SECRET,
            "INTERNAL_API_TOKEN": INTERNAL_API_TOKEN,
            "REDIS_URL": REDIS_URL,
            "DATABASE_URL": DATABASE_URL,
        },
        api_docs_enabled=API_DOCS_ENABLED,
    )
