import re

from app.constants import MAX_DISTANCE_MILES, MIN_DISTANCE_MILES

KILOMETERS_PER_MILE = 1.609344


def parse_distance_input(text: str) -> float | None:
    """Parse miles or kilometers and normalize the value to miles."""

    match = re.search(
        r"(\d+(?:[.,]\d+)?)\s*"
        r"(miles?|millas?|mi|kilometers?|kilómetros?|kilometros?|km)\b",
        text.casefold(),
    )

    if match is None:
        match = re.fullmatch(r"\s*(\d+(?:[.,]\d+)?)\s*", text)

    if match is None:
        return None

    distance = float(match.group(1).replace(",", "."))
    unit = match.group(2) if match.lastindex == 2 else "miles"

    if unit == "km" or unit.startswith(("kilomet", "kilómet")):
        return round(distance / KILOMETERS_PER_MILE, 3)

    return distance


def is_distance_in_range(distance_miles: float) -> bool:
    return MIN_DISTANCE_MILES <= distance_miles <= MAX_DISTANCE_MILES
