from app.intelligence.interpreter import NaturalLanguageInterpreter
from app.intelligence.models import IntentType, MessageInterpretation
from app.intelligence.openai_interpreter import AIInterpretationError


class HybridIntentInterpreter:
    """Use deterministic rules first and AI only for ambiguous messages."""

    def __init__(
        self,
        rules: NaturalLanguageInterpreter,
        fallback: NaturalLanguageInterpreter,
        confidence_threshold: float = 0.7,
    ) -> None:
        self.rules = rules
        self.fallback = fallback
        self.confidence_threshold = confidence_threshold

    def interpret(self, text: str) -> MessageInterpretation:
        rule_result = self.rules.interpret(text)

        if not self._needs_fallback(rule_result):
            return rule_result

        try:
            fallback_result = self.fallback.interpret(text)
        except AIInterpretationError as exc:
            print(f"AI intent fallback unavailable: {exc}")
            return rule_result

        if (
            rule_result.intent == IntentType.SEARCH_GAS
            and fallback_result.intent == IntentType.UNKNOWN
        ):
            return rule_result

        return fallback_result

    def _needs_fallback(self, result: MessageInterpretation) -> bool:
        return (
            result.intent == IntentType.UNKNOWN
            or result.confidence < self.confidence_threshold
        )
