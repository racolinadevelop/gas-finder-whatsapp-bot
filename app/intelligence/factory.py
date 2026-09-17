from app import config
from app.intelligence.hybrid import HybridIntentInterpreter
from app.intelligence.interpreter import (
    NaturalLanguageInterpreter,
    RuleBasedIntentInterpreter,
)
from app.intelligence.openai_interpreter import OpenAIIntentInterpreter


def build_intent_interpreter() -> NaturalLanguageInterpreter:
    rules = RuleBasedIntentInterpreter()

    if not config.AI_INTENT_ENABLED or not config.OPENAI_API_KEY:
        return rules

    return HybridIntentInterpreter(
        rules=rules,
        fallback=OpenAIIntentInterpreter(
            api_key=config.OPENAI_API_KEY,
            model=config.OPENAI_MODEL,
        ),
    )
