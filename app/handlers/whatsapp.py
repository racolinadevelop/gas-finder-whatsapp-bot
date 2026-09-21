import logging

from app.billing.test_store import PostgresTestBillingStore
from app.billing.whatsapp_test_checkout import (
    WhatsAppTestCheckoutError,
    create_sender_checkout, create_sender_portal, links_enabled,
)
from app.config import DATABASE_URL, STRIPE_TEST_MODE_ENABLED, GAS_STATION_PROVIDER
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
from app.favorites.comparison import compare_saved_places, format_favorite_comparison
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
from app.preferences.language import InMemoryLanguageStore, PostgresLanguageStore
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
from app.presentation.prompts import (
    build_favorites_navigation_prompt,
    build_favorite_removal_prompt,
    build_plan_navigation_prompt,
    build_favorites_result_navigation_prompt,
    build_favorites_compare_pages_prompt,
    build_favorites_compare_fuel_prompt,
    build_favorites_compare_location_prompt,
    build_favorites_compare_results_prompt,
)
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
user_language_store = (
    PostgresLanguageStore(DATABASE_URL) if DATABASE_URL else InMemoryLanguageStore()
)
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


def load_saved_language(sender: str) -> str | None:
    """Explicit choice survives session expiry; migrate old search profiles."""
    try:
        saved = user_language_store.get(sender)
        if saved in {"es", "en"}:
            return saved
        profile = search_preferences_store.get(sender)
        if profile is not None and profile.language in {"es", "en"}:
            user_language_store.save(sender, profile.language)
            return profile.language
        # Existing users may have selected a language but not completed a
        # search yet. Migrate an already advanced conversation as well.
        current = conversation_store.get(sender)
        if (
            current is not None
            and current.state not in {
                ConversationState.NEW, ConversationState.WAITING_LANGUAGE,
            }
            and current.language in {"es", "en"}
        ):
            user_language_store.save(sender, current.language)
            return current.language
    except Exception:
        logger.warning("Could not retrieve saved language preference")
    return None


def save_selected_language(sender: str, language: str) -> bool:
    try:
        user_language_store.save(sender, language)
        return True
    except Exception:
        logger.warning("Could not save language preference")
        return False


