import re

from app.conversation import (
    ConversationSession,
    ConversationState,
    InMemoryConversationStore,
    NavigationAction,
    get_previous_state,
    parse_navigation_action,
)
from app.i18n import t
from app.intelligence import IntentType, build_intent_interpreter
from app.intelligence.models import MAX_DISTANCE_MILES, MIN_DISTANCE_MILES
from app.models import IncomingMessage
from app.parsers import parse_incoming_message
from app.routing import MessageRouter
from app.providers import GasStationProviderError
from app.services.stations import search_nearby_gas_stations
from app.services.whatsapp import (
    WhatsAppServiceError,
    build_gas_stations_reply,
    send_list_message,
    send_reply_buttons,
    send_text_message,
)
from app.subscriptions import SubscriptionService

GREETINGS = {
    "hi",
    "hello",
    "hey",
    "hola",
    "good morning",
    "good afternoon",
    "good evening",
}

LANGUAGE_BUTTONS = {
    "lang_en": "en",
    "lang_es": "es",
}

FUEL_BUTTONS = {
    "fuel_regular": "regular",
    "fuel_premium": "premium",
    "fuel_diesel": "diesel",
}

SORT_BUTTONS = {
    "sort_distance": "distance",
    "sort_price": "price",
    "sort_best": "best",
}

DISTANCE_OPTIONS = {
    "distance_1": 1.0,
    "distance_3": 3.0,
    "distance_5": 5.0,
    "distance_10": 10.0,
}
CUSTOM_DISTANCE_ID = "distance_custom"

FUEL_NAMES = {
    "en": {
        "regular": "Regular",
        "premium": "Premium",
        "diesel": "Diesel",
    },
    "es": {
        "regular": "Regular",
        "premium": "Premium",
        "diesel": "Diésel",
    },
}

SORT_NAMES = {
    "en": {
        "distance": "Closest",
        "price": "Cheapest",
        "best": "Best",
    },
    "es": {
        "distance": "Más cerca",
        "price": "Más barato",
        "best": "Mejor opción",
    },
}

conversation_store = InMemoryConversationStore()
intent_interpreter = build_intent_interpreter()
subscription_service = SubscriptionService()


def send_language_prompt(sender: str, error: bool = False) -> None:
    body_text = (
        f"{t('en', 'invalid_language' if error else 'choose_language')}\n\n"
        f"{t('en', 'navigation_hint')}"
    )

    try:
        send_reply_buttons(
            to=sender,
            body_text=body_text,
            buttons=[
                {
                    "id": "lang_en",
                    "title": "English",
                },
                {
                    "id": "lang_es",
                    "title": "Español",
                },
            ],
        )
    except WhatsAppServiceError as exc:
        print(f"Could not send language buttons: {exc}")


def send_fuel_prompt(
    sender: str,
    language: str,
    welcome: bool = False,
    error: bool = False,
) -> None:
    body_parts = []

    if welcome:
        body_parts.append(t(language, "welcome"))
    if error:
        body_parts.append(t(language, "invalid_fuel"))

    body_parts.append(t(language, "choose_fuel"))
    body_parts.append(t(language, "navigation_hint"))

    try:
        send_reply_buttons(
            to=sender,
            body_text="\n\n".join(body_parts),
            buttons=[
                {
                    "id": "fuel_regular",
                    "title": t(language, "button_fuel_regular"),
                },
                {
                    "id": "fuel_premium",
                    "title": t(language, "button_fuel_premium"),
                },
                {
                    "id": "fuel_diesel",
                    "title": t(language, "button_fuel_diesel"),
                },
            ],
        )
    except WhatsAppServiceError as exc:
        print(f"Could not send fuel buttons: {exc}")


