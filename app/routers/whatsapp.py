from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from app.config import META_APP_SECRET, WHATSAPP_VERIFY_TOKEN
from app.handlers.whatsapp import handle_whatsapp_webhook
from app.schemas import WhatsAppMessageRequest
from app.security import verify_meta_webhook_signature
from app.services.whatsapp import WhatsAppServiceError, send_text_message

router = APIRouter(prefix="/api/v1/whatsapp", tags=["whatsapp"])


@router.post("/send-message")
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


@router.get(
    "/webhook",
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


@router.post("/webhook")
async def receive_whatsapp_webhook(request: Request):
    raw_body = await request.body()

    if META_APP_SECRET:
        signature = request.headers.get("x-hub-signature-256")
        if not verify_meta_webhook_signature(
            raw_body,
            signature,
            META_APP_SECRET,
        ):
            raise HTTPException(
                status_code=401,
                detail="Invalid webhook signature.",
            )

    payload = await request.json()
    return handle_whatsapp_webhook(payload)
