import logging

from app.billing.test_store import PostgresTestBillingStore
from app.config import DATABASE_URL, STRIPE_TEST_MODE_ENABLED
from app.conversation import (
    ConversationSession,
    ConversationState,
    ConversationTransitions,
    NavigationAction,
    SearchFlowDecision,
)
from app.conversation.options import LANGUAGE_BUTTONS
from app.favorites import (
    FavoriteStoreError,
    InMemoryFavoriteStore,
    PostgresFavoriteStore,
)
from app.favorites.models import FavoriteStation
from app.handlers.conversation_states import ConversationStateHandlers
from app.handlers.interactive_messages import process_interactive_message
from app.handlers.location_messages import process_location_message
from app.handlers.location_results import run_location_search
from app.handlers.plan_messages import build_plan_message
from app.handlers.search_flow_delivery import deliver_search_flow_decision
from app.handlers.text_messages import process_text_message
from app.handlers.webhook_dispatch import process_webhook
from app.intelligence import build_intent_interpreter
from app.models import IncomingMessage
from app.parsers import parse_incoming_message
from app.preferences import SearchPreferences
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
from app.presentation.prompts import build_favorites_result_navigation_prompt
from app.routing.whatsapp_routers import build_whatsapp_routers
from app.services.location_search import LocationSearchService
from app.services.whatsapp import (
    WhatsAppServiceError,
    send_list_message,
    send_reply_buttons,
    send_text_message,
)
from app.runtime import build_runtime_state
from app.subscriptions import Feature, SubscriptionService

logger = logging.getLogger(__name__)

runtime_state = build_runtime_state()
conversation_store = runtime_state.conversation_store
search_preferences_store = runtime_state.search_preferences_store
intent_interpreter = build_intent_interpreter()
test_billing_store = (
    PostgresTestBillingStore(DATABASE_URL)
    if STRIPE_TEST_MODE_ENABLED and DATABASE_URL else None
)
subscription_service = SubscriptionService(
    runtime_state.subscription_store, test_entitlements=test_billing_store,
)
location_search_service = LocationSearchService()
try:
    favorites_store = (
        PostgresFavoriteStore(DATABASE_URL) if DATABASE_URL else InMemoryFavoriteStore()
    )
except Exception:
    # Optional Premium storage must not prevent free gas searches from starting.
    logger.warning("Could not initialize optional favorite station storage")
    favorites_store = None
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


def handle_plan_status(sender: str) -> None:
    """Show this WhatsApp sender's own plan without changing search state."""
    session = conversation_store.get(sender)
    language = (
        session.language
        if session is not None
        and session.state not in {ConversationState.NEW, ConversationState.WAITING_LANGUAGE}
        else "both"
    )
    try:
        regular_premium = subscription_service.get_subscription(sender).has_premium_access
        test_status = None
        if test_billing_store is not None:
            record = test_billing_store.get_test_subscription(sender)
            test_status = record["status"] if record is not None else None
        message = build_plan_message(
            language, regular_premium=regular_premium, test_status=test_status,
        )
    except Exception:
        logger.warning("Could not check WhatsApp plan status")
        message = (
            "⚠️ No pude consultar tu plan ahora. Inténtalo de nuevo."
            if language == "es"
            else "⚠️ Couldn't check your plan right now. Please try again."
        )
    send_text_message(to=sender, message=message)



def favorite_language(sender: str) -> str:
    session = conversation_store.get(sender)
    return session.language if session and session.state not in {
        ConversationState.NEW, ConversationState.WAITING_LANGUAGE
    } else "es"


