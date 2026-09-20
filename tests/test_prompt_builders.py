from app.conversation import ConversationSession, ConversationState
from app.presentation import (
    ListPrompt,
    ReplyButtonsPrompt,
    TextPrompt,
    build_custom_distance_prompt,
    build_distance_prompt,
    build_fuel_prompt,
    build_language_prompt,
    build_location_prompt,
    build_sort_prompt,
    build_state_prompt,
)


def test_language_prompt_contains_language_buttons():
    prompt = build_language_prompt()

    assert isinstance(prompt, ReplyButtonsPrompt)
    assert [button["id"] for button in prompt.buttons] == [
        "lang_en",
        "lang_es",
    ]


def test_language_prompt_can_include_profile_name():
    prompt = build_language_prompt(display_name="Ramon")

    assert "Ramon" in prompt.body_text
    assert "Hi, Ramon!" in prompt.body_text
    assert "¡Hola, Ramon!" in prompt.body_text


def test_spanish_fuel_prompt_can_include_welcome_and_error():
    prompt = build_fuel_prompt("es", welcome=True, error=True)

    assert "bienvenido" in prompt.body_text.casefold()
    assert "no corresponde" in prompt.body_text.casefold()
    assert [button["id"] for button in prompt.buttons] == [
        "fuel_regular",
        "fuel_premium",
        "fuel_diesel",
    ]


def test_spanish_fuel_welcome_can_include_profile_name():
    prompt = build_fuel_prompt(
        "es",
        welcome=True,
        display_name="Ramon",
    )

    assert "¡Hola, Ramon!" in prompt.body_text


def test_sort_prompt_describes_selected_fuel():
    session = ConversationSession(
        sender="15551234567",
        state=ConversationState.WAITING_SORT,
        language="es",
        fuel_type="diesel",
    )

    prompt = build_sort_prompt(session, selected=True)

    assert "Diésel" in prompt.body_text
    assert [button["id"] for button in prompt.buttons] == [
        "sort_distance",
        "sort_price",
        "sort_best",
    ]


def test_distance_prompt_contains_presets_and_custom_option():
    session = ConversationSession(
        sender="15551234567",
        state=ConversationState.WAITING_DISTANCE,
        language="en",
    )

    prompt = build_distance_prompt(session)

    assert isinstance(prompt, ListPrompt)
    assert [row["id"] for row in prompt.rows] == [
        "distance_1",
        "distance_3",
        "distance_5",
        "distance_10",
        "distance_custom",
    ]


def test_custom_distance_prompt_includes_range_error():
    prompt = build_custom_distance_prompt("en", range_error=True)

    assert isinstance(prompt, TextPrompt)
    assert "between 0.1 and 31 miles" in prompt.message


def test_location_prompt_includes_saved_preferences_and_distance():
    session = ConversationSession(
        sender="15551234567",
        state=ConversationState.WAITING_LOCATION,
        language="es",
        fuel_type="premium",
        sort="price",
        max_distance_miles=3,
    )

    prompt = build_location_prompt(session, saved=True)

    assert "Premium" in prompt.message
    assert "Más barato" in prompt.message
    assert "Distancia máxima: 3 mi" in prompt.message


def test_state_prompt_selects_prompt_type_for_current_state():
    session = ConversationSession(
        sender="15551234567",
        state=ConversationState.WAITING_CUSTOM_DISTANCE,
        language="en",
    )

    prompt = build_state_prompt(session, error=True)

    assert isinstance(prompt, TextPrompt)
    assert "couldn't recognize that distance" in prompt.message.casefold()


def test_results_navigation_prompt_uses_whatsapp_reply_buttons():
    prompt = build_state_prompt(
        ConversationSession(
            sender="sender",
            state=ConversationState.WAITING_RESULTS,
            language="es",
        )
    )

    assert isinstance(prompt, ReplyButtonsPrompt)
    assert [button["id"] for button in prompt.buttons] == [
        "nav_back", "nav_menu",
    ]
    assert [button["title"] for button in prompt.buttons] == [
        "⬅️ Atrás", "🏠 Menú",
    ]


def test_returning_to_language_selection_does_not_repeat_welcome():
    prompt = build_state_prompt(
        ConversationSession(
            sender="sender",
            state=ConversationState.WAITING_LANGUAGE,
            profile_name="Ramon",
        )
    )

    assert isinstance(prompt, ReplyButtonsPrompt)
    assert "choose your preferred language" in prompt.body_text
    assert "Welcome" not in prompt.body_text
    assert "Ramon" not in prompt.body_text


def test_initial_language_prompt_has_no_navigation_hint():
    prompt = build_language_prompt(display_name="Ramon")
    assert "Hi, Ramon!" in prompt.body_text
    assert "back" not in prompt.body_text.lower()
    assert "menu" not in prompt.body_text.lower()