def send_sort_prompt(
    sender: str,
    session: ConversationSession,
    selected: bool = False,
    error: bool = False,
) -> None:
    language = session.language
    body_parts = []

    if selected:
        body_parts.append(
            t(
                language,
                "fuel_selected",
                fuel=FUEL_NAMES[language][session.fuel_type],
            )
        )
    if error:
        body_parts.append(t(language, "invalid_sort"))

    body_parts.append(t(language, "choose_sort"))
    body_parts.append(t(language, "navigation_hint"))

    try:
        send_reply_buttons(
            to=sender,
            body_text="\n\n".join(body_parts),
            buttons=[
                {
                    "id": "sort_distance",
                    "title": t(language, "button_sort_distance"),
                },
                {
                    "id": "sort_price",
                    "title": t(language, "button_sort_price"),
                },
                {
                    "id": "sort_best",
                    "title": t(language, "button_sort_best"),
                },
            ],
        )
    except WhatsAppServiceError as exc:
        print(f"Could not send sort buttons: {exc}")


def send_distance_prompt(
    sender: str,
    session: ConversationSession,
    error: bool = False,
) -> None:
    language = session.language
    body_parts = []

    if error:
        body_parts.append(t(language, "invalid_distance_option"))
    body_parts.append(t(language, "choose_distance"))
    body_parts.append(t(language, "navigation_hint"))

    rows = [
        {
            "id": f"distance_{distance}",
            "title": f"📏 {distance} mi",
        }
        for distance in (1, 3, 5, 10)
    ]
    rows.append(
        {
            "id": CUSTOM_DISTANCE_ID,
            "title": t(language, "distance_custom_title"),
            "description": t(language, "distance_custom_description"),
        }
    )

    try:
        send_list_message(
            to=sender,
            body_text="\n\n".join(body_parts),
            button_text=t(language, "distance_list_button"),
            section_title=t(language, "distance_section_title"),
            rows=rows,
        )
    except WhatsAppServiceError as exc:
        print(f"Could not send distance list: {exc}")


def send_custom_distance_prompt(
    sender: str,
    language: str,
    error: bool = False,
    range_error: bool = False,
) -> None:
    parts = []
    if error:
        parts.append(t(language, "invalid_custom_distance"))
    if range_error:
        parts.append(
            t(
                language,
                "invalid_max_distance",
                minimum=MIN_DISTANCE_MILES,
                maximum=MAX_DISTANCE_MILES,
            )
        )
    parts.extend(
        [
            t(
                language,
                "custom_distance_prompt",
                minimum=MIN_DISTANCE_MILES,
                maximum=MAX_DISTANCE_MILES,
            ),
            t(language, "navigation_hint"),
        ]
    )

    try:
        send_text_message(to=sender, message="\n\n".join(parts))
    except WhatsAppServiceError as exc:
        print(f"Could not send custom distance prompt: {exc}")


def parse_distance_input(text: str) -> float | None:
    match = re.search(
        r"(\d+(?:[.,]\d+)?)\s*"
        r"(miles?|millas?|mi|kilometers?|kilómetros?|kilometros?|km)\b",
        text.casefold(),
    )

    if match is None:
        match = re.fullmatch(r"\s*(\d+(?:[.,]\d+)?)\s*", text)

    if match is None:
        return None

    distance = float(match.group(1).replace(",", "."))
    unit = match.group(2) if match.lastindex == 2 else "miles"

    if unit == "km" or unit.startswith("kilomet"):
        return round(distance / 1.609344, 3)

    return distance


def handle_distance_selection(sender: str, distance: float) -> None:
    session = conversation_store.update(
        sender,
        state=ConversationState.WAITING_LOCATION,
        max_distance_miles=distance,
    )
    send_location_prompt(sender, session, saved=True)


def send_location_prompt(
    sender: str,
    session: ConversationSession,
    saved: bool = False,
) -> None:
    language = session.language

    if saved:
        message = t(
            language,
            "preferences_saved",
            fuel=FUEL_NAMES[language][session.fuel_type],
            sort=SORT_NAMES[language][session.sort],
        )
    else:
        message = t(language, "invalid_location")

    message = f"{message}\n\n{t(language, 'navigation_hint')}"

    if session.max_distance_miles is not None:
        message = (
            f"{message}\n\n"
            f"{t(language, 'max_distance_saved', distance=session.max_distance_miles)}"
        )

    try:
        send_text_message(
            to=sender,
            message=message,
        )
    except WhatsAppServiceError as exc:
        print(f"Could not send WhatsApp reply: {exc}")


