"""Payment provider webhooks with HMAC-SHA256 signature verification."""

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services import payment_service

router = APIRouter(prefix="/webhooks", tags=["Payment Webhooks"])


@router.post("/payments/{provider}")
async def payment_webhook(
    provider: str, request: Request, db: Session = Depends(get_db)
):
    raw_body = await request.body()
    signature = (
        request.headers.get("x-webhook-signature")
        or request.headers.get("x-signature")
        or request.headers.get("x-hub-signature-256")
    )
    try:
        payload = json.loads(raw_body)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event_id = (
        request.headers.get("x-webhook-event-id")
        or payload.get("event_id")
        or payload.get("id")
        or str(uuid.uuid4())
    )

    # Verify the signature before doing anything else. A bad signature never
    # reaches payment state mutation.
    if not payment_service.verify_webhook_signature(
        raw_body, signature, None
    ):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        event = payment_service.process_webhook(
            db, provider, event_id, payload, raw_body, signature
        )
    except payment_service.PaymentError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {
        "received": True,
        "event_id": event_id,
        "processed": event.processed,
        "error": event.error,
    }
