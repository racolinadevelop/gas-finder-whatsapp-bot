from fastapi import FastAPI

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
    radius: int = 5000,
    fuel_type: str = "regular",
    sort: str = "distance"
):
    return {
        "latitude": latitude,
        "longitude": longitude,
        "radius": radius,
        "fuel_type": fuel_type,
        "sort": sort,
        "stations": []
    }