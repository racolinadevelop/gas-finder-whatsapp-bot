from app.conversation import (
    ConversationState,
    NavigationAction,
    get_previous_state,
    parse_navigation_action,
)


def test_parse_navigation_action_understands_english_and_spanish():
    assert parse_navigation_action("back") == NavigationAction.BACK
    assert parse_navigation_action("⬅️ Atrás") == NavigationAction.BACK
    assert parse_navigation_action("menu") == NavigationAction.MENU
    assert parse_navigation_action("🏠 Menú") == NavigationAction.MENU


def test_parse_navigation_action_understands_button_ids():
    assert parse_navigation_action("nav_back") == NavigationAction.BACK
    assert parse_navigation_action("nav_menu") == NavigationAction.MENU


def test_parse_navigation_action_ignores_regular_text():
    assert parse_navigation_action("premium closest") is None


def test_get_previous_state_moves_back_one_step():
    assert get_previous_state(ConversationState.WAITING_LOCATION) == (
        ConversationState.WAITING_DISTANCE
    )
    assert get_previous_state(ConversationState.WAITING_RESULTS) == (
        ConversationState.WAITING_LOCATION
    )
    assert get_previous_state(ConversationState.WAITING_CUSTOM_DISTANCE) == (
        ConversationState.WAITING_DISTANCE
    )
    assert get_previous_state(ConversationState.WAITING_DISTANCE) == (
        ConversationState.WAITING_SORT
    )
    assert get_previous_state(ConversationState.WAITING_SORT) == (
        ConversationState.WAITING_FUEL
    )
    assert get_previous_state(ConversationState.WAITING_FUEL) == (
        ConversationState.MAIN_MENU
    )
    assert get_previous_state(ConversationState.WAITING_LANGUAGE) == (
        ConversationState.WAITING_LANGUAGE
    )
