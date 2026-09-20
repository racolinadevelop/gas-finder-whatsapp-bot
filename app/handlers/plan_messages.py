"""Read-only, bilingual plan summary for a WhatsApp user's own account.

No Checkout or billing URLs are sent from this flow. The global command must
not change the current gas-station search session.
"""

PLAN_SELECTION_ID = "account_plan"
PLAN_TEXT_COMMANDS = frozenset(
    {
        "mi plan",
        "mi suscripción",
        "mi suscripcion",
        "my plan",
        "my subscription",
        "/plan",
    }
)


def is_plan_command(text: str | None) -> bool:
    return " ".join((text or "").casefold().split()) in PLAN_TEXT_COMMANDS


def build_plan_message(
    language: str,
    *,
    regular_premium: bool,
    test_status: str | None,
) -> str:
    """Report verified stored access, not aspirational Premium features."""
    if language not in {"es", "en"}:
        return (
            build_plan_message(
                "en", regular_premium=regular_premium, test_status=test_status
            )
            + "\n\n"
            + build_plan_message(
                "es", regular_premium=regular_premium, test_status=test_status
            )
        )

    sandbox_premium = test_status == "active" and not regular_premium
    if language == "es":
        if regular_premium:
            headline = "⭐ Tu plan actual: Premium."
        elif sandbox_premium:
            headline = "⭐ Tu plan actual: Premium (prueba de Stripe)."
        else:
            headline = "⛽ Tu plan actual: Gratis."
        note = ""
        if not regular_premium and test_status == "canceled":
            note = "\nTu suscripción de prueba está cancelada."
        elif not regular_premium and test_status == "past_due":
            note = "\nTu suscripción de prueba no tiene acceso Premium activo."
        return (
            f"{headline}{note}\n\n"
            "La búsqueda básica de gasolineras sigue disponible. "
            "Las funciones exclusivas de Premium todavía están en desarrollo.\n\n"
            "Puedes continuar donde estabas o escribir «menú» para empezar de nuevo."
        )

    if regular_premium:
        headline = "⭐ Your current plan: Premium."
    elif sandbox_premium:
        headline = "⭐ Your current plan: Premium (Stripe test)."
    else:
        headline = "⛽ Your current plan: Free."
    note = ""
    if not regular_premium and test_status == "canceled":
        note = "\nYour test subscription has been canceled."
    elif not regular_premium and test_status == "past_due":
        note = "\nYour test subscription has no active Premium access."
    return (
        f"{headline}{note}\n\n"
        "Basic gas-station search is still available. "
        "Premium-only features are still under development.\n\n"
        "Continue where you left off, or type “menu” to start over."
    )
