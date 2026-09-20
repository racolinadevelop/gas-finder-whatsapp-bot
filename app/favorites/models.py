"""Small, bounded station snapshots; never persist a user's search coordinates."""

from dataclasses import dataclass
from hashlib import sha256


@dataclass(frozen=True, slots=True)
class FavoriteStation:
    key: str
    name: str
    address: str


@dataclass(frozen=True, slots=True)
class SearchReply:
    text: str
    stations: tuple[FavoriteStation, ...]


def shown_stations(stations: list[dict]) -> tuple[FavoriteStation, ...]:
    """Mirror the five stations displayed by the existing reply formatter."""
    shown = []
    for station in stations:
        if station.get("open_now") is False:
            continue
        name = " ".join(str(station.get("name") or "Gas station").split())[:100]
        address = " ".join(str(station.get("address") or "").split())[:180]
        place_id = str(station.get("id") or "").strip()
        # Prefix even provider IDs to keep separate namespaces unambiguous.
        key = (
            "place:" + place_id[:150]
            if place_id
            else "location:" + sha256(
                (name.casefold() + "|" + address.casefold()).encode()
            ).hexdigest()
        )
        shown.append(FavoriteStation(key=key, name=name, address=address))
        if len(shown) == 5:
            break
    return tuple(shown)
