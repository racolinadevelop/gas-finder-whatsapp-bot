from dataclasses import dataclass

from app.constants import MAX_DISTANCE_MILES, MIN_DISTANCE_MILES
from app.conversation.models import ConversationSession, ConversationState
from app.conversation.options import CUSTOM_DISTANCE_ID
from app.i18n import t


@dataclass(frozen=True, slots=True)
class TextPrompt:
    message: str


@dataclass(frozen=True, slots=True)
class ReplyButtonsPrompt:
    body_text: str
    buttons: list[dict]


@dataclass(frozen=True, slots=True)
class ListPrompt:
    body_text: str
    button_text: str
    section_title: str
    rows: list[dict]


Prompt = TextPrompt | ReplyButtonsPrompt | ListPrompt


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


def build_language_prompt(
    error: bool = False,
    display_name: str | None = None,
    greeting: bool = True,
) -> ReplyButtonsPrompt:
    if error:
        body_text = t("en", "invalid_language")
    elif not greeting:
        body_text = t("en", "choose_language_again")
    elif display_name:
        body_text = t("en", "choose_language_named", name=display_name)
    else:
        body_text = t("en", "choose_language")

    return ReplyButtonsPrompt(
        body_text=body_text,
        buttons=[
            {"id": "lang_en", "title": "English"},
            {"id": "lang_es", "title": "Español"},
            {"id": "account_plan", "title": "Mi plan / My plan"},
        ],
    )


def build_fuel_prompt(
    language: str,
    welcome: bool = False,
    error: bool = False,
    display_name: str | None = None,
) -> ReplyButtonsPrompt:
    body_parts = []

    if welcome:
        if display_name:
            body_parts.append(
                t(language, "welcome_named", name=display_name)
            )
        else:
            body_parts.append(t(language, "welcome"))
    if error:
        body_parts.append(t(language, "invalid_fuel"))

    body_parts.extend(
        [
            t(language, "choose_fuel"),
        ]
    )

    return ReplyButtonsPrompt(
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


def build_sort_prompt(
    session: ConversationSession,
    selected: bool = False,
    error: bool = False,
) -> ReplyButtonsPrompt:
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

    body_parts.extend(
        [
            t(language, "choose_sort"),
        ]
    )

    return ReplyButtonsPrompt(
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


def build_distance_prompt(
    session: ConversationSession,
    error: bool = False,
) -> ListPrompt:
    language = session.language
    body_parts = []

    if error:
        body_parts.append(t(language, "invalid_distance_option"))
    body_parts.extend(
        [
            t(language, "choose_distance"),
        ]
    )

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

    return ListPrompt(
        body_text="\n\n".join(body_parts),
        button_text=t(language, "distance_list_button"),
        section_title=t(language, "distance_section_title"),
        rows=rows,
    )


def build_custom_distance_prompt(
    language: str,
    error: bool = False,
    range_error: bool = False,
) -> TextPrompt:
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
        ]
    )

    return TextPrompt(message="\n\n".join(parts))


def build_location_prompt(
    session: ConversationSession,
    saved: bool = False,
) -> TextPrompt:
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

    if session.max_distance_miles is not None:
        message = (
            f"{message}\n\n"
            f"{t(language, 'max_distance_saved', distance=session.max_distance_miles)}"
        )

    return TextPrompt(message=message)


def build_navigation_prompt(language: str) -> ReplyButtonsPrompt:
    return ReplyButtonsPrompt(
        body_text=t(language, "navigation_buttons_prompt"),
        buttons=[
            {"id": "nav_back", "title": t(language, "button_nav_back")},
            {"id": "nav_menu", "title": t(language, "button_nav_menu")},
        ],
    )


def build_results_navigation_prompt(language: str) -> ReplyButtonsPrompt:
    return ReplyButtonsPrompt(
        body_text=t(language, "results_next_step"),
        buttons=[
            {"id": "nav_back", "title": t(language, "button_nav_back")},
            {"id": "nav_menu", "title": t(language, "button_nav_menu")},
        ],
    )


def build_favorites_result_navigation_prompt(language: str, count: int) -> ListPrompt:
    """Premium-only choices for the five displayed results; Back/Menu included by delivery."""
    language = language if language in {"es", "en"} else "en"
    rows = [
        {
            "id": f"fav_save_{index}",
            "title": f"⭐ {'Guardar' if language == 'es' else 'Save'} {index}",
        }
        for index in range(1, min(max(count, 0), 5) + 1)
    ]
    rows.append({
        "id": "fav_list",
        "title": "⭐ Mis favoritas" if language == "es" else "⭐ My favorites",
    })
    return ListPrompt(
        body_text=(
            "⭐ ¿Quieres guardar una de estas gasolineras?"
            if language == "es"
            else "⭐ Want to save one of these gas stations?"
        ),
        button_text="Opciones" if language == "es" else "Options",
        section_title="Favoritas y navegación" if language == "es" else "Favorites and navigation",
        rows=rows,
    )


