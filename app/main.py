from fastapi import FastAPI

from app.routers.gas_stations import router as gas_stations_router
from app.routers.whatsapp import router as whatsapp_router

app = FastAPI(
    title="Gas Finder API",
    description="REST API for finding nearby gas stations and comparing fuel prices.",
    version="0.1.0",
)

app.include_router(gas_stations_router)
app.include_router(whatsapp_router)


@app.get("/")
def root():
    return {"message": "Gas Finder API is running"}


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}
