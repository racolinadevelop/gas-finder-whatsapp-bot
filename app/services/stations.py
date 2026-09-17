from app.config import GAS_STATION_PROVIDER, HERE_API_KEY
from app.providers import GasStationProvider
from app.providers.here import HereFuelPricesProvider
from app.services.google_places import GooglePlacesProvider


def build_gas_station_provider() -> GasStationProvider:
    if GAS_STATION_PROVIDER == "here":
        return HereFuelPricesProvider(api_key=HERE_API_KEY or "")
    return GooglePlacesProvider()


gas_station_provider = build_gas_station_provider()


def search_nearby_gas_stations(**kwargs) -> dict:
    return gas_station_provider.search_nearby(**kwargs)
