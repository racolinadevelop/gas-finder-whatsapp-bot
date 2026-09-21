"""Read-only, concise bilingual plan summary for a WhatsApp user's own account.

Only describes plan status; a separate opt-in handler issues TEST links.
"""

PLAN_SELECTION_ID = "account_plan"
PLAN_TEXT_COMMANDS = frozenset(
    {"mi plan", "mi suscripción", "mi suscripcion",
     "my plan", "my subscription", "/plan"}
)


def is_plan_command(text: str | None) -> bool:
    return " ".join((text or "").casefold().split()) in PLAN_TEXT_COMMANDS


def build_plan_message(
    language: str,
    *,
    regular_premium: bool,
    test_status: str | None,
) -> str:
    """Describe verified local access, including an isolated Stripe sandbox."""
    sandbox_premium = test_status == "active" and not regular_premium
    if language not in {"es", "en"}:
        # Before language selection, keep both languages genuinely brief.
        es = ("⭐ Premium" if regular_premium else
              "⭐ Premium (prueba)" if sandbox_premium else "⛽ Gratis")
        en = ("⭐ Premium" if regular_premium else
              "⭐ Premium (test)" if sandbox_premium else "⛽ Free")
        cancelled = (
            "\nPrueba cancelada. / Test subscription canceled."
            if test_status == "canceled" and not regular_premium else ""
        )
        return (
            f"Tu plan / Your plan: {es} · {en}.{cancelled}\n"
            "Búsqueda básica gratis / Basic search is free.\n"
            "Favoritas: solo Premium / Favorites: Premium only.\n"
            "Elige idioma para continuar / Choose a language to continue."
        )

    if language == "es":
        headline = (
            "⭐ Tu plan actual: Premium."
            if regular_premium else
            "⭐ Tu plan actual: Premium (prueba de Stripe)."
            if sandbox_premium else
            "⛽ Tu plan actual: Gratis."
        )
        note = (
            "\nTu suscripción de prueba está cancelada."
            if test_status == "canceled" and not regular_premium else
            "\nTu suscripción de prueba no tiene acceso Premium activo."
            if test_status == "past_due" and not regular_premium else ""
        )
        return (
            f"{headline}{note}\n"
            "La búsqueda básica de gasolineras es gratis. "
            "Guardar y consultar favoritas requiere Premium.\n"
            "Selecciona una opción para continuar."
        )

    headline = (
        "⭐ Your current plan: Premium."
        if regular_premium else
        "⭐ Your current plan: Premium (Stripe test)."
        if sandbox_premium else
        "⛽ Your current plan: Free."
    )
    note = (
        "\nYour test subscription has been canceled."
        if test_status == "canceled" and not regular_premium else
        "\nYour test subscription has no active Premium access."
        if test_status == "past_due" and not regular_premium else ""
    )
    return (
        f"{headline}{note}\n"
        "Basic gas-station search is free. "
        "Saving and viewing favorites requires Premium.\n"
        "Choose an option to continue."
    )