def build_main_menu_prompt(language: str, display_name: str | None = None) -> ListPrompt:
    """Four clear choices after language selection, in one WhatsApp list."""
    language = language if language in {"es", "en"} else "en"
    title = (
        f"👋 ¡Hola, {display_name}! ¿Qué deseas hacer?"
        if language == "es" and display_name else
        "👋 ¿Qué deseas hacer?" if language == "es" else
        f"👋 Hi, {display_name}! What would you like to do?"
        if display_name else "👋 What would you like to do?"
    )
    return ListPrompt(
        body_text=title,
        button_text="Abrir menú" if language == "es" else "Open menu",
        section_title="Menú principal" if language == "es" else "Main menu",
        rows=[
            {"id": "home_search", "title": "⛽ Buscar gasolineras" if language == "es" else "⛽ Find gas stations"},
            {"id": "fav_list", "title": "⭐ Mis favoritas" if language == "es" else "⭐ My favorites"},
            {"id": "account_plan", "title": "👤 Mi plan" if language == "es" else "👤 My plan"},
            {"id": "nav_language", "title": "🌐 Cambiar idioma" if language == "es" else "🌐 Change language"},
        ],
    )



def build_plan_navigation_prompt(
    language: str, *, offer_test_checkout: bool = False,
    offer_test_portal: bool = False,
) -> ListPrompt:
    """Expose only user-appropriate TEST subscription actions, never real billing."""
    es = language == "es"
    rows = [
        {"id": "home_search", "title": "⛽ Buscar gasolineras" if es else "⛽ Find gas stations"},
        {"id": "fav_list", "title": "⭐ Mis favoritas" if es else "⭐ My favorites"},
    ]
    if offer_test_checkout:
        rows.append({
            "id": "account_test_checkout",
            "title": "⭐ Probar Premium" if es else "⭐ Try Premium",
            "description": "Stripe TEST · sin cobros reales" if es else "Stripe TEST · no real charges",
        })
    if offer_test_portal:
        rows.append({
            "id": "account_test_portal",
            "title": "💳 Gestionar prueba" if es else "💳 Manage test plan",
        })
    rows.extend([
        {"id": "nav_language", "title": "🌐 Cambiar idioma" if es else "🌐 Change language"},
        {"id": "nav_menu", "title": "🏠 Menú principal" if es else "🏠 Main menu"},
    ])
    return ListPrompt(
        body_text="¿Qué deseas hacer ahora?" if es else "What would you like to do next?",
        button_text="Opciones" if es else "Options",
        section_title="Mi cuenta" if es else "My account",
        rows=rows,
    )


def build_favorites_navigation_prompt(
    language: str, *, has_items: bool, premium: bool = True, show_view: bool = False
) -> ListPrompt:
    """Small actions view even when a user has no favorites or has Free."""
    es = language == "es"
    rows = [
        {"id": "home_search", "title": "⛽ Buscar gasolineras" if es else "⛽ Find gas stations"},
    ]
    if premium and has_items:
        rows.append({
            "id": "fav_compare",
            "title": "📊 Comparar favoritas" if es else "📊 Compare favorites",
        })
    if premium and has_items and show_view:
        rows.append({"id": "fav_list", "title": "⭐ Mis favoritas" if es else "⭐ My favorites"})
    if premium and has_items:
        rows.append({
            "id": "fav_remove_menu",
            "title": "🗑 Eliminar favorita" if es else "🗑 Remove a favorite",
        })
    if not premium:
        rows.append({"id": "account_plan", "title": "👤 Mi plan" if es else "👤 My plan"})
    rows.append({"id": "nav_menu", "title": "🏠 Menú principal" if es else "🏠 Main menu"})
    return ListPrompt(
        body_text="¿Qué deseas hacer ahora?" if es else "What would you like to do next?",
        button_text="Opciones" if es else "Options",
        section_title="Favoritas" if es else "Favorites",
        rows=rows,
    )


def build_favorite_removal_prompt(
    language: str, favorites: tuple, page: int = 1
) -> ListPrompt:
    """Five stable station choices per page, always <= WhatsApp's 10-row limit."""
    from hashlib import sha256

    es = language == "es"
    if page not in (1, 2):
        raise ValueError("Invalid favorite removal page")
    start = (page - 1) * 5
    rows = [
        {
            "id": "fav_delete_" + sha256(item.key.encode("utf-8")).hexdigest(),
            "title": f"🗑 {start + index}. {item.name}"[:24],
            "description": item.address[:72] if item.address else "",
        }
        for index, item in enumerate(favorites[start:start + 5], start=1)
    ]
    if page == 1 and len(favorites) > 5:
        rows.append({"id": "fav_remove_page_2", "title": "➡️ Siguiente" if es else "➡️ Next"})
    if page == 2:
        rows.append({"id": "fav_remove_page_1", "title": "⬅️ Anterior" if es else "⬅️ Previous"})
    rows.extend([
        {"id": "fav_remove_back", "title": "⬅️ Mis favoritas" if es else "⬅️ My favorites"},
        {"id": "nav_menu", "title": "🏠 Menú principal" if es else "🏠 Main menu"},
    ])
    return ListPrompt(
        body_text=(
            "Selecciona la gasolinera que deseas eliminar."
            if es else "Choose the gas station to remove."
        ),
        button_text="Elegir favorita" if es else "Choose favorite",
        section_title="Eliminar favoritas" if es else "Remove favorites",
        rows=rows,
    )