conversation_state_handlers = ConversationStateHandlers(
    conversation_transitions,
    send_prompt,
    save_language=save_selected_language,
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
    if action == NavigationAction.CHANGE_LANGUAGE:
        session = conversation_transitions.show_language_selection(sender)
        send_state_prompt(sender, session)
        return

    if action == NavigationAction.MENU:
        existing = conversation_store.get(sender)
        saved = load_saved_language(sender)
        if saved is None and existing is not None and existing.state not in {
            ConversationState.NEW, ConversationState.WAITING_LANGUAGE
        }:
            saved = existing.language
        if saved is None:
            session = conversation_transitions.begin(sender)
        else:
            session = conversation_transitions.resume(sender, saved)
        send_state_prompt(sender, session)
        return

    current = conversation_store.get(sender)
    if current is not None and action == NavigationAction.BACK:
        if current.state == ConversationState.WAITING_FAVORITES_FUEL:
            conversation_transitions.apply(sender, {"state": ConversationState.MAIN_MENU})
            handle_favorite_action(sender, "list", None)
            return
        if current.state == ConversationState.WAITING_FAVORITES_LOCATION:
            session = conversation_transitions.apply(
                sender, {"state": ConversationState.WAITING_FAVORITES_FUEL}
            )
            send_state_prompt(sender, session)
            return
    if current is not None and current.state == ConversationState.WAITING_LANGUAGE:
        # Back cannot silently undo a first-time language choice.
        send_state_prompt(sender, current)
        return
    session = conversation_transitions.navigate(sender, action)
    send_state_prompt(sender, session)


def begin_or_resume(sender: str, profile_name: str | None = None) -> ConversationSession:
    current = conversation_store.get(sender)
    if current is not None and current.state == ConversationState.WAITING_LANGUAGE:
        return conversation_transitions.begin(sender, profile_name=profile_name)
    saved = load_saved_language(sender)
    if saved:
        return conversation_transitions.resume(sender, saved, profile_name=profile_name)
    return conversation_transitions.begin(sender, profile_name=profile_name)


def send_entry_prompt(sender: str, display_name: str | None = None) -> None:
    session = conversation_store.get(sender)
    if session is None or session.state == ConversationState.WAITING_LANGUAGE:
        send_language_prompt(sender, display_name=display_name)
    else:
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


def send_account_actions(sender: str, prompt: Prompt) -> None:
    """These stand-alone lists include their own navigation in every state."""
    try:
        send_list_message(
            to=sender,
            body_text=prompt.body_text,
            button_text=prompt.button_text,
            section_title=prompt.section_title,
            rows=prompt.rows,
        )
    except WhatsAppServiceError:
        logger.warning("Could not deliver account actions")


def handle_start_search(sender: str) -> None:
    """A contextual Search button works from plan/favorites as well as home."""
    current = conversation_store.get(sender)
    if current is not None and current.state == ConversationState.WAITING_LANGUAGE:
        send_state_prompt(sender, current)
        return

    language = load_saved_language(sender)
    if language is None and current is not None and current.state not in {
        ConversationState.NEW, ConversationState.WAITING_LANGUAGE,
    }:
        language = current.language
    if language is None:
        session = conversation_transitions.begin(sender)
        send_state_prompt(sender, session)
        return

    conversation_transitions.resume(sender, language)
    session = conversation_transitions.start_search(sender)
    send_state_prompt(sender, session)


def handle_plan_status(sender: str) -> None:
    """Show this WhatsApp sender's own plan without changing search state."""
    session = conversation_store.get(sender)
    language = (
        session.language
        if session is not None
        and session.state not in {ConversationState.NEW, ConversationState.WAITING_LANGUAGE}
        else "both"
    )
    offer_checkout = False
    offer_portal = False
    try:
        regular_premium = subscription_service.get_subscription(sender).has_premium_access
        test_status = None
        if test_billing_store is not None:
            record = test_billing_store.get_test_subscription(sender)
            test_status = record["status"] if record is not None else None
        message = build_plan_message(
            language, regular_premium=regular_premium, test_status=test_status,
        )
        offer_checkout = (
            links_enabled() and test_billing_store is not None
            and not regular_premium and test_status in {None, "canceled"}
        )
        offer_portal = (
            links_enabled() and test_billing_store is not None
            and test_status in {"active", "past_due"}
        )
    except Exception:
        logger.warning("Could not check WhatsApp plan status")
        message = (
            "⚠️ No pude consultar tu plan ahora. Inténtalo de nuevo."
            if language == "es"
            else "⚠️ Couldn't check your plan right now. Please try again."
        )
    send_text_message(to=sender, message=message)
    if language in {"es", "en"}:
        send_account_actions(
            sender, build_plan_navigation_prompt(
                language, offer_test_checkout=offer_checkout,
                offer_test_portal=offer_portal,
            ),
        )
    else:
        # An explicit first-time language choice (or change) comes first.
        send_language_prompt(sender, display_name=session.profile_name if session else None)


def handle_test_checkout(sender: str) -> None:
    """Only a signed WhatsApp webhook sender may request their own TEST link."""
    session = conversation_store.get(sender)
    language = load_saved_language(sender)
    if session is not None and session.state == ConversationState.WAITING_LANGUAGE:
        send_state_prompt(sender, session)
        return
    if language not in {"es", "en"}:
        send_language_prompt(sender)
        return
    try:
        url = create_sender_checkout(
            sender, store=test_billing_store,
            subscription_service=subscription_service,
        )
    except WhatsAppTestCheckoutError as exc:
        messages = {
            "already_premium": (
                "⭐ Ya tienes Premium activo.", "⭐ You already have active Premium."
            ),
            "already_linked": (
                "Tu suscripción de prueba ya está vinculada. Consulta «Mi plan».",
                "Your test subscription is already linked. Check My plan.",
            ),
            "processing": (
                "⏳ Estamos comprobando tu pago de prueba. Consulta «Mi plan» "
                "en unos momentos.",
                "⏳ We're verifying your test payment. Check My plan shortly.",
            ),
            "disabled": (
                "La inscripción de prueba aún no está disponible.",
                "Test signup isn't available yet.",
            ),
        }
        option = messages.get(exc.args[0], (
            "⚠️ No pude abrir Stripe de prueba ahora. Inténtalo más tarde.",
            "⚠️ Couldn't open Stripe test checkout. Please try again later.",
        ))
        send_text_message(to=sender, message=option[0 if language == "es" else 1])
        handle_plan_status(sender)
        return
    text = (
        "⭐ *Probar Premium — Stripe TEST*\n"
        "Este enlace es exclusivo para pruebas: no se cobra dinero real. "
        "No introduzcas una tarjeta bancaria real; usa solamente los datos "
        "de prueba de Stripe.\n\n"
        f"Abre tu enlace de prueba:\n{url}\n\n"
        "Después, vuelve a «Mi plan» en WhatsApp. "
        "Premium se activa únicamente cuando Stripe confirma el pago de prueba."
        if language == "es" else
        "⭐ *Try Premium — Stripe TEST*\n"
        "This link is for testing only: no real money is charged. "
        "Do not enter a real bank card; use Stripe test payment details only.\n\n"
        f"Open your test link:\n{url}\n\n"
        "Then return to My plan in WhatsApp. "
        "Premium activates only after Stripe verifies the test payment."
    )
    send_text_message(to=sender, message=text)


def handle_test_portal(sender: str) -> None:
    language = load_saved_language(sender)
    if language not in {"es", "en"}:
        send_language_prompt(sender)
        return
    try:
        url = create_sender_portal(sender, store=test_billing_store)
    except WhatsAppTestCheckoutError:
        send_text_message(
            to=sender, message=(
                "No pude abrir la gestión de la prueba ahora. Consulta «Mi plan»."
                if language == "es" else
                "Couldn't open test subscription management. Check My plan."
            ),
        )
        return
    send_text_message(
        to=sender, message=(
            "💳 Gestiona tu suscripción de *prueba* en Stripe. "
            "No se realizan cobros reales:\n" + url
            if language == "es" else
            "💳 Manage your Stripe *test* subscription. "
            "No real charges are made:\n" + url
        ),
    )


def favorite_language(sender: str) -> str:
    session = conversation_store.get(sender)
    return session.language if session and session.state not in {
        ConversationState.NEW, ConversationState.WAITING_LANGUAGE
    } else "es"


def handle_favorite_action(
    sender: str, action: str, index: int | str | None,
    preferred_language: str | None = None,
) -> None:
    """Every view and mutation checks this WhatsApp sender's current entitlement."""
    language = preferred_language or favorite_language(sender)
    es = language == "es"
    try:
        if not subscription_service.can_use_feature(sender, Feature.FAVORITES):
            message = (
                "⭐ Guardar y consultar favoritas requiere Premium. "
                "La búsqueda de gasolineras sigue siendo gratis."
                if es else
                "⭐ Saving and viewing favorites requires Premium. "
                "Gas-station search stays free."
            )
            send_text_message(to=sender, message=message)
            send_account_actions(
                sender, build_favorites_navigation_prompt(
                    language, has_items=False, premium=False,
                ),
            )
            return

        if favorites_store is None:
            raise RuntimeError("Favorites storage is unavailable")

        if action in {"compare_menu", "compare_page", "compare_fuel"}:
            session = conversation_store.get(sender)
            if session is None or session.state == ConversationState.WAITING_LANGUAGE:
                send_language_prompt(sender)
                return
            favorites = favorites_store.list_favorites(sender)
            if not favorites:
                action = "list"
            elif action == "compare_menu":
                if len(favorites) <= 5:
                    session = conversation_transitions.apply(sender, {
                        "state": ConversationState.WAITING_FAVORITES_FUEL,
                        "favorite_page": 1,
                    })
                    send_state_prompt(sender, session)
                else:
                    send_account_actions(
                        sender, build_favorites_compare_pages_prompt(
                            language, len(favorites),
                        ),
                    )
                return
            elif action == "compare_page":
                if (
                    not isinstance(index, int) or index not in (1, 2)
                    or (index == 2 and len(favorites) <= 5)
                ):
                    send_account_actions(
                        sender, build_favorites_compare_pages_prompt(
                            language, len(favorites),
                        ),
                    )
                    return
                session = conversation_transitions.apply(sender, {
                    "state": ConversationState.WAITING_FAVORITES_FUEL,
                    "favorite_page": index,
                })
                send_state_prompt(sender, session)
                return
            elif action == "compare_fuel":
                if (
                    session.state != ConversationState.WAITING_FAVORITES_FUEL
                    or index not in {"regular", "premium", "diesel"}
                ):
                    send_expected_prompt(sender, session)
                    return
                session = conversation_transitions.apply(sender, {
                    "state": ConversationState.WAITING_FAVORITES_LOCATION,
                    "fuel_type": index,
                })
                send_state_prompt(sender, session)
                return

        if action == "remove_menu":
            favorites = favorites_store.list_favorites(sender)
            if favorites:
                page = index if index in (1, 2) else 1
                if page == 2 and len(favorites) <= 5:
                    page = 1
                send_account_actions(
                    sender, build_favorite_removal_prompt(language, favorites, page),
                )
                return
            action = "list"

        show_view = False
        if action == "list":
            session = conversation_store.get(sender)
            if session is not None and session.state in {
                ConversationState.WAITING_FAVORITES_FUEL,
                ConversationState.WAITING_FAVORITES_LOCATION,
            }:
                conversation_transitions.apply(
                    sender, {"state": ConversationState.MAIN_MENU}
                )
            favorites = favorites_store.list_favorites(sender)
            if not favorites:
                message = (
                    "⭐ Aún no tienes favoritas. Busca gasolineras y elige "
                    "«Guardar» junto a una de ellas."
                    if es else
                    "⭐ You have no favorites yet. Search for gas stations "
                    "and choose Save next to one."
                )
            else:
                lines = ["⭐ Mis favoritas" if es else "⭐ My favorites"]
                for position, station in enumerate(favorites, start=1):
                    address = f" — {station.address}" if station.address else ""
                    lines.append(f"{position}. {station.name}{address}")
                message = "\n".join(lines)
        elif action == "save" and isinstance(index, int):
            chosen = favorites_store.add_from_recent(sender, index)
            message = (
                f"⭐ Guardada: {chosen.name}."
                if es else f"⭐ Saved: {chosen.name}."
            )
            favorites = favorites_store.list_favorites(sender)
            show_view = True
        elif action == "remove" and isinstance(index, int):
            chosen = favorites_store.remove_favorite(sender, index)
            message = (
                f"✅ Eliminada: {chosen.name}."
                if es else f"✅ Removed: {chosen.name}."
            )
            favorites = favorites_store.list_favorites(sender)
            show_view = bool(favorites)
        elif action == "remove_key" and isinstance(index, str):
            chosen = favorites_store.remove_by_digest(sender, index)
            message = (
                f"✅ Eliminada: {chosen.name}."
                if es else f"✅ Removed: {chosen.name}."
            )
            favorites = favorites_store.list_favorites(sender)
            show_view = bool(favorites)
        else:
            return

        send_text_message(to=sender, message=message)
        send_account_actions(
            sender, build_favorites_navigation_prompt(
                language, has_items=bool(favorites), show_view=show_view,
            ),
        )
    except FavoriteStoreError as exc:
        if str(exc) == "no_recent_result":
            message = (
                "Busca gasolineras primero y elige una de las opciones Guardar."
                if es else "Search for gas stations and choose a Save option first."
            )
        elif str(exc) == "limit":
            message = (
                "Has llegado al límite de 10 favoritas. "
                "Elimina una antes de guardar otra."
                if es else
                "You've reached the 10-favorite limit. Remove one before saving another."
            )
        else:
            message = (
                "Esa favorita ya no está disponible. Consulta tu lista actual."
                if es else "That favorite is no longer available. Check your current list."
            )
        try:
            send_text_message(to=sender, message=message)
            # Refreshing the list avoids asking the user to type after a stale tap.
            handle_favorite_action(sender, "list", None, preferred_language=language)
        except WhatsAppServiceError:
            logger.warning("Could not deliver favorite action error")
    except WhatsAppServiceError:
        # The mutation may already be committed. Do not retry the same button:
        # a user must intentionally select another action.
        logger.warning("Could not deliver favorite action acknowledgement")
    except Exception:
        logger.warning("Could not process favorite action")
        try:
            send_text_message(
                to=sender,
                message=(
                    "⚠️ No pude consultar tus favoritas ahora. Inténtalo de nuevo."
                    if es else
                    "⚠️ Couldn't open your favorites right now. Please try again."
                ),
            )
            send_account_actions(
                sender, build_favorites_navigation_prompt(
                    language, has_items=False, premium=False,
                ),
            )
        except WhatsAppServiceError:
            logger.warning("Could not deliver favorites failure prompt")


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
        begin=begin_or_resume,
        send_language=send_entry_prompt,
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
        start_search=handle_start_search,
        create_test_checkout=handle_test_checkout,
        manage_test_subscription=handle_test_portal,
    )


