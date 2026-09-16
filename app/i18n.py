TRANSLATIONS = {
    "en": {
        "choose_language": (
            "🌎 Choose your language\n"
            "Selecciona tu idioma"
        ),

        "welcome": (
            "👋 Hi! Welcome to Gas Finder!\n\n"
            "I'll help you find nearby gas stations "
            "and compare available fuel prices."
        ),

        "choose_fuel": (
            "⛽ To get started, what type of fuel do you need?"
        ),

        "fuel_regular": "Regular",
        "fuel_premium": "Premium",
        "fuel_diesel": "Diesel",

        "button_fuel_regular": "⛽ Regular",
        "button_fuel_premium": "✨ Premium",
        "button_fuel_diesel": "🚛 Diesel",

        "fuel_selected": (
            "Perfect! 👍 You selected {fuel}."
        ),

        "choose_sort": (
            "How would you like me to rank the results?\n\n"
            "📍 Closest — shortest distance\n"
            "💵 Cheapest — lowest available price\n"
            "⭐ Best option — balance of price and distance"
        ),

        "sort_distance": "Closest",
        "sort_price": "Cheapest",
        "sort_best": "Best option",

        "button_sort_distance": "📍 Closest",
        "button_sort_price": "💵 Cheapest",
        "button_sort_best": "⭐ Best option",

        "preferences_saved": (
            "Great! ✅ Your search is ready.\n\n"
            "⛽ Fuel: {fuel}\n"
            "🔎 Search: {sort}\n\n"
            "📍 Now share your location and I'll find "
            "the best nearby options for you."
        ),

        "results_title": (
            "⛽ Nearby gas stations"
        ),

        "results_summary": (
            "🚗 Fuel: {fuel}\n"
            "🔎 Sorted by: {sort}"
        ),

        "price_unavailable": (
            "Price unavailable"
        ),

        "no_results": (
            "I couldn't find nearby gas stations "
            "for this search."
        ),
        "results_count": (
            "📊 Results shown: {count}"
        ),
    },

    "es": {
        "choose_language": (
            "🌎 Choose your language\n"
            "Selecciona tu idioma"
        ),

        "welcome": (
            "👋 ¡Hola! Bienvenido a Gas Finder.\n\n"
            "Te ayudaré a encontrar gasolineras cercanas "
            "y comparar los precios disponibles."
        ),

        "choose_fuel": (
            "⛽ Para comenzar, ¿qué tipo de combustible necesitas?"
        ),

        "fuel_regular": "Regular",
        "fuel_premium": "Premium",
        "fuel_diesel": "Diésel",

        "button_fuel_regular": "⛽ Regular",
        "button_fuel_premium": "✨ Premium",
        "button_fuel_diesel": "🚛 Diésel",

        "fuel_selected": (
            "¡Perfecto! 👍 Elegiste {fuel}."
        ),

        "choose_sort": (
            "¿Cómo prefieres que ordene los resultados?\n\n"
            "📍 Más cerca — menor distancia\n"
            "💵 Más barato — menor precio disponible\n"
            "⭐ Mejor opción — balance entre precio y distancia"
        ),

        "sort_distance": "Más cerca",
        "sort_price": "Más barato",
        "sort_best": "Mejor opción",

        "button_sort_distance": "📍 Más cerca",
        "button_sort_price": "💵 Más barato",
        "button_sort_best": "⭐ Mejor opción",

        "preferences_saved": (
            "¡Perfecto! ✅ Tu búsqueda está lista.\n\n"
            "⛽ Combustible: {fuel}\n"
            "🔎 Búsqueda: {sort}\n\n"
            "📍 Ahora comparte tu ubicación y buscaré "
            "las mejores opciones cercanas para ti."
        ),

        "results_title": (
            "⛽ Gasolineras cercanas"
        ),

        "results_summary": (
            "🚗 Combustible: {fuel}\n"
            "🔎 Ordenado por: {sort}"
        ),

        "price_unavailable": (
            "Precio no disponible"
        ),

        "no_results": (
            "No encontré gasolineras cercanas "
            "para esta búsqueda."
        ),
        "results_count": (
            "📊 Resultados mostrados: {count}"
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