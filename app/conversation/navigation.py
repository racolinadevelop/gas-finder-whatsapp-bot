from enum import StrEnum

from app.conversation.models import ConversationState


class NavigationAction(StrEnum):
    BACK = "back"
    MENU = "menu"


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
}

PREVIOUS_STATES = {
    ConversationState.WAITING_FUEL: ConversationState.WAITING_LANGUAGE,
    ConversationState.WAITING_SORT: ConversationState.WAITING_FUEL,
    ConversationState.WAITING_LOCATION: ConversationState.WAITING_SORT,
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
    if normalized in BACK_COMMANDS:
        return NavigationAction.BACK
    if normalized in MENU_COMMANDS:
        return NavigationAction.MENU

    return None


def get_previous_state(state: ConversationState) -> ConversationState:
    return PREVIOUS_STATES.get(state, ConversationState.WAITING_LANGUAGE)
