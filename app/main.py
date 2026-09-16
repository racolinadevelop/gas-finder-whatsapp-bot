from fastapi import FastAPI, HTTPException, Query, Request
from typing import Literal

from app.services.google_places import (
    GooglePlacesServiceError,
    search_nearby_gas_stations,
)
from app.schemas import GasStationsResponse, WhatsAppMessageRequest

from app.services.whatsapp import (
    WhatsAppServiceError,
    build_text_reply,
    send_text_message,
    extract_incoming_message,
    build_gas_stations_reply,
    parse_search_preferences,
)

from app.config import WHATSAPP_VERIFY_TOKEN
from fastapi.responses import PlainTextResponse

app = FastAPI(
    title="Gas Finder API",
    description="REST API for finding nearby gas stations and comparing fuel prices.",
    version="0.1.0",
)

pending_search_preferences = {}


@app.get("/")
def root():
    return {"message": "Gas Finder API is running"}


@app.get(
    "/api/v1/gas-stations/nearby",
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


@app.post("/api/v1/whatsapp/send-message")
def send_whatsapp_message(payload: WhatsAppMessageRequest):
    try:
        return send_text_message(
            to=payload.to,
            message=payload.message,
        )

    except WhatsAppServiceError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc


@app.get(
    "/api/v1/whatsapp/webhook",
    response_class=PlainTextResponse,
)
def verify_whatsapp_webhook(
    hub_mode: str = Query(..., alias="hub.mode"),
    hub_verify_token: str = Query(..., alias="hub.verify_token"),
    hub_challenge: str = Query(..., alias="hub.challenge"),
):
    if hub_mode == "subscribe" and hub_verify_token == WHATSAPP_VERIFY_TOKEN:
        return hub_challenge

    raise HTTPException(
        status_code=403,
        detail="Invalid webhook verification token.",
    )


@app.post("/api/v1/whatsapp/webhook")
async def receive_whatsapp_webhook(request: Request):
    payload = await request.json()

    incoming_message = extract_incoming_message(payload)

    if not incoming_message:
        print("WhatsApp webhook event without a user message.")
        return {"status": "ok"}

    print("Incoming WhatsApp message:")
    print(incoming_message)

    sender = incoming_message["from"]
    message_type = incoming_message["type"]

    # Text message
    if message_type == "text":
        text = incoming_message.get("text", "")

        parsed_preferences = parse_search_preferences(text)

        if parsed_preferences:
            preferences = {
                "fuel_type": "regular",
                "sort": "best",
            }

            preferences.update(parsed_preferences)

            pending_search_preferences[sender] = preferences

            sort_names = {
                "distance": "closest",
                "price": "cheapest",
                "best": "best",
            }

            reply = (
                "✅ Search preferences saved.\n\n"
                f"⛽ Fuel: {preferences['fuel_type'].title()}\n"
                f"🔎 Sort: {sort_names[preferences['sort']].title()}\n\n"
                "Now send me your location 📍"
            )

        else:
            reply = build_text_reply(incoming_message)

        if reply:
            try:
                send_text_message(
                    to=sender,
                    message=reply,
                )
            except WhatsAppServiceError as exc:
                print(f"Could not send WhatsApp reply: {exc}")

    # Location message
    elif message_type == "location":
        latitude = incoming_message.get("latitude")
        longitude = incoming_message.get("longitude")

        if latitude is None or longitude is None:
            return {"status": "ok"}

        try:
            preferences = pending_search_preferences.pop(
                sender,
                {
                    "fuel_type": "regular",
                    "sort": "best",
                },
            )
            result = search_nearby_gas_stations(
                latitude=latitude,
                longitude=longitude,
                radius=5000,
                fuel_type=preferences["fuel_type"],
                sort=preferences["sort"],
                limit=5,
                gallons_needed=10,
                vehicle_mpg=25,
            )

            reply = build_gas_stations_reply(result)

            send_text_message(
                to=sender,
                message=reply,
            )

        except GooglePlacesServiceError as exc:
            print(f"Unable to search gas stations: {exc}")

        except WhatsAppServiceError as exc:
            print(f"Unable to send WhatsApp reply: {exc}")

    return {"status": "ok"}
