"""One-off diagnostic: does Google report fuel-center hours, not store hours?

Run from repository root after configuring GOOGLE_MAPS_API_KEY in .env:
    python scripts/diagnose_sams_hours.py

This script does not change the bot or store data. One paid Text Search (New)
API request is made; currentOpeningHours uses the Enterprise billing tier.
Do not paste API keys or .env contents when sharing the output.
"""

import os
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
from dotenv import load_dotenv

SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
QUERY = "Sam's Club fuel center 6622 Preston Hwy Louisville KY"
FIELD_MASK = ",".join(
    (
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.primaryType",
        "places.types",
        "places.businessStatus",
        "places.currentOpeningHours",
        "places.regularOpeningHours",
    )
)
STATION_TZ = ZoneInfo("America/Kentucky/Louisville")


def format_status(hours: dict) -> str:
    if "openNow" not in hours:
        return "UNKNOWN (Google supplied no openNow value)"
    return "OPEN" if hours["openNow"] is True else "CLOSED"


def format_local_time(value: str | None) -> str:
    if not value:
        return "not provided"
    instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return instant.astimezone(STATION_TZ).strftime("%a %I:%M %p %Z")


def fetch_candidates(api_key: str) -> list[dict]:
    response = httpx.post(
        SEARCH_URL,
        headers={
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": FIELD_MASK,
            "Content-Type": "application/json",
        },
        json={
            "textQuery": QUERY,
            "pageSize": 5,
            "languageCode": "en",
        },
        timeout=10.0,
    )
    response.raise_for_status()
    return response.json().get("places", [])


def main() -> None:
    load_dotenv()
    key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not key:
        raise SystemExit("GOOGLE_MAPS_API_KEY is not set; no request was sent.")

    try:
        candidates = fetch_candidates(key)
    except (httpx.HTTPError, ValueError) as exc:
        raise SystemExit(
            f"Google Places query failed ({type(exc).__name__}). "
            "Check key permissions, billing and API access; do not share your key."
        ) from None

    print("Sam's Club Fuel Center — 6622 Preston Hwy, Louisville, KY")
    print(f"Google Places returned {len(candidates)} candidate(s).")
    if not candidates:
        print("No match. Cannot conclude whether the fuel center is open.")
        return

    for index, place in enumerate(candidates, start=1):
        name = place.get("displayName", {}).get("text", "(no name)")
        current = place.get("currentOpeningHours") or {}
        regular = place.get("regularOpeningHours") or {}
        print(f"\nCandidate {index}: {name}")
        print(f"  Address: {place.get('formattedAddress', '(missing)')}")
        print(f"  Place ID: {place.get('id', '(missing)')}")
        print(f"  Primary type: {place.get('primaryType', '(missing)')}")
        print(f"  Types: {', '.join(place.get('types', [])) or '(missing)'}")
        print(f"  Business status: {place.get('businessStatus', '(missing)')}")
        print(f"  OPEN NOW: {format_status(current)}")
        print(f"  Next opening (Louisville): {format_local_time(current.get('nextOpenTime'))}")
        print(f"  Next closing (Louisville): {format_local_time(current.get('nextCloseTime'))}")
        print("  Current schedule: " + " | ".join(
            current.get("weekdayDescriptions") or ["not provided"]
        ))
        print("  Regular schedule: " + " | ".join(
            regular.get("weekdayDescriptions") or ["not provided"]
        ))

    print(
        "\nIMPORTANT: Compare the place name, type, ID and hours against the "
        "fuel-center listing, not the Sam's Club store. Do not infer "
        "the fuel center is open from the store's opening hours."
    )


if __name__ == "__main__":
    main()