def send_state_prompt(
    sender: str,
    session: ConversationSession,
    error: bool = False,
) -> None:
    if session.state in {
        ConversationState.NEW,
        ConversationState.WAITING_LANGUAGE,
    }:
        send_language_prompt(sender, error=error)
    elif session.state == ConversationState.WAITING_FUEL:
        send_fuel_prompt(sender, session.language, error=error)
    elif session.state == ConversationState.WAITING_SORT:
        send_sort_prompt(sender, session, error=error)
    elif session.state == ConversationState.WAITING_DISTANCE:
        send_distance_prompt(sender, session, error=error)
    elif session.state == ConversationState.WAITING_CUSTOM_DISTANCE:
        send_custom_distance_prompt(sender, session.language, error=error)
    elif session.state == ConversationState.WAITING_LOCATION:
        send_location_prompt(sender, session)


def send_expected_prompt(sender: str, session: ConversationSession) -> None:
    send_state_prompt(sender, session, error=True)


def handle_navigation(sender: str, action: NavigationAction) -> None:
    if action == NavigationAction.MENU:
        session = conversation_store.update(
            sender,
            state=ConversationState.WAITING_LANGUAGE,
            language="en",
            fuel_type="regular",
            sort="best",
            max_distance_miles=None,
        )
    else:
        current_session = conversation_store.get(sender)
        current_state = (
            current_session.state
            if current_session is not None
            else ConversationState.NEW
        )
        session = conversation_store.update(
            sender,
            state=get_previous_state(current_state),
        )

    send_state_prompt(sender, session)


def handle_whatsapp_webhook(payload: dict) -> dict:
    incoming_message = parse_incoming_message(payload)

    if not incoming_message:
        print("WhatsApp webhook event without a user message.")
        return {"status": "ok"}

    print("Incoming WhatsApp message:")
    print(incoming_message)

    subscription_service.ensure_user(incoming_message.sender)
    message_router.dispatch(incoming_message)

    return {"status": "ok"}


