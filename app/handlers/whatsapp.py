from app.conversation import (
    ConversationSession,
    ConversationState,
    InMemoryConversationStore,
    NavigationAction,
    get_previous_state,
    parse_navigation_action,
)
from app.i18n import t
from app.models import IncomingMessage
from app.parsers import parse_incoming_message
from app.routing import MessageRouter
from app.services.google_places import (
    GooglePlacesServiceError,
    search_nearby_gas_stations,
)
from app.services.whatsapp import (
    WhatsAppServiceError,
    build_gas_stations_reply,
    parse_search_preferences,
    send_reply_buttons,
    send_text_message,
)

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

    parsed_preferences = parse_search_preferences(text)

    if parsed_preferences:
        session = conversation_store.update(
            sender,
            state=ConversationState.WAITING_LOCATION,
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
    else:
        send_expected_prompt(sender, session)


def handle_language_selection(sender: str, language: str) -> None:
    conversation_store.update(
        sender,
        state=ConversationState.WAITING_FUEL,
        language=language,
        fuel_type="regular",
        sort="best",
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
    session = conversation_store.update(
        sender,
        state=ConversationState.WAITING_LOCATION,
        sort=sort_option,
    )
    send_location_prompt(sender, session, saved=True)


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
        result = search_nearby_gas_stations(
            latitude=latitude,
            longitude=longitude,
            radius=5000,
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
        )

        send_text_message(
            to=sender,
            message=reply,
        )
    except GooglePlacesServiceError as exc:
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
