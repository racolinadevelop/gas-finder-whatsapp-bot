from fastapi import FastAPI

from app.services.google_places import search_nearby_gas_stations

app = FastAPI(
    title="Gas Finder API",
    description="REST API for finding nearby gas stations and comparing fuel prices.",
    version="0.1.0"
)


@app.get("/")
def root():
    return {"message": "Gas Finder API is running"}

@app.get("/api/v1/gas-stations/nearby")
def get_nearby_gas_stations(
    latitude: float,
    longitude: float,
    radius: int = 5000
):
    return search_nearby_gas_stations(
        latitude=latitude,
        longitude=longitude,
        radius=radius
    )