def handle_text_message(incoming_message: IncomingMessage) -> None:
    sender = incoming_message.sender
    text = incoming_message.text or ""
    normalized_text = text.lower().strip()
    navigation_action = parse_navigation_action(text)

    if navigation_action is not None:
        handle_navigation(sender, navigation_action)
        return

    if normalized_text in GREETINGS:
        conversation_store.update(
            sender,
            state=ConversationState.WAITING_LANGUAGE,
        )

        send_language_prompt(sender)

        return

    current_session = conversation_store.get(sender)
    if current_session is not None and current_session.state in {
        ConversationState.WAITING_DISTANCE,
        ConversationState.WAITING_CUSTOM_DISTANCE,
    }:
        distance = parse_distance_input(text)
        if distance is None:
            if current_session.state == ConversationState.WAITING_DISTANCE:
                send_distance_prompt(sender, current_session, error=True)
            else:
                send_custom_distance_prompt(
                    sender,
                    current_session.language,
                    error=True,
                )
            return

        if not MIN_DISTANCE_MILES <= distance <= MAX_DISTANCE_MILES:
            send_custom_distance_prompt(
                sender,
                current_session.language,
                range_error=True,
            )
            conversation_store.update(
                sender,
                state=ConversationState.WAITING_CUSTOM_DISTANCE,
            )
            return

        handle_distance_selection(sender, distance)
        return

    interpretation = intent_interpreter.interpret(text)
    parsed_preferences = interpretation.search_preferences

    if interpretation.intent == IntentType.SEARCH_GAS:
        current_session = conversation_store.get(sender)
        language = (
            current_session.language
            if current_session is not None
            and current_session.state
            not in {ConversationState.NEW, ConversationState.WAITING_LANGUAGE}
            else interpretation.language or "en"
        )

        if (
            interpretation.max_distance_miles is not None
            and not MIN_DISTANCE_MILES
            <= interpretation.max_distance_miles
            <= MAX_DISTANCE_MILES
        ):
            try:
                send_text_message(
                    to=sender,
                    message=t(
                        language,
                        "invalid_max_distance",
                        minimum=MIN_DISTANCE_MILES,
                        maximum=MAX_DISTANCE_MILES,
                    ),
                )
            except WhatsAppServiceError as exc:
                print(f"Could not send distance validation message: {exc}")
            return

        if (
            current_session is not None
            and current_session.state == ConversationState.WAITING_FUEL
            and interpretation.fuel_type is not None
            and interpretation.sort is None
        ):
            session = conversation_store.update(
                sender,
                state=ConversationState.WAITING_SORT,
                language=language,
                fuel_type=interpretation.fuel_type,
                **(
                    {
                        "max_distance_miles": (
                            interpretation.max_distance_miles
                        )
                    }
                    if interpretation.max_distance_miles is not None
                    else {}
                ),
            )
            send_sort_prompt(sender, session, selected=True)
            return

        if (
            interpretation.max_distance_miles is not None
            and interpretation.fuel_type is None
            and interpretation.sort is None
        ):
            if (
                current_session is not None
                and current_session.state == ConversationState.WAITING_SORT
            ):
                session = conversation_store.update(
                    sender,
                    max_distance_miles=interpretation.max_distance_miles,
                )
                send_sort_prompt(sender, session)
                return

            conversation_store.update(
                sender,
                state=ConversationState.WAITING_FUEL,
                language=language,
                max_distance_miles=interpretation.max_distance_miles,
            )
            send_fuel_prompt(sender, language)
            return

        if (
            current_session is not None
            and current_session.state == ConversationState.WAITING_SORT
            and interpretation.sort is not None
            and interpretation.fuel_type is None
        ):
            next_state = (
                ConversationState.WAITING_LOCATION
                if interpretation.max_distance_miles is not None
                or current_session.max_distance_miles is not None
                else ConversationState.WAITING_DISTANCE
            )
            session = conversation_store.update(
                sender,
                state=next_state,
                language=language,
                sort=interpretation.sort,
                **(
                    {
                        "max_distance_miles": (
                            interpretation.max_distance_miles
                        )
                    }
                    if interpretation.max_distance_miles is not None
                    else {}
                ),
            )
            if next_state == ConversationState.WAITING_LOCATION:
                send_location_prompt(sender, session, saved=True)
            else:
                send_distance_prompt(sender, session)
            return

        if not parsed_preferences:
            conversation_store.update(
                sender,
                state=ConversationState.WAITING_FUEL,
                language=language,
            )
            send_fuel_prompt(sender, language)
            return

        session = conversation_store.update(
            sender,
            state=ConversationState.WAITING_LOCATION,
            language=language,
            **parsed_preferences,
        )

        send_location_prompt(sender, session, saved=True)
    else:
        session = conversation_store.get(sender)

        if session is None:
            session = conversation_store.update(
                sender,
                state=ConversationState.WAITING_LANGUAGE,
            )

        send_expected_prompt(sender, session)