def build_favorites_compare_pages_prompt(language: str, count: int) -> ListPrompt:
    es = language == "es"
    rows = [
        {"id": "fav_compare_page_1", "title": "📊 Comparar 1–5" if es else "📊 Compare 1–5"},
    ]
    if count > 5:
        rows.append({
            "id": "fav_compare_page_2",
            "title": "📊 Comparar 6–10" if es else "📊 Compare 6–10",
        })
    rows.extend([
        {"id": "fav_list", "title": "⭐ Mis favoritas" if es else "⭐ My favorites"},
        {"id": "nav_menu", "title": "🏠 Menú principal" if es else "🏠 Main menu"},
    ])
    return ListPrompt(
        body_text=(
            "Elige qué favoritas quieres comparar (máximo 5 por consulta)."
            if es else "Choose your favorites to compare (up to 5 per request)."
        ),
        button_text="Comparar" if es else "Compare",
        section_title="Comparación" if es else "Comparison",
        rows=rows,
    )


def build_favorites_compare_fuel_prompt(language: str) -> ListPrompt:
    es = language == "es"
    return ListPrompt(
        body_text=(
            "⛽ ¿Qué combustible quieres comparar en tus favoritas?"
            if es else "⛽ Which fuel would you like to compare at your favorites?"
        ),
        button_text="Combustible" if es else "Fuel",
        section_title="Combustible" if es else "Fuel type",
        rows=[
            {"id": "fav_fuel_regular", "title": "⛽ Regular"},
            {"id": "fav_fuel_premium", "title": "✨ Premium"},
            {"id": "fav_fuel_diesel", "title": "🚛 Diésel" if es else "🚛 Diesel"},
        ],
    )


def build_favorites_compare_location_prompt(language: str) -> TextPrompt:
    return TextPrompt(message=(
        "📍 Compararemos solo tus favoritas guardadas. "
        "Comparte tu ubicación desde WhatsApp para calcular la ruta por carretera "
        "si está disponible. No guardamos tu ubicación."
        if language == "es" else
        "📍 We'll compare only your saved favorites. Share your WhatsApp location "
        "to calculate a driving route when available. We don't store your location."
    ))


def build_favorites_compare_results_prompt(language: str, count: int) -> ListPrompt:
    es = language == "es"
    return ListPrompt(
        body_text="¿Qué deseas hacer ahora?" if es else "What would you like to do next?",
        button_text="Opciones" if es else "Options",
        section_title="Comparar favoritas" if es else "Compare favorites",
        rows=[
            {"id": "fav_compare", "title": "📊 Comparar otra vez" if es else "📊 Compare again"},
            {"id": "fav_list", "title": "⭐ Mis favoritas" if es else "⭐ My favorites"},
            {"id": "home_search", "title": "⛽ Buscar gasolineras" if es else "⛽ Find gas stations"},
            {"id": "nav_menu", "title": "🏠 Menú principal" if es else "🏠 Main menu"},
        ],
    )


def build_state_prompt(
    session: ConversationSession,
    error: bool = False,
) -> Prompt:
    if session.state in {
        ConversationState.NEW,
        ConversationState.WAITING_LANGUAGE,
    }:
        return build_language_prompt(
            error=error,
            display_name=session.profile_name,
            greeting=False,
        )
    if session.state == ConversationState.MAIN_MENU:
        return build_main_menu_prompt(session.language, session.profile_name)
    if session.state == ConversationState.WAITING_FAVORITES_FUEL:
        return build_favorites_compare_fuel_prompt(session.language)
    if session.state == ConversationState.WAITING_FAVORITES_LOCATION:
        return build_favorites_compare_location_prompt(session.language)
    if session.state == ConversationState.WAITING_FUEL:
        return build_fuel_prompt(session.language, error=error)
    if session.state == ConversationState.WAITING_SORT:
        return build_sort_prompt(session, error=error)
    if session.state == ConversationState.WAITING_DISTANCE:
        return build_distance_prompt(session, error=error)
    if session.state == ConversationState.WAITING_CUSTOM_DISTANCE:
        return build_custom_distance_prompt(session.language, error=error)
    if session.state == ConversationState.WAITING_RESULTS:
        return build_results_navigation_prompt(session.language)

    return build_location_prompt(session)
