from enum import StrEnum

from app.conversation.models import ConversationState


class NavigationAction(StrEnum):
    BACK = "back"
    MENU = "menu"
    CHANGE_LANGUAGE = "change_language"


BACK_COMMANDS = {
    "back",
    "/back",
    "go back",
    "atras",
    "atrás",
    "volver",
}

MENU_COMMANDS = {
    "menu",
    "menú",
    "/menu",
    "main menu",
    "menu principal",
    "menú principal",
    "home",
    "inicio",
    "restart",
    "start over",
}

NAVIGATION_BUTTONS = {
    "nav_back": NavigationAction.BACK,
    "nav_menu": NavigationAction.MENU,
    "nav_language": NavigationAction.CHANGE_LANGUAGE,
}

LANGUAGE_COMMANDS = {"cambiar idioma", "change language", "/language", "idioma"}

PREVIOUS_STATES = {
    ConversationState.MAIN_MENU: ConversationState.MAIN_MENU,
    ConversationState.WAITING_LANGUAGE: ConversationState.WAITING_LANGUAGE,
    ConversationState.WAITING_FUEL: ConversationState.MAIN_MENU,
    ConversationState.WAITING_SORT: ConversationState.WAITING_FUEL,
    ConversationState.WAITING_DISTANCE: ConversationState.WAITING_SORT,
    ConversationState.WAITING_CUSTOM_DISTANCE: (
        ConversationState.WAITING_DISTANCE
    ),
    ConversationState.WAITING_LOCATION: ConversationState.WAITING_DISTANCE,
    ConversationState.WAITING_RESULTS: ConversationState.WAITING_LOCATION,
}


def parse_navigation_action(value: str | None) -> NavigationAction | None:
    if not value:
        return None

    normalized = (
        value.casefold()
        .replace("⬅️", "")
        .replace("⬅", "")
        .replace("🏠", "")
        .strip()
    )

    if normalized in NAVIGATION_BUTTONS:
        return NAVIGATION_BUTTONS[normalized]
    if normalized in LANGUAGE_COMMANDS:
        return NavigationAction.CHANGE_LANGUAGE
    if normalized in BACK_COMMANDS:
        return NavigationAction.BACK
    if normalized in MENU_COMMANDS:
        return NavigationAction.MENU

    return None


def get_previous_state(state: ConversationState) -> ConversationState:
    return PREVIOUS_STATES.get(state, ConversationState.WAITING_LANGUAGE)
