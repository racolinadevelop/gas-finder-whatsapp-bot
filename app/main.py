from fastapi import FastAPI, HTTPException, Query

from app.services.google_places import (
    GooglePlacesServiceError,
    search_nearby_gas_stations,
)

app = FastAPI(
    title="Gas Finder API",
    description="REST API for finding nearby gas stations and comparing fuel prices.",
    version="0.1.0",
)


@app.get("/")
def root():
    return {"message": "Gas Finder API is running"}


@app.get("/api/v1/gas-stations/nearby")
def get_nearby_gas_stations(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    radius: int = Query(5000, gt=0, le=50000),
):
    try:
        return search_nearby_gas_stations(
            latitude=latitude,
            longitude=longitude,
            radius=radius,
        )

    except GooglePlacesServiceError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.message,
        ) from exc
