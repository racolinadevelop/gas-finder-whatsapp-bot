import httpx
from app.intelligence import RuleBasedIntentInterpreter
from app.i18n import t
from app.models import IncomingMessage
from app.presentation.price_freshness import price_update_lines

from app.config import (
    WHATSAPP_ACCESS_TOKEN,
    WHATSAPP_API_VERSION,
    WHATSAPP_PHONE_NUMBER_ID,
)


class WhatsAppServiceError(Exception):
    pass


LOCATION_REQUEST_MARKERS = (
    "share your location",
    "waiting for your location",
    "comparte tu ubicación",
    "esperando tu ubicación",
)


def _is_location_request_prompt(message: str) -> bool:
    normalized = message.casefold()
    return any(marker in normalized for marker in LOCATION_REQUEST_MARKERS)


def send_location_request_message(to: str, message: str) -> dict:
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
        "type": "interactive",
        "interactive": {
            "type": "location_request_message",
            "body": {
                "text": message,
            },
            "action": {
                "name": "send_location",
            },
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


def send_text_message(to: str, message: str) -> dict:
    if _is_location_request_prompt(message):
        return send_location_request_message(to=to, message=message)

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


def send_list_message(
    to: str,
    body_text: str,
    button_text: str,
    section_title: str,
    rows: list[dict],
) -> dict:
    """Send one WhatsApp interactive list containing up to ten rows."""

    if not WHATSAPP_ACCESS_TOKEN:
        raise WhatsAppServiceError("WHATSAPP_ACCESS_TOKEN is not configured")
    if not WHATSAPP_PHONE_NUMBER_ID:
        raise WhatsAppServiceError("WHATSAPP_PHONE_NUMBER_ID is not configured")
    if not rows or len(rows) > 10:
        raise WhatsAppServiceError(
            "WhatsApp list messages require between 1 and 10 rows"
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
            "type": "list",
            "body": {"text": body_text},
            "action": {
                "button": button_text,
                "sections": [
                    {
                        "title": section_title,
                        "rows": rows,
                    }
                ],
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
            f"WhatsApp API returned HTTP {exc.response.status_code}"
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
    max_distance_miles: float | None = None,
) -> str:
    stations = result.get("stations", [])

    fuel_name = t(language, f"fuel_{fuel_type}")
    sort_name = t(language, f"sort_{sort}")

    if not stations:
        lines = [t(language, "no_results", fuel=fuel_name, sort=sort_name)]
        if max_distance_miles is not None:
            lines.append(
                t(
                    language,
                    "search_max_distance",
                    distance=max_distance_miles,
                )
            )
        lines.append(t(language, "results_navigation_hint"))
        return "\n\n".join(lines)

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

    if max_distance_miles is not None:
        lines.append(
            t(
                language,
                "search_max_distance",
                distance=max_distance_miles,
            )
        )

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
            route_ready = (
                not result.get("routes_requested")
                or sort == "price"
                or station.get("road_distance_miles") is not None
            )
            if route_ready:
                station_lines.append(t(language, f"top_result_{sort}"))
                if sort == "best":
                    station_lines.append(
                        build_best_recommendation_explanation(stations, language)
                    )

        if station.get("open_now") is True:
            station_lines.append(t(language, "station_open_now"))
        else:
            # Both HERE and Google without opening-hour data are unknown.
            # Explicitly closed Google stations are filtered before this step.
            station_lines.append(t(language, "station_hours_unknown"))

        station_lines.append(
            t(language, "station_price", fuel=fuel_name, price=price_text)
        )
        if price is not None:
            station_lines.extend(
                price_update_lines(selected_fuel.get("updated_at"), language=language)
            )
        road_miles = station.get("road_distance_miles")
        if road_miles is not None:
            # This is the actual driving distance, not geographic miles.
            station_lines.append(
                t(language, "station_distance", distance=road_miles)
            )
            drive_minutes = station.get("road_eta_minutes")
            if drive_minutes is not None:
                station_lines.append(
                    t(language, "station_drive_eta", minutes=drive_minutes)
                )
        elif result.get("routes_requested"):
            # An unavailable route must never appear as an actual driving
            # distance just because geographic coordinates exist.
            station_lines.append(t(language, "station_route_unavailable"))
        else:
            # Routes is separately billable and disabled until configured.
            station_lines.append(
                t(language, "station_distance_estimated", distance=distance)
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
            t(language, "results_navigation_hint"),
        ]
    )

    return "\n\n".join(lines)


def build_best_recommendation_explanation(
    stations: list[dict],
    language: str,
) -> str:
    winner = stations[0]
    comparable = [
        station
        for station in stations
        if station.get("selected_fuel", {}).get("price") is not None
        and station.get("estimated_cost") is not None
        and (station.get("open_now") is True)
        == (winner.get("open_now") is True)
    ]

    if winner not in comparable:
        return t(language, "best_reason_general")

    cheapest = min(
        comparable,
        key=lambda station: station["selected_fuel"]["price"],
    )
    closest = min(
        comparable,
        key=lambda station: station.get("road_distance_miles", station["distance_miles"]),
    )

    if winner is cheapest and winner is closest:
        return t(language, "best_reason_both")

    if winner is not cheapest:
        winner_total = winner["estimated_cost"]["estimated_total_cost"]
        alternative_total = cheapest["estimated_cost"][
            "estimated_total_cost"
        ]

        if winner_total >= alternative_total:
            return t(language, "best_reason_general")

        return t(
            language,
            "best_reason_lower_total",
            alternative=cheapest.get("name", "Another station"),
            winner_total=winner_total,
            alternative_total=alternative_total,
        )

    if winner is not closest:
        return t(language, "best_reason_price")

    return t(language, "best_reason_general")


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
