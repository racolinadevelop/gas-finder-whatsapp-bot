"""My Plan is read-only and must never short-circuit a gas search."""

import pytest

from app.conversation import ConversationSession, ConversationState
from app.handlers.interactive_messages import process_interactive_message
from app.handlers.plan_messages import (
    PLAN_SELECTION_ID,
    build_plan_message,
    is_plan_command,
)
from app.handlers.text_messages import process_text_message
from app.models import IncomingMessage


@pytest.mark.parametrize("value", [
    "mi plan", "  MI   PLAN  ", "mi suscripción", "mi suscripcion",
    "My Plan", "/plan", "my subscription",
])
def test_plan_text_commands_are_explicit_and_normalized(value):
    assert is_plan_command(value)


@pytest.mark.parametrize("value", ["premium", "regular", "3", "mi planeta", "gasolina", ""])
def test_plan_text_does_not_take_over_search_or_fuel_selection(value):
    assert not is_plan_command(value)


def test_plan_summary_distinguishes_free_sandbox_real_and_cancelled():
    free = build_plan_message("es", regular_premium=False, test_status=None)
    assert "Gratis" in free and "búsqueda básica" in free
    active = build_plan_message("es", regular_premium=False, test_status="active")
    assert "Premium (prueba de Stripe)" in active
    canceled = build_plan_message("es", regular_premium=False, test_status="canceled")
    assert "Gratis" in canceled and "cancelada" in canceled
    assert "Premium (prueba de Stripe)" not in canceled
    real = build_plan_message("en", regular_premium=True, test_status="canceled")
    assert "plan: Premium" in real and "has been canceled" not in real
    pending = build_plan_message("en", regular_premium=False, test_status="past_due")
    assert "plan: Free" in pending and "no active Premium" in pending
    bilingual = build_plan_message("both", regular_premium=False, test_status=None)
    assert "plan: Free" in bilingual and "plan actual: Gratis" in bilingual
    for summary in [free, active, canceled, real, pending, bilingual]:
        assert "checkout.stripe.com" not in summary


@pytest.mark.parametrize("state", list(ConversationState))
def test_text_plan_command_has_priority_and_preserves_current_state(state):
    sender = "15551234567"
    session = ConversationSession(sender=sender, state=state, language="es")
    seen = []
    process_text_message(
        IncomingMessage(sender=sender, message_type="text", text="MI   PLAN"),
        navigate=lambda *_: pytest.fail("should not navigate"),
        begin=lambda *_ , **__: pytest.fail("should not start over"),
        send_language=lambda *_ , **__: pytest.fail("should not restart language"),
        get_session=lambda *_: session,
        dispatch_state_text=lambda *_: pytest.fail("should not dispatch search text"),
        send_expected=lambda *_: pytest.fail("should not send expected search prompt"),
        interpret=lambda *_: pytest.fail("should not interpret a plan command"),
        ensure_started=lambda *_: pytest.fail("should not reset state"),
        apply_decision=lambda *_: pytest.fail("should not apply search changes"),
        show_plan=lambda who: seen.append(who),
    )
    assert seen == [sender]
    assert session.state == state


@pytest.mark.parametrize("state", list(ConversationState))
def test_plan_button_has_priority_and_preserves_current_state(state):
    sender = "15551234567"
    session = ConversationSession(sender=sender, state=state)
    seen = []
    process_interactive_message(
        IncomingMessage(
            sender=sender, message_type="interactive",
            selection_id=PLAN_SELECTION_ID,
        ),
        navigate=lambda *_: pytest.fail("should not navigate"),
        ensure_started=lambda *_: pytest.fail("should not initialize"),
        language_buttons={"lang_en": "en", "lang_es": "es"},
        select_language=lambda *_, **__: pytest.fail("should not change language"),
        dispatch_state_interactive=lambda *_: pytest.fail("should not advance state"),
        send_expected=lambda *_: pytest.fail("should not reprompt search"),
        show_plan=lambda who: seen.append(who),
    )
    assert seen == [sender]
    assert session.state == state