def handle_interactive_message(incoming_message: IncomingMessage) -> None:
    sender = incoming_message.sender
    button_id = incoming_message.selection_id or ""
    navigation_action = parse_navigation_action(button_id)

    if navigation_action is not None:
        handle_navigation(sender, navigation_action)
        return

    if button_id in LANGUAGE_BUTTONS:
        handle_language_selection(sender, LANGUAGE_BUTTONS[button_id])
        return

    session = conversation_store.get(sender)

    if session is None:
        session = conversation_store.update(
            sender,
            state=ConversationState.WAITING_LANGUAGE,
        )

    if (
        button_id in FUEL_BUTTONS
        and session.state == ConversationState.WAITING_FUEL
    ):
        handle_fuel_selection(sender, FUEL_BUTTONS[button_id])
    elif (
        button_id in SORT_BUTTONS
        and session.state == ConversationState.WAITING_SORT
    ):
        handle_sort_selection(sender, SORT_BUTTONS[button_id])
    elif (
        button_id in DISTANCE_OPTIONS
        and session.state == ConversationState.WAITING_DISTANCE
    ):
        handle_distance_selection(sender, DISTANCE_OPTIONS[button_id])
    elif (
        button_id == CUSTOM_DISTANCE_ID
        and session.state == ConversationState.WAITING_DISTANCE
    ):
        conversation_store.update(
            sender,
            state=ConversationState.WAITING_CUSTOM_DISTANCE,
        )
        send_custom_distance_prompt(sender, session.language)
    else:
        send_expected_prompt(sender, session)


def handle_language_selection(sender: str, language: str) -> None:
    conversation_store.update(
        sender,
        state=ConversationState.WAITING_FUEL,
        language=language,
        fuel_type="regular",
        sort="best",
        max_distance_miles=None,
    )

    send_fuel_prompt(sender, language, welcome=True)


def handle_fuel_selection(sender: str, fuel_type: str) -> None:
    session = conversation_store.update(
        sender,
        state=ConversationState.WAITING_SORT,
        fuel_type=fuel_type,
    )
    send_sort_prompt(sender, session, selected=True)


def handle_sort_selection(sender: str, sort_option: str) -> None:
    current_session = conversation_store.get(sender)
    next_state = (
        ConversationState.WAITING_LOCATION
        if current_session is not None
        and current_session.max_distance_miles is not None
        else ConversationState.WAITING_DISTANCE
    )
    session = conversation_store.update(
        sender,
        state=next_state,
        sort=sort_option,
    )
    if next_state == ConversationState.WAITING_LOCATION:
        send_location_prompt(sender, session, saved=True)
    else:
        send_distance_prompt(sender, session)


def handle_location_message(incoming_message: IncomingMessage) -> None:
    sender = incoming_message.sender
    latitude = incoming_message.latitude
    longitude = incoming_message.longitude

    if latitude is None or longitude is None:
        return

    current_session = conversation_store.get(sender)

    if (
        current_session is not None
        and current_session.state != ConversationState.WAITING_LOCATION
    ):
        send_expected_prompt(sender, current_session)
        return

    try:
        session = conversation_store.pop(sender) or ConversationSession(sender=sender)
        radius = (
            session.max_distance_miles * 1609.344
            if session.max_distance_miles is not None
            else 5000
        )
        result = search_nearby_gas_stations(
            latitude=latitude,
            longitude=longitude,
            radius=radius,
            fuel_type=session.fuel_type,
            sort=session.sort,
            limit=5,
            gallons_needed=10,
            vehicle_mpg=25,
        )

        reply = build_gas_stations_reply(
            result,
            language=session.language,
            fuel_type=session.fuel_type,
            sort=session.sort,
            max_distance_miles=session.max_distance_miles,
        )

        send_text_message(
            to=sender,
            message=reply,
        )
    except GasStationProviderError as exc:
        print(f"Unable to search gas stations: {exc}")
    except WhatsAppServiceError as exc:
        print(f"Unable to send WhatsApp reply: {exc}")


def handle_unsupported_message(incoming_message: IncomingMessage) -> None:
    print(
        "WhatsApp message type is not supported yet: "
        f"{incoming_message.message_type}"
    )

    session = conversation_store.get(incoming_message.sender)

    if session is None:
        session = conversation_store.update(
            incoming_message.sender,
            state=ConversationState.WAITING_LANGUAGE,
        )

    send_expected_prompt(incoming_message.sender, session)


message_router = MessageRouter(
    handlers={
        "text": handle_text_message,
        "interactive": handle_interactive_message,
        "location": handle_location_message,
    },
    default_handler=handle_unsupported_message,
)
