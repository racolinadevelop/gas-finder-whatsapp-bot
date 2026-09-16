import httpx

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


def extract_incoming_message(payload: dict):
    try:
        value = payload["entry"][0]["changes"][0]["value"]

        messages = value.get("messages", [])

        if not messages:
            return None

        message = messages[0]

        sender = message.get("from")
        message_type = message.get("type")

        result = {
            "from": sender,
            "type": message_type,
            "message_id": message.get("id"),
        }

        if message_type == "text":
            result["text"] = message.get("text", {}).get("body")

        elif message_type == "location":
            location = message.get("location", {})

            result["latitude"] = location.get("latitude")
            result["longitude"] = location.get("longitude")

        elif message_type == "interactive":
            interactive = message.get("interactive", {})
            interactive_type = interactive.get("type")

            result["interactive_type"] = interactive_type

            if interactive_type == "button_reply":
                button_reply = interactive.get("button_reply", {})

                result["button_id"] = button_reply.get("id")
                result["button_title"] = button_reply.get("title")

        return result

    except (KeyError, IndexError, TypeError):
        return None


def build_text_reply(incoming_message: dict) -> str | None:
    if incoming_message.get("type") != "text":
        return None

    return "Hi! 👋\n" "Send me your location and I'll find nearby gas stations for you."


def build_gas_stations_reply(result: dict) -> str:
    stations = result.get("stations", [])

    if not stations:
        return (
            "⛽ I couldn't find gas stations with available results "
            "near your location."
        )

    lines = [
        "⛽ Nearby gas stations",
        "",
    ]

    for index, station in enumerate(stations[:5], start=1):
        selected_fuel = station.get("selected_fuel", {})
        price = selected_fuel.get("price")
        distance = station.get("distance_miles")
        name = station.get("name", "Unknown gas station")

        if price is not None:
            price_text = f"${price:.3f}/gal"
        else:
            price_text = "Price unavailable"

        lines.append(
            f"{index}. {name}\n" f"   💵 {price_text}\n" f"   📍 {distance:.2f} mi"
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

    preferences = {}

    if not text:
        return preferences

    words = text.lower().strip().split()

    # Fuel type
    if "regular" in words:
        preferences["fuel_type"] = "regular"
    elif "premium" in words:
        preferences["fuel_type"] = "premium"
    elif "diesel" in words:
        preferences["fuel_type"] = "diesel"

    # Sort option
    if "closest" in words:
        preferences["sort"] = "distance"
    elif "cheapest" in words:
        preferences["sort"] = "price"
    elif "best" in words:
        preferences["sort"] = "best"

    return preferences
