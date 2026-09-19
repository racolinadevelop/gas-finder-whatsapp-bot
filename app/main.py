from fastapi import FastAPI

from app.config import API_DOCS_ENABLED
from app.routers.gas_stations import router as gas_stations_router
from app.routers.whatsapp import router as whatsapp_router


def create_app(*, api_docs_enabled: bool = API_DOCS_ENABLED) -> FastAPI:
    docs_url = "/docs" if api_docs_enabled else None
    redoc_url = "/redoc" if api_docs_enabled else None
    openapi_url = "/openapi.json" if api_docs_enabled else None

    app = FastAPI(
        title="Gas Finder API",
        description=(
            "REST API for finding nearby gas stations "
            "and comparing fuel prices."
        ),
        version="0.1.0",
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
    )

    app.include_router(gas_stations_router)
    app.include_router(whatsapp_router)

    @app.get("/")
    def root():
        return {"message": "Gas Finder API is running"}

    @app.get("/health", tags=["health"])
    def health():
        return {"status": "ok"}

    return app


app = create_app()
