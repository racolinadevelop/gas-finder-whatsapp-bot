from collections.abc import Callable

from app.conversation.models import ConversationSession
from app.services.stations import search_nearby_gas_stations
from app.services.whatsapp import build_gas_stations_reply

StationSearch = Callable[..., dict]
ReplyBuilder = Callable[..., str]


class LocationSearchService:
    """Run a gas-station search from one conversation location step."""

    def __init__(
        self,
        station_search: StationSearch = search_nearby_gas_stations,
        reply_builder: ReplyBuilder = build_gas_stations_reply,
        result_limit: int = 5,
        gallons_needed: float = 10,
        vehicle_mpg: float = 25,
    ) -> None:
        self._station_search = station_search
        self._reply_builder = reply_builder
        self._result_limit = result_limit
        self._gallons_needed = gallons_needed
        self._vehicle_mpg = vehicle_mpg

    def search(
        self,
        *,
        session: ConversationSession,
        latitude: float,
        longitude: float,
    ) -> str:
        radius = (
            session.max_distance_miles * 1609.344
            if session.max_distance_miles is not None
            else 5000
        )
        result = self._station_search(
            latitude=latitude,
            longitude=longitude,
            radius=radius,
            fuel_type=session.fuel_type,
            sort=session.sort,
            limit=self._result_limit,
            gallons_needed=self._gallons_needed,
            vehicle_mpg=self._vehicle_mpg,
        )

        return self._reply_builder(
            result,
            language=session.language,
            fuel_type=session.fuel_type,
            sort=session.sort,
            max_distance_miles=session.max_distance_miles,
        )
