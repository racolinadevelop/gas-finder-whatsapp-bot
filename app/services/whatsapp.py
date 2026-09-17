import httpx
from app.intelligence import RuleBasedIntentInterpreter
from app.i18n import t
from app.models import IncomingMessage

from app.config import (
    WHATSAPP_ACCESS_TOKEN,
    WHATSAPP_API_VERSION,
    WHATSAPP_PHONE_NUMBER_ID,
)


class WhatsAppServiceError(Exception):
    pass


def send_text_message(to: str, message: str) -> dict:
    if not WHATSAPP_ACCESS_TOKEN or not WHATSAPP_PHONE_NUMBER_ID:
        raise WhatsAppServiceError("WhatsApp configuration is missing.")

    url = (
        f"https://graph.facebook.com/"
        f"{WHATSAPP_API_VERSION}/"
        f"{WHATSAPP_PHONE_NUMBER_ID}/messages"
    )

    headers = {
        "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {
            "body": message,
        },
    }

    try:
        response = httpx.post(
            url,
            headers=headers,
            json=payload,
            timeout=10.0,
        )

        response.raise_for_status()

    except httpx.TimeoutException as exc:
        raise WhatsAppServiceError("WhatsApp API took too long to respond.") from exc

    except httpx.HTTPStatusError as exc:
        raise WhatsAppServiceError(
            f"WhatsApp API returned HTTP {exc.response.status_code}."
        ) from exc

    except httpx.RequestError as exc:
        raise WhatsAppServiceError("Unable to connect to WhatsApp API.") from exc

    return response.json()


def send_reply_buttons(
    to: str,
    body_text: str,
    buttons: list[dict],
) -> dict:
    """
    Send an interactive WhatsApp message with reply buttons.

    Example buttons:
    [
        {"id": "fuel_regular", "title": "Regular"},
        {"id": "fuel_premium", "title": "Premium"},
        {"id": "fuel_diesel", "title": "Diesel"},
    ]
    """

    if not WHATSAPP_ACCESS_TOKEN:
        raise WhatsAppServiceError("WHATSAPP_ACCESS_TOKEN is not configured")

    if not WHATSAPP_PHONE_NUMBER_ID:
        raise WhatsAppServiceError("WHATSAPP_PHONE_NUMBER_ID is not configured")

    if not buttons:
        raise WhatsAppServiceError("At least one button is required")

    if len(buttons) > 3:
        raise WhatsAppServiceError(
            "WhatsApp reply button messages support a maximum of 3 buttons"
        )

    url = (
        f"https://graph.facebook.com/"
        f"{WHATSAPP_API_VERSION}/"
        f"{WHATSAPP_PHONE_NUMBER_ID}/messages"
    )

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {
                "text": body_text,
            },
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {
                            "id": button["id"],
                            "title": button["title"],
                        },
                    }
                    for button in buttons
                ]
            },
        },
    }

    headers = {
        "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    try:
        response = httpx.post(
            url,
            headers=headers,
            json=payload,
            timeout=15.0,
        )

        response.raise_for_status()

    except httpx.TimeoutException as exc:
        raise WhatsAppServiceError("WhatsApp API request timed out") from exc

    except httpx.HTTPStatusError as exc:
        raise WhatsAppServiceError(
            f"WhatsApp API returned HTTP " f"{exc.response.status_code}"
        ) from exc

    except httpx.RequestError as exc:
        raise WhatsAppServiceError("Could not connect to WhatsApp API") from exc

    return response.json()


def build_text_reply(incoming_message: IncomingMessage) -> str | None:
    if incoming_message.message_type != "text":
        return None

    return "Hi! 👋\n" "Send me your location and I'll find nearby gas stations for you."


def build_gas_stations_reply(
    result: dict,
    language: str = "en",
    fuel_type: str = "regular",
    sort: str = "best",
) -> str:
    stations = result.get("stations", [])

    fuel_name = t(language, f"fuel_{fuel_type}")
    sort_name = t(language, f"sort_{sort}")

    if not stations:
        return (
            f"{t(language, 'no_results', fuel=fuel_name, sort=sort_name)}\n\n"
            f"{t(language, 'navigation_hint')}"
        )

    displayed_count = min(len(stations), 5)

    lines = [
        t(language, "results_title"),
        "━━━━━━━━━━━━━━",
        t(
            language,
            "results_summary",
            fuel=fuel_name,
            sort=sort_name,
        ),
        t(
            language,
            "results_count",
            count=displayed_count,
        ),
    ]

    rank_labels = {
        1: "1️⃣",
        2: "2️⃣",
        3: "3️⃣",
        4: "4️⃣",
        5: "5️⃣",
    }

    for index, station in enumerate(stations[:5], start=1):
        selected_fuel = station.get("selected_fuel", {})
        price = selected_fuel.get("price")
        distance = station.get("distance_miles")
        name = station.get("name", "Unknown gas station")
        address = station.get("address")

        if price is not None:
            price_text = f"${price:.3f}/gal"
        else:
            price_text = t(language, "price_unavailable")

        station_lines = [
            f"{rank_labels[index]} {name}",
        ]

        if index == 1:
            station_lines.append(t(language, f"top_result_{sort}"))

        station_lines.extend(
            [
                t(
                    language,
                    "station_price",
                    fuel=fuel_name,
                    price=price_text,
                ),
                t(
                    language,
                    "station_distance",
                    distance=distance,
                ),
            ]
        )

        if address:
            station_lines.append(
                t(
                    language,
                    "station_address",
                    address=address,
                )
            )

        lines.append("\n".join(station_lines))

    lines.extend(
        [
            "━━━━━━━━━━━━━━",
            t(language, "navigation_hint"),
        ]
    )

    return "\n\n".join(lines)


def parse_search_preferences(text: str) -> dict:
    """
    Extract gas search preferences from a WhatsApp text message.

    Examples:
        "diesel cheapest"
        -> {"fuel_type": "diesel", "sort": "price"}

        "premium closest"
        -> {"fuel_type": "premium", "sort": "distance"}
    """

    interpretation = RuleBasedIntentInterpreter().interpret(text)
    return interpretation.search_preferences
