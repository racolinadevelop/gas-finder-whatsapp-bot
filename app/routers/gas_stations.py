from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from app.schemas import GasStationsResponse
from app.services.google_places import (
    GooglePlacesServiceError,
    search_nearby_gas_stations,
)

router = APIRouter(prefix="/api/v1/gas-stations", tags=["gas-stations"])


@router.get(
    "/nearby",
    response_model=GasStationsResponse,
)
def get_nearby_gas_stations(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    radius: int = Query(5000, gt=0, le=50000),
    fuel_type: Literal["regular", "premium", "diesel"] = "regular",
    sort: Literal["distance", "price", "best"] = "distance",
    limit: int = Query(10, ge=1, le=20),
    gallons_needed: float = Query(10, gt=0, le=100),
    vehicle_mpg: float = Query(25, gt=0, le=200),
):
    try:
        return search_nearby_gas_stations(
            latitude=latitude,
            longitude=longitude,
            radius=radius,
            fuel_type=fuel_type,
            sort=sort,
            limit=limit,
            gallons_needed=gallons_needed,
            vehicle_mpg=vehicle_mpg,
        )
    except GooglePlacesServiceError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.message,
        ) from exc
