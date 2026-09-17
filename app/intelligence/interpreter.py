import re
import unicodedata
from typing import Protocol

from app.intelligence.models import IntentType, MessageInterpretation


class NaturalLanguageInterpreter(Protocol):
    """Contract for rule-based or model-backed message interpreters."""

    def interpret(self, text: str) -> MessageInterpretation:
        ...


class RuleBasedIntentInterpreter:
    """Conservative bilingual interpreter for the supported search domain."""

    _fuel_aliases = {
        "regular": (
            "regular",
            "unleaded",
            "gasolina normal",
            "gasolina regular",
        ),
        "premium": (
            "premium",
            "supreme",
            "gasolina premium",
        ),
        "diesel": (
            "diesel",
            "diésel",
        ),
    }

    _sort_aliases = {
        "distance": (
            "closest",
            "nearest",
            "nearby",
            "close to me",
            "near me",
            "mas cerca",
            "más cerca",
            "cercana",
            "cercano",
            "cerca de mi",
            "cerca de mí",
        ),
        "price": (
            "cheapest",
            "lowest price",
            "least expensive",
            "mas barata",
            "más barata",
            "mas barato",
            "más barato",
            "economica",
            "económica",
            "economico",
            "económico",
        ),
        "best": (
            "best",
            "best option",
            "best choice",
            "balanced",
            "most convenient",
            "mejor",
            "mejor opcion",
            "mejor opción",
            "conveniente",
            "balanceada",
            "balanceado",
        ),
    }

    _balanced_phrases = (
        "cheap but not too far",
        "cheapest but not too far",
        "cheap and close",
        "low price and close",
        "barata pero no muy lejos",
        "barato pero no muy lejos",
        "barata y cerca",
        "barato y cerca",
        "precio bajo y cerca",
    )

    _search_terms = {
        "gas",
        "gasoline",
        "fuel",
        "station",
        "find",
        "search",
        "need",
        "gasolina",
        "gasolinera",
        "combustible",
        "buscar",
        "busca",
        "buscame",
        "necesito",
        "quiero",
    }

    _spanish_terms = {
        "gasolina",
        "gasolinera",
        "combustible",
        "buscar",
        "busca",
        "buscame",
        "necesito",
        "quiero",
        "cerca",
        "barata",
        "barato",
        "mejor",
        "opcion",
        "economica",
        "economico",
    }

    def interpret(self, text: str) -> MessageInterpretation:
        normalized = self._normalize(text)

        if not normalized:
            return MessageInterpretation(intent=IntentType.UNKNOWN)

        fuel_type = self._match_alias(normalized, self._fuel_aliases)
        sort = self._match_sort(normalized)
        words = set(normalized.split())
        search_requested = bool(words & self._search_terms)

        if fuel_type is None and sort is None and not search_requested:
            return MessageInterpretation(intent=IntentType.UNKNOWN)

        entity_count = sum(value is not None for value in (fuel_type, sort))
        confidence = 0.95 if entity_count == 2 else 0.8

        if entity_count == 0:
            confidence = 0.65
        elif not search_requested:
            confidence -= 0.1

        language = "es" if words & self._spanish_terms else "en"

        return MessageInterpretation(
            intent=IntentType.SEARCH_GAS,
            fuel_type=fuel_type,
            sort=sort,
            language=language,
            confidence=confidence,
        )

    def _match_sort(self, text: str) -> str | None:
        if any(self._contains(text, phrase) for phrase in self._balanced_phrases):
            return "best"

        has_distance_preference = any(
            self._contains(text, alias)
            for alias in self._sort_aliases["distance"]
        )
        has_price_preference = any(
            self._contains(text, alias)
            for alias in self._sort_aliases["price"]
        )

        if has_distance_preference and has_price_preference:
            return "best"

        return self._match_alias(text, self._sort_aliases)

    def _match_alias(
        self,
        text: str,
        aliases_by_value: dict[str, tuple[str, ...]],
    ) -> str | None:
        for value, aliases in aliases_by_value.items():
            if any(self._contains(text, alias) for alias in aliases):
                return value

        return None

    @staticmethod
    def _contains(text: str, phrase: str) -> bool:
        normalized_phrase = RuleBasedIntentInterpreter._normalize(phrase)
        pattern = rf"(?:^|\s){re.escape(normalized_phrase)}(?:$|\s)"
        return re.search(pattern, text) is not None

    @staticmethod
    def _normalize(text: str) -> str:
        decomposed = unicodedata.normalize("NFKD", text or "")
        without_accents = "".join(
            character
            for character in decomposed
            if not unicodedata.combining(character)
        )
        lowercase = without_accents.casefold()
        return " ".join(re.findall(r"[a-z0-9]+", lowercase))
