import logging

from app.constants import MAX_DISTANCE_MILES, MIN_DISTANCE_MILES
from app.conversation import (
    ConversationSession,
    ConversationState,
    ConversationTransitions,
    NavigationAction,
    SearchFlowDecision,
    SearchFlowPrompt,
    decide_search_flow,
    parse_navigation_action,
)
from app.conversation.options import LANGUAGE_BUTTONS
from app.handlers.conversation_states import ConversationStateHandlers
from app.i18n import t
from app.intelligence import IntentType, build_intent_interpreter
from app.models import IncomingMessage
from app.parsers import parse_incoming_message
from app.presentation import (
    ListPrompt,
    Prompt,
    ReplyButtonsPrompt,
    TextPrompt,
    build_distance_prompt,
    build_fuel_prompt,
    build_language_prompt,
    build_location_prompt,
    build_sort_prompt,
    build_state_prompt,
)
from app.routing import ConversationStateRouter, MessageRouter
from app.providers import GasStationProviderError
from app.services.location_search import LocationSearchService
from app.services.whatsapp import (
    WhatsAppServiceError,
    send_list_message,
    send_reply_buttons,
    send_text_message,
)
from app.subscriptions import SubscriptionService
from app.runtime import build_runtime_state

logger = logging.getLogger(__name__)

GREETINGS = {
    "hi",
    "hello",
    "hey",
    "hola",
    "good morning",
    "good afternoon",
    "good evening",
}

runtime_state = build_runtime_state()
conversation_store = runtime_state.conversation_store
intent_interpreter = build_intent_interpreter()
subscription_service = SubscriptionService(runtime_state.subscription_store)
location_search_service = LocationSearchService()
conversation_transitions = ConversationTransitions(conversation_store)
message_deduplicator = runtime_state.message_deduplicator
search_rate_limiter = runtime_state.search_rate_limiter


def send_prompt(sender: str, prompt: Prompt) -> None:
    try:
        if isinstance(prompt, ReplyButtonsPrompt):
            send_reply_buttons(
                to=sender,
                body_text=prompt.body_text,
                buttons=prompt.buttons,
            )
        elif isinstance(prompt, ListPrompt):
            send_list_message(
                to=sender,
                body_text=prompt.body_text,
                button_text=prompt.button_text,
                section_title=prompt.section_title,
                rows=prompt.rows,
            )
        elif isinstance(prompt, TextPrompt):
            send_text_message(to=sender, message=prompt.message)
    except WhatsAppServiceError as exc:
        logger.warning("Could not send conversation prompt: %s", exc)


conversation_state_handlers = ConversationStateHandlers(
    conversation_transitions,
    send_prompt,
)


def send_language_prompt(
    sender: str,
    error: bool = False,
    display_name: str | None = None,
) -> None:
    send_prompt(
        sender,
        build_language_prompt(
            error=error,
            display_name=display_name,
        ),
    )


def send_fuel_prompt(
    sender: str,
    language: str,
    welcome: bool = False,
    error: bool = False,
) -> None:
    send_prompt(
        sender,
        build_fuel_prompt(language, welcome=welcome, error=error),
    )


def send_sort_prompt(
    sender: str,
    session: ConversationSession,
    selected: bool = False,
    error: bool = False,
) -> None:
    send_prompt(
        sender,
        build_sort_prompt(session, selected=selected, error=error),
    )


def send_distance_prompt(
    sender: str,
    session: ConversationSession,
    error: bool = False,
) -> None:
    send_prompt(sender, build_distance_prompt(session, error=error))


def send_location_prompt(
    sender: str,
    session: ConversationSession,
    saved: bool = False,
) -> None:
    send_prompt(sender, build_location_prompt(session, saved=saved))


def send_state_prompt(
    sender: str,
    session: ConversationSession,
    error: bool = False,
) -> None:
    send_prompt(sender, build_state_prompt(session, error=error))


def send_expected_prompt(sender: str, session: ConversationSession) -> None:
    send_state_prompt(sender, session, error=True)


def handle_navigation(sender: str, action: NavigationAction) -> None:
    session = conversation_transitions.navigate(sender, action)
    send_state_prompt(sender, session)


def handle_whatsapp_webhook(payload: dict) -> dict:
    incoming_message = parse_incoming_message(payload)

    if not incoming_message:
        logger.info("WhatsApp webhook event without a user message")
        return {"status": "ok"}

    if not message_deduplicator.claim(incoming_message.message_id):
        logger.info("Ignoring duplicate WhatsApp message")
        return {"status": "ok"}

    logger.info(
        "Incoming WhatsApp message type=%s",
        incoming_message.message_type,
    )

    try:
        subscription_service.ensure_user(incoming_message.sender)
        message_router.dispatch(incoming_message)
    except Exception:
        message_deduplicator.release(incoming_message.message_id)
        raise

    return {"status": "ok"}


def apply_search_flow_decision(
    sender: str,
    decision: SearchFlowDecision,
) -> None:
    if decision.prompt == SearchFlowPrompt.INVALID_DISTANCE:
        try:
            send_text_message(
                to=sender,
                message=t(
                    decision.language,
                    "invalid_max_distance",
                    minimum=MIN_DISTANCE_MILES,
                    maximum=MAX_DISTANCE_MILES,
                ),
            )
        except WhatsAppServiceError as exc:
            logger.warning("Could not send distance validation message: %s", exc)
        return

    session = conversation_transitions.apply(
        sender,
        decision.session_changes,
    )

    if decision.prompt == SearchFlowPrompt.FUEL:
        send_fuel_prompt(sender, decision.language)
    elif decision.prompt == SearchFlowPrompt.SORT:
        send_sort_prompt(sender, session, selected=decision.selected)
    elif decision.prompt == SearchFlowPrompt.DISTANCE:
        send_distance_prompt(sender, session)
    elif decision.prompt == SearchFlowPrompt.LOCATION:
        send_location_prompt(sender, session, saved=decision.saved)