def load_search_preferences(sender: str) -> SearchPreferences | None:
    try:
        profile = search_preferences_store.get(sender)
        language = load_saved_language(sender)
        if profile is not None and language and profile.language != language:
            from dataclasses import replace
            return replace(profile, language=language)
        if profile is None and language:
            return SearchPreferences(
                language=language, fuel_type="regular",
                sort="best", max_distance_miles=None,
            )
        return profile
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


def compare_favorites_from_location(
    incoming_message: IncomingMessage, session: ConversationSession
) -> None:
    """Refresh the chosen favorites only after explicit location and entitlement checks."""
    sender = incoming_message.sender
    es = session.language == "es"
    if incoming_message.latitude is None or incoming_message.longitude is None:
        return
    if not subscription_service.can_use_feature(sender, Feature.FAVORITES):
        send_text_message(
            to=sender,
            message=(
                "⭐ Comparar favoritas requiere Premium activo."
                if es else "⭐ Comparing favorites requires active Premium."
            ),
        )
        conversation_transitions.apply(sender, {"state": ConversationState.MAIN_MENU})
        send_account_actions(
            sender, build_favorites_navigation_prompt(
                session.language, has_items=False, premium=False,
            ),
        )
        return
    if favorites_store is None:
        send_text_message(
            to=sender,
            message="⚠️ Favoritas no disponibles ahora." if es
            else "⚠️ Favorites aren't available right now.",
        )
        return
    if GAS_STATION_PROVIDER != "google":
        send_text_message(
            to=sender,
            message=(
                "⚠️ Esta comparación necesita favoritas de Google Places; "
                "el proveedor actual no permite consultar sus precios por estación."
                if es else
                "⚠️ This comparison needs Google Places favorites; "
                "the current provider cannot retrieve prices for saved station IDs."
            ),
        )
        return
    favorites = favorites_store.list_favorites(sender)
    selected = favorites[(session.favorite_page - 1) * 5:session.favorite_page * 5]
    if not selected:
        send_text_message(
            to=sender,
            message="⭐ No hay favoritas en ese grupo." if es
            else "⭐ No favorites in that group.",
        )
        conversation_transitions.apply(sender, {"state": ConversationState.MAIN_MENU})
        send_account_actions(
            sender, build_favorites_compare_pages_prompt(
                session.language, len(favorites),
            ),
        ) if favorites else send_account_actions(
            sender, build_favorites_navigation_prompt(
                session.language, has_items=False,
            ),
        )
        return
    if not search_rate_limiter.allow(sender):
        send_text_message(
            to=sender,
            message=(
                "⏳ Has realizado varias consultas. Espera unos minutos para "
                "comparar de nuevo tus favoritas."
                if es else
                "⏳ You've made several requests. Wait a few minutes "
                "before comparing your favorites again."
            ),
        )
        return
    try:
        result = compare_saved_places(
            selected,
            latitude=incoming_message.latitude,
            longitude=incoming_message.longitude,
            fuel_type=session.fuel_type,
        )
    except Exception:
        logger.warning("Unable to refresh favorite comparison")
        send_text_message(
            to=sender,
            message=(
                "⚠️ No pude actualizar tus favoritas ahora. "
                "Inténtalo de nuevo más tarde."
                if es else
                "⚠️ Couldn't refresh your favorites right now. "
                "Please try again later."
            ),
        )
        return

    send_text_message(
        to=sender,
        message=format_favorite_comparison(result, session.language),
    )
    # Do not persist the location or any fetched price/route; leave the user's
    # independent gas-search preferences and saved favorites unchanged.
    conversation_transitions.apply(sender, {"state": ConversationState.MAIN_MENU})
    send_account_actions(
        sender, build_favorites_compare_results_prompt(
            session.language, len(selected),
        ),
    )


def handle_location_message(incoming_message: IncomingMessage) -> None:
    session = conversation_store.get(incoming_message.sender)
    if session is not None and session.state == ConversationState.WAITING_FAVORITES_LOCATION:
        compare_favorites_from_location(incoming_message, session)
        return
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
