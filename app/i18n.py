TRANSLATIONS = {
    "en": {
        "choose_language": ("🌎 Choose your language\n" "Selecciona tu idioma"),
        "welcome": (
            "👋 Hi! Welcome to Gas Finder!\n\n"
            "I can help you find nearby gas stations "
            "and compare fuel prices."
        ),
        "choose_fuel": ("⛽ What type of fuel are you looking for?"),
        "fuel_selected": ("⛽ {fuel} selected."),
        "choose_sort": ("How would you like me to find your gas station?"),
        "preferences_saved": (
            "✅ Search preferences saved.\n\n"
            "⛽ Fuel: {fuel}\n"
            "🔎 Sort: {sort}\n\n"
            "📍 Now send me your location."
        ),
    },
    "es": {
        "choose_language": ("🌎 Choose your language\n" "Selecciona tu idioma"),
        "welcome": (
            "👋 ¡Bienvenido a Gas Finder!\n\n"
            "Puedo ayudarte a encontrar gasolineras cercanas "
            "y comparar precios de combustible."
        ),
        "choose_fuel": ("⛽ ¿Qué tipo de combustible buscas?"),
        "fuel_selected": ("⛽ {fuel} seleccionado."),
        "choose_sort": ("¿Cómo quieres buscar tu gasolinera?"),
        "preferences_saved": (
            "✅ Preferencias guardadas.\n\n"
            "⛽ Combustible: {fuel}\n"
            "🔎 Orden: {sort}\n\n"
            "📍 Ahora envíame tu ubicación."
        ),
    },
}


def t(language: str, key: str, **kwargs) -> str:
    language = language if language in TRANSLATIONS else "en"

    text = TRANSLATIONS[language].get(
        key,
        TRANSLATIONS["en"].get(key, key),
    )

    return text.format(**kwargs)