def handle_text_message(incoming_message: IncomingMessage) -> None:
    sender = incoming_message.sender
    text = incoming_message.text or ""
    normalized_text = text.lower().strip()
    navigation_action = parse_navigation_action(text)

    if navigation_action is not None:
        handle_navigation(sender, navigation_action)
        return

    if normalized_text in GREETINGS:
        conversation_transitions.begin(sender)

        send_language_prompt(
            sender,
            display_name=incoming_message.profile_name,
        )

        return

    current_session = conversation_store.get(sender)
    if current_session is not None and text_state_router.dispatch(
        incoming_message,
        current_session,
    ):
        return

    # While waiting for a location, unrelated text must not silently
    # overwrite the search preferences. Navigation and greetings were
    # already handled above.
    if (
        current_session is not None
        and current_session.state == ConversationState.WAITING_LOCATION
    ):
        send_expected_prompt(sender, current_session)
        return

    interpretation = intent_interpreter.interpret(text)
    if interpretation.intent != IntentType.SEARCH_GAS:
        session = conversation_transitions.ensure_started(sender)
        send_expected_prompt(sender, session)
        return

    decision = decide_search_flow(
        conversation_store.get(sender),
        interpretation,
    )
    apply_search_flow_decision(sender, decision)


def handle_interactive_message(incoming_message: IncomingMessage) -> None:
    sender = incoming_message.sender
    button_id = incoming_message.selection_id or ""
    navigation_action = parse_navigation_action(button_id)

    if navigation_action is not None:
        handle_navigation(sender, navigation_action)
        return

    session = conversation_transitions.ensure_started(sender)

    if button_id in LANGUAGE_BUTTONS:
        # Old interactive messages can still be tapped in WhatsApp.
        # Accept a language choice only at the language-selection step.
        if session.state != ConversationState.WAITING_LANGUAGE:
            send_expected_prompt(sender, session)
            return

        conversation_state_handlers.language_selection(
            sender,
            LANGUAGE_BUTTONS[button_id],
            display_name=incoming_message.profile_name,
        )
        return

    if not interactive_state_router.dispatch(incoming_message, session):
        send_expected_prompt(sender, session)


def search_from_location(
    incoming_message: IncomingMessage,
    session: ConversationSession,
) -> None:
    sender = incoming_message.sender
    latitude = incoming_message.latitude
    longitude = incoming_message.longitude

    if latitude is None or longitude is None:
        return

    if not search_rate_limiter.allow(sender):
        try:
            send_text_message(
                to=sender,
                message=t(
                    session.language,
                    "search_rate_limited",
                ),
            )
        except WhatsAppServiceError as exc:
            logger.warning("Unable to send search rate-limit reply: %s", exc)
        return

    try:
        reply = location_search_service.search(
            session=session,
            latitude=latitude,
            longitude=longitude,
        )
    except GasStationProviderError as exc:
        logger.warning("Unable to search gas stations: %s", exc)
        try:
            send_text_message(
                to=sender,
                message=t(
                    session.language,
                    "search_temporarily_unavailable",
                ),
            )
        except WhatsAppServiceError as send_exc:
            logger.warning("Unable to send search error reply: %s", send_exc)
        return

    try:
        send_text_message(
            to=sender,
            message=reply,
        )
    except WhatsAppServiceError as exc:
        logger.warning("Unable to send WhatsApp reply: %s", exc)
        return

    conversation_transitions.finish(sender)


def handle_location_message(incoming_message: IncomingMessage) -> None:
    if (
        incoming_message.latitude is None
        or incoming_message.longitude is None
    ):
        return

    sender = incoming_message.sender
    session = conversation_store.get(sender)

    if session is None:
        search_from_location(
            incoming_message,
            ConversationSession(sender=sender),
        )
        return

    if not location_state_router.dispatch(incoming_message, session):
        send_expected_prompt(sender, session)


def handle_unsupported_message(incoming_message: IncomingMessage) -> None:
    logger.info(
        "WhatsApp message type is not supported yet: %s",
        incoming_message.message_type,
    )

    session = conversation_transitions.ensure_started(
        incoming_message.sender
    )

    send_expected_prompt(incoming_message.sender, session)


text_state_router = ConversationStateRouter(
    handlers={
        ConversationState.WAITING_DISTANCE: (
            conversation_state_handlers.distance_text
        ),
        ConversationState.WAITING_CUSTOM_DISTANCE: (
            conversation_state_handlers.distance_text
        ),
    }
)

interactive_state_router = ConversationStateRouter(
    handlers={
        ConversationState.WAITING_FUEL: (
            conversation_state_handlers.fuel_interaction
        ),
        ConversationState.WAITING_SORT: (
            conversation_state_handlers.sort_interaction
        ),
        ConversationState.WAITING_DISTANCE: (
            conversation_state_handlers.distance_interaction
        ),
    }
)

location_state_router = ConversationStateRouter(
    handlers={
        ConversationState.WAITING_LOCATION: search_from_location,
    }
)


message_router = MessageRouter(
    handlers={
        "text": handle_text_message,
        "interactive": handle_interactive_message,
        "location": handle_location_message,
    },
    default_handler=handle_unsupported_message,
)
