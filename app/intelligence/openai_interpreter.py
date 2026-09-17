import json
from collections.abc import Callable
from typing import Any

import httpx

from app.intelligence.models import IntentType, MessageInterpretation

OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"

INTENT_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {
            "type": "string",
            "enum": ["search_gas", "unknown"],
        },
        "fuel_type": {
            "anyOf": [
                {
                    "type": "string",
                    "enum": ["regular", "premium", "diesel"],
                },
                {"type": "null"},
            ]
        },
        "sort": {
            "anyOf": [
                {
                    "type": "string",
                    "enum": ["distance", "price", "best"],
                },
                {"type": "null"},
            ]
        },
        "language": {
            "anyOf": [
                {"type": "string", "enum": ["en", "es"]},
                {"type": "null"},
            ]
        },
        "confidence": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
        },
    },
    "required": [
        "intent",
        "fuel_type",
        "sort",
        "language",
        "confidence",
    ],
    "additionalProperties": False,
}

INTENT_INSTRUCTIONS = """You classify messages for a gas-station finder.
Return search_gas only when the user is asking to find or compare fuel or gas
stations. Extract only information explicitly stated or clearly implied.
Use distance for closest, price for cheapest, and best when the user wants a
balance between price and distance. Use null for missing values. Detect English
or Spanish. For unrelated or unclear input, return unknown with null values.
Never invent a station, location, price, preference, or user detail."""


class AIInterpretationError(Exception):
    pass


class OpenAIIntentInterpreter:
    """Extract an intent through OpenAI without granting tools or actions."""

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout: float = 6.0,
        http_post: Callable[..., Any] = httpx.post,
    ) -> None:
        if not api_key:
            raise ValueError("An OpenAI API key is required.")

        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self._http_post = http_post

    def interpret(self, text: str) -> MessageInterpretation:
        if not text.strip():
            return MessageInterpretation(
                intent=IntentType.UNKNOWN,
                source="openai",
            )

        try:
            response = self._http_post(
                OPENAI_RESPONSES_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=self._build_payload(text),
                timeout=self.timeout,
            )
            response.raise_for_status()
            response_data = response.json()
        except httpx.TimeoutException as exc:
            raise AIInterpretationError(
                "OpenAI intent interpretation timed out."
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise AIInterpretationError(
                f"OpenAI returned HTTP {exc.response.status_code}."
            ) from exc
        except (httpx.RequestError, ValueError) as exc:
            raise AIInterpretationError(
                "OpenAI intent interpretation failed."
            ) from exc

        return self._parse_response(response_data)

    def _build_payload(self, text: str) -> dict:
        return {
            "model": self.model,
            "store": False,
            "instructions": INTENT_INSTRUCTIONS,
            "input": text,
            "max_output_tokens": 150,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "gas_search_intent",
                    "strict": True,
                    "schema": INTENT_SCHEMA,
                }
            },
        }

    def _parse_response(self, response_data: dict) -> MessageInterpretation:
        if not isinstance(response_data, dict):
            raise AIInterpretationError(
                "OpenAI returned an invalid response body."
            )

        output_text = self._find_output_text(response_data)

        if output_text is None:
            raise AIInterpretationError(
                "OpenAI returned no structured intent output."
            )

        try:
            data = json.loads(output_text)
            intent = IntentType(data["intent"])
            confidence = float(data["confidence"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise AIInterpretationError(
                "OpenAI returned an invalid intent response."
            ) from exc

        fuel_type = data.get("fuel_type")
        sort = data.get("sort")
        language = data.get("language")

        if fuel_type not in {None, "regular", "premium", "diesel"}:
            raise AIInterpretationError("OpenAI returned an invalid fuel type.")
        if sort not in {None, "distance", "price", "best"}:
            raise AIInterpretationError("OpenAI returned an invalid sort option.")
        if language not in {None, "en", "es"}:
            raise AIInterpretationError("OpenAI returned an invalid language.")
        if not 0 <= confidence <= 1:
            raise AIInterpretationError("OpenAI returned invalid confidence.")

        return MessageInterpretation(
            intent=intent,
            fuel_type=fuel_type,
            sort=sort,
            language=language,
            confidence=confidence,
            source="openai",
        )

    @staticmethod
    def _find_output_text(response_data: dict) -> str | None:
        for item in response_data.get("output", []):
            if not isinstance(item, dict):
                continue
            if item.get("type") != "message":
                continue

            for content in item.get("content", []):
                if not isinstance(content, dict):
                    continue
                if content.get("type") == "refusal":
                    raise AIInterpretationError(
                        "OpenAI refused to interpret the message."
                    )
                if content.get("type") == "output_text":
                    return content.get("text")

        return None