def handle_favorite_action(
    sender: str, action: str, index: int | None,
    preferred_language: str | None = None,
) -> None:
    """Operate only on the authenticated Meta webhook sender, never a supplied ID."""
    language = preferred_language or favorite_language(sender)
    spanish = language == "es"
    try:
        if not subscription_service.can_use_feature(sender, Feature.FAVORITES):
            send_text_message(
                to=sender,
                message=(
                    "⭐ Guardar y consultar favoritas requiere Premium. "
                    "La búsqueda de gasolineras sigue siendo gratis. "
                    "Los pagos reales aún no están activados."
                    if spanish else
                    "⭐ Saving and viewing favorites requires Premium. "
                    "Gas-station search stays free. Real payments are not enabled."
                ),
            )
            return

        if favorites_store is None:
            raise RuntimeError("Favorites storage is unavailable")

        if action == "list":
            favorites = favorites_store.list_favorites(sender)
            if not favorites:
                message = (
                    "⭐ Aún no tienes favoritas. Tras buscar gasolineras, "
                    "elige «Guardar 1–5» para añadir una."
                    if spanish else
                    "⭐ You have no favorites yet. After a search, "
                    "choose Save 1–5 to add one."
                )
            else:
                title = "⭐ Mis favoritas" if spanish else "⭐ My favorites"
                lines = [title]
                for position, station in enumerate(favorites, start=1):
                    address = f" — {station.address}" if station.address else ""
                    lines.append(f"{position}. {station.name}{address}")
                lines.append(
                    "Para quitar una: «eliminar favorita 1»."
                    if spanish else
                    "To remove one: “remove favorite 1”."
                )
                message = "\n".join(lines)
        elif action == "save" and index is not None:
            chosen = favorites_store.add_from_recent(sender, index)
            message = (
                f"⭐ Guardada: {chosen.name}. Escribe «mis favoritas» para ver tu lista."
                if spanish else
                f"⭐ Saved: {chosen.name}. Type “my favorites” to view your list."
            )
        elif action == "remove" and index is not None:
            chosen = favorites_store.remove_favorite(sender, index)
            message = (
                f"✅ Eliminada: {chosen.name}."
                if spanish else
                f"✅ Removed: {chosen.name}."
            )
        else:
            return
    except FavoriteStoreError as exc:
        reason = str(exc)
        if reason == "no_recent_result":
            message = (
                "Busca gasolineras primero y elige el número mostrado más reciente."
                if spanish else
                "Search for gas stations first and choose a number from the latest results."
            )
        elif reason == "limit":
            message = (
                "Has llegado al límite de 10 favoritas. "
                "Escribe «mis favoritas» y elimina una antes de guardar otra."
                if spanish else
                "You've reached the 10-favorite limit. "
                "Type “my favorites” and remove one before saving another."
            )
        else:
            message = (
                "No encontré esa favorita. Escribe «mis favoritas» para ver los números."
                if spanish else
                "I couldn't find that favorite. Type “my favorites” for the numbers."
            )
    except Exception:
        logger.warning("Could not process favorite action")
        message = (
            "⚠️ No pude actualizar tus favoritas ahora. Inténtalo de nuevo."
            if spanish else
            "⚠️ Couldn't update favorites right now. Please try again."
        )
    try:
        send_text_message(to=sender, message=message)
    except WhatsAppServiceError:
        # A remove already committed to the store. Retrying the same message
        # could remove the NEXT numbered favorite. Never replay that mutation.
        logger.warning("Could not deliver favorite action acknowledgement")


def save_recent_if_premium(
    sender: str, stations: tuple[FavoriteStation, ...]
) -> bool:
    if not subscription_service.can_use_feature(sender, Feature.FAVORITES):
        return False
    if favorites_store is None:
        return False
    favorites_store.record_results(sender, stations)
    return True

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
        show_plan=handle_plan_status,
        show_favorite=lambda sender, action, index: handle_favorite_action(
            sender, action, index,
            preferred_language=(
                "en" if (incoming_message.text or "").strip().casefold().startswith(
                    ("my ", "save", "remove", "favorites")
                ) else "es"
                if (incoming_message.text or "").strip().casefold().startswith(
                    ("mis ", "guardar", "eliminar", "borrar", "favoritas")
                ) else None
            ),
        ),
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
        show_plan=handle_plan_status,
        show_favorite=handle_favorite_action,
    )


def load_search_preferences(sender: str) -> SearchPreferences | None:
    try:
        return search_preferences_store.get(sender)
    except Exception:
        # Profile persistence is optional enrichment, not a reason to stop gas searches.
        logger.warning("Could not load search preferences")
        return None


def save_search_preferences(sender: str, preferences: SearchPreferences) -> None:
    try:
        search_preferences_store.save(sender, preferences)
    except Exception:
        # Delivery succeeded already; do not let a profile write break navigation.
        logger.warning("Could not save search preferences")


def search_from_location(
    incoming_message: IncomingMessage,
    session: ConversationSession,
) -> None:
    run_location_search(
        incoming_message,
        session,
        allow_search=search_rate_limiter.allow,
        search=lambda **kwargs: location_search_service.search(
            **kwargs, capture_results=True
        ),
        send_text=send_text_message,
        update_session=conversation_transitions.apply,
        send_prompt=send_prompt,
        save_preferences=save_search_preferences,
        save_recent=save_recent_if_premium,
    )


def handle_location_message(incoming_message: IncomingMessage) -> None:
    process_location_message(
        incoming_message,
        get_session=conversation_store.get,
        search_from_location=search_from_location,
        dispatch_state_location=location_state_router.dispatch,
        send_expected=send_expected_prompt,
        load_preferences=load_search_preferences,
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
