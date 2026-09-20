import logging

from app.conversation import (
    ConversationSession,
    ConversationTransitions,
    NavigationAction,
    SearchFlowDecision,
)
from app.conversation.options import LANGUAGE_BUTTONS
from app.handlers.conversation_states import ConversationStateHandlers
from app.handlers.interactive_messages import process_interactive_message
from app.handlers.location_messages import process_location_message
from app.handlers.location_results import run_location_search
from app.handlers.search_flow_delivery import deliver_search_flow_decision
from app.handlers.text_messages import process_text_message
from app.handlers.webhook_dispatch import process_webhook
from app.intelligence import build_intent_interpreter
from app.models import IncomingMessage
from app.parsers import parse_incoming_message
from app.presentation import (
    Prompt,
    build_distance_prompt,
    build_fuel_prompt,
    build_language_prompt,
    build_location_prompt,
    build_sort_prompt,
    build_state_prompt,
)
from app.presentation.delivery import deliver_prompt
from app.routing.whatsapp_routers import build_whatsapp_routers
from app.services.location_search import LocationSearchService
from app.services.whatsapp import (
    WhatsAppServiceError,
    send_list_message,
    send_reply_buttons,
    send_text_message,
)
from app.runtime import build_runtime_state
from app.subscriptions import SubscriptionService

logger = logging.getLogger(__name__)

runtime_state = build_runtime_state()
conversation_store = runtime_state.conversation_store
intent_interpreter = build_intent_interpreter()
subscription_service = SubscriptionService(runtime_state.subscription_store)
location_search_service = LocationSearchService()
conversation_transitions = ConversationTransitions(conversation_store)
message_deduplicator = runtime_state.message_deduplicator
search_rate_limiter = runtime_state.search_rate_limiter


def send_prompt(sender: str, prompt: Prompt) -> None:
    session = conversation_store.get(sender)
    try:
        deliver_prompt(
            sender,
            prompt,
            session,
            send_buttons=send_reply_buttons,
            send_list=send_list_message,
            send_text=send_text_message,
        )
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
    return process_webhook(
        payload,
        parse_message=parse_incoming_message,
        claim_message=message_deduplicator.claim,
        release_message=message_deduplicator.release,
        ensure_user=subscription_service.ensure_user,
        dispatch_message=message_router.dispatch,
    )


def apply_search_flow_decision(
    sender: str,
    decision: SearchFlowDecision,
) -> None:
    deliver_search_flow_decision(
        sender,
        decision,
        apply_changes=conversation_transitions.apply,
        send_text=send_text_message,
        send_fuel=send_fuel_prompt,
        send_sort=send_sort_prompt,
        send_distance=send_distance_prompt,
        send_location=send_location_prompt,
    )


def handle_text_message(incoming_message: IncomingMessage) -> None:
    process_text_message(
        incoming_message,
        navigate=handle_navigation,
        begin=conversation_transitions.begin,
        send_language=send_language_prompt,
        get_session=conversation_store.get,
        dispatch_state_text=text_state_router.dispatch,
        send_expected=send_expected_prompt,
        interpret=intent_interpreter.interpret,
        ensure_started=conversation_transitions.ensure_started,
        apply_decision=apply_search_flow_decision,
    )


def handle_interactive_message(incoming_message: IncomingMessage) -> None:
    process_interactive_message(
        incoming_message,
        navigate=handle_navigation,
        ensure_started=conversation_transitions.ensure_started,
        language_buttons=LANGUAGE_BUTTONS,
        select_language=conversation_state_handlers.language_selection,
        dispatch_state_interactive=interactive_state_router.dispatch,
        send_expected=send_expected_prompt,
    )


def search_from_location(
    incoming_message: IncomingMessage,
    session: ConversationSession,
) -> None:
    run_location_search(
        incoming_message,
        session,
        allow_search=search_rate_limiter.allow,
        search=location_search_service.search,
        send_text=send_text_message,
        update_session=conversation_transitions.apply,
        send_prompt=send_prompt,
    )


def handle_location_message(incoming_message: IncomingMessage) -> None:
    process_location_message(
        incoming_message,
        get_session=conversation_store.get,
        search_from_location=search_from_location,
        dispatch_state_location=location_state_router.dispatch,
        send_expected=send_expected_prompt,
    )


def handle_unsupported_message(incoming_message: IncomingMessage) -> None:
    logger.info(
        "WhatsApp message type is not supported yet: %s",
        incoming_message.message_type,
    )

    session = conversation_transitions.ensure_started(
        incoming_message.sender
    )

    send_expected_prompt(incoming_message.sender, session)


(
    text_state_router,
    interactive_state_router,
    location_state_router,
    message_router,
) = build_whatsapp_routers(
    state_handlers=conversation_state_handlers,
    search_from_location=search_from_location,
    handle_text=handle_text_message,
    handle_interactive=handle_interactive_message,
    handle_location=handle_location_message,
    handle_unsupported=handle_unsupported_message,
)
