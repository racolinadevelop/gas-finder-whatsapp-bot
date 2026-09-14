from typing import Optional

from pydantic import BaseModel


class FuelPrice(BaseModel):
    price: float
    currency: str
    updated_at: Optional[str] = None


class SelectedFuel(BaseModel):
    available: bool
    price: Optional[float] = None
    currency: Optional[str] = None
    updated_at: Optional[str] = None


class EstimatedCost(BaseModel):
    fuel_purchase_cost: float
    travel_cost: float
    estimated_total_cost: float


class GasStation(BaseModel):
    id: Optional[str] = None
    name: str
    address: str
    latitude: float
    longitude: float
    distance_miles: float
    fuel_prices: dict[str, FuelPrice]
    selected_fuel: SelectedFuel
    estimated_cost: Optional[EstimatedCost] = None


class GasStationsResponse(BaseModel):
    stations: list[GasStation]
    count: int
    message: str