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

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-6-astra")
AI_INTENT_ENABLED = os.getenv("AI_INTENT_ENABLED", "false").lower() in {
    "1",
    "true",
    "yes",
}

if GAS_STATION_PROVIDER not in {"google", "here"}:
    raise RuntimeError("GAS_STATION_PROVIDER must be 'google' or 'here'")

if GAS_STATION_PROVIDER == "google" and not GOOGLE_MAPS_API_KEY:
    raise RuntimeError("GOOGLE_MAPS_API_KEY is not configured")

if GAS_STATION_PROVIDER == "here" and not HERE_API_KEY:
    raise RuntimeError("HERE_API_KEY is not configured")
