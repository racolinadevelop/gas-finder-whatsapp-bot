from typing import Protocol


class GasStationProviderError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class GasStationProvider(Protocol):
    """Contract implemented by gas-station data providers."""

    def search_nearby(
        self,
        *,
        latitude: float,
        longitude: float,
        radius: float = 5000,
        fuel_type: str = "regular",
        sort: str = "distance",
        limit: int = 10,
        gallons_needed: float = 10,
        vehicle_mpg: float = 25,
    ) -> dict: ...